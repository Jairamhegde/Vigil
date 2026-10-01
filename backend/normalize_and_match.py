import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Tuple, Optional, Any, Set

from utils.path import (
    HYBRIDDB,
    IDENTITIES_JSON,
    OKTA_JSON,
    AWS_JSON,
    AZURE_JSON,
)
from backend.db_connection import connect_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ___________________________ HELPER FUNCTIONS __________________________________
def clean_email(email: Any) -> str:
    """Normalize email: strip whitespace and lowercase for consistent deterministic matching."""
    if not email:
        return ""
    return str(email).strip().lower()


def parse_timestamp(ts_str: Any) -> Optional[str]:
    """Parse an ISO 8601 timestamp string into a normalized SQLite DATETIME string (YYYY-MM-DD HH:MM:SS).
    Returns None if the timestamp is missing, malformed, or unparseable.
    """
    if not ts_str:
        return None
    s = str(ts_str).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ___________________________ SCHEMA INITIALIZATION _____________________________
def init_schema(conn: sqlite3.Connection, drop_existing: bool = True) -> None:
    """Initialize the 3NF Vigil relational schema in SQLite."""
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = OFF;")

    if drop_existing:
        tables = [
            "audit_events",
            "tokens",
            "account_groups",
            "group_roles",
            "role_services",
            "accounts",
            "resources",
            "services",
            "roles",
            "groups",
            "platforms",
            "identities",
        ]
        for t in tables:
            cur.execute(f"DROP TABLE IF EXISTS {t};")

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS identities (
        identity_id TEXT PRIMARY KEY,
        employee_id TEXT NOT NULL UNIQUE,
        full_name TEXT NOT NULL,
        company_email TEXT NOT NULL UNIQUE,
        department TEXT,
        role_title TEXT,
        manager_identity_id TEXT,
        baseline_group TEXT,
        hr_status TEXT NOT NULL CHECK (hr_status IN ('Active', 'Terminated', 'On Leave')),
        hire_date DATE NOT NULL,
        termination_date DATE,
        leave_start_date DATE,
        work_location TEXT,
        office_ip TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (manager_identity_id) REFERENCES identities(identity_id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS platforms (
        platform_id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform_code TEXT NOT NULL UNIQUE,
        platform_name TEXT NOT NULL UNIQUE,
        platform_type TEXT NOT NULL CHECK (platform_type IN ('Identity Provider', 'Cloud Platform')),
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS services (
        service_id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform_id INTEGER NOT NULL,
        service_code TEXT NOT NULL,
        service_name TEXT NOT NULL,
        description TEXT,
        FOREIGN KEY (platform_id) REFERENCES platforms(platform_id) ON DELETE RESTRICT,
        UNIQUE (platform_id, service_code)
    );

    CREATE TABLE IF NOT EXISTS resources (
        resource_id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_id INTEGER NOT NULL,
        resource_type TEXT NOT NULL,
        resource_name TEXT,
        external_resource_id TEXT NOT NULL,
        region TEXT,
        FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE RESTRICT,
        UNIQUE (service_id, external_resource_id)
    );

    CREATE TABLE IF NOT EXISTS roles (
        role_id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform_id INTEGER NOT NULL,
        role_code TEXT NOT NULL,
        role_name TEXT NOT NULL,
        description TEXT,
        FOREIGN KEY (platform_id) REFERENCES platforms(platform_id) ON DELETE RESTRICT,
        UNIQUE (platform_id, role_code)
    );

    CREATE TABLE IF NOT EXISTS groups (
        group_id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform_id INTEGER NOT NULL,
        external_group_id TEXT NOT NULL,
        group_name TEXT NOT NULL,
        privilege_tier INTEGER NOT NULL CHECK (privilege_tier >= 0),
        description TEXT,
        FOREIGN KEY (platform_id) REFERENCES platforms(platform_id) ON DELETE RESTRICT,
        UNIQUE (platform_id, external_group_id)
    );

    CREATE TABLE IF NOT EXISTS group_roles (
        group_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (group_id, role_id),
        FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE,
        FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS account_groups (
        account_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (account_id, group_id),
        FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
        FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS role_services (
        role_id INTEGER NOT NULL,
        service_id INTEGER NOT NULL,
        PRIMARY KEY (role_id, service_id),
        FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE,
        FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS accounts (
        account_id INTEGER PRIMARY KEY AUTOINCREMENT,
        identity_id TEXT,
        platform_id INTEGER NOT NULL,
        external_account_id TEXT NOT NULL,
        username TEXT,
        account_type TEXT NOT NULL CHECK (account_type IN ('User', 'Service', 'Role')),
        status TEXT NOT NULL,
        created_at DATETIME,
        last_seen_at DATETIME,
        mfa_enrolled BOOLEAN,
        FOREIGN KEY (identity_id) REFERENCES identities(identity_id) ON DELETE RESTRICT,
        FOREIGN KEY (platform_id) REFERENCES platforms(platform_id) ON DELETE RESTRICT,
        UNIQUE (platform_id, external_account_id)
    );

    CREATE TABLE IF NOT EXISTS tokens (
        token_id TEXT PRIMARY KEY,
        account_id INTEGER NOT NULL,
        token_name TEXT,
        token_type TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at DATETIME,
        last_rotated_at DATETIME,
        last_used_at DATETIME,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS audit_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_event_id TEXT,
        platform_id INTEGER NOT NULL,
        account_id INTEGER,
        identity_id TEXT,
        service_id INTEGER,
        resource_id INTEGER,
        event_name TEXT NOT NULL,
        event_time DATETIME NOT NULL,
        source_ip TEXT,
        outcome TEXT,
        raw_data TEXT,
        FOREIGN KEY (platform_id) REFERENCES platforms(platform_id) ON DELETE RESTRICT,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE SET NULL,
        FOREIGN KEY (identity_id) REFERENCES identities(identity_id) ON DELETE SET NULL,
        FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE SET NULL,
        FOREIGN KEY (resource_id) REFERENCES resources(resource_id) ON DELETE SET NULL,
        UNIQUE (platform_id, source_event_id)
    );
    """)

    cur.execute("PRAGMA foreign_keys = ON;")
    conn.commit()


# ___________________________ INGESTION PIPELINE ________________________________
def run_ingestion(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Run the complete Vigil multi-platform ingestion and normalization pipeline."""
    cur = conn.cursor()
    logging.info("Starting Vigil Ingestion Pipeline...")

    # 1. Seed Platforms
    logging.info("Step 1: Seeding Platforms (Okta, AWS, Azure)...")
    platforms_data = [
        ("okta", "Okta", "Identity Provider", "Enterprise Identity and Access Management"),
        ("aws", "AWS", "Cloud Platform", "Amazon Web Services Multi-Cloud Infrastructure"),
        ("azure", "Azure", "Cloud Platform", "Microsoft Azure Cloud Services"),
    ]
    cur.executemany(
        """
        INSERT INTO platforms (platform_code, platform_name, platform_type, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (platform_code) DO NOTHING;
    """,
        platforms_data,
    )
    conn.commit()

    cur.execute("SELECT platform_code, platform_id FROM platforms;")
    platform_map = dict(cur.fetchall())
    okta_pid = platform_map["okta"]
    aws_pid = platform_map["aws"]
    azure_pid = platform_map["azure"]

    # 2. Ingest Canonical HR Identities
    logging.info(f"Step 2: Ingesting Canonical HR Identities from {IDENTITIES_JSON}...")
    with open(IDENTITIES_JSON, "r", encoding="utf-8") as f:
        id_data = json.load(f)

    emp_to_id: Dict[str, str] = {}
    email_to_id: Dict[str, str] = {}

    identities_rows = []
    for item in id_data.get("identities", []):
        c_email = clean_email(item.get("company_email"))
        emp_id = str(item.get("employee_id", "")).strip()
        ident_id = item["identity_id"]

        emp_to_id[emp_id] = ident_id
        if c_email:
            email_to_id[c_email] = ident_id

        identities_rows.append(
            (
                ident_id,
                emp_id,
                item["full_name"],
                c_email,
                item.get("department"),
                item.get("role_title"),
                item.get("manager_identity_id"),
                item.get("baseline_group"),
                item.get("hr_status", "Active"),
                item.get("hire_date"),
                item.get("termination_date"),
                item.get("leave_start_date"),
                item.get("work_location"),
                item.get("office_ip"),
            )
        )

    cur.executemany(
        """
        INSERT INTO identities (
            identity_id, employee_id, full_name, company_email, department, role_title,
            manager_identity_id, baseline_group, hr_status, hire_date, termination_date,
            leave_start_date, work_location, office_ip
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (identity_id) DO UPDATE SET
            hr_status = excluded.hr_status,
            termination_date = excluded.termination_date,
            updated_at = CURRENT_TIMESTAMP;
    """,
        identities_rows,
    )
    conn.commit()
    logging.info(f"Successfully ingested {len(identities_rows)} canonical identities.")

    # 3. Ingest Okta Groups, User Accounts, and API Tokens
    logging.info(f"Step 3: Ingesting Okta Groups, Accounts, and Tokens from {OKTA_JSON}...")
    with open(OKTA_JSON, "r", encoding="utf-8") as f:
        okta_data = json.load(f)

    # 3.1 Groups
    group_rows = []
    for g in okta_data.get("groups", []):
        group_rows.append(
            (
                okta_pid,
                g["id"],
                g["name"],
                int(g.get("privilegeTier", 2)),
                g.get("description"),
            )
        )
    cur.executemany(
        """
        INSERT INTO groups (platform_id, external_group_id, group_name, privilege_tier, description)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (platform_id, external_group_id) DO NOTHING;
    """,
        group_rows,
    )
    conn.commit()

    cur.execute("SELECT group_name, group_id FROM groups WHERE platform_id = ?;", (okta_pid,))
    group_name_to_id = dict(cur.fetchall())

    # 3.2 User Accounts & API Tokens
    okta_ext_to_acc_id: Dict[str, int] = {}
    okta_ext_to_identity: Dict[str, Optional[str]] = {}
    email_to_acc_id: Dict[str, int] = {}
    tokens_rows = []
    acc_groups_rows = []

    for u in okta_data.get("users", []):
        prof = u.get("profile", {})
        u_email = clean_email(prof.get("email") or prof.get("login"))
        emp_num = str(prof.get("employeeNumber", "")).strip()

        # Deterministic Resolution Waterfall: employee_id -> normalized email
        matched_ident = emp_to_id.get(emp_num) or email_to_id.get(u_email)

        created_ts = parse_timestamp(u.get("created"))
        last_login_ts = parse_timestamp(u.get("lastLogin"))
        mfa = any(f.get("status") == "ACTIVE" for f in u.get("factors", []))

        cur.execute(
            """
            INSERT INTO accounts (
                identity_id, platform_id, external_account_id, username,
                account_type, status, created_at, last_seen_at, mfa_enrolled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (platform_id, external_account_id) DO UPDATE SET
                identity_id = excluded.identity_id,
                status = excluded.status,
                last_seen_at = excluded.last_seen_at,
                mfa_enrolled = excluded.mfa_enrolled
            RETURNING account_id;
        """,
            (
                matched_ident,
                okta_pid,
                u["id"],
                u_email,
                "User",
                str(u.get("status", "ACTIVE")).upper(),
                created_ts,
                last_login_ts,
                mfa,
            ),
        )
        acc_id = cur.fetchone()[0]
        okta_ext_to_acc_id[u["id"]] = acc_id
        okta_ext_to_identity[u["id"]] = matched_ident
        if u_email:
            email_to_acc_id[u_email] = acc_id

        # Group Memberships
        for gname in u.get("groups", []):
            gid = group_name_to_id.get(gname)
            if gid:
                acc_groups_rows.append((acc_id, gid))

        # API Tokens (with rotation metadata)
        for tok in u.get("tokens", []):
            tokens_rows.append(
                (
                    tok["tokenId"],
                    acc_id,
                    tok.get("name"),
                    tok.get("type", "API_TOKEN"),
                    tok.get("status", "ACTIVE"),
                    parse_timestamp(tok.get("createdAt")),
                    parse_timestamp(tok.get("lastRotatedAt")),
                    parse_timestamp(tok.get("lastUsedAt")),
                )
            )

    cur.executemany(
        """
        INSERT INTO account_groups (account_id, group_id)
        VALUES (?, ?)
        ON CONFLICT (account_id, group_id) DO NOTHING;
    """,
        acc_groups_rows,
    )
    cur.executemany(
        """
        INSERT INTO tokens (token_id, account_id, token_name, token_type, status, created_at, last_rotated_at, last_used_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (token_id) DO UPDATE SET
            status = excluded.status,
            last_rotated_at = excluded.last_rotated_at,
            last_used_at = excluded.last_used_at;
    """,
        tokens_rows,
    )
    conn.commit()
    logging.info(
        f"Okta Ingested: {len(okta_ext_to_acc_id)} accounts, {len(acc_groups_rows)} group memberships, {len(tokens_rows)} API tokens."
    )

    # 4. Services & Resources Catalog
    logging.info("Step 4: Seeding Cloud Services and Resources...")
    services_seed = [
        (aws_pid, "s3", "Amazon Simple Storage Service", "Object storage service"),
        (aws_pid, "ec2", "Amazon Elastic Compute Cloud", "Cloud compute capacity"),
        (aws_pid, "iam", "AWS Identity & Access Management", "Identity and access management"),
        (aws_pid, "ssm", "AWS Systems Manager", "Operations management"),
        (aws_pid, "secrets_manager", "AWS Secrets Manager", "Secrets management service"),
        (azure_pid, "storage", "Azure Blob Storage", "Scalable cloud object storage"),
        (azure_pid, "key_vault", "Azure Key Vault", "Cryptographic keys and secrets vault"),
    ]
    cur.executemany(
        """
        INSERT INTO services (platform_id, service_code, service_name, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (platform_id, service_code) DO NOTHING;
    """,
        services_seed,
    )
    conn.commit()

    cur.execute("SELECT platform_id, service_code, service_id FROM services;")
    service_lookup = {(row[0], row[1]): row[2] for row in cur.fetchall()}

    # Service-Scope Resources (for actions without explicit target objects)
    scope_resources = [
        (service_lookup[(aws_pid, "s3")], "service_scope", "S3 Service Scope", "s3_service_scope", "global"),
        (service_lookup[(aws_pid, "ec2")], "service_scope", "EC2 Service Scope", "ec2_service_scope", "global"),
        (service_lookup[(aws_pid, "iam")], "service_scope", "IAM Service Scope", "iam_service_scope", "global"),
        (service_lookup[(aws_pid, "ssm")], "service_scope", "SSM Service Scope", "ssm_service_scope", "global"),
        (
            service_lookup[(aws_pid, "secrets_manager")],
            "service_scope",
            "Secrets Manager Service Scope",
            "secrets_manager_service_scope",
            "global",
        ),
        (
            service_lookup[(azure_pid, "storage")],
            "service_scope",
            "Azure Storage Service Scope",
            "storage_service_scope",
            "global",
        ),
        (
            service_lookup[(azure_pid, "key_vault")],
            "service_scope",
            "Azure Key Vault Service Scope",
            "key_vault_service_scope",
            "global",
        ),
    ]
    cur.executemany(
        """
        INSERT INTO resources (service_id, resource_type, resource_name, external_resource_id, region)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (service_id, external_resource_id) DO NOTHING;
    """,
        scope_resources,
    )
    conn.commit()

    cur.execute("SELECT external_resource_id, resource_id FROM resources;")
    resource_lookup: Dict[str, int] = dict(cur.fetchall())

    def get_or_create_resource(
        service_id: int, res_type: str, res_name: str, ext_id: str, region: Optional[str] = None
    ) -> int:
        if ext_id in resource_lookup:
            return resource_lookup[ext_id]
        cur.execute(
            """
            INSERT INTO resources (service_id, resource_type, resource_name, external_resource_id, region)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (service_id, external_resource_id) DO UPDATE SET resource_name = excluded.resource_name
            RETURNING resource_id;
        """,
            (service_id, res_type, res_name, ext_id, region),
        )
        rid = cur.fetchone()[0]
        resource_lookup[ext_id] = rid
        return rid

    # 5. Ingest Audit Events Streams (Okta, AWS, Azure)
    logging.info("Step 5: Processing and Normalizing Cross-Platform Audit Events...")
    seen_events: Set[Tuple[int, str]] = set()
    audit_events_rows = []

    # 5.1 Okta SystemLog
    okta_dupes = 0
    okta_invalid_ts = 0
    for item in okta_data.get("systemLog", []):
        evt_uuid = item.get("uuid")
        if not evt_uuid or (okta_pid, evt_uuid) in seen_events:
            okta_dupes += 1
            continue
        seen_events.add((okta_pid, evt_uuid))

        pub_ts = parse_timestamp(item.get("published"))
        if not pub_ts:
            okta_invalid_ts += 1
            continue

        actor = item.get("actor") or {}
        actor_id = actor.get("id")
        alt_id = clean_email(actor.get("alternateId"))
        acc_id = okta_ext_to_acc_id.get(actor_id) or email_to_acc_id.get(alt_id)
        ident_id = okta_ext_to_identity.get(actor_id) or email_to_id.get(alt_id)

        client = item.get("client") or {}
        src_ip = client.get("ipAddress")
        outcome = (item.get("outcome") or {}).get("result", "UNKNOWN")

        audit_events_rows.append(
            (
                evt_uuid,
                okta_pid,
                acc_id,
                ident_id,
                None,
                None,
                item.get("eventType", "unknown"),
                pub_ts,
                src_ip,
                outcome,
                json.dumps(item),
            )
        )

    logging.info(
        f"Okta SystemLog parsed: {len(audit_events_rows)} valid events (skipped {okta_dupes} duplicates, {okta_invalid_ts} invalid timestamps)."
    )

    # 5.2 AWS CloudTrail Records
    logging.info(f"Processing AWS CloudTrail Records from {AWS_JSON}...")
    with open(AWS_JSON, "r", encoding="utf-8") as f:
        aws_data = json.load(f)

    aws_accounts_cache: Dict[str, Tuple[int, Optional[str]]] = {}
    aws_dupes = 0
    aws_invalid_ts = 0
    aws_events_count = 0

    for item in aws_data.get("Records", []):
        evt_id = item.get("eventID")
        if not evt_id or (aws_pid, evt_id) in seen_events:
            aws_dupes += 1
            continue
        seen_events.add((aws_pid, evt_id))

        evt_time = parse_timestamp(item.get("eventTime"))
        if not evt_time:
            aws_invalid_ts += 1
            continue

        u_ident = item.get("userIdentity") or {}
        user_name_raw = str(u_ident.get("userName", "")).strip()
        user_name_clean = clean_email(user_name_raw)
        p_id = u_ident.get("principalId")
        ext_acc_id = p_id or user_name_clean or user_name_raw

        # Service Account Detection: Machine accounts (svc-ci-*) remain unlinked (identity_id = NULL)
        is_svc = user_name_raw.lower().startswith("svc-") or "service" in u_ident.get("type", "").lower()
        if is_svc:
            acc_type = "Service"
            ident_id = None
        else:
            acc_type = "User"
            ident_id = email_to_id.get(user_name_clean)

        # Get or create AWS account
        if ext_acc_id not in aws_accounts_cache:
            cur.execute(
                """
                INSERT INTO accounts (
                    identity_id, platform_id, external_account_id, username,
                    account_type, status, created_at, last_seen_at, mfa_enrolled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (platform_id, external_account_id) DO UPDATE SET
                    last_seen_at = CASE WHEN excluded.last_seen_at > accounts.last_seen_at THEN excluded.last_seen_at ELSE accounts.last_seen_at END
                RETURNING account_id;
            """,
                (
                    ident_id,
                    aws_pid,
                    ext_acc_id,
                    user_name_clean,
                    acc_type,
                    "ACTIVE",
                    evt_time,
                    evt_time,
                    (u_ident.get("sessionContext", {}).get("attributes", {}).get("mfaAuthenticated") == "true"),
                ),
            )
            aws_acc_id = cur.fetchone()[0]
            aws_accounts_cache[ext_acc_id] = (aws_acc_id, ident_id)
        else:
            aws_acc_id, ident_id = aws_accounts_cache[ext_acc_id]

        # Service Resolution
        ev_src = str(item.get("eventSource", "")).lower()
        if "s3" in ev_src:
            s_code = "s3"
        elif "ec2" in ev_src:
            s_code = "ec2"
        elif "iam" in ev_src:
            s_code = "iam"
        elif "secret" in ev_src:
            s_code = "secrets_manager"
        elif "ssm" in ev_src:
            s_code = "ssm"
        else:
            s_code = "s3"

        svc_id = service_lookup[(aws_pid, s_code)]

        # Resource Resolution
        req_params = item.get("requestParameters") or {}
        res_ext_id = None
        res_type = s_code
        if "bucketName" in req_params:
            res_ext_id = f"arn:aws:s3:::{req_params['bucketName']}"
            res_type = "bucket"
        elif "instanceId" in req_params:
            res_ext_id = f"arn:aws:ec2::{req_params['instanceId']}"
            res_type = "instance"
        elif "roleName" in req_params:
            res_ext_id = f"arn:aws:iam::role/{req_params['roleName']}"
            res_type = "role"
        elif "userName" in req_params:
            res_ext_id = f"arn:aws:iam::user/{req_params['userName']}"
            res_type = "user"

        if res_ext_id:
            res_id = get_or_create_resource(
                svc_id, res_type, res_ext_id.split("/")[-1], res_ext_id, item.get("awsRegion")
            )
        else:
            res_id = resource_lookup.get(f"{s_code}_service_scope")

        audit_events_rows.append(
            (
                evt_id,
                aws_pid,
                aws_acc_id,
                ident_id,
                svc_id,
                res_id,
                item.get("eventName", "unknown"),
                evt_time,
                item.get("sourceIPAddress"),
                "SUCCESS" if not item.get("errorCode") else "FAILURE",
                json.dumps(item),
            )
        )
        aws_events_count += 1

    logging.info(
        f"AWS Records parsed: {aws_events_count} valid events (skipped {aws_dupes} duplicates, {aws_invalid_ts} invalid timestamps)."
    )

    # 5.3 Azure Activity Records
    logging.info(f"Processing Azure Activity Records from {AZURE_JSON}...")
    with open(AZURE_JSON, "r", encoding="utf-8") as f:
        azure_data = json.load(f)

    azure_accounts_cache: Dict[str, Tuple[int, Optional[str]]] = {}
    azure_dupes = 0
    azure_invalid_ts = 0
    azure_events_count = 0

    for item in azure_data.get("records", []):
        cid = item.get("correlationId", "")
        time_raw = item.get("time", "")
        evt_key = f"{cid}_{time_raw}"
        if not cid or (azure_pid, evt_key) in seen_events:
            azure_dupes += 1
            continue
        seen_events.add((azure_pid, evt_key))

        evt_time = parse_timestamp(time_raw)
        if not evt_time:
            azure_invalid_ts += 1
            continue

        ident_claim = (item.get("identity") or {}).get("claim") or {}
        upn_clean = clean_email(ident_claim.get("upn"))
        oid = ident_claim.get("oid")
        ext_acc_id = oid or upn_clean or "unknown_azure_principal"

        matched_ident = email_to_id.get(upn_clean) if upn_clean else None

        if ext_acc_id not in azure_accounts_cache:
            cur.execute(
                """
                INSERT INTO accounts (
                    identity_id, platform_id, external_account_id, username,
                    account_type, status, created_at, last_seen_at, mfa_enrolled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (platform_id, external_account_id) DO UPDATE SET
                    last_seen_at = CASE WHEN excluded.last_seen_at > accounts.last_seen_at THEN excluded.last_seen_at ELSE accounts.last_seen_at END
                RETURNING account_id;
            """,
                (
                    matched_ident,
                    azure_pid,
                    ext_acc_id,
                    upn_clean,
                    "User",
                    "ACTIVE",
                    evt_time,
                    evt_time,
                    None,
                ),
            )
            azure_acc_id = cur.fetchone()[0]
            azure_accounts_cache[ext_acc_id] = (azure_acc_id, matched_ident)
        else:
            azure_acc_id, matched_ident = azure_accounts_cache[ext_acc_id]

        res_id_raw = item.get("resourceId", "")
        props = item.get("properties") or {}
        res_type = str(props.get("resourceType", "")).upper()
        if "storage" in res_id_raw.lower() or res_type == "STORAGEACCOUNTS":
            s_code = "storage"
        else:
            s_code = "key_vault"

        svc_id = service_lookup[(azure_pid, s_code)]
        if res_id_raw:
            res_name = res_id_raw.split("/")[-1]
            res_id = get_or_create_resource(svc_id, res_type or s_code, res_name, res_id_raw)
        else:
            res_id = resource_lookup.get(f"{s_code}_service_scope")

        audit_events_rows.append(
            (
                evt_key,
                azure_pid,
                azure_acc_id,
                matched_ident,
                svc_id,
                res_id,
                item.get("operationName", "unknown"),
                evt_time,
                item.get("callerIpAddress"),
                str(item.get("resultType", "SUCCESS")).upper(),
                json.dumps(item),
            )
        )
        azure_events_count += 1

    logging.info(
        f"Azure Records parsed: {azure_events_count} valid events (skipped {azure_dupes} duplicates, {azure_invalid_ts} invalid timestamps)."
    )

    # Batch Insert Audit Events
    logging.info(f"Inserting {len(audit_events_rows)} normalized audit events into audit_events table...")
    cur.executemany(
        """
        INSERT INTO audit_events (
            source_event_id, platform_id, account_id, identity_id, service_id,
            resource_id, event_name, event_time, source_ip, outcome, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (platform_id, source_event_id) DO NOTHING;
    """,
        audit_events_rows,
    )
    conn.commit()

    logging.info("Vigil Ingestion Pipeline completed successfully.")

    # Return summary metrics
    summary = {}
    for tbl in ["identities", "platforms", "services", "resources", "groups", "accounts", "tokens", "audit_events"]:
        cur.execute(f"SELECT COUNT(*) FROM {tbl};")
        summary[tbl] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM accounts WHERE account_type = 'Service' AND identity_id IS NULL;")
    summary["quarantined_service_accounts"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM audit_events WHERE identity_id IS NOT NULL;")
    summary["audit_events_with_identity"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM audit_events WHERE identity_id IS NULL;")
    summary["audit_events_without_identity"] = cur.fetchone()[0]

    return summary


def main():
    conn = connect_db()
    init_schema(conn)
    metrics = run_ingestion(conn)
    conn.close()

    print("\n==================================================")
    print("           VIGIL INGESTION METRICS                ")
    print("==================================================")
    for k, v in metrics.items():
        print(f" {k:<30}: {v:>6}")
    print("==================================================")


if __name__ == "__main__":
    main()
