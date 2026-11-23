// Revoke an identity's access in two steps:
//   1. choose the accounts and give a reason   -> POST /api/revocations/prepare  (server issues a challenge)
//   2. re-enter your password + type the ID    -> POST /api/revocations/confirm  (server verifies, then revokes)

import { Check, ShieldAlert, ShieldOff, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useActions } from "../lib/actions";
import { formatDate, platformName } from "../lib/format";
import { Badge, HrBadge } from "./ui";

// preselect(account) picks the accounts ticked at the start; default: every enabled account
export function RevokeButton({ row, reason, preselect, compact = false }) {
    const [open, setOpen] = useState(false);

    return (
        <>
            <button className={compact ? "btn btn-danger btn-sm" : "btn btn-danger"} onClick={() => setOpen(true)}
                    title={`Revoke access for ${row.full_name}`}>
                <ShieldOff size={14} />
                <span>Revoke</span>
            </button>
            {open && <RevokeDialog employeeId={row.employee_id} suggestedReason={reason} preselect={preselect}
                                  onClose={() => setOpen(false)} />}
        </>
    );
}

export default function RevokeDialog({ employeeId, suggestedReason = "", preselect, onClose }) {
    const { request, notify, dataChanged } = useActions();
    const [step, setStep] = useState("select");          // select -> verify -> done
    const [person, setPerson] = useState(null);
    const [selected, setSelected] = useState(new Set());
    const [reason, setReason] = useState(suggestedReason);
    const [challenge, setChallenge] = useState(null);
    const [password, setPassword] = useState("");
    const [confirmText, setConfirmText] = useState("");
    const [result, setResult] = useState(null);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [now, setNow] = useState(Date.now());
    const dialogRef = useRef(null);

    useEffect(() => {
        request(`/api/identities/${encodeURIComponent(employeeId)}/access`)
            .then((data) => {
                const active = data.accounts.filter((account) => account.enabled);
                const picked = preselect ? active.filter(preselect) : active;

                setPerson(data);
                setSelected(new Set((picked.length ? picked : active).map((account) => account.account_id)));
            })
            .catch((failure) => setError(failure.message));
        // preselect is only read once, when the dialog opens
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [employeeId, request]);

    // Escape closes, and focus starts inside the dialog
    useEffect(() => {
        const onKey = (event) => event.key === "Escape" && !busy && onClose();

        window.addEventListener("keydown", onKey);
        dialogRef.current && dialogRef.current.focus();
        return () => window.removeEventListener("keydown", onKey);
    }, [busy, onClose]);

    // Countdown for the confirmation challenge
    useEffect(() => {
        if (step !== "verify") {
            return undefined;
        }

        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, [step]);

    const enabled = person ? person.accounts.filter((account) => account.enabled) : [];
    const chosen = enabled.filter((account) => selected.has(account.account_id));
    const privilegeCount = chosen.reduce((sum, account) => sum + account.entitlements.length, 0);
    const secondsLeft = challenge ? Math.max(0, Math.round(challenge.expires_at - now / 1000)) : 0;

    const toggle = (accountId) => {
        const next = new Set(selected);
        next.has(accountId) ? next.delete(accountId) : next.add(accountId);
        setSelected(next);
    };

    const toggleAll = () => {
        setSelected(chosen.length === enabled.length ? new Set() : new Set(enabled.map((account) => account.account_id)));
    };

    const prepare = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");

        try {
            const issued = await request("/api/revocations/prepare", {
                method: "POST",
                body: { employee_id: employeeId, account_ids: [...selected], reason },
            });

            setChallenge(issued);
            setNow(Date.now());
            setStep("verify");
        } catch (failure) {
            setError(failure.message);
        } finally {
            setBusy(false);
        }
    };

    const confirm = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");

        try {
            const done = await request("/api/revocations/confirm", {
                method: "POST",
                body: { challenge_id: challenge.challenge_id, password, confirm_text: confirmText },
            });

            setResult(done);
            setStep("done");
            notify({
                kind: done.saved === false ? "error" : "success",
                title: done.saved === false ? "Revoked, but not saved to storage" : "Access revoked",
                body: `${done.full_name}: ${done.revoked_accounts} account${done.revoked_accounts === 1 ? "" : "s"} disabled. `
                    + `Risk is now ${done.risk_score}.`,
            });
        } catch (failure) {
            setError(failure.message);
            setPassword("");

            if (failure.message.includes("no longer valid")) {
                setChallenge(null);
                setStep("select");
            }
        } finally {
            setBusy(false);
        }
    };

    const close = () => {
        if (step === "done") {
            dataChanged();
        }

        onClose();
    };

    return (
        <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && close()}>
            <div className="modal" role="dialog" aria-modal="true" aria-labelledby="revoke-title" tabIndex={-1} ref={dialogRef}>
                <div className="modal-head">
                    <div className="modal-icon"><ShieldAlert size={18} /></div>
                    <div>
                        <h3 id="revoke-title">Revoke access</h3>
                        <p>{person ? `${person.full_name} · ${person.employee_id}` : employeeId}</p>
                    </div>
                    <button className="icon-btn" onClick={close} disabled={busy} aria-label="Close"><X size={16} /></button>
                </div>

                <ol className="steps">
                    <li className={step === "select" ? "active" : "complete"}><span>1</span>Choose access</li>
                    <li className={step === "verify" ? "active" : step === "done" ? "complete" : ""}><span>2</span>Verify it is you</li>
                </ol>

                {!person && !error && <div className="modal-body muted">Loading accounts…</div>}

                {person && step === "select" && (
                    <form onSubmit={prepare}>
                        <div className="modal-body">
                            <div className="chips" style={{ marginBottom: 14 }}>
                                <HrBadge status={person.hr_status} />
                                {person.is_ghost === 1 && <Badge kind="critical">Ghost</Badge>}
                                {person.is_dormant === 1 && <Badge kind="medium">Dormant</Badge>}
                                {person.risk_score != null && <Badge kind="info">Risk {person.risk_score}</Badge>}
                                {person.department && <Badge>{person.department}</Badge>}
                            </div>

                            {enabled.length ? (
                                <>
                                    <div className="account-list-head">
                                        <span>{chosen.length} of {enabled.length} enabled accounts selected</span>
                                        <button type="button" className="more-btn" onClick={toggleAll}>
                                            {chosen.length === enabled.length ? "Select none" : "Select all"}
                                        </button>
                                    </div>
                                    <div className="account-list">
                                        {enabled.map((account) => (
                                            <AccountOption key={account.account_id} account={account}
                                                           checked={selected.has(account.account_id)}
                                                           onToggle={() => toggle(account.account_id)} />
                                        ))}
                                    </div>
                                </>
                            ) : (
                                <div className="empty">Every account of this identity is already disabled.</div>
                            )}

                            {person.revocations.length > 0 && (
                                <div className="modal-note">
                                    Revoked before: {person.revocations.map((item) =>
                                        `${platformName(item.platform)} ${item.account_key} by ${item.revoked_by} on ${formatDate(item.revoked_at)}`,
                                    ).join(" · ")}
                                </div>
                            )}

                            <label className="field" style={{ marginTop: 16 }}>
                                <span>Reason (kept in the audit log)</span>
                                <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2}
                                          maxLength={500} required minLength={5}
                                          placeholder="e.g. Terminated 2026-08-14, account still enabled" />
                            </label>

                            <div className="modal-note">
                                Selected accounts are disabled and their privileges removed in Vigil, and the change is logged.
                                Vigil reads exported data, so apply the same change in the source system.
                            </div>
                        </div>

                        <div className="form-error modal-error" role="alert">{error}</div>

                        <div className="modal-foot">
                            <button type="button" className="btn" onClick={close}>Cancel</button>
                            <button type="submit" className="btn btn-danger" disabled={busy || !chosen.length || reason.trim().length < 5}>
                                {busy ? "Checking…" : `Continue with ${chosen.length} account${chosen.length === 1 ? "" : "s"}`}
                            </button>
                        </div>
                    </form>
                )}

                {person && step === "verify" && challenge && (
                    <form onSubmit={confirm}>
                        <div className="modal-body">
                            <div className="verify-summary">
                                You are about to disable <b>{challenge.accounts.length} account{challenge.accounts.length === 1 ? "" : "s"}</b>
                                {" "}and remove <b>{privilegeCount} privilege{privilegeCount === 1 ? "" : "s"}</b> for <b>{challenge.full_name}</b>:
                                <div className="chips" style={{ marginTop: 10 }}>
                                    {challenge.accounts.map((account) => (
                                        <span key={account.platform + account.account_key} className="chip">
                                            {platformName(account.platform)}: {account.account_key}
                                        </span>
                                    ))}
                                </div>
                            </div>

                            <label className="field">
                                <span>Your password</span>
                                <input type="password" value={password} onChange={(event) => setPassword(event.target.value)}
                                       autoComplete="current-password" autoFocus required />
                            </label>

                            <label className="field">
                                <span>Type <b className="mono">{challenge.employee_id}</b> to confirm</span>
                                <input value={confirmText} onChange={(event) => setConfirmText(event.target.value)}
                                       autoComplete="off" spellCheck={false} required />
                            </label>

                            <div className={secondsLeft < 60 ? "modal-note warn" : "modal-note"}>
                                {secondsLeft > 0
                                    ? `This confirmation expires in ${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, "0")}.`
                                    : "This confirmation has expired. Go back and start again."}
                            </div>
                        </div>

                        <div className="form-error modal-error" role="alert">{error}</div>

                        <div className="modal-foot">
                            <button type="button" className="btn" disabled={busy}
                                    onClick={() => { setStep("select"); setChallenge(null); setError(""); setPassword(""); }}>
                                Back
                            </button>
                            <button type="submit" className="btn btn-danger"
                                    disabled={busy || !password || secondsLeft === 0
                                              || confirmText.trim().toUpperCase() !== challenge.employee_id.toUpperCase()}>
                                <ShieldOff size={14} />
                                {busy ? "Revoking…" : "Revoke access"}
                            </button>
                        </div>
                    </form>
                )}

                {step === "done" && result && (
                    <>
                        <div className="modal-body done">
                            <div className="done-icon"><Check size={22} /></div>
                            <h4>Access revoked</h4>
                            <p>
                                {result.revoked_accounts} account{result.revoked_accounts === 1 ? "" : "s"} of {result.full_name} disabled
                                and logged. Risk score is now <b>{result.risk_score}</b>.
                            </p>
                        </div>
                        <div className="modal-foot">
                            <button className="btn btn-primary" onClick={close} autoFocus>Done</button>
                        </div>
                    </>
                )}

                {error && !person && <div className="form-error modal-error" role="alert">{error}</div>}
            </div>
        </div>
    );
}

function AccountOption({ account, checked, onToggle }) {
    const privileged = account.entitlements.filter((item) => item.privilege_tier <= 1);

    return (
        <label className={checked ? "account-option checked" : "account-option"}>
            <input type="checkbox" checked={checked} onChange={onToggle} />
            <div className="account-main">
                <div className="account-title">
                    <b>{platformName(account.platform)}</b>
                    <span className="mono">{account.account_key}</span>
                    {account.account_type !== "human" && <Badge>{account.account_type}</Badge>}
                </div>
                <div className="account-sub">
                    Last sign-in {account.last_login ? formatDate(account.last_login) : "never"}
                    {" · "}{account.entitlements.length} privilege{account.entitlements.length === 1 ? "" : "s"}
                    {account.mfa_level && ` · MFA ${account.mfa_level}`}
                </div>
                {privileged.length > 0 && (
                    <div className="chips" style={{ marginTop: 6 }}>
                        {privileged.map((item) => (
                            <span key={item.entitlement + item.scope} className={`chip t${item.privilege_tier}`}>
                                <b>T{item.privilege_tier}</b>{item.entitlement}{item.scope ? ` @ ${item.scope}` : ""}
                            </span>
                        ))}
                    </div>
                )}
            </div>
        </label>
    );
}
