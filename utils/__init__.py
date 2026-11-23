"""
utils/__init__.py
-----------------
Dashboard UI helper functions: CSS injection, reusable HTML components
(KPI cards, severity pills, section headers), colour constants, and
a shared Plotly template.
"""

try:
    import pandas as pd
except ImportError:
    pd = None
try:
    import streamlit as st
except ImportError:
    st = None



# ── Colour constants ──────────────────────────────────────────────────────
NAVY = "#16223a"
GOLD = "#a9842c"
SLATE = "#3a5a78"
CRIT = "#9b2226"
HIGH = "#bb4d00"
MED = "#8a6d00"
LOW = "#2f5d3a"

SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"]
TIER_ORDER = ["Tier0", "Tier1", "Tier2"]

SEVERITY_COLORS = {
    "Critical": "#9b2226",
    "High": "#bb4d00",
    "Medium": "#8a6d00",
    "Low": "#2f5d3a",
}

TIER_COLORS = {
    "Tier0": "#9b2226",
    "Tier1": "#bb4d00",
    "Tier2": "#3a5a78",
}

PLOTLY_TEMPLATE = "plotly_white"


# ── CSS injection ─────────────────────────────────────────────────────────
def inject_base_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@600;700&family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"]  {
            font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
        }

        :root {
            --ink: #1c2733;
            --ink-soft: #4a5568;
            --hairline: #dfe3e8;
            --panel: #ffffff;
            --bg: #f4f5f7;
            --navy: #16223a;
            --navy-2: #1f3358;
            --gold: #a9842c;
        }

        .stApp { background: var(--bg); }

        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header[data-testid="stHeader"] {background: transparent;}

        section[data-testid="stSidebar"] {
            background: var(--navy);
            border-right: 1px solid #0d1626;
        }
        section[data-testid="stSidebar"] * { color: #e7ebf2 !important; }
        section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.12); }

        .block-container {
            padding-top: 1.6rem;
            padding-bottom: 3rem;
            max-width: 1280px;
        }

        .masthead {
            border-bottom: 2px solid var(--navy);
            padding-bottom: 0.85rem;
            margin-bottom: 1.6rem;
            display: flex;
            justify-content: space-between;
            align-items: baseline;
        }
        .masthead-title {
            font-family: 'Source Serif 4', serif;
            font-size: 1.85rem;
            font-weight: 700;
            color: var(--navy);
            letter-spacing: 0.2px;
            margin: 0;
        }
        .masthead-sub {
            color: var(--ink-soft);
            font-size: 0.92rem;
            margin-top: 0.15rem;
        }
        .masthead-meta {
            text-align: right;
            color: var(--ink-soft);
            font-size: 0.82rem;
            line-height: 1.5;
        }

        .section-head {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            margin: 1.7rem 0 0.7rem 0;
        }
        .section-head .bar {
            width: 4px;
            height: 1.15rem;
            background: var(--gold);
            display: inline-block;
            border-radius: 1px;
        }
        .section-head h3 {
            font-family: 'Source Serif 4', serif;
            font-size: 1.12rem;
            font-weight: 700;
            color: var(--navy);
            margin: 0;
        }
        .section-note {
            color: var(--ink-soft);
            font-size: 0.85rem;
            margin: -0.2rem 0 0.9rem 0.65rem;
        }

        .kpi-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 0.9rem;
            margin-bottom: 0.4rem;
        }
        .kpi-card {
            background: var(--panel);
            border: 1px solid var(--hairline);
            border-top: 3px solid var(--navy-2);
            border-radius: 6px;
            padding: 1.0rem 1.1rem 0.9rem 1.1rem;
            box-shadow: 0 1px 2px rgba(20,30,50,0.04);
        }
        .kpi-card.accent-critical { border-top-color: #9b2226; }
        .kpi-card.accent-high     { border-top-color: #bb4d00; }
        .kpi-card.accent-medium   { border-top-color: #8a6d00; }
        .kpi-card.accent-gold     { border-top-color: var(--gold); }
        .kpi-card.accent-green    { border-top-color: #2f5d3a; }

        .kpi-label {
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--ink-soft);
            font-weight: 600;
            margin-bottom: 0.35rem;
        }
        .kpi-value {
            font-family: 'Source Serif 4', serif;
            font-size: 1.95rem;
            font-weight: 700;
            color: var(--ink);
            line-height: 1.1;
        }
        .kpi-foot {
            font-size: 0.78rem;
            color: var(--ink-soft);
            margin-top: 0.3rem;
        }

        .pill {
            display: inline-block;
            padding: 0.15rem 0.55rem;
            border-radius: 3px;
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            color: #ffffff;
        }

        .panel {
            background: var(--panel);
            border: 1px solid var(--hairline);
            border-radius: 6px;
            padding: 1.1rem 1.2rem;
            margin-bottom: 1.1rem;
        }

        .footnote {
            color: var(--ink-soft);
            font-size: 0.78rem;
            border-top: 1px solid var(--hairline);
            padding-top: 0.7rem;
            margin-top: 2.2rem;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--hairline);
            border-radius: 6px;
        }

        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--hairline);
            border-radius: 6px;
            padding: 0.8rem 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Layout components ─────────────────────────────────────────────────────
def masthead(page_label: str):
    st.markdown(
        f"""
        <div class="masthead">
            <div>
                <p class="masthead-title">Identity Risk & Threat Analytics</p>
                <p class="masthead-sub">Cross-Platform Privilege, Dormancy & Damage Intelligence &nbsp;·&nbsp; {page_label}</p>
            </div>
            <div class="masthead-meta">
                Platforms monitored: AD &middot; AWS IAM &middot; Okta<br>
                Snapshot date: 20 Jun 2026
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_head(title: str, note: str = ""):
    st.markdown(
        f"""
        <div class="section-head"><span class="bar"></span><h3>{title}</h3></div>
        {f'<p class="section-note">{note}</p>' if note else ''}
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label, value, foot="", accent="navy"):
    accent_class = f"accent-{accent}" if accent != "navy" else ""
    return f"""
        <div class="kpi-card {accent_class}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-foot">{foot}</div>
        </div>
    """


def kpi_row(cards_html: list):
    st.markdown(f'<div class="kpi-row">{"".join(cards_html)}</div>', unsafe_allow_html=True)


def severity_pill(sev: str) -> str:
    color = SEVERITY_COLORS.get(sev, "#4a5568")
    return f'<span class="pill" style="background:{color}">{sev.upper()}</span>'


def tier_pill(tier: str) -> str:
    color = TIER_COLORS.get(tier, "#4a5568")
    return f'<span class="pill" style="background:{color}">{tier}</span>'


def render_html_table(df: pd.DataFrame, pill_cols=None, max_rows=None):
    """Render a DataFrame as a classic bordered HTML table with optional pill columns."""
    pill_cols = pill_cols or {}
    d = df.copy()
    if max_rows:
        d = d.head(max_rows)

    headers = "".join(f"<th>{c.replace('_', ' ').title()}</th>" for c in d.columns)
    rows_html = ""
    for _, r in d.iterrows():
        cells = []
        for c in d.columns:
            val = r[c]
            if c in pill_cols:
                val = pill_cols[c](val)
            cells.append(f"<td>{val}</td>")
        rows_html += f"<tr>{''.join(cells)}</tr>"

    table_html = f"""
    <style>
        .classic-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.86rem;
        }}
        .classic-table th {{
            text-align: left;
            background: #f0f2f5;
            color: #1c2733;
            font-weight: 700;
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 0.55rem 0.7rem;
            border-bottom: 2px solid #16223a;
        }}
        .classic-table td {{
            padding: 0.5rem 0.7rem;
            border-bottom: 1px solid #e4e7eb;
            color: #2a333d;
        }}
        .classic-table tr:hover td {{
            background: #f7f8fa;
        }}
    </style>
    <table class="classic-table">
        <thead><tr>{headers}</tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)