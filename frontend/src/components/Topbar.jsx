import { RefreshCw } from "lucide-react";

export default function Topbar({ title, subtitle, stamp, refreshing, onRefresh }) {
    return (
        <header className="topbar">
            <div className="page-title">
                <h2>{title}</h2>
                <p>{subtitle}</p>
            </div>

            <div className="topbar-actions">
                <div className="data-stamp">
                    <span className="live-dot" />
                    <span>{stamp}</span>
                </div>

                <button className="btn btn-primary" onClick={onRefresh} disabled={refreshing}>
                    <RefreshCw size={16} className={refreshing ? "spin" : ""} />
                    <span>{refreshing ? "Refreshing…" : "Refresh data"}</span>
                </button>
            </div>
        </header>
    );
}
