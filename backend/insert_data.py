"""
Step 2 - Loader service.

Takes the dictionaries produced by ingest_data.py and writes them into the schema from table_creation.py.
Safe to run again and again:
    identities and accounts are upserted, so their ids never change
    entitlements are replaced with the latest snapshot
    events are skipped when (platform, source_event_id) is already stored
"""
import logging

from backend.db_connection import connect_db
from backend.ingest_data import extract_all
from backend.revocation import apply_saved_revocations
from backend.table_creation import create_all_tables
from utils.path import GUARD_DB


def insert_identities(cursor, identities):
    cursor.executemany('''
        INSERT INTO identities (employee_id, full_name, company_email, department, role_title,
                                hr_status, hire_date, termination_date, leave_start_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (employee_id) DO UPDATE SET
            full_name        = excluded.full_name,
            company_email    = excluded.company_email,
            department       = excluded.department,
            role_title       = excluded.role_title,
            hr_status        = excluded.hr_status,
            hire_date        = excluded.hire_date,
            termination_date = excluded.termination_date,
            leave_start_date = excluded.leave_start_date
    ''', [(person["employee_id"], person["full_name"], person["email"], person["department"],
           person["role_title"], person["hr_status"], person["hire_date"], person["termination_date"],
           person["leave_start_date"]) for person in identities])

    identity_ids = get_identity_ids(cursor)

    # Second pass: every employee exists now, so manager links can be set
    cursor.executemany("UPDATE identities SET manager_identity_id = ? WHERE employee_id = ?",
                       [(identity_ids.get(person["manager_employee_id"]), person["employee_id"])
                        for person in identities])

    return len(identities)


def insert_accounts(cursor, accounts, identity_ids):
    cursor.executemany('''
        INSERT INTO accounts (platform, account_key, identity_id, account_type, enabled, status,
                              mfa_level, last_login, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (platform, account_key) DO UPDATE SET
            identity_id  = excluded.identity_id,
            account_type = excluded.account_type,
            enabled      = excluded.enabled,
            status       = excluded.status,
            mfa_level    = excluded.mfa_level,
            last_login   = COALESCE(excluded.last_login, accounts.last_login),
            created_at   = COALESCE(excluded.created_at, accounts.created_at)
    ''', [(account["platform"], account["account_key"], identity_ids.get(account["employee_id"]),
           account["account_type"], int(account["enabled"]), account["status"], account["mfa_level"],
           account["last_login"], account["created_at"]) for account in accounts])

    return len(accounts)


def insert_entitlements(cursor, entitlements, account_ids):
    # Entitlements are a point-in-time snapshot: removed access must disappear too
    cursor.execute("DELETE FROM entitlements")

    # The same grant can arrive twice (direct and nested): keep the most privileged tier
    cursor.executemany('''
        INSERT INTO entitlements (account_id, entitlement, scope, privilege_tier, via)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (account_id, entitlement, scope) DO UPDATE SET
            privilege_tier = CASE WHEN excluded.privilege_tier < entitlements.privilege_tier
                                  THEN excluded.privilege_tier ELSE entitlements.privilege_tier END
    ''', [(account_ids[(item["platform"], item["account_key"])], item["entitlement"], item["scope"] or "",
           item["tier"], item["via"]) for item in entitlements])

    return len(entitlements)


def count_rows(cursor, table):
    return cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def insert_audit_events(cursor, events, account_ids, identity_ids_by_email):
    # Someone active on a platform without an account from the directory exports: record them anyway
    for event in events:
        key = (event["platform"], event["actor_email"])

        if key not in account_ids and event["actor_email"]:
            new_id = cursor.execute('''
                INSERT INTO accounts (platform, account_key, identity_id, account_type, enabled, status)
                VALUES (?, ?, ?, 'human', 1, 'seen in logs only')
                RETURNING account_id
            ''', (event["platform"], event["actor_email"], identity_ids_by_email.get(event["actor_email"]))).fetchone()[0]
            account_ids[key] = new_id

    before = count_rows(cursor, "audit_events")

    # Events already stored (same platform + source id) are skipped, so a reload only adds new ones
    cursor.executemany('''
        INSERT INTO audit_events (platform, source_event_id, event_time, account_id, event_name,
                                  target, source_ip, outcome, error_code, token_id, is_sensitive)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (platform, source_event_id) DO NOTHING
    ''', [(event["platform"], event["source_event_id"], event["event_time"],
           account_ids.get((event["platform"], event["actor_email"])), event["event_name"], event["target"],
           event["source_ip"], event["outcome"], event["error_code"], event["token_id"], int(event["is_sensitive"]))
          for event in events])

    inserted = count_rows(cursor, "audit_events") - before

    # Cloud platforms have no last-login field, so use the latest activity in the logs
    cursor.execute('''
        UPDATE accounts
        SET last_login = (SELECT MAX(event_time) FROM audit_events WHERE audit_events.account_id = accounts.account_id)
        WHERE platform IN ('aws', 'azure')
          AND EXISTS (SELECT 1 FROM audit_events WHERE audit_events.account_id = accounts.account_id)
    ''')

    return inserted


def get_identity_ids(cursor):
    return dict(cursor.execute("SELECT employee_id, identity_id FROM identities"))


def get_account_ids(cursor):
    rows = cursor.execute("SELECT platform, account_key, account_id FROM accounts")
    return {(platform, key): account_id for platform, key, account_id in rows}


def load_all(db_path=GUARD_DB):
    """Extract every JSON file and load it into the database. Returns row counts."""
    data = extract_all()

    conn = connect_db(db_path)
    try:
        counts = _load(conn, data)
    finally:
        conn.close()

    logging.info(f"Data load complete: {counts}")
    return counts


def _load(conn, data):
    create_all_tables(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    with conn:
        counts = {"identities": insert_identities(cursor, data["identities"])}

        identity_ids = get_identity_ids(cursor)
        identity_ids_by_email = dict(cursor.execute("SELECT lower(company_email), identity_id FROM identities"))

        counts["accounts"] = insert_accounts(cursor, data["accounts"], identity_ids)

        account_ids = get_account_ids(cursor)

        counts["entitlements"] = insert_entitlements(cursor, data["entitlements"], account_ids)
        counts["new_audit_events"] = insert_audit_events(cursor, data["audit_events"], account_ids,
                                                         identity_ids_by_email)

        # The exports still show revoked accounts as enabled. Keep them disabled.
        counts["revoked_accounts"] = apply_saved_revocations(cursor)

    return counts


if __name__ == "__main__":
    print(load_all())
