import sqlite3
import sys
import os

# Add project root to sys.path so imports work regardless of where script is run from
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db_connection import connect_db

conn = connect_db()
cur = conn.cursor()
cur.execute("PRAGMA foreign_keys = ON;")

huma_identity_table ="""
CREATE TABLE IF NOT EXISTS human_identities (
    identity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    hr_status TEXT NOT NULL
);"""

platforms ="""
CREATE TABLE IF NOT EXISTS platforms (
    platform_id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_name TEXT UNIQUE NOT NULL
);"""

accounts_table ='''
CREATE TABLE IF NOT EXISTS accounts (
        account_id TEXT PRIMARY KEY, 
        identity_id INTEGER,
        platform_id INTEGER,
        platform_username TEXT NOT NULL,
        account_status TEXT NOT NULL,
        token_usage INTEGER,
        token_created_date DATE,
        token_rotated_date DATE,
        FOREIGN KEY (identity_id) REFERENCES human_identities(identity_id) ON DELETE CASCADE,
        FOREIGN KEY (platform_id) REFERENCES platforms(platform_id) ON DELETE RESTRICT
    );'''

role_defination_table ='''
CREATE TABLE IF NOT EXISTS role_definitions (
    role_id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id INTEGER,
    raw_role_name TEXT NOT NULL,
    normalized_tier TEXT NOT NULL,
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id) ON DELETE CASCADE,
    UNIQUE(platform_id, raw_role_name) -- Prevents duplicate roles on the same platform
);'''

account_role_mapping = """
    CREATE TABLE IF NOT EXISTS account_role_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT,
    role_id INTEGER,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES role_definitions(role_id) ON DELETE CASCADE,
    UNIQUE(account_id, role_id) -- Prevents assigning the exact same role to the same account twice
);"""

security_incidents = """

    CREATE TABLE IF NOT EXISTS security_incidents (
        incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
        identity_id INTEGER,
        incident_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT DEFAULT 'OPEN',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (identity_id) REFERENCES human_identities(identity_id) ON DELETE CASCADE
    );
    """

alter_table = '''
alter table accounts
add last_login_date DATETIME;
'''

table_audit = '''
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    identity_id INTEGER,
    platform TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    source_ip TEXT,
    resource_accessed TEXT,
    status TEXT,
    FOREIGN KEY (identity_id) REFERENCES human_identities(identity_id)
);
'''
incidentce = ("""
    CREATE TABLE IF NOT EXISTS security_incidents (
        incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
        identity_id INTEGER,
        incident_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT DEFAULT 'OPEN',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (identity_id) REFERENCES human_identities(identity_id)
    );
    """)

previlageeed_watchlist =  '''
    CREATE VIEW IF NOT EXISTS live_privileged_watchlist AS 
    SELECT 
        h.identity_id,
        h.full_name AS identity_name,
        h.hr_status,
        MAX(r.normalized_tier) AS highest_tier_held,
        MAX(a.last_login_date) AS last_login_date,
        COALESCE(a.last_login_date, a.token_created_date) AS effective_last_activity,
        CAST(julianday('now') - julianday(COALESCE(a.last_login_date, a.token_created_date)) AS INTEGER) AS days_dormant
        
    FROM human_identities h
    JOIN accounts a ON h.identity_id = a.identity_id
    JOIN account_role_mapping arm ON a.account_id = arm.account_id
    JOIN role_definitions r ON arm.role_id = r.role_id
    WHERE r.normalized_tier IN ('Tier 0', 'Tier 1', 'Tier 2')
    AND a.account_status = 'ACTIVE'
    GROUP BY h.identity_id;
'''




alter_securitty_insident = """
alter table security_incidents
add column elevated_tier TEXT;
"""

try:
    cur.execute(alter_securitty_insident)
except sqlite3.OperationalError:
    pass
# cur.execute(huma_identity_table)
# cur.execute(platforms)
# cur.execute(accounts_table)
# cur.execute(role_defination_table)
# cur.execute(account_role_mapping)
# cur.execute(security_incidents)

conn.commit()
conn.close()