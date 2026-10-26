"""
Vigil metrics schema. It stores only what the dashboard metrics need.

  identities        HR record, the single source of truth for who is employed
  accounts          one row per account on AD / Okta / AWS / Azure, linked to an identity
  entitlements      effective privileges per account (AD nesting already flattened), with a tier
  audit_events      activity per account (who, what, when, from where, did it succeed)
  identity_metrics  computed dormant / ghost / damage / risk results, one row per identity per run

Facts are stored here. Conclusions (dormant, ghost, risky) are computed by backend/metrics.py,
so changing a rule only needs a re-run, not a re-ingest. The raw JSON in data/ stays the archive.
"""
from backend.db_connection import connect_db
from utils.path import GUARD_DB

table_identities = '''
CREATE TABLE IF NOT EXISTS identities (
    identity_id         INTEGER PRIMARY KEY,
    employee_id         TEXT NOT NULL UNIQUE,
    full_name           TEXT NOT NULL,
    company_email       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    department          TEXT,
    role_title          TEXT,
    hr_status           TEXT NOT NULL CHECK (hr_status IN ('Active', 'Terminated', 'On Leave')),
    hire_date           TEXT NOT NULL,
    termination_date    TEXT,
    leave_start_date    TEXT,
    manager_identity_id INTEGER REFERENCES identities(identity_id)
                            ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
) STRICT;
'''

table_accounts = '''
CREATE TABLE IF NOT EXISTS accounts (
    account_id      INTEGER PRIMARY KEY,
    platform        TEXT NOT NULL CHECK (platform IN ('ad', 'okta', 'aws', 'azure')),
    account_key     TEXT NOT NULL,              -- AD sAMAccountName, Okta / AWS / Azure sign-in email
    identity_id     INTEGER REFERENCES identities(identity_id) ON DELETE SET NULL,  -- NULL = no HR owner
    account_type    TEXT NOT NULL CHECK (account_type IN ('human', 'admin', 'service')),
    enabled         INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    status          TEXT,                       -- platform status as reported, e.g. SUSPENDED
    mfa_level       TEXT CHECK (mfa_level IN ('none', 'sms', 'strong')),  -- Okta only
    last_login      TEXT,
    created_at      TEXT,
    UNIQUE (platform, account_key)
) STRICT;
'''

# privilege_tier: 0 = can take over the domain/cloud (Domain Admins, AWS AdministratorAccess, Azure Owner)
#                 1 = high (server admins, PowerUser, Contributor)
#                 2 = standard
table_entitlements = '''
CREATE TABLE IF NOT EXISTS entitlements (
    account_id      INTEGER NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    entitlement     TEXT NOT NULL,              -- AD group, permission set, RBAC role, Okta admin role
    scope           TEXT NOT NULL DEFAULT '',   -- AWS account / Azure subscription, '' when global
    privilege_tier  INTEGER NOT NULL CHECK (privilege_tier IN (0, 1, 2)),
    via             TEXT,                       -- how it was granted, e.g. nested via GG-Tier0-Admins
    PRIMARY KEY (account_id, entitlement, scope)
) STRICT, WITHOUT ROWID;
'''

table_audit_events = '''
CREATE TABLE IF NOT EXISTS audit_events (
    event_id        INTEGER PRIMARY KEY,
    platform        TEXT NOT NULL CHECK (platform IN ('okta', 'aws', 'azure')),
    source_event_id TEXT NOT NULL,
    event_time      TEXT NOT NULL,
    account_id      INTEGER REFERENCES accounts(account_id),
    event_name      TEXT NOT NULL,
    target          TEXT,                       -- AWS account / Azure subscription / Okta app
    source_ip       TEXT,
    outcome         TEXT NOT NULL CHECK (outcome IN ('success', 'failure')),
    error_code      TEXT,
    token_id        TEXT,                       -- access key / session credential id (never the secret)
    is_sensitive    INTEGER NOT NULL DEFAULT 0 CHECK (is_sensitive IN (0, 1)),
    UNIQUE (platform, source_event_id)
) STRICT;
'''

table_identity_metrics = '''
CREATE TABLE IF NOT EXISTS identity_metrics (
    identity_id     INTEGER NOT NULL REFERENCES identities(identity_id) ON DELETE CASCADE,
    as_of           TEXT NOT NULL,
    is_dormant      INTEGER NOT NULL CHECK (is_dormant IN (0, 1)),
    is_ghost        INTEGER NOT NULL CHECK (is_ghost IN (0, 1)),
    damage_score    INTEGER NOT NULL CHECK (damage_score BETWEEN 0 AND 100),
    risk_score      INTEGER NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    is_risky        INTEGER NOT NULL CHECK (is_risky IN (0, 1)),
    reasons         TEXT NOT NULL CHECK (json_valid(reasons)),
    PRIMARY KEY (identity_id, as_of)
) STRICT;
'''

indexes = '''
CREATE INDEX IF NOT EXISTS ix_accounts_identity       ON accounts(identity_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_account    ON audit_events(account_id, event_time);
CREATE INDEX IF NOT EXISTS ix_audit_events_time       ON audit_events(event_time);
CREATE INDEX IF NOT EXISTS ix_identity_metrics_as_of  ON identity_metrics(as_of, risk_score);
'''

ALL_TABLES = [table_identities, table_accounts, table_entitlements, table_audit_events, table_identity_metrics]


def create_all_tables(conn=None):
    own_conn = conn is None
    if own_conn:
        conn = connect_db(GUARD_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    with conn:
        for ddl in ALL_TABLES:
            conn.execute(ddl)
        conn.executescript(indexes)
    if own_conn:
        conn.close()


if __name__ == "__main__":
    create_all_tables()
