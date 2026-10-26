"""
Computes per-identity dashboard metrics from the stored facts and writes them to identity_metrics.

  Dormant  : HR Active, with an enabled AD/Okta account that has had no sign-in for DORMANT_DAYS
             (or never signed in and is older than that).
  Ghost    : HR Terminated, but at least one account on any platform is still enabled.
  Damage   : 0-100 blast radius. What the identity could break with its enabled privileges.
  Risk     : 0-100. Risk signals plus a share of the damage score. Risky when >= RISKY_THRESHOLD.

Rules and weights live here, so tuning them only needs a re-run, not a re-ingest.
"""
import json
from datetime import datetime, timedelta

from backend.db_connection import connect_db
from utils.path import GUARD_DB

DORMANT_DAYS = 90
RECENT_DAYS = 30
RISKY_THRESHOLD = 40

TIER_WEIGHTS = {0: 25, 1: 10, 2: 0}
NON_PROD_FACTOR = 0.5
NON_PROD_MARKERS = ("dev", "staging", "test", "sandbox")
DAMAGE_SHARE_OF_RISK = 0.3

SIGNAL_POINTS = {
    "ghost_account": 40,
    "activity_after_termination": 30,
    "no_mfa": 20,
    "active_while_on_leave": 15,
    "dormant_account": 10,
    "sms_only_mfa": 10,
    "repeated_access_denied": 10,
    "sensitive_actions": 10,
    "suspended_not_deprovisioned": 5,
    "disabled_account_retains_privilege": 5,
}
ACCESS_DENIED_MIN = 3
INTERACTIVE_PLATFORMS = ("ad", "okta")


def _parse(ts):
    return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S") if ts else None


def _day(ts):
    return ts[:10] if ts else None


def _default_as_of(conn):
    """The most recent activity in the data. That is about 'now' for live feeds, and also gives
    stable results on the synthetic export."""
    return conn.execute('''
        SELECT MAX(t) FROM (SELECT MAX(event_time) AS t FROM audit_events
                            UNION ALL SELECT MAX(last_login) FROM accounts)
    ''').fetchone()[0]


def _damage_score(entitlements):
    score = 0.0
    for name, scope, tier in {(e["entitlement"], e["scope"], e["privilege_tier"]) for e in entitlements}:
        weight = TIER_WEIGHTS[tier]
        if any(m in scope.lower() for m in NON_PROD_MARKERS):
            weight *= NON_PROD_FACTOR
        score += weight
    return min(100, round(score))


def compute_identity_metrics(conn, as_of=None):
    conn.row_factory = None
    as_of = as_of or _default_as_of(conn)
    now = _parse(as_of)
    dormant_cutoff = (now - timedelta(days=DORMANT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent_cutoff = (now - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def rows(sql, params=()):
        cur = conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    identities = rows("SELECT * FROM identities")
    accounts_by_identity, entitlements_by_account = {}, {}
    for a in rows("SELECT * FROM accounts WHERE identity_id IS NOT NULL"):
        accounts_by_identity.setdefault(a["identity_id"], []).append(a)
    for e in rows("SELECT * FROM entitlements"):
        entitlements_by_account.setdefault(e["account_id"], []).append(e)
    events = {r["identity_id"]: r for r in rows('''
        SELECT a.identity_id,
               MAX(e.event_time)                                                       AS last_event,
               SUM(e.outcome = 'failure' AND e.event_time >= :recent)                  AS recent_failures,
               SUM(e.is_sensitive = 1 AND e.event_time >= :recent)                     AS recent_sensitive
        FROM audit_events e JOIN accounts a ON a.account_id = e.account_id
        WHERE a.identity_id IS NOT NULL AND e.event_time <= :as_of
        GROUP BY a.identity_id
    ''', {"recent": recent_cutoff, "as_of": as_of})}

    results = []
    for ident in identities:
        accts = accounts_by_identity.get(ident["identity_id"], [])
        enabled = [a for a in accts if a["enabled"]]
        ev = events.get(ident["identity_id"], {})
        signals, reasons = set(), []

        def flag(signal, detail):
            signals.add(signal)
            reasons.append(f"{signal}: {detail}")

        # Ghost: terminated in HR, account still usable
        is_ghost = ident["hr_status"] == "Terminated" and bool(enabled)
        if is_ghost:
            flag("ghost_account", f"terminated {ident['termination_date']}, still enabled on "
                                  + ", ".join(sorted({a['platform'] for a in enabled})))

        # Activity after termination
        if ident["hr_status"] == "Terminated" and ident["termination_date"]:
            last_seen = max(filter(None, [ev.get("last_event")] + [a["last_login"] for a in accts]), default=None)
            if last_seen and _day(last_seen) > ident["termination_date"]:
                flag("activity_after_termination", f"last activity {last_seen}")

        # Dormant: active employee, interactive account unused for DORMANT_DAYS
        dormant_accts = [
            a for a in enabled
            if a["platform"] in INTERACTIVE_PLATFORMS
            and (a["last_login"] or a["created_at"] or as_of) < dormant_cutoff
        ]
        is_dormant = ident["hr_status"] == "Active" and bool(dormant_accts)
        if is_dormant:
            flag("dormant_account", "; ".join(f"{a['platform']} last login {a['last_login'] or 'never'}"
                                              for a in dormant_accts))

        # Active while on leave
        if ident["hr_status"] == "On Leave" and ident["leave_start_date"]:
            used = [a for a in enabled if a["last_login"] and _day(a["last_login"]) > ident["leave_start_date"]]
            if used:
                flag("active_while_on_leave", f"on leave since {ident['leave_start_date']}, "
                                              f"signed in on {', '.join(a['platform'] for a in used)}")

        # MFA posture, judged on enabled Okta accounts (the IdP for every federated app)
        mfa = {a["mfa_level"] for a in enabled if a["platform"] == "okta"}
        if "none" in mfa:
            flag("no_mfa", "Okta account has no MFA factor")
        elif "sms" in mfa:
            flag("sms_only_mfa", "Okta account relies on SMS only")

        if ident["hr_status"] == "Terminated" and any(a["status"] == "SUSPENDED" for a in accts):
            flag("suspended_not_deprovisioned", "Okta account suspended, never deprovisioned")

        priv_on_disabled = [e["entitlement"] for a in accts if not a["enabled"]
                            for e in entitlements_by_account.get(a["account_id"], []) if e["privilege_tier"] <= 1]
        if priv_on_disabled:
            flag("disabled_account_retains_privilege", ", ".join(sorted(set(priv_on_disabled))))

        if (ev.get("recent_failures") or 0) >= ACCESS_DENIED_MIN:
            flag("repeated_access_denied", f"{ev['recent_failures']} failed calls in {RECENT_DAYS}d")
        if ev.get("recent_sensitive"):
            flag("sensitive_actions", f"{ev['recent_sensitive']} sensitive calls in {RECENT_DAYS}d")

        enabled_ents = [e for a in enabled for e in entitlements_by_account.get(a["account_id"], [])]
        damage = _damage_score(enabled_ents)
        top = sorted({(e["privilege_tier"], e["entitlement"], e["scope"]) for e in enabled_ents if e["privilege_tier"] <= 1})
        if top:
            reasons.append("privileges: " + ", ".join(f"{n}{'@' + s if s else ''} (tier {t})" for t, n, s in top))

        risk = min(100, sum(SIGNAL_POINTS[s] for s in signals) + round(damage * DAMAGE_SHARE_OF_RISK))
        results.append((ident["identity_id"], as_of, int(is_dormant), int(is_ghost), damage, risk,
                        int(risk >= RISKY_THRESHOLD), json.dumps(reasons)))

    with conn:
        conn.executemany('''
            INSERT OR REPLACE INTO identity_metrics(identity_id, as_of, is_dormant, is_ghost, damage_score,
                                                    risk_score, is_risky, reasons)
            VALUES (?,?,?,?,?,?,?,?)
        ''', results)
    return as_of, len(results)


def run(db_path=GUARD_DB, as_of=None):
    conn = connect_db(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    result = compute_identity_metrics(conn, as_of)
    conn.close()
    return result


if __name__ == "__main__":
    print(run())
