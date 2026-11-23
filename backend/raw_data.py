"""
Raw data browser: the JSON exports in data/ exactly as Vigil reads them, plus Vigil's own revocation log.

Each dataset is one list inside one file (for example the users list in ad_directory.json). The API
returns a page of the original records, filtered by a text search, with a short list of columns the
dashboard shows in its table. The full record is always included, so nothing is hidden.
"""
import json
import threading

from backend import revocation
from utils.path import AD_JSON, AWS_CLOUDTRAIL_JSON, HR_IDENTITIES_JSON, OKTA_IDENTITIES_JSON

DATASETS = {
    "hr_identities": {
        "source": "HR", "label": "Employees", "file": HR_IDENTITIES_JSON, "key": "identities",
        "description": "HR system of record: the single source of truth for who is employed.",
        "columns": ["employee_id", "full_name", "company_email", "department", "role_title", "hr_status",
                    "hire_date", "termination_date", "leave_start_date", "manager_employee_id"],
    },
    "ad_users": {
        "source": "Active Directory", "label": "Users", "file": AD_JSON, "key": "users",
        "description": "Employee, admin (adm-*) and service (svc-*) accounts.",
        "columns": ["sAMAccountName", "displayName", "employeeID", "employeeType", "department", "enabled",
                    "lastLogonTimestamp", "adminCount", "memberOf"],
    },
    "ad_groups": {
        "source": "Active Directory", "label": "Groups", "file": AD_JSON, "key": "groups",
        "description": "Security groups, their nesting (member / memberOf) and privilege tier.",
        "columns": ["sAMAccountName", "groupScope", "privilegeTier", "description", "member", "memberOf"],
    },
    "ad_ous": {
        "source": "Active Directory", "label": "Organizational units", "file": AD_JSON, "key": "organizationalUnits",
        "description": "The OU tree accounts live in.",
        "columns": ["name", "distinguishedName", "description"],
    },
    "okta_users": {
        "source": "Okta", "label": "Users", "file": OKTA_IDENTITIES_JSON, "key": "users",
        "description": "Okta users with groups, MFA factors, admin roles and app (AWS / Azure) assignments.",
        "columns": ["profile.login", "profile.employeeNumber", "status", "lastLogin", "groups", "factors",
                    "adminRoles"],
    },
    "okta_groups": {
        "source": "Okta", "label": "Groups", "file": OKTA_IDENTITIES_JSON, "key": "groups",
        "description": "Okta groups, including the ones pushed to AWS and Azure.",
        "columns": ["id", "type", "profile.name", "profile.description"],
    },
    "okta_apps": {
        "source": "Okta", "label": "Apps", "file": OKTA_IDENTITIES_JSON, "key": "apps",
        "description": "Applications connected to Okta.",
        "columns": ["id", "name", "label", "status", "signOnMode", "created"],
    },
    "aws_cloudtrail": {
        "source": "AWS", "label": "CloudTrail events", "file": AWS_CLOUDTRAIL_JSON, "key": "Records",
        "description": "AWS API activity, May to September 2026.",
        "columns": ["eventTime", "userIdentity.userName", "eventName", "eventSource", "sourceIPAddress",
                    "awsRegion", "errorCode"],
    },
    "revocations": {
        "source": "Vigil", "label": "Access revocations", "file": None, "key": None,
        "description": "Every revocation made from this dashboard, with who did it and why.",
        "columns": ["revoked_at", "employee_id", "full_name", "platform", "account_key", "entitlements", "reason",
                    "revoked_by"],
    },
}

_cache = {}
_cache_lock = threading.Lock()


def _load_file(path):
    """Parse a JSON file once per change on disk. CloudTrail is ~20 MB, so it is not re-read per request."""
    stamp = path.stat().st_mtime

    with _cache_lock:
        cached = _cache.get(path)

        if cached and cached["stamp"] == stamp:
            return cached

        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)

        cached = {"stamp": stamp, "data": data, "search": {}}
        _cache[path] = cached
        return cached


def _records(name):
    """Return (records, search_texts, meta) for a dataset."""
    spec = DATASETS[name]

    if spec["file"] is None:
        rows = revocation.list_revocations()

        for row in rows:
            row["entitlements"] = [item for item in row["entitlements"].split("||") if item]

        return rows, [json.dumps(row).lower() for row in rows], None

    loaded = _load_file(spec["file"])
    records = loaded["data"].get(spec["key"], [])

    if spec["key"] not in loaded["search"]:
        loaded["search"][spec["key"]] = [json.dumps(record, ensure_ascii=False).lower() for record in records]

    return records, loaded["search"][spec["key"]], loaded["data"].get("meta")


def list_datasets():
    result = []

    for name, spec in DATASETS.items():
        entry = {"id": name, "source": spec["source"], "label": spec["label"], "description": spec["description"]}

        if spec["file"] is not None:
            if not spec["file"].exists():
                continue

            entry["file"] = spec["file"].name
            entry["size_bytes"] = spec["file"].stat().st_size

        records, _, _ = _records(name)
        entry["records"] = len(records)
        result.append(entry)

    return result


def get_dataset_page(name, search="", offset=0, limit=50):
    if name not in DATASETS:
        return None

    spec = DATASETS[name]
    records, texts, meta = _records(name)
    terms = search.lower().split()

    if terms:
        matches = [record for record, text in zip(records, texts) if all(term in text for term in terms)]
    else:
        matches = records

    return {
        "id": name,
        "source": spec["source"],
        "label": spec["label"],
        "description": spec["description"],
        "file": spec["file"].name if spec["file"] else "backend/database.db (revocations table)",
        "meta": meta,
        "columns": spec["columns"],
        "total": len(records),
        "matched": len(matches),
        "offset": offset,
        "limit": limit,
        "records": matches[offset:offset + limit],
    }
