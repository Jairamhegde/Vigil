// Raw data browser: the JSON exports exactly as Vigil reads them, one dataset at a time.

import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Database, FileJson } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Badge, Empty, PageError, PageSkeleton, Panel, SearchBox } from "../components/ui";
import { useApi } from "../lib/data";
import { formatNumber } from "../lib/format";

const PAGE_SIZE = 50;

function formatBytes(bytes) {
    if (bytes == null) return "";
    if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function valueAt(record, path) {
    return path.split(".").reduce((value, key) => (value == null ? undefined : value[key]), record);
}

// Short label for an object inside a list (Okta groups, MFA factors, admin roles...)
function itemLabel(item) {
    if (item == null || typeof item !== "object") return String(item);
    return item.name || item.label || item.type || item.factorType || item.appLabel || item.id || "{…}";
}

function Cell({ value }) {
    if (value === null || value === undefined || value === "") {
        return <span className="muted">—</span>;
    }

    if (typeof value === "boolean") {
        return <Badge kind={value ? "low" : "neutral"}>{String(value)}</Badge>;
    }

    if (Array.isArray(value)) {
        if (!value.length) return <span className="muted">none</span>;

        const labels = value.map(itemLabel);
        // AD lists hold distinguished names: CN=Domain Admins,OU=... -> Domain Admins
        const short = labels.map((label) => (label.startsWith("CN=") ? label.slice(3).split(",")[0] : label));

        return (
            <div className="chips">
                {short.slice(0, 3).map((label, index) => <span key={index} className="chip" title={labels[index]}>{label}</span>)}
                {short.length > 3 && <span className="chip muted">+{short.length - 3}</span>}
            </div>
        );
    }

    if (typeof value === "object") {
        const text = JSON.stringify(value);
        return <span className="mono raw-object" title={text}>{text.length > 60 ? text.slice(0, 60) + "…" : text}</span>;
    }

    return <span className="raw-text" title={String(value)}>{String(value)}</span>;
}

export default function RawDataPage() {
    const datasets = useApi("/api/raw");
    const [active, setActive] = useState("hr_identities");
    const [input, setInput] = useState("");
    const [search, setSearch] = useState("");
    const [offset, setOffset] = useState(0);
    const [expanded, setExpanded] = useState(null);

    // Wait for typing to pause before searching (CloudTrail has 12k records)
    useEffect(() => {
        const timer = setTimeout(() => setSearch(input.trim()), 300);
        return () => clearTimeout(timer);
    }, [input]);

    useEffect(() => {
        setOffset(0);
        setExpanded(null);
    }, [active, search]);

    const query = new URLSearchParams({ search, offset: String(offset), limit: String(PAGE_SIZE) });
    const page = useApi(`/api/raw/${active}?${query}`);

    if (datasets.error) {
        return <PageError error={datasets.error} />;
    }

    if (!datasets.data) {
        return <PageSkeleton />;
    }

    const sources = [...new Set(datasets.data.map((item) => item.source))];
    const totalRecords = datasets.data.reduce((sum, item) => sum + item.records, 0);
    const files = [...new Set(datasets.data.filter((item) => item.file).map((item) => item.file))];
    const data = page.data;

    return (
        <>
            <div className="raw-summary">
                <Database size={16} />
                <span><b>{files.length}</b> export files · <b>{datasets.data.length}</b> datasets · <b>{formatNumber(totalRecords)}</b> records</span>
                <span className="muted">Read-only. This is the input Vigil matches, scores and shows on the other pages.</span>
            </div>

            <div className="raw-sources">
                {sources.map((source) => (
                    <div key={source} className="raw-source">
                        <div className="raw-source-name">{source}</div>
                        <div className="raw-datasets">
                            {datasets.data.filter((item) => item.source === source).map((item) => (
                                <button key={item.id} className={item.id === active ? "raw-dataset active" : "raw-dataset"}
                                        onClick={() => setActive(item.id)}>
                                    <span>{item.label}</span>
                                    <small>{formatNumber(item.records)}</small>
                                </button>
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            <Panel
                title={data ? `${data.source} · ${data.label}` : "Loading…"}
                subtitle={data && data.description}
                flush
                actions={<div className="toolbar"><SearchBox value={input} onChange={setInput} placeholder="Search any field" /></div>}
            >
                {data && (
                    <div className="raw-meta">
                        <span><FileJson size={14} /> <span className="mono">{data.file}</span></span>
                        {datasets.data.find((item) => item.id === active)?.size_bytes != null && (
                            <span>{formatBytes(datasets.data.find((item) => item.id === active).size_bytes)}</span>
                        )}
                        {data.meta && Object.entries(data.meta)
                            .filter(([, value]) => typeof value !== "object")
                            .slice(0, 4)
                            .map(([key, value]) => <span key={key}><b>{key}</b> {String(value)}</span>)}
                    </div>
                )}

                {page.error && <Empty>{page.error.message}</Empty>}
                {!data && !page.error && <div className="skeleton" style={{ minHeight: 240, margin: 16 }} />}

                {data && (data.records.length ? (
                    <div className={page.loading ? "table-wrap loading" : "table-wrap"}>
                        <table className="raw-table">
                            <thead>
                                <tr>
                                    <th style={{ width: 32 }} />
                                    <th>#</th>
                                    {data.columns.map((column) => <th key={column}>{column}</th>)}
                                </tr>
                            </thead>
                            <tbody>
                                {data.records.map((record, index) => {
                                    const number = data.offset + index;
                                    const open = expanded === number;

                                    return (
                                        <Fragment key={number}>
                                            <tr className={open ? "raw-row open" : "raw-row"} onClick={() => setExpanded(open ? null : number)}>
                                                <td>{open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</td>
                                                <td className="mono muted">{number + 1}</td>
                                                {data.columns.map((column) => <td key={column}><Cell value={valueAt(record, column)} /></td>)}
                                            </tr>
                                            {open && (
                                                <tr className="raw-detail">
                                                    <td colSpan={data.columns.length + 2}>
                                                        <pre>{JSON.stringify(record, null, 2)}</pre>
                                                    </td>
                                                </tr>
                                            )}
                                        </Fragment>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <Empty>{search ? `No records match "${search}".` : "This dataset is empty."}</Empty>
                ))}

                {data && data.matched > 0 && (
                    <div className="raw-pager">
                        <span className="muted">
                            {formatNumber(data.offset + 1)}–{formatNumber(Math.min(data.offset + PAGE_SIZE, data.matched))} of {formatNumber(data.matched)}
                            {search && ` matching (${formatNumber(data.total)} total)`} · click a row for the full record
                        </span>
                        <div className="toolbar">
                            <button className="btn btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                                <ChevronLeft size={14} /> Previous
                            </button>
                            <button className="btn btn-sm" disabled={offset + PAGE_SIZE >= data.matched}
                                    onClick={() => setOffset(offset + PAGE_SIZE)}>
                                Next <ChevronRight size={14} />
                            </button>
                        </div>
                    </div>
                )}
            </Panel>
        </>
    );
}
