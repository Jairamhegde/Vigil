"""
Step 3 - Query service.

Read-only queries that power the dashboard. Every function returns a list of dictionaries (or one
dictionary), so the API layer can send the result as JSON without knowing any SQL.

"Now" is the most recent activity in the database. For live feeds that is roughly the current time,
and for the synthetic export it keeps results stable (the data ends on 2026-09-30).
"""
import json
import sqlite3

from backend.db_connection import connect_db
from utils.path import GUARD_DB

INACTIVE_DAYS = 30


def run_query(sql, params=(), db_path=GUARD_DB):
    conn = connect_db(db_path)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def split_list(value):
    """GROUP_CONCAT returns one string. Turn it back into a sorted list."""
    if not value:
        return []

    return sorted(set(value.split("||")))


def get_reference_time():
    rows = run_query('''
        SELECT MAX(latest) AS reference_time
        FROM (
            SELECT MAX(event_time) AS latest FROM audit_events
            UNION ALL
            SELECT MAX(last_login) FROM accounts
        )
    ''')

    return rows[0]["reference_time"]


# ___________________ Dormant: inactive in HR or AD, but still active in the cloud ___________

def get_cross_platform_dormant_identities():
    """
    Identities that are not active in HR (terminated / on leave) or have no enabled AD account,
    yet AWS or Azure still recorded events for them. For HR leavers, only events after the
    termination or leave date count.
    """
    rows = run_query('''
        WITH ad_state AS (
            SELECT identity_id, MAX(enabled) AS ad_enabled
            FROM accounts
            WHERE platform = 'ad' AND account_type = 'human'
            GROUP BY identity_id
        )
        SELECT
            i.employee_id,
            i.full_name,
            i.department,
            i.hr_status,
            COALESCE(i.termination_date, i.leave_start_date)       AS inactive_since,
            CASE
                WHEN ad.ad_enabled = 1 THEN 'enabled'
                WHEN ad.ad_enabled = 0 THEN 'disabled'
                ELSE 'no account'
            END                                                     AS ad_status,
            GROUP_CONCAT(DISTINCT a.platform)                       AS cloud_platforms,
            COUNT(*)                                                AS events_after_inactive,
            SUM(e.is_sensitive)                                     AS sensitive_events,
            MIN(e.event_time)                                       AS first_event,
            MAX(e.event_time)                                       AS last_event
        FROM identities i
        LEFT JOIN ad_state ad      ON ad.identity_id = i.identity_id
        JOIN accounts a            ON a.identity_id = i.identity_id AND a.platform IN ('aws', 'azure')
        JOIN audit_events e        ON e.account_id = a.account_id
        WHERE (i.hr_status <> 'Active' OR COALESCE(ad.ad_enabled, 0) = 0)
          AND substr(e.event_time, 1, 10) >
              CASE WHEN i.hr_status = 'Active' THEN '0000-00-00'
                   ELSE COALESCE(i.termination_date, i.leave_start_date) END
        GROUP BY i.identity_id
        ORDER BY events_after_inactive DESC
    ''')

    for row in rows:
        row["cloud_platforms"] = row["cloud_platforms"].split(",")

    return rows


# ___________________ Dormant: no activity anywhere for 30+ days ______________

def get_inactive_identities(days=INACTIVE_DAYS):
    """
    Active employees with at least one enabled account unused for more than `days` (or never used).
    Unused access is dormant even when the person still signs in elsewhere, so each stale account is
    listed. fully_inactive = 1 means every enabled account of that person is stale.
    """
    reference_time = get_reference_time()

    rows = run_query('''
        WITH enabled_accounts AS (
            SELECT
                identity_id,
                platform,
                last_login,
                CAST(julianday(:reference_time) - julianday(last_login) AS INTEGER)    AS days_unused
            FROM accounts
            WHERE identity_id IS NOT NULL
              AND enabled = 1
              -- AD and Okta report last login. Cloud accounts can only be judged when their logs are loaded,
              -- otherwise a missing log feed would make every cloud account look unused.
              AND (platform IN ('ad', 'okta') OR platform IN (SELECT DISTINCT platform FROM audit_events))
        )
        SELECT
            i.employee_id,
            i.full_name,
            i.department,
            i.role_title,
            i.hr_status,
            COUNT(*)                                                                AS enabled_accounts,
            SUM(ea.last_login IS NULL OR ea.days_unused > :days)                    AS stale_accounts,
            MAX(ea.last_login)                                                      AS last_activity,
            MAX(CASE WHEN ea.last_login IS NULL OR ea.days_unused > :days
                     THEN COALESCE(ea.days_unused, 9999) END)                       AS max_days_unused,
            GROUP_CONCAT(CASE WHEN ea.last_login IS NULL OR ea.days_unused > :days
                              THEN ea.platform || ': ' || COALESCE(substr(ea.last_login, 1, 10), 'never used')
                         END, '||')                                                 AS stale_detail
        FROM identities i
        JOIN enabled_accounts ea ON ea.identity_id = i.identity_id
        WHERE i.hr_status = 'Active'
        GROUP BY i.identity_id
        HAVING stale_accounts > 0
        ORDER BY stale_accounts = enabled_accounts DESC, max_days_unused DESC
    ''', {"reference_time": reference_time, "days": days})

    for row in rows:
        row["fully_inactive"] = int(row["stale_accounts"] == row["enabled_accounts"])
        row["never_used"] = row["max_days_unused"] == 9999
        row["max_days_unused"] = None if row["never_used"] else row["max_days_unused"]
        row["stale_detail"] = split_list(row["stale_detail"])

    return rows


# ___________________ Privileged identities ___________________________________

def get_privileged_identities(max_tier=1):
    """Identities holding tier 0 (admin) or tier 1 (elevated) access on an enabled account."""
    rows = run_query('''
        SELECT
            i.employee_id,
            i.full_name,
            i.department,
            i.role_title,
            i.hr_status,
            MIN(e.privilege_tier)                                                   AS highest_tier,
            COUNT(DISTINCT CASE WHEN e.privilege_tier = 0 THEN a.platform || e.entitlement || e.scope END)
                                                                                    AS tier0_count,
            COUNT(DISTINCT CASE WHEN e.privilege_tier = 1 THEN a.platform || e.entitlement || e.scope END)
                                                                                    AS tier1_count,
            GROUP_CONCAT(
                'T' || e.privilege_tier || ' ' || a.platform || ': ' || e.entitlement
                || CASE WHEN e.scope <> '' THEN ' @ ' || e.scope ELSE '' END
                || CASE WHEN e.via LIKE 'nested%' THEN ' (' || e.via || ')' ELSE '' END,
                '||')                                                               AS privileges
        FROM identities i
        JOIN accounts a     ON a.identity_id = i.identity_id AND a.enabled = 1
        JOIN entitlements e ON e.account_id = a.account_id
        WHERE e.privilege_tier <= :max_tier
        GROUP BY i.identity_id
        ORDER BY highest_tier, tier0_count DESC, tier1_count DESC
    ''', {"max_tier": max_tier})

    for row in rows:
        row["privileges"] = split_list(row["privileges"])

    return rows


# ___________________ Risky identities (computed by metrics.py) ________________

def get_risky_identities(only_risky=True):
    rows = run_query('''
        SELECT
            i.employee_id,
            i.full_name,
            i.department,
            i.role_title,
            i.hr_status,
            m.risk_score,
            m.damage_score,
            m.is_dormant,
            m.is_ghost,
            m.is_risky,
            m.reasons,
            m.as_of
        FROM identity_metrics m
        JOIN identities i ON i.identity_id = m.identity_id
        WHERE m.as_of = (SELECT MAX(as_of) FROM identity_metrics)
          AND (m.is_risky = 1 OR :only_risky = 0)
        ORDER BY m.risk_score DESC, m.damage_score DESC
    ''', {"only_risky": int(only_risky)})

    for row in rows:
        row["reasons"] = json.loads(row["reasons"])

    return rows


# ___________________ Dashboard summary and chart data ________________________

def get_summary():
    counts = run_query('''
        SELECT
            (SELECT COUNT(*) FROM identities)                                       AS total_identities,
            (SELECT COUNT(*) FROM identities WHERE hr_status = 'Active')            AS active_identities,
            (SELECT COUNT(*) FROM accounts)                                         AS total_accounts,
            (SELECT COUNT(*) FROM accounts WHERE identity_id IS NULL)               AS unowned_accounts,
            (SELECT COUNT(*) FROM audit_events)                                     AS total_events,
            (SELECT COUNT(*) FROM audit_events WHERE outcome = 'failure')           AS failed_events,
            (SELECT COUNT(*) FROM audit_events WHERE is_sensitive = 1)              AS sensitive_events,
            (SELECT COUNT(*) FROM identity_metrics
              WHERE is_risky = 1 AND as_of = (SELECT MAX(as_of) FROM identity_metrics))  AS risky_identities,
            (SELECT COUNT(*) FROM identity_metrics
              WHERE is_ghost = 1 AND as_of = (SELECT MAX(as_of) FROM identity_metrics))  AS ghost_identities,
            (SELECT MAX(as_of) FROM identity_metrics)                               AS metrics_as_of
    ''')[0]

    counts["reference_time"] = get_reference_time()
    counts["cross_platform_dormant"] = len(get_cross_platform_dormant_identities())
    inactive = get_inactive_identities()
    counts["inactive_identities"] = len(inactive)
    counts["fully_inactive_identities"] = sum(row["fully_inactive"] for row in inactive)

    privileged = get_privileged_identities()
    counts["tier0_identities"] = sum(1 for row in privileged if row["highest_tier"] == 0)
    counts["tier1_identities"] = sum(1 for row in privileged if row["highest_tier"] == 1)

    return counts


def get_tier_distribution():
    """Distinct privileged grants per platform and tier, for a stacked bar chart."""
    return run_query('''
        SELECT a.platform, e.privilege_tier AS tier, COUNT(*) AS grants
        FROM entitlements e
        JOIN accounts a ON a.account_id = e.account_id
        WHERE a.enabled = 1
        GROUP BY a.platform, e.privilege_tier
        ORDER BY a.platform, tier
    ''')


def get_risk_distribution():
    """How many identities fall in each risk band, for a doughnut chart."""
    return run_query('''
        SELECT
            CASE
                WHEN risk_score >= 70 THEN 'Critical'
                WHEN risk_score >= 40 THEN 'High'
                WHEN risk_score >= 20 THEN 'Medium'
                ELSE 'Low'
            END             AS band,
            COUNT(*)        AS identities
        FROM identity_metrics
        WHERE as_of = (SELECT MAX(as_of) FROM identity_metrics)
        GROUP BY band
    ''')


def get_department_risk():
    return run_query('''
        SELECT
            i.department,
            COUNT(*)                        AS identities,
            SUM(m.is_risky)                 AS risky,
            SUM(m.is_dormant)               AS dormant,
            SUM(m.is_ghost)                 AS ghost,
            ROUND(AVG(m.risk_score), 1)     AS avg_risk
        FROM identity_metrics m
        JOIN identities i ON i.identity_id = m.identity_id
        WHERE m.as_of = (SELECT MAX(as_of) FROM identity_metrics)
        GROUP BY i.department
        ORDER BY avg_risk DESC
    ''')


def get_event_timeline():
    """Events per week, split into normal, failed and sensitive, for a line chart."""
    return run_query('''
        SELECT
            strftime('%Y-%W', event_time)                  AS week,
            MIN(substr(event_time, 1, 10))                 AS week_start,
            COUNT(*)                                       AS total,
            SUM(outcome = 'failure')                       AS failed,
            SUM(is_sensitive)                              AS sensitive
        FROM audit_events
        GROUP BY week
        ORDER BY week
    ''')


if __name__ == "__main__":
    print("summary:", get_summary())
    print("cross-platform dormant:", len(get_cross_platform_dormant_identities()))
    print("inactive 30d:", len(get_inactive_identities()))
    print("privileged:", len(get_privileged_identities()))
    print("risky:", len(get_risky_identities()))
