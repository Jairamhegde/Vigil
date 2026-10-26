"""
Auth service: dashboard users, password hashing and signed session tokens.

It keeps its own small database (backend/auth.db), so it does not depend on the identity data.

Create users from the command line:
    python -m backend.auth create-user <username> super_admin
    python -m backend.auth create-user <username> viewer

On first start, if no users exist, a super admin is created from the VIGIL_ADMIN_USER and
VIGIL_ADMIN_PASSWORD environment variables. When those are not set, the documented demo login
(DEMO_USERNAME / DEMO_PASSWORD, listed in the README) is used. Change it before using real data.
"""
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
import time

from utils.path import AUTH_DB

ROLES = ("super_admin", "viewer")

# Demo login for the synthetic dataset, documented in the README. Not for real data.
DEMO_USERNAME = "superadmin"
DEMO_PASSWORD = "Vigil@Demo2026"
TOKEN_LIFETIME_SECONDS = 8 * 60 * 60
PASSWORD_ITERATIONS = 200_000
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 5 * 60

_failed_logins = {}


# ___________________ Storage _________________________________________________

def connect_auth_db():
    conn = sqlite3.connect(AUTH_DB)

    conn.execute('''
        CREATE TABLE IF NOT EXISTS app_users (
            username        TEXT PRIMARY KEY COLLATE NOCASE,
            password_hash   TEXT NOT NULL,
            salt            TEXT NOT NULL,
            role            TEXT NOT NULL CHECK (role IN ('super_admin', 'viewer')),
            created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS auth_settings (
            name    TEXT PRIMARY KEY,
            value   TEXT NOT NULL
        )
    ''')

    return conn


def get_signing_secret():
    """VIGIL_AUTH_SECRET if set, otherwise a random secret stored once, so tokens survive restarts."""
    env_secret = os.environ.get("VIGIL_AUTH_SECRET")

    if env_secret:
        return env_secret.encode()

    conn = connect_auth_db()

    with conn:
        row = conn.execute("SELECT value FROM auth_settings WHERE name = 'signing_secret'").fetchone()

        if row is None:
            secret = secrets.token_hex(32)
            conn.execute("INSERT INTO auth_settings (name, value) VALUES ('signing_secret', ?)", (secret,))
        else:
            secret = row[0]

    conn.close()

    return secret.encode()


# ___________________ Passwords _______________________________________________

def hash_password(password, salt):
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PASSWORD_ITERATIONS)
    return digest.hex()


def create_user(username, password, role):
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")

    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")

    salt = secrets.token_hex(16)
    conn = connect_auth_db()

    with conn:
        conn.execute('''
            INSERT INTO app_users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)
            ON CONFLICT (username) DO UPDATE SET
                password_hash = excluded.password_hash, salt = excluded.salt, role = excluded.role
        ''', (username, hash_password(password, salt), salt, role))

    conn.close()


def ensure_default_admin():
    conn = connect_auth_db()
    user_count = conn.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
    conn.close()

    if user_count > 0:
        return

    username = os.environ.get("VIGIL_ADMIN_USER", DEMO_USERNAME)
    password = os.environ.get("VIGIL_ADMIN_PASSWORD")

    if not password:
        password = DEMO_PASSWORD
        print(f"\n[Vigil] Created the demo super admin: {username} / {password}\n"
              f"[Vigil] This login is public (see README). Change it before using real data:\n"
              f"[Vigil]     python -m backend.auth create-user {username} super_admin\n")

    create_user(username, password, "super_admin")


def verify_user(username, password):
    """Return {'username', 'role'} on success, None on bad credentials. Raises PermissionError when locked."""
    key = username.lower()
    failures, locked_until = _failed_logins.get(key, (0, 0))

    if locked_until > time.time():
        raise PermissionError("Too many failed attempts. Try again in a few minutes.")

    conn = connect_auth_db()
    row = conn.execute("SELECT username, password_hash, salt, role FROM app_users WHERE username = ?",
                       (username,)).fetchone()
    conn.close()

    if row and hmac.compare_digest(row[1], hash_password(password, row[2])):
        _failed_logins.pop(key, None)
        return {"username": row[0], "role": row[3]}

    failures += 1

    if failures >= MAX_FAILED_LOGINS:
        _failed_logins[key] = (0, time.time() + LOCKOUT_SECONDS)
    else:
        _failed_logins[key] = (failures, 0)

    return None


# ___________________ Tokens __________________________________________________

def _encode(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(user):
    expires_at = int(time.time()) + TOKEN_LIFETIME_SECONDS
    payload = _encode(json.dumps({"sub": user["username"], "role": user["role"], "exp": expires_at}).encode())
    signature = _encode(hmac.new(get_signing_secret(), payload.encode(), hashlib.sha256).digest())

    return f"{payload}.{signature}", expires_at


def read_token(token):
    """Return the token payload, or None when it is malformed, tampered with or expired."""
    try:
        payload, signature = token.split(".")
    except (ValueError, AttributeError):
        return None

    expected = _encode(hmac.new(get_signing_secret(), payload.encode(), hashlib.sha256).digest())

    if not hmac.compare_digest(signature, expected):
        return None

    data = json.loads(_decode(payload))

    if data["exp"] < time.time():
        return None

    return data


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "create-user":
        new_password = getpass.getpass("Password (min 10 characters): ")
        create_user(sys.argv[2], new_password, sys.argv[3])
        print(f"User '{sys.argv[2]}' saved with role {sys.argv[3]}")
    else:
        print("usage: python -m backend.auth create-user <username> <super_admin|viewer>")
