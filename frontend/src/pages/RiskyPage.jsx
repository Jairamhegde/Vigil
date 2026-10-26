import { Activity, Ghost, Layers, TriangleAlert } from "lucide-react";
import { useState } from "react";
import {
    Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import {
    Badge, ChartBox, Empty, HrBadge, KpiCard, PageError, PageSkeleton, Panel, Person, ReasonList, ScoreBar, SearchBox,
} from "../components/ui";
import { AXIS, CURSOR, GRID, LEGEND } from "../lib/charts";
import { useApi } from "../lib/data";
import { BANDS, COLORS, matchesSearch, prettySignal, riskBand, splitReason } from "../lib/format";

export default function RiskyPage() {
    const risky = useApi("/api/identities/risky");
    const everyone = useApi("/api/identities/risky?include_all=true");
    const [search, setSearch] = useState("");

    const error = risky.error || everyone.error;

    if (error) {
        return <PageError error={error} />;
    }

    if (!risky.data || !everyone.data) {
        return <PageSkeleton />;
    }

    const rows = risky.data;
    const critical = rows.filter((row) => row.risk_score >= 70).length;
    const ghosts = rows.filter((row) => row.is_ghost).length;
    const avgDamage = rows.length ? Math.round(rows.reduce((sum, row) => sum + row.damage_score, 0) / rows.length) : 0;
    const filtered = rows.filter((row) => matchesSearch(row, search));

    return (
        <>
            <div className="kpi-grid">
                <KpiCard label="Risky identities" value={rows.length} color={COLORS.critical} icon={TriangleAlert}
                         note={`of ${everyone.data.length} scored identities`} />
                <KpiCard label="Critical" value={critical} color={COLORS.critical} icon={Activity}
                         note="Risk score 70 or higher" />
                <KpiCard label="Average damage" value={avgDamage} color={COLORS.high} icon={Layers}
                         note="Blast radius of the risky group (0-100)" />
                <KpiCard label="Ghosts among them" value={ghosts} color={COLORS.medium} icon={Ghost}
                         note="Terminated but still enabled" />
            </div>

            <div className="grid-2">
                <Panel title="Risk vs. damage" subtitle="Every identity. Top right = likely to be misused and costly if it is. Large dots are ghosts">
                    <RiskScatter rows={everyone.data} />
                </Panel>
                <Panel title="What makes them risky" subtitle="How often each signal appears among risky identities">
                    <SignalChart rows={rows} />
                </Panel>
            </div>

            <Panel title="Risky identities" subtitle="Sorted by risk score" flush
                   actions={<div className="toolbar"><SearchBox value={search} onChange={setSearch} /></div>}>
                {filtered.length ? (
                    <div className="table-wrap">
                        <table>
                            <thead>
                                <tr><th>Identity</th><th>HR status</th><th>Risk</th><th>Damage</th><th>Flags</th><th>Why</th></tr>
                            </thead>
                            <tbody>
                                {filtered.map((row) => <RiskyRow key={row.employee_id} row={row} />)}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <Empty>No identities match your search.</Empty>
                )}
            </Panel>
        </>
    );
}

function RiskyRow({ row }) {
    const band = riskBand(row.risk_score);

    return (
        <tr>
            <td><Person row={row} /></td>
            <td><HrBadge status={row.hr_status} /></td>
            <td><ScoreBar score={row.risk_score} label="risk" /></td>
            <td><ScoreBar score={row.damage_score} label="damage" /></td>
            <td>
                <div className="chips">
                    {row.is_ghost === 1 && <Badge kind="critical">Ghost</Badge>}
                    {row.is_dormant === 1 && <Badge kind="medium">Dormant</Badge>}
                    <Badge kind={band.css}>{band.name}</Badge>
                </div>
            </td>
            <td><ReasonList reasons={row.reasons} /></td>
        </tr>
    );
}

function RiskScatter({ rows }) {
    return (
        <ChartBox tall>
            <ResponsiveContainer>
                <ScatterChart margin={{ top: 8, right: 16, left: -8, bottom: 8 }}>
                    <CartesianGrid {...GRID} />
                    <XAxis type="number" dataKey="damage_score" name="Damage" domain={[0, 100]} {...AXIS}
                           label={{ value: "Damage score", position: "insideBottom", offset: -4, fill: COLORS.text, fontSize: 12 }} />
                    <YAxis type="number" dataKey="risk_score" name="Risk" domain={[0, 100]} {...AXIS} />
                    <ZAxis type="number" dataKey="size" range={[40, 220]} />
                    <Tooltip content={<ScatterTooltip />} cursor={{ strokeDasharray: "3 3", stroke: COLORS.grid }} />
                    <Legend {...LEGEND} />
                    {BANDS.map((band) => (
                        <Scatter key={band.name} name={band.name} fill={band.color} fillOpacity={0.75}
                                 data={rows.filter((row) => riskBand(row.risk_score).name === band.name)
                                           .map((row) => ({ ...row, size: row.is_ghost ? 3 : 1 }))} />
                    ))}
                </ScatterChart>
            </ResponsiveContainer>
        </ChartBox>
    );
}

function ScatterTooltip({ active, payload }) {
    if (!active || !payload || !payload.length) {
        return null;
    }

    const row = payload[0].payload;

    return (
        <div className="chart-tooltip">
            <div className="chart-tooltip-title">{row.full_name}</div>
            <div className="chart-tooltip-row"><span>Risk</span><b>{row.risk_score}</b></div>
            <div className="chart-tooltip-row"><span>Damage</span><b>{row.damage_score}</b></div>
            <div className="chart-tooltip-row"><span>{row.department}</span><b>{row.hr_status}</b></div>
        </div>
    );
}

function SignalChart({ rows }) {
    const counts = {};

    rows.forEach((row) => {
        row.reasons.forEach((reason) => {
            const { signal } = splitReason(reason);

            if (signal !== "privileges") {
                counts[signal] = (counts[signal] || 0) + 1;
            }
        });
    });

    const data = Object.entries(counts)
        .map(([signal, count]) => ({ signal: prettySignal(signal), count }))
        .sort((a, b) => b.count - a.count);

    return (
        <ChartBox tall>
            <ResponsiveContainer>
                <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 24, bottom: 0 }}>
                    <CartesianGrid {...GRID} horizontal={false} />
                    <XAxis type="number" allowDecimals={false} {...AXIS} />
                    <YAxis type="category" dataKey="signal" {...AXIS} width={170} />
                    <Tooltip content={<CountTooltip />} cursor={CURSOR} />
                    <Bar dataKey="count" name="Identities" fill={COLORS.accent} radius={[0, 6, 6, 0]} maxBarSize={18} />
                </BarChart>
            </ResponsiveContainer>
        </ChartBox>
    );
}

function CountTooltip({ active, payload, label }) {
    if (!active || !payload || !payload.length) {
        return null;
    }

    return (
        <div className="chart-tooltip">
            <div className="chart-tooltip-title">{label}</div>
            <div className="chart-tooltip-row"><span>Identities</span><b>{payload[0].value}</b></div>
        </div>
    );
}
