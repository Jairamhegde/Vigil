import { Activity, Cloud, Layers, Moon } from "lucide-react";
import { useState } from "react";
import {
    Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
    Badge, ChartBox, ChartTooltip, Empty, HrBadge, KpiCard, PageError, PageSkeleton, Panel, Person, SearchBox, Segmented,
} from "../components/ui";
import { AXIS, CURSOR, GRID, LEGEND, PIE_STROKE } from "../lib/charts";
import { useApi } from "../lib/data";
import { COLORS, PLATFORM_COLORS, countBy, formatDate, formatNumber, matchesSearch, platformName } from "../lib/format";

const DAY_OPTIONS = [
    { value: 30, label: "30 days" },
    { value: 60, label: "60 days" },
    { value: 90, label: "90 days" },
];

export default function DormantPage() {
    const [days, setDays] = useState(30);
    const [search, setSearch] = useState("");

    const crossPlatform = useApi("/api/identities/dormant/cross-platform");
    const inactive = useApi(`/api/identities/dormant/inactive?days=${days}`);

    const error = crossPlatform.error || inactive.error;

    if (error) {
        return <PageError error={error} />;
    }

    if (!crossPlatform.data || !inactive.data) {
        return <PageSkeleton />;
    }

    const leavers = crossPlatform.data;
    const rows = inactive.data;
    const eventsAfterExit = leavers.reduce((sum, row) => sum + row.events_after_inactive, 0);
    const unusedAccounts = rows.reduce((sum, row) => sum + row.stale_accounts, 0);
    const fullyInactive = rows.filter((row) => row.fully_inactive).length;
    const filtered = rows.filter((row) => matchesSearch(row, search));

    return (
        <>
            <div className="kpi-grid">
                <KpiCard label="Active after leaving" value={leavers.length} color={COLORS.critical} icon={Cloud}
                         note="Not active in HR or AD, still active in cloud" />
                <KpiCard label="Events after exit" value={formatNumber(eventsAfterExit)} color={COLORS.high} icon={Activity}
                         note="Cloud events after the leave / termination date" />
                <KpiCard label="Dormant access" value={rows.length} color={COLORS.medium} icon={Moon}
                         note={`Identities with an account unused for ${days}+ days`} />
                <KpiCard label="Unused accounts" value={unusedAccounts} color={COLORS.accent} icon={Layers}
                         note={`${fullyInactive} ${fullyInactive === 1 ? "identity" : "identities"} inactive on every platform`} />
            </div>

            <Panel title="Still active in the cloud after leaving"
                   subtitle="Terminated or on leave in HR, or no enabled AD account, yet AWS / Azure recorded activity afterwards">
                {leavers.length ? (
                    <div className="alert-grid">
                        {leavers.map((row) => <LeaverCard key={row.employee_id} row={row} />)}
                    </div>
                ) : (
                    <Empty>No identity is active in the cloud after leaving.</Empty>
                )}
            </Panel>

            <div className="grid-2" style={{ marginTop: 20 }}>
                <Panel title="Unused accounts by platform" subtitle={`Enabled accounts with no sign-in for ${days}+ days`}>
                    <PlatformChart rows={rows} />
                </Panel>
                <Panel title="How long unused" subtitle="Longest gap per identity">
                    <AgeDonut rows={rows} days={days} />
                </Panel>
            </div>

            <Panel title="Dormant access" subtitle="Active employees holding accounts they no longer use" flush
                   actions={
                       <div className="toolbar">
                           <SearchBox value={search} onChange={setSearch} />
                           <Segmented options={DAY_OPTIONS} value={days} onChange={setDays} label="Inactive for" />
                       </div>
                   }>
                {filtered.length ? (
                    <div className="table-wrap">
                        <table>
                            <thead>
                                <tr><th>Identity</th><th>Role</th><th>Unused accounts</th><th>Longest unused</th><th>Last activity anywhere</th></tr>
                            </thead>
                            <tbody>
                                {filtered.map((row) => <DormantRow key={row.employee_id} row={row} />)}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <Empty>No dormant access found.</Empty>
                )}
            </Panel>
        </>
    );
}

function LeaverCard({ row }) {
    return (
        <article className="alert-card">
            <Person row={row} />

            <div className="alert-stats">
                <div className="alert-stat">
                    <strong>{formatNumber(row.events_after_inactive)}</strong>
                    <span>events after</span>
                </div>
                <div className="alert-stat">
                    <strong>{formatNumber(row.sensitive_events)}</strong>
                    <span>sensitive</span>
                </div>
                <div className="alert-stat">
                    <strong>{row.cloud_platforms.map(platformName).join(", ")}</strong>
                    <span>platform</span>
                </div>
            </div>

            <div className="chips" style={{ marginBottom: 10 }}>
                <HrBadge status={row.hr_status} />
                <Badge kind={row.ad_status === "enabled" ? "high" : "neutral"}>AD {row.ad_status}</Badge>
            </div>

            <div className="alert-foot">
                Inactive since <b>{formatDate(row.inactive_since)}</b> · last cloud event <b>{formatDate(row.last_event)}</b>
            </div>
        </article>
    );
}

function DormantRow({ row }) {
    let longest;

    if (row.never_used) {
        longest = <Badge kind="neutral">Never used</Badge>;
    } else {
        const kind = row.max_days_unused > 180 ? "critical" : row.max_days_unused > 90 ? "high" : "medium";
        longest = <Badge kind={kind}>{row.max_days_unused} days</Badge>;
    }

    return (
        <tr>
            <td><Person row={row} /></td>
            <td className="muted">{row.role_title || "—"}</td>
            <td>
                <div className="chips">
                    {row.stale_detail.map((detail) => <span key={detail} className="chip">{detail}</span>)}
                    {row.fully_inactive === 1 && <Badge kind="critical">Inactive everywhere</Badge>}
                </div>
            </td>
            <td>{longest}</td>
            <td className="mono">{formatDate(row.last_activity)}</td>
        </tr>
    );
}

function PlatformChart({ rows }) {
    const details = rows.flatMap((row) => row.stale_detail);
    const counts = countBy(details, (detail) => detail.split(":")[0]);
    const data = Object.entries(counts).map(([platform, count]) => ({ platform: platformName(platform), count }));

    return (
        <ChartBox>
            <ResponsiveContainer>
                <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
                    <CartesianGrid {...GRID} vertical={false} />
                    <XAxis dataKey="platform" {...AXIS} />
                    <YAxis allowDecimals={false} {...AXIS} />
                    <Tooltip content={<ChartTooltip />} cursor={CURSOR} />
                    <Bar dataKey="count" name="Unused accounts" radius={[8, 8, 0, 0]} maxBarSize={56}>
                        {data.map((item, index) => <Cell key={item.platform} fill={PLATFORM_COLORS[index % PLATFORM_COLORS.length]} />)}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </ChartBox>
    );
}

function AgeDonut({ rows, days }) {
    const buckets = [
        { name: `${days}-90 days`, color: COLORS.medium, test: (row) => !row.never_used && row.max_days_unused <= 90 },
        { name: "90-180 days", color: COLORS.high, test: (row) => !row.never_used && row.max_days_unused > 90 && row.max_days_unused <= 180 },
        { name: "180+ days", color: COLORS.critical, test: (row) => !row.never_used && row.max_days_unused > 180 },
        { name: "Never used", color: COLORS.slate, test: (row) => row.never_used },
    ];

    const data = buckets
        .map((bucket) => ({ name: bucket.name, color: bucket.color, value: rows.filter(bucket.test).length }))
        .filter((item) => item.value > 0);

    return (
        <ChartBox>
            <div className="donut-center">
                <strong>{rows.length}</strong>
                <span>identities</span>
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
