// Small presentational building blocks shared by every page.

import { Search } from "lucide-react";
import { useState } from "react";
import { initials, prettySignal, riskBand, splitReason, TIER_LABELS } from "../lib/format";

// Square status icon, used on the access-denied screen
export function BrandMark({ danger = false, icon: Icon }) {
    return (
        <div className={danger ? "brand-mark danger" : "brand-mark"}>
            <Icon size={20} strokeWidth={2.2} />
        </div>
    );
}

// Text-only wordmark
export function Brand() {
    return (
        <div className="brand">
            <div className="brand-name">Vigil<span className="brand-dot">.</span></div>
            <div className="brand-sub">Identity Security Console</div>
        </div>
    );
}

export function KpiCard({ label, value, note, color, icon: Icon }) {
    return (
        <div className="kpi" style={{ "--kpi-color": color }}>
            <div className="kpi-head">
                <span>{label}</span>
                <span className="kpi-icon"><Icon size={17} /></span>
            </div>
            <div className="kpi-value">{value}</div>
            <div className="kpi-note">{note}</div>
        </div>
    );
}

// flush = content runs edge to edge (tables, lists); otherwise it gets padding
export function Panel({ title, subtitle, actions, flush = false, children, style }) {
    return (
        <section className="panel" style={style}>
            <div className="panel-head">
                <div>
                    <h3>{title}</h3>
                    {subtitle && <p>{subtitle}</p>}
                </div>
                {actions}
            </div>
            <div className={flush ? "panel-body flush" : "panel-body"}>{children}</div>
        </section>
    );
}

export function ChartBox({ tall = false, children }) {
    return <div className={tall ? "chart-box tall" : "chart-box"}>{children}</div>;
}

export function Badge({ kind = "neutral", children }) {
    return <span className={`badge badge-${kind}`}>{children}</span>;
}

export function HrBadge({ status }) {
    const kind = status === "Active" ? "low" : status === "On Leave" ? "medium" : "critical";
    return <Badge kind={kind}>{status}</Badge>;
}

export function TierBadge({ tier }) {
    const kind = ["critical", "high", "neutral"][tier];
    return <Badge kind={kind}>{TIER_LABELS[tier]}</Badge>;
}

export function Person({ row }) {
    return (
        <div className="person">
            <div className="person-avatar">{initials(row.full_name)}</div>
            <div>
                <div className="person-name">{row.full_name}</div>
                <div className="person-sub">{row.employee_id} · {row.department || "No department"}</div>
            </div>
        </div>
    );
}

export function ScoreBar({ score, label }) {
    const band = riskBand(score);

    return (
        <div className="score">
            <div className="score-top" style={{ color: band.color }}>
                {score}
                <small>/ 100 {label}</small>
            </div>
            <div className="score-bar">
                <span style={{ width: `${score}%`, background: band.color }} />
            </div>
        </div>
    );
}

export function SearchBox({ value, onChange, placeholder = "Search name, ID, department" }) {
    return (
        <label className="search">
            <Search />
            <input type="search" value={value} placeholder={placeholder} aria-label={placeholder}
                   onChange={(event) => onChange(event.target.value)} />
        </label>
    );
}

export function Segmented({ options, value, onChange, label }) {
    return (
        <div className="segmented" role="group" aria-label={label}>
            {options.map((option) => (
                <button key={option.value} className={option.value === value ? "active" : ""}
                        onClick={() => onChange(option.value)}>
                    {option.label}
                </button>
            ))}
        </div>
    );
}

export function Empty({ children }) {
    return <div className="empty">{children}</div>;
}

export function PageSkeleton() {
    return (
        <>
            <div className="kpi-grid">
                {[1, 2, 3, 4].map((key) => <div key={key} className="skeleton" />)}
            </div>
            <div className="skeleton" style={{ minHeight: 300 }} />
        </>
    );
}

export function PageError({ error }) {
    return (
        <Panel title="Could not load data">
            <Empty>{error.message}</Empty>
        </Panel>
    );
}

export function ReasonList({ reasons, visible = 3 }) {
    const [expanded, setExpanded] = useState(false);
    const shown = expanded ? reasons : reasons.slice(0, visible);
    const hiddenCount = reasons.length - visible;

    return (
        <>
            <ul className="reasons">
                {shown.map((reason) => {
                    const { signal, detail } = splitReason(reason);

                    return <li key={reason}><b>{prettySignal(signal)}</b> {detail}</li>;
                })}
            </ul>
            {hiddenCount > 0 && (
                <button className="more-btn" onClick={() => setExpanded(!expanded)}>
                    {expanded ? "Show less" : `Show ${hiddenCount} more`}
                </button>
            )}
        </>
    );
}

// Dark tooltip used by every Recharts chart
export function ChartTooltip({ active, payload, label, labelFormatter }) {
    if (!active || !payload || !payload.length) {
        return null;
    }

    return (
        <div className="chart-tooltip">
            {label !== undefined && <div className="chart-tooltip-title">{labelFormatter ? labelFormatter(label) : label}</div>}
            {payload.map((item) => (
                <div key={item.dataKey + item.name} className="chart-tooltip-row">
                    <span className="dot" style={{ background: item.payload.color || item.color || item.payload.fill }} />
                    <span>{item.name}</span>
                    <b>{item.value}</b>
                </div>
            ))}
        </div>
    );
}
