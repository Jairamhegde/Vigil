import { Ghost, KeyRound, Layers, Network } from "lucide-react";
import { useState } from "react";
import {
    Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
    ChartBox, ChartTooltip, Empty, HrBadge, KpiCard, PageError, PageSkeleton, Panel, Person, SearchBox, Segmented,
    TierBadge,
} from "../components/ui";
import { AXIS, CURSOR, GRID, LEGEND, PIE_STROKE } from "../lib/charts";
import { useApi } from "../lib/data";
import { COLORS, PLATFORM_COLORS, countBy, matchesSearch, platformName, TIER_COLORS, TIER_LABELS } from "../lib/format";

const FILTERS = [
    { value: "all", label: "All" },
    { value: "tier0", label: "Tier 0" },
    { value: "leavers", label: "Leavers" },
];

// Each privilege arrives as "T0 ad: Domain Admins @ scope (nested via Group)"
function parsePrivilege(text) {
    return { tier: text.slice(0, 2), platform: text.slice(3).split(":")[0], label: text.slice(3) };
}

export default function PrivilegedPage() {
    const privileged = useApi("/api/identities/privileged");
    const [search, setSearch] = useState("");
    const [filter, setFilter] = useState("all");

    if (privileged.error) {
        return <PageError error={privileged.error} />;
    }

    if (!privileged.data) {
        return <PageSkeleton />;
    }

    const rows = privileged.data;
    const tier0 = rows.filter((row) => row.highest_tier === 0);
    const leavers = rows.filter((row) => row.hr_status !== "Active");
    const inherited = rows.flatMap((row) => row.privileges).filter((item) => item.includes("nested via")).length;

    const filtered = rows.filter((row) => {
        if (filter === "tier0" && row.highest_tier !== 0) return false;
        if (filter === "leavers" && row.hr_status === "Active") return false;
        return matchesSearch(row, search);
    });

    return (
        <>
            <div className="kpi-grid">
                <KpiCard label="Tier 0 holders" value={tier0.length} color={COLORS.critical} icon={KeyRound}
                         note="Any kind of admin access" />
                <KpiCard label="Tier 1 holders" value={rows.length - tier0.length} color={COLORS.high} icon={Layers}
                         note="Elevated, not admin" />
                <KpiCard label="Leavers with privilege" value={leavers.length} color={COLORS.critical} icon={Ghost}
                         note="Terminated or on leave, still privileged" />
                <KpiCard label="Inherited grants" value={inherited} color={COLORS.accent} icon={Network}
                         note="Privilege that comes through nested groups" />
            </div>

            <div className="grid-2">
                <Panel title="Privileged identities by department" subtitle="Grouped by highest tier held">
                    <DepartmentChart rows={rows} />
                </Panel>
                <Panel title="Tier 0 grants by platform" subtitle="Where admin access lives">
                    <PlatformDonut rows={rows} />
                </Panel>
            </div>

            <Panel title="Privileged identities" subtitle="T0 = admin, T1 = elevated. Nested grants show the group they come through" flush
                   actions={
                       <div className="toolbar">
                           <SearchBox value={search} onChange={setSearch} />
                           <Segmented options={FILTERS} value={filter} onChange={setFilter} label="Filter" />
                       </div>
                   }>
                {filtered.length ? (
                    <div className="table-wrap">
                        <table>
                            <thead>
                                <tr><th>Identity</th><th>HR status</th><th>Highest tier</th><th>Grants</th><th>Privileges</th></tr>
                            </thead>
                            <tbody>
                                {filtered.map((row) => <PrivilegedRow key={row.employee_id} row={row} />)}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <Empty>No identities match this filter.</Empty>
                )}
            </Panel>
        </>
    );
}

function PrivilegedRow({ row }) {
    return (
        <tr>
            <td><Person row={row} /></td>
            <td><HrBadge status={row.hr_status} /></td>
            <td><TierBadge tier={row.highest_tier} /></td>
            <td className="mono">{row.tier0_count} × T0<br />{row.tier1_count} × T1</td>
            <td>
                <div className="chips">
                    {row.privileges.map((text) => {
                        const item = parsePrivilege(text);

                        return (
                            <span key={text} className={`chip ${item.tier.toLowerCase()}`}>
                                <b>{item.tier}</b>{item.label}
                            </span>
                        );
                    })}
                </div>
            </td>
        </tr>
    );
}

function DepartmentChart({ rows }) {
    const departments = [...new Set(rows.map((row) => row.department || "None"))].sort();

    const data = departments.map((department) => {
        const inDepartment = rows.filter((row) => (row.department || "None") === department);

        return {
            department,
            tier0: inDepartment.filter((row) => row.highest_tier === 0).length,
            tier1: inDepartment.filter((row) => row.highest_tier === 1).length,
        };
    });

    return (
        <ChartBox>
            <ResponsiveContainer>
                <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, left: 16, bottom: 0 }}>
                    <CartesianGrid {...GRID} horizontal={false} />
                    <XAxis type="number" allowDecimals={false} {...AXIS} />
                    <YAxis type="category" dataKey="department" {...AXIS} width={100} />
                    <Tooltip content={<ChartTooltip />} cursor={CURSOR} />
                    <Legend {...LEGEND} />
                    <Bar dataKey="tier0" name={TIER_LABELS[0]} stackId="tiers" fill={TIER_COLORS[0]} maxBarSize={16} />
                    <Bar dataKey="tier1" name={TIER_LABELS[1]} stackId="tiers" fill={TIER_COLORS[1]} maxBarSize={16}
                         radius={[0, 6, 6, 0]} />
                </BarChart>
            </ResponsiveContainer>
        </ChartBox>
    );
}

function PlatformDonut({ rows }) {
    const tier0Grants = rows.flatMap((row) => row.privileges).map(parsePrivilege).filter((item) => item.tier === "T0");
    const counts = countBy(tier0Grants, (item) => item.platform);

    const data = Object.entries(counts).map(([platform, value], index) => ({
        name: platformName(platform),
        value,
        color: PLATFORM_COLORS[index % PLATFORM_COLORS.length],
    }));

    return (
        <ChartBox>
            <div className="donut-center">
                <strong>{tier0Grants.length}</strong>
                <span>admin grants</span>
            </div>
            <ResponsiveContainer>
                <PieChart>
                    <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="86%"
                         paddingAngle={2} {...PIE_STROKE}>
                        {data.map((item) => <Cell key={item.name} fill={item.color} />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                    <Legend {...LEGEND} />
                </PieChart>
            </ResponsiveContainer>
        </ChartBox>
    );
}
