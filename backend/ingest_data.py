"""
Step 1 - Extraction service.

Reads the synthetic JSON exports and returns plain Python lists of dictionaries.
This module never touches the database, so it can be reused or replaced on its own.

Main outputs
    extract_hr_identities()      -> one dict per HR employee
    extract_ad_users()           -> one dict per AD account (employee, admin and service accounts)
    extract_ad_groups()          -> one dict per AD group
    extract_okta_users()         -> one dict per Okta user
    build_accounts(...)          -> every platform account, matched to an HR identity
    build_entitlements(...)      -> every effective permission with a normalized tier (nesting resolved)
    build_audit_events(...)      -> AWS, Okta and Azure events in one common structure
"""
import json
import logging
from collections import deque
from pathlib import Path

from utils.path import (
    HR_IDENTITIES_JSON,
    AD_JSON,
    OKTA_IDENTITIES_JSON,
    AWS_CLOUDTRAIL_JSON,
    OKTA_SYSTEM_LOG_JSON,
    AZURE_ACTIVITY_LOG_JSON,
)


# ___________________ Tier normalization rules _________________________________
# Tier 0 = any kind of admin (highest), Tier 1 = elevated but not admin, Tier 2 = normal user (lowest)

TIER_0_KEYWORDS = ["admin", "owner", "super", "dcsync", "domain controllers", "schema", "enterprise"]

TIER_1_KEYWORDS = ["operator", "poweruser", "power user", "contributor", "prod-access", "helpdesk",
                   "help_desk", "escalation", "dataengineer", "it-operations"]

# AWS actions that change permissions, credentials, logging or network exposure
SENSITIVE_EVENTS = ["AttachRolePolicy", "AuthorizeSecurityGroupIngress", "CreateAccessKey",
                    "CreateLoginProfile", "CreateRole", "CreateUser", "DeleteTrail", "PutBucketPolicy",
                    "PutUserPolicy", "StartSession", "StopLogging", "UpdateAssumeRolePolicy"]

AD_ACCOUNT_TYPES = {"Employee": "human", "Admin": "admin", "Service": "service"}

OKTA_DISABLED_STATUSES = ["SUSPENDED", "DEPROVISIONED"]


# ___________________ Small helpers ____________________________________________

def read_json(path):
    """Read a JSON file. Returns None when the file does not exist."""
    path = Path(path)

    if not path.exists():
        logging.warning(f"Data file not found, skipping: {path}")
        return None

    with open(path, encoding="utf-8") as file:
        return json.load(file)


def normalize_email(email):
    """Lower-case and trim an email so the same person matches across platforms."""
    if not email:
        return None

    email = email.strip().lower()

    if "@" not in email:
        return None

    return email


def normalize_timestamp(value):
    """Convert timestamps to YYYY-MM-DDTHH:MM:SSZ (Okta adds milliseconds, AD and AWS do not)."""
    if not value:
        return None

    return value[:19] + "Z"


# ___________________ 1. Extract each source file ______________________________

def extract_hr_identities(path=HR_IDENTITIES_JSON):
    """HR export: the single source of truth for who works here."""
    data = read_json(path)

    if data is None:
        return []

    identities = []

    for person in data["identities"]:
        identities.append({
            "employee_id": person["employee_id"],
            "full_name": person["full_name"],
            "email": normalize_email(person["company_email"]),
            "department": person["department"],
            "role_title": person["role_title"],
            "hr_status": person["hr_status"],
            "hire_date": person["hire_date"],
            "termination_date": person["termination_date"],
            "leave_start_date": person["leave_start_date"],
            "manager_employee_id": person["manager_employee_id"],
        })

    return identities


def extract_ad_users(path=AD_JSON):
    """Active Directory accounts, including admin (adm-*) and service (svc-*) accounts."""
    data = read_json(path)

    if data is None:
        return []

    users = []

    for user in data["users"]:
        users.append({
            "account_key": user["sAMAccountName"].lower(),
            "full_name": user["displayName"],
            "email": normalize_email(user["mail"]),
            "employee_id": user["employeeID"],
            "account_type": AD_ACCOUNT_TYPES.get(user["employeeType"], "human"),
            "department": user["department"],
            "enabled": bool(user["enabled"]),
            "status": "enabled" if user["enabled"] else "disabled",
            "last_login": normalize_timestamp(user["lastLogonTimestamp"]),
            "created_at": normalize_timestamp(user["whenCreated"]),
            "direct_groups": [dn.lower() for dn in user["memberOf"]],
            "domain_rights": user.get("_domainRights", []),
        })

    return users


def extract_ad_groups(path=AD_JSON):
    """Active Directory groups, with the parent groups each group is nested in."""
    data = read_json(path)

    if data is None:
        return []

    groups = []

    for group in data["groups"]:
        groups.append({
            "dn": group["distinguishedName"].lower(),
            "name": group["cn"],
            "source_tier": group.get("privilegeTier"),
            "parent_groups": [dn.lower() for dn in group["memberOf"]],
        })

    return groups


def get_mfa_level(factors):
    """Summarise Okta MFA factors as none, sms or strong."""
    active_types = set()

    for factor in factors:
        if factor["status"] == "ACTIVE":
            active_types.add(factor["factorType"])

    if not active_types:
        return "none"

    if active_types.issubset({"sms", "call", "email"}):
        return "sms"

    return "strong"


def extract_okta_users(path=OKTA_IDENTITIES_JSON):
    """Okta users, with their admin roles and the AWS / Azure access granted through Okta apps."""
    data = read_json(path)

    if data is None:
        return []

    users = []

    for user in data["users"]:
        profile = user["profile"]

        aws_access = []
        azure_access = []

        for assignment in user["appAssignments"]:
            app_profile = assignment["profile"]

            if "permissionSets" in app_profile:
                for permission_set in app_profile["permissionSets"]:
                    for aws_account in app_profile.get("accounts", [""]):
                        aws_access.append({"role": permission_set, "scope": aws_account})

            if "azureRbacRole" in app_profile:
                azure_access.append({"role": app_profile["azureRbacRole"],
                                     "scope": app_profile.get("subscription", "")})

        users.append({
            "account_key": normalize_email(profile["login"]),
            "full_name": profile["displayName"],
            "email": normalize_email(profile["email"]),
            "employee_id": profile["employeeNumber"],
            "account_type": "human",
            "department": profile["department"],
            "enabled": user["status"] not in OKTA_DISABLED_STATUSES,
            "status": user["status"],
            "mfa_level": get_mfa_level(user["factors"]),
            "last_login": normalize_timestamp(user["lastLogin"]),
            "created_at": normalize_timestamp(user["created"]),
            "admin_roles": [role["type"] for role in user["adminRoles"]],
            "aws_access": aws_access,
            "azure_access": azure_access,
        })

    return users


def extract_aws_events(path=AWS_CLOUDTRAIL_JSON):
    """Raw AWS CloudTrail records."""
    data = read_json(path)

    if data is None:
        return []

    return data["Records"]


def extract_okta_events(path=OKTA_SYSTEM_LOG_JSON):
    """Raw Okta System Log events (/api/v1/logs format). Not present in the current dataset."""
    data = read_json(path)

    if data is None:
        return []

    if isinstance(data, dict):
        return data.get("events", [])

    return data


def extract_azure_events(path=AZURE_ACTIVITY_LOG_JSON):
    """Raw Azure activity / sign-in log records. Not present in the current dataset."""
    data = read_json(path)

    if data is None:
        return []

    if isinstance(data, dict):
        return data.get("value", data.get("records", []))

    return data


# ___________________ 2. Match users across platforms (by email) ________________

def build_identity_index(hr_identities):
    """Lookup tables used to match any platform account back to its HR identity."""
    by_email = {}
    by_employee_id = {}

    for person in hr_identities:
        by_email[person["email"]] = person["employee_id"]
        by_employee_id[person["employee_id"]] = person["employee_id"]

    return {"by_email": by_email, "by_employee_id": by_employee_id}


def match_identity(email, employee_id, identity_index):
    """
    Return the HR employee_id that owns an account, or None.

    1. Email is the primary match key (same address in HR, AD, Okta, AWS and Azure).
    2. Admin accounts (adm-*) have no mailbox. They carry their owner's employeeID, so that is the fallback.
    Service accounts have neither, so they stay unmatched (owner = None).
    """
    email = normalize_email(email)

    if email and email in identity_index["by_email"]:
        return identity_index["by_email"][email]

    if employee_id and employee_id in identity_index["by_employee_id"]:
        return identity_index["by_employee_id"][employee_id]

    return None


# ___________________ 3. Normalize privilege tiers ______________________________

def normalize_tier(permission_name, source_tier=None):
    """
    Map any permission name to tier 0 (admin), 1 (elevated) or 2 (normal user).
    When the source system already rates the permission (AD privilegeTier), the stricter rating wins.
    """
    name = permission_name.lower()

    if any(keyword in name for keyword in TIER_0_KEYWORDS):
        tier = 0
    elif any(keyword in name for keyword in TIER_1_KEYWORDS):
        tier = 1
    else:
        tier = 2

    if source_tier in (0, 1, 2):
        tier = min(tier, source_tier)

    return tier


# ___________________ 4. Resolve nested AD groups ______________________________

def resolve_nested_groups(direct_groups, group_parents):
    """
    Breadth-first search up the memberOf graph.

    Starts from the user's direct groups and follows each group's parent groups.
    A visited set stops the walk at groups already seen, so circular nesting (A -> B -> A) cannot loop forever.
    Returns {group_dn: direct_group_dn} so every inherited permission can say where it came from.
    """
    effective = {}
    queue = deque()

    for group_dn in direct_groups:
        queue.append((group_dn, group_dn))

    while queue:
        group_dn, came_from = queue.popleft()

        if group_dn in effective:
            continue

        effective[group_dn] = came_from

        for parent_dn in group_parents.get(group_dn, []):
            queue.append((parent_dn, came_from))

    return effective


# ___________________ 5. Build accounts and entitlements ______________________

def build_accounts(hr_identities, ad_users, okta_users):
    """Every platform account in one list, each matched to its HR owner."""
    identity_index = build_identity_index(hr_identities)
    accounts = []

    for user in ad_users:
        accounts.append({
            "platform": "ad",
            "account_key": user["account_key"],
            "employee_id": match_identity(user["email"], user["employee_id"], identity_index),
            "account_type": user["account_type"],
            "enabled": user["enabled"],
            "status": user["status"],
            "mfa_level": None,
            "last_login": user["last_login"],
            "created_at": user["created_at"],
        })

    for user in okta_users:
        owner = match_identity(user["email"], user["employee_id"], identity_index)

        accounts.append({
            "platform": "okta",
            "account_key": user["account_key"],
            "employee_id": owner,
            "account_type": "human",
            "enabled": user["enabled"],
            "status": user["status"],
            "mfa_level": user["mfa_level"],
            "last_login": user["last_login"],
            "created_at": user["created_at"],
        })

        # AWS and Azure sign-in is federated through Okta, so the cloud account follows the Okta account
        for platform, access in [("aws", user["aws_access"]), ("azure", user["azure_access"])]:
            if access:
                accounts.append({
                    "platform": platform,
                    "account_key": user["account_key"],
                    "employee_id": owner,
                    "account_type": "human",
                    "enabled": user["enabled"],
                    "status": "federated",
                    "mfa_level": None,
                    "last_login": None,
                    "created_at": None,
                })

    return accounts


def build_entitlements(ad_users, ad_groups, okta_users):
    """Every effective permission per account, with a normalized tier and how it was granted."""
    groups_by_dn = {}
    group_parents = {}

    for group in ad_groups:
        groups_by_dn[group["dn"]] = group
        group_parents[group["dn"]] = group["parent_groups"]

    entitlements = []

    for user in ad_users:
        effective_groups = resolve_nested_groups(user["direct_groups"], group_parents)

        for group_dn, came_from in effective_groups.items():
            group = groups_by_dn[group_dn]

            if group_dn == came_from:
                via = "direct"
            else:
                via = "nested via " + groups_by_dn[came_from]["name"]

            entitlements.append({
                "platform": "ad",
                "account_key": user["account_key"],
                "entitlement": group["name"],
                "scope": "",
                "tier": normalize_tier(group["name"], group["source_tier"]),
                "via": via,
            })

        if "DS-Replication-Get-Changes-All" in user["domain_rights"]:
            entitlements.append({
                "platform": "ad",
                "account_key": user["account_key"],
                "entitlement": "DCSync replication rights",
                "scope": "",
                "tier": 0,
                "via": "direct domain permission",
            })

    for user in okta_users:
        for role in user["admin_roles"]:
            entitlements.append({
                "platform": "okta",
                "account_key": user["account_key"],
                "entitlement": role,
                "scope": "",
                "tier": normalize_tier(role),
                "via": "Okta admin role",
            })

        for access in user["aws_access"]:
            entitlements.append({
                "platform": "aws",
                "account_key": user["account_key"],
                "entitlement": access["role"],
                "scope": access["scope"],
                "tier": normalize_tier(access["role"]),
                "via": "Okta app assignment",
            })

        for access in user["azure_access"]:
            entitlements.append({
                "platform": "azure",
                "account_key": user["account_key"],
                "entitlement": access["role"],
                "scope": access["scope"],
                "tier": normalize_tier(access["role"]),
                "via": "Okta app assignment",
            })

    return entitlements


# ___________________ 6. Convert events to one structure ______________________

def convert_aws_event(record):
    identity = record["userIdentity"]
    actor = identity.get("userName") or identity.get("arn", "").rsplit("/", 1)[-1]

    return {
        "platform": "aws",
        "source_event_id": record["eventID"],
        "event_time": normalize_timestamp(record["eventTime"]),
        "actor_email": normalize_email(actor),
        "event_name": record["eventName"],
        "target": record.get("recipientAccountId"),
        "source_ip": record.get("sourceIPAddress"),
        "outcome": "failure" if record.get("errorCode") else "success",
        "error_code": record.get("errorCode"),
        "token_id": identity.get("accessKeyId") or identity.get("credentialId"),
        "is_sensitive": record["eventName"] in SENSITIVE_EVENTS,
    }


def convert_okta_event(event):
    actor = event.get("actor", {})
    client = event.get("client", {})
    outcome = event.get("outcome", {}).get("result", "")
    targets = event.get("target") or [{}]

    return {
        "platform": "okta",
        "source_event_id": event.get("uuid"),
        "event_time": normalize_timestamp(event.get("published")),
        "actor_email": normalize_email(actor.get("alternateId")),
        "event_name": event.get("eventType"),
        "target": targets[0].get("displayName"),
        "source_ip": client.get("ipAddress"),
        "outcome": "success" if outcome == "SUCCESS" else "failure",
        "error_code": event.get("outcome", {}).get("reason"),
        "token_id": event.get("authenticationContext", {}).get("externalSessionId"),
        "is_sensitive": "admin" in (event.get("eventType") or "").lower(),
    }


def convert_azure_event(event):
    properties = event.get("properties", event)
    status = str(event.get("status", {}).get("value", event.get("resultType", ""))).lower()

    return {
        "platform": "azure",
        "source_event_id": event.get("eventDataId") or event.get("id") or event.get("correlationId"),
        "event_time": normalize_timestamp(event.get("eventTimestamp") or event.get("time")),
        "actor_email": normalize_email(event.get("caller") or properties.get("userPrincipalName")),
        "event_name": event.get("operationName", {}).get("value", event.get("operationName")),
        "target": event.get("subscriptionId"),
        "source_ip": event.get("callerIpAddress") or properties.get("ipAddress"),
        "outcome": "success" if status in ("succeeded", "success", "0") else "failure",
        "error_code": None if status in ("succeeded", "success", "0") else status,
        "token_id": event.get("correlationId"),
        "is_sensitive": "roleassignments/write" in str(event.get("operationName", "")).lower(),
    }


def build_audit_events(aws_records, okta_records, azure_records):
    """One list of events from every platform, ready for the audit_events table."""
    events = []

    for record in aws_records:
        events.append(convert_aws_event(record))

    for record in okta_records:
        events.append(convert_okta_event(record))

    for record in azure_records:
        events.append(convert_azure_event(record))

    # An event without an id or a time cannot be de-duplicated or placed on a timeline
    return [event for event in events if event["source_event_id"] and event["event_time"]]


# ___________________ Run the whole extraction ________________________________

def extract_all():
    """Run every extractor and return the data, ready for insert_data.py."""
    hr_identities = extract_hr_identities()
    ad_users = extract_ad_users()
    ad_groups = extract_ad_groups()
    okta_users = extract_okta_users()

    return {
        "identities": hr_identities,
        "accounts": build_accounts(hr_identities, ad_users, okta_users),
        "entitlements": build_entitlements(ad_users, ad_groups, okta_users),
        "audit_events": build_audit_events(extract_aws_events(), extract_okta_events(), extract_azure_events()),
    }


if __name__ == "__main__":
    data = extract_all()

    for name, rows in data.items():
        print(f"{name:14} {len(rows)}")
