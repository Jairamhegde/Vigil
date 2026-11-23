"""
Access revocation with two-step verification.

    Step 1  prepare_revocation()  the admin picks the accounts and a reason. The server checks them and
                                  returns a challenge that expires after CHALLENGE_SECONDS.
    Step 2  check_challenge()     the same admin re-enters their password and types the employee ID.
            + revoke()            Only then are the accounts disabled, their privileges removed and the
                                  action logged (with the privileges each account held).

Every revocation is stored in the revocations table and re-applied after each data load
(apply_saved_revocations), so a refresh from the JSON exports cannot quietly re-enable an account.

On PostgreSQL (Azure) the database itself persists, so nothing more is needed. With SQLite, when
VIGIL_STATE_DIR is set (a folder that outlives the container), the log is also written there as
revocations.json after every revocation, and restored from it when the app starts. The database
itself stays inside the container, so a restart or a new image rebuilds it from data/ and then
re-applies the saved revocations. A plain JSON file is used because SQLite locking is unreliable on
network file shares.

Vigil works on exported data. Revoking disables the account in Vigil's records. It does not call
AD, Okta, AWS or Azure: carry out the change in those systems (or wire a connector in here).
"""
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone

from backend.db_connection import IS_POSTGRES, connect_db
from utils.path import GUARD_DB, REVOCATIONS_STATE_FILE

CHALLENGE_SECONDS = 300
REVOKED_STATUS = "REVOKED"

table_revocations = '''
CREATE TABLE IF NOT EXISTS revocations (
    revocation_id   INTEGER PRIMARY KEY,
    employee_id     TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    platform        TEXT NOT NULL,
    account_key     TEXT NOT NULL,              -- (platform, account_key) survives a full reload
    account_type    TEXT NOT NULL,
    entitlements    TEXT NOT NULL DEFAULT '',   -- privileges the account held when revoked
    reason          TEXT NOT NULL,
    revoked_by      TEXT NOT NULL,
    revoked_at      TEXT NOT NULL
) STRICT;
'''

_challenges = {}
_lock = threading.Lock()


class RevocationError(Exception):
    """A request that cannot go through. The message is safe to show to the admin."""


def _connect(db_path):
    """Open the database, creating the revocations table if this database predates it."""
    conn = connect_db(db_path)
    try:
        conn.execute(table_revocations)
        conn.commit()
    except BaseException:
        conn.close()
        raise
    return conn


def _rows(conn, sql, params=()):
    return conn.rows(sql, params)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


REVOKED_ACCOUNTS = '''
    SELECT a.account_id FROM accounts a
    JOIN revocations r ON r.platform = a.platform AND r.account_key = a.account_key
'''


def apply_saved_revocations(cursor):
    """Disable every revoked account and strip its privileges again. Called at the end of each data load."""
    cursor.execute(f"DELETE FROM entitlements WHERE account_id IN ({REVOKED_ACCOUNTS})")
    cursor.execute(f"UPDATE accounts SET enabled = 0, status = ? WHERE account_id IN ({REVOKED_ACCOUNTS})",
                   (REVOKED_STATUS,))
    return cursor.rowcount


# ___________________ Persistent copy (VIGIL_STATE_DIR) _______________________

COLUMNS = ["revocation_id", "employee_id", "full_name", "platform", "account_key", "account_type",
           "entitlements", "reason", "revoked_by", "revoked_at"]


def save_state(db_path=GUARD_DB, state_file=REVOCATIONS_STATE_FILE):
    """Write the whole revocation log to the state folder. Returns False when it could not be saved."""
    if state_file is None or IS_POSTGRES:   # PostgreSQL already keeps the log
        return True

    rows = list_revocations(db_path)
    temp = state_file.with_name(state_file.name + ".tmp")

    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps({"version": 1, "revocations": rows}, indent=1), encoding="utf-8")
        os.replace(temp, state_file)   # readers never see a half-written file
        return True
    except OSError as error:
        logging.error(f"Could not save revocations to {state_file}: {error}")
        return False


def restore_state(db_path=GUARD_DB, state_file=REVOCATIONS_STATE_FILE):
    """
    Load the saved revocation log into the database and apply it. Called when the app starts.
    Returns how many revocations were restored (0 when there is no state folder or no file yet).
    """
    if state_file is None or IS_POSTGRES or not state_file.exists():
        return 0

    rows = json.loads(state_file.read_text(encoding="utf-8")).get("revocations", [])
    conn = _connect(db_path)

    try:
        with conn:
            conn.execute("DELETE FROM revocations")
            conn.executemany(
                f"INSERT INTO revocations ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                [[row.get(column) for column in COLUMNS] for row in rows],
            )
            apply_saved_revocations(conn.cursor())
    finally:
        conn.close()

    return len(rows)


# ___________________ Reads ___________________________________________________

def get_identity_access(employee_id, db_path=GUARD_DB):
    """One identity with every account it owns, the privileges on each, and past revocations."""
    conn = _connect(db_path)

    try:
        people = _rows(conn, '''
            SELECT i.identity_id, i.employee_id, i.full_name, i.department, i.role_title, i.hr_status,
                   i.termination_date, i.leave_start_date,
                   m.risk_score, m.damage_score, m.is_dormant, m.is_ghost, m.is_risky
            FROM identities i
            LEFT JOIN identity_metrics m
                   ON m.identity_id = i.identity_id AND m.as_of = (SELECT MAX(as_of) FROM identity_metrics)
            WHERE i.employee_id = ?
        ''', (employee_id,))

        if not people:
            return None

        person = people[0]
        accounts = _rows(conn, '''
            SELECT account_id, platform, account_key, account_type, enabled, status, mfa_level, last_login
            FROM accounts WHERE identity_id = ?
            ORDER BY enabled DESC, platform, account_key
        ''', (person.pop("identity_id"),))

        for account in accounts:
            account["entitlements"] = _rows(conn, '''
                SELECT entitlement, scope, privilege_tier, via FROM entitlements
                WHERE account_id = ? ORDER BY privilege_tier, entitlement
            ''', (account["account_id"],))

        person["accounts"] = accounts
        person["revocations"] = _rows(conn, '''
            SELECT platform, account_key, reason, revoked_by, revoked_at
            FROM revocations WHERE employee_id = ? ORDER BY revoked_at DESC
        ''', (employee_id,))
    finally:
        conn.close()

    return person


def list_revocations(db_path=GUARD_DB):
    conn = _connect(db_path)

    try:
        return _rows(conn, "SELECT * FROM revocations ORDER BY revoked_at DESC, revocation_id DESC")
    finally:
        conn.close()


# ___________________ Step 1: prepare _________________________________________

def prepare_revocation(username, employee_id, account_ids, reason, db_path=GUARD_DB):
    reason = (reason or "").strip()

    if len(reason) < 5:
        raise RevocationError("Give a reason (at least 5 characters). It is kept in the audit log.")

    if not account_ids:
        raise RevocationError("Select at least one account to revoke.")

    person = get_identity_access(employee_id, db_path)

    if person is None:
        raise RevocationError(f"Unknown employee {employee_id}.")

    owned = {account["account_id"]: account for account in person["accounts"]}
    selected = []

    for account_id in sorted(set(account_ids)):
        account = owned.get(account_id)

        if account is None:
            raise RevocationError(f"Account {account_id} does not belong to {employee_id}.")

        if not account["enabled"]:
            raise RevocationError(f"{account['platform']}: {account['account_key']} is already disabled.")

        selected.append(account)

    challenge_id = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + CHALLENGE_SECONDS

    with _lock:
        # Drop expired challenges so the store cannot grow forever
        for key in [key for key, value in _challenges.items() if value["expires_at"] < time.time()]:
            _challenges.pop(key, None)

        _challenges[challenge_id] = {
            "username": username,
            "employee_id": employee_id,
            "full_name": person["full_name"],
            "accounts": selected,
            "reason": reason,
            "expires_at": expires_at,
        }

    return {
        "challenge_id": challenge_id,
        "expires_at": expires_at,
        "employee_id": employee_id,
        "full_name": person["full_name"],
        "accounts": [{"platform": a["platform"], "account_key": a["account_key"],
                      "privileges": len(a["entitlements"])} for a in selected],
    }


# ___________________ Step 2: confirm _________________________________________

def check_challenge(username, challenge_id, confirm_text, consume=False):
    """
    Check the challenge and the typed employee ID. With consume=True the challenge is used up, so it
    cannot be replayed. The API checks first, verifies the password, then consumes: a typo or a wrong
    password lets the admin retry without starting over.
    """
    with _lock:
        challenge = _challenges.get(challenge_id)

        if challenge is None or challenge["expires_at"] < time.time():
            _challenges.pop(challenge_id, None)
            raise RevocationError("This confirmation is no longer valid (expired or already used). Start again.")

        if challenge["username"] != username:
            raise RevocationError("This confirmation belongs to another admin.")

        if (confirm_text or "").strip().upper() != challenge["employee_id"].upper():
            raise RevocationError(f"Type the employee ID {challenge['employee_id']} exactly to confirm.")

        return _challenges.pop(challenge_id) if consume else challenge


def revoke(challenge, db_path=GUARD_DB):
    """Disable the accounts from a verified challenge and write the audit log. Returns the count."""
    revoked_at = _now()
    conn = _connect(db_path)

    try:
        with conn:
            for account in challenge["accounts"]:
                privileges = "||".join(
                    f"T{e['privilege_tier']} {e['entitlement']}" + (f" @ {e['scope']}" if e["scope"] else "")
                    for e in account["entitlements"]
                )
                conn.execute('''
                    INSERT INTO revocations (employee_id, full_name, platform, account_key, account_type,
                                             entitlements, reason, revoked_by, revoked_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (challenge["employee_id"], challenge["full_name"], account["platform"],
                      account["account_key"], account["account_type"], privileges, challenge["reason"],
                      challenge["username"], revoked_at))
                conn.execute("UPDATE accounts SET enabled = 0, status = ? WHERE account_id = ?",
                             (REVOKED_STATUS, account["account_id"]))
                conn.execute("DELETE FROM entitlements WHERE account_id = ?", (account["account_id"],))
    finally:
        conn.close()

    return len(challenge["accounts"])
