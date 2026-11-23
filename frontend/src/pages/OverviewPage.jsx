import { Activity, Cloud, Ghost, KeyRound, Moon, TriangleAlert, Users, XCircle } from "lucide-react";
import {
    Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart,
    ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
    ChartBox, ChartTooltip, Empty, HrBadge, KpiCard, PageError, PageSkeleton, Panel, Person, ScoreBar,
} from "../components/ui";
import { AXIS, CURSOR, GRID, LEGEND, PIE_STROKE } from "../lib/charts";
import { useApi } from "../lib/data";
import { BANDS, COLORS, formatDate, formatNumber, platformName, prettySignal, TIER_COLORS, TIER_LABELS } from "../lib/format";

export default function OverviewPage() {
    const summary = useApi("/api/summary");
    const charts = useApi("/api/charts");
    const risky = useApi("/api/identities/risky");

    const error = summary.error || charts.error || risky.error;

    if (error) {
        return <PageError error={error} />;
    }

    if (!summary.data || !charts.data || !risky.data) {
        return <PageSkeleton />;
    }

    const s = summary.data;

    return (
        <>
            <div className="kpi-grid">
                <KpiCard label="Total identities" value={formatNumber(s.total_identities)} color={COLORS.accent} icon={Users}
                         note={`${s.active_identities} active in HR · ${s.total_accounts} accounts`} />
                <KpiCard label="Risky identities" value={s.risky_identities} color={COLORS.critical} icon={TriangleAlert}
                         note="Risk score 40 or higher" />
                <KpiCard label="Ghost identities" value={s.ghost_identities} color={COLORS.high} icon={Ghost}
                         note="Terminated, account still enabled" />
                <KpiCard label="Dormant access" value={s.inactive_identities} color={COLORS.medium} icon={Moon}
                         note={`${s.fully_inactive_identities} inactive on every platform`} />
                <KpiCard label="Active after leaving" value={s.cross_platform_dormant} color={COLORS.critical} icon={Cloud}
                         note="Cloud activity after HR / AD exit" />
                <KpiCard label="Tier 0 holders" value={s.tier0_identities} color={COLORS.high} icon={KeyRound}
                         note={`${s.tier1_identities} more hold Tier 1`} />
                <KpiCard label="Sensitive actions" value={formatNumber(s.sensitive_events)} color={COLORS.light} icon={Activity}
                         note={`of ${formatNumber(s.total_events)} events`} />
                <KpiCard label="Failed calls" value={formatNumber(s.failed_events)} color={COLORS.grey} icon={XCircle}
                         note={`${s.unowned_accounts} accounts have no HR owner`} />
            </div>

            <div className="grid-3-1">
                <Panel title="Activity timeline" subtitle="Weekly events across cloud platforms">
                    <TimelineChart rows={charts.data.event_timeline} />
                </Panel>
                <Panel title="Risk distribution" subtitle="Identities by risk band">
                    <RiskDonut rows={charts.data.risk_distribution} />
                </Panel>
            </div>

            <div className="grid-2">
                <Panel title="Privilege tiers by platform" subtitle="Enabled grants, after resolving nested groups">
                    <TierChart rows={charts.data.tier_distribution} />
                </Panel>
                <Panel title="Risk by department" subtitle="Average risk score and risky identities">
                    <DepartmentChart rows={charts.data.department_risk} />
                </Panel>
            </div>

            <Panel title="Highest-risk identities" subtitle="Open Risky identities for the full list" flush
                   actions={<a className="btn" href="#/risky">View all</a>}>
                <TopRiskList rows={risky.data.slice(0, 5)} />
            </Panel>
        </>
    );
}

function TimelineChart({ rows }) {
    return (
        <ChartBox>
            <ResponsiveContainer>
                <ComposedChart data={rows} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
                    <defs>
                        <linearGradient id="timelineFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={COLORS.accent} stopOpacity={0.28} />
                            <stop offset="100%" stopColor={COLORS.accent} stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid {...GRID} vertical={false} />
                    <XAxis dataKey="week_start" {...AXIS} tickFormatter={formatDate} minTickGap={40} />
                    <YAxis yAxisId="all" {...AXIS} />
                    <YAxis yAxisId="small" orientation="right" {...AXIS} />
                    <Tooltip content={<ChartTooltip labelFormatter={formatDate} />} />
                    <Legend {...LEGEND} />
                    <Area yAxisId="all" type="monotone" dataKey="total" name="All events"
                          stroke={COLORS.accent} strokeWidth={2} fill="url(#timelineFill)" />
                    <Line yAxisId="small" type="monotone" dataKey="sensitive" name="Sensitive"
                          stroke={COLORS.light} strokeWidth={1.5} dot={false} />
                    <Line yAxisId="small" type="monotone" dataKey="failed" name="Failed"
                          stroke={COLORS.critical} strokeWidth={1.5} dot={false} />
                </ComposedChart>
            </ResponsiveContainer>
        </ChartBox>
    );
}

export function RiskDonut({ rows }) {
    const data = BANDS.map((band) => ({
        name: band.name,
        value: (rows.find((row) => row.band === band.name) || {}).identities || 0,
        color: band.color,
    }));

    const total = data.reduce((sum, item) => sum + item.value, 0);

    return (
        <ChartBox>
            <div className="donut-center">
                <strong>{total}</strong>
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

function TierChart({ rows }) {
    const platforms = [...new Set(rows.map((row) => row.platform))];

    const data = platforms.map((platform) => {
        const item = { platform: platformName(platform) };

        [0, 1, 2].forEach((tier) => {
            item[`tier${tier}`] = (rows.find((row) => row.platform === platform && row.tier === tier) || {}).grants || 0;
        });

        return item;
    });

    return (
        <ChartBox>
            <ResponsiveContainer>
                <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
                    <CartesianGrid {...GRID} vertical={false} />
                    <XAxis dataKey="platform" {...AXIS} />
                    <YAxis {...AXIS} />
                    <Tooltip content={<ChartTooltip />} cursor={CURSOR} />
                    <Legend {...LEGEND} />
                    {[0, 1, 2].map((tier) => (
                        <Bar key={tier} dataKey={`tier${tier}`} name={TIER_LABELS[tier]} stackId="tiers"
                             fill={TIER_COLORS[tier]} maxBarSize={46} radius={tier === 2 ? [6, 6, 0, 0] : 0} />
                    ))}
                </BarChart>
            </ResponsiveContainer>
        </ChartBox>
    );
}

function DepartmentChart({ rows }) {
    const data = rows.map((row) => ({ ...row, department: row.department || "None" }));

    return (
        <ChartBox>
            <ResponsiveContainer>
                <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, left: 16, bottom: 0 }}>
                    <CartesianGrid {...GRID} horizontal={false} />
                    <XAxis type="number" {...AXIS} />
                    <YAxis type="category" dataKey="department" {...AXIS} width={100} />
                    <Tooltip content={<ChartTooltip />} cursor={CURSOR} />
                    <Legend {...LEGEND} />
                    <Bar dataKey="avg_risk" name="Average risk" fill={COLORS.accent} radius={[0, 6, 6, 0]} maxBarSize={14} />
                    <Bar dataKey="risky" name="Risky identities" fill={COLORS.critical} radius={[0, 6, 6, 0]} maxBarSize={14} />
                </BarChart>
            </ResponsiveContainer>
        </ChartBox>
    );
}

function TopRiskList({ rows }) {
    if (!rows.length) {
        return <Empty>No risky identities right now.</Empty>;
    }

    return (
        <div className="top-list">
            {rows.map((row) => {
                const firstSignal = row.reasons.find((reason) => !reason.startsWith("privileges")) || "";

                return (
                    <div key={row.employee_id} className="top-item">
                        <Person row={row} />
                        <div className="top-reason">{prettySignal(firstSignal.split(":")[0])}</div>
                        <HrBadge status={row.hr_status} />
                        <ScoreBar score={row.risk_score} label="risk" />
                    </div>
                );
            })}
        </div>
    );
}
