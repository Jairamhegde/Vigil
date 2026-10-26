import { KeyRound, LayoutDashboard, LogOut, Moon, TriangleAlert } from "lucide-react";
import { initials } from "../lib/format";
import { Brand } from "./ui";

const LINKS = [
    { page: "overview", label: "Overview", icon: LayoutDashboard },
    { page: "risky", label: "Risky identities", icon: TriangleAlert },
    { page: "dormant", label: "Dormant identities", icon: Moon },
    { page: "privileged", label: "Privileged access", icon: KeyRound },
];

export default function Sidebar({ page, username, riskyCount, onLogout }) {
    return (
        <aside className="sidebar">
            <Brand />

            <nav className="nav">
                <div className="nav-label">Monitor</div>

                {LINKS.map(({ page: target, label, icon: Icon }) => (
                    <a key={target} href={`#/${target}`} className={page === target ? "active" : ""}>
                        <Icon size={18} />
                        <span>{label}</span>
                        {target === "risky" && riskyCount > 0 && <span className="nav-count">{riskyCount}</span>}
                    </a>
                ))}
            </nav>

            <div className="sidebar-foot">
                <div className="avatar">{initials(username)}</div>
                <div className="user-meta">
                    <div className="user-name">{username}</div>
                    <div className="user-role">Super admin</div>
                </div>
                <button className="icon-btn" onClick={onLogout} title="Sign out" aria-label="Sign out">
                    <LogOut size={16} />
                </button>
            </div>
        </aside>
    );
}
