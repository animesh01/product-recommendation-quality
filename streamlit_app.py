"""Product Set Relevance (PSR) — a plain-language relevance report for an AI shopping assistant.

PSR grades each product in the assistant's carousel from 0 to 3 against what the customer
asked for, averages that to a 0-100 score per carousel, tracks it week over week, and — when
it moves — explains why (which kinds of searches slipped, and which recent change likely caused it).

Written so anyone can follow it: plain wording, always-visible definitions, numbers explained in
counts, labeled charts, and a one-click leadership summary. Runs out of the box — no API key, no setup.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from relevance_judge import get_judge

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# Dark theme palette (matches CQS)
BG = "#0f1715"
SURFACE = "#16211e"
SURFACE2 = "#1d2b27"
BORDER = "#2a3a35"
TEAL = "#3fd6ab"
TEAL_DEEP = "#0d766e"
INK = "#eaf2ef"
MUTED = "#90a39d"
AMBER = "#e0a23c"
RED = "#e26d6d"
BLUE = "#6aa3e0"
SAND = "#241f17"

st.set_page_config(page_title="PSR — Product Set Relevance", page_icon="🛒",
                   layout="wide", initial_sidebar_state="collapsed")

# What each grade means, in plain words
GRADE_PLAIN = {
    3: "Perfect — exactly what they asked for",
    2: "Good — fits the request",
    1: "Off — right area, but misses something they asked for",
    0: "Wrong — not what they wanted",
}

# Plain-language metric definitions (always shown, never hidden in a tooltip)
METRIC_DEFS = {
    "Relevance score": "Average product grade in a carousel (0–3), put on a 0–100 scale. Higher = the results matched the request better.",
    "Change this week": "How much the score moved versus last week, in points.",
    "Exact match": "How often the automated checker gave a product the very same grade a human did.",
    "Close enough": "How often the checker was within one grade of the human — the practical bar.",
    "Typical miss": "On average, how far the checker's grade was from the human's (0–3 scale).",
    "Move together": "Whether the checker's scores rise and fall in step with the human's.",
}

# Plain names for the search-intent categories
INTENT_PLAIN = {
    "product_discovery": "Browsing for a product",
    "pricing_constraint": "Has a budget limit",
    "dietary_constraint": "Has a dietary need",
    "gifting": "Shopping for a gift",
    "reorder": "Reordering something",
    "substitution": "Looking for a substitute",
}


def inject_styles() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
        .stApp {{ background:{BG}; }}
        html, body, [class*="css"] {{ font-family:"DM Sans",sans-serif; color:{INK}; }}
        h1,h2,h3,h4,h5 {{ font-family:"Manrope",sans-serif !important; letter-spacing:-0.02em; color:{INK} !important; }}
        p, span, div, label, li, td, th {{ color:{INK}; }}
        [data-testid="stCaptionContainer"], .stCaption {{ color:{MUTED} !important; }}
        .hero {{ border-radius:20px; padding:30px 34px; margin-bottom:18px; color:#fff;
            background:linear-gradient(135deg,#0b5f59 0%,#0f8a73 58%,#19c79f 100%);
            position:relative; overflow:hidden;
            box-shadow:0 0 0 1px rgba(63,214,171,0.18), 0 18px 50px -20px rgba(25,199,159,0.45); }}
        .hero h1 {{ color:#fff !important; font-size:2.05rem; margin:8px 0 6px; }}
        .hero p {{ color:#e7f6f1 !important; font-size:1.02rem; line-height:1.5; max-width:78%; margin:0; }}
        .hero .pill {{ display:inline-block; padding:4px 13px; border-radius:999px;
            background:rgba(255,255,255,0.18); color:#fff !important; font-size:0.74rem; font-weight:700;
            letter-spacing:0.06em; text-transform:uppercase; }}
        .hero .verdict {{ margin-top:16px; display:inline-block; background:#0c2a25; color:#fff;
            font-weight:800; font-family:Manrope; font-size:1.02rem; padding:9px 16px; border-radius:11px; }}
        .hero-art {{ position:absolute; right:-8px; bottom:-10px; opacity:0.9; }}
        .section-title {{ font-family:Manrope; font-weight:800; font-size:1.3rem; margin:8px 0 2px; }}
        .section-copy {{ color:{MUTED}; font-size:0.97rem; margin-bottom:14px; max-width:800px; line-height:1.5; }}
        .mcard {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:14px; padding:16px 18px; height:100%; }}
        .mcard .lbl {{ font-size:0.78rem; font-weight:700; color:{MUTED}; text-transform:uppercase; letter-spacing:0.04em; }}
        .mcard .val {{ font-family:Manrope; font-weight:800; font-size:1.9rem; line-height:1.1; margin:5px 0 5px; }}
        .mcard .def {{ font-size:0.79rem; color:{MUTED}; line-height:1.4; }}
        .takeaway {{ background:{SAND}; border-radius:12px; padding:13px 16px; font-size:0.96rem;
            line-height:1.55; margin:8px 0 6px; }}
        .takeaway b {{ font-family:Manrope; }}
        .tag {{ font-size:0.78rem; font-weight:700; padding:3px 10px; border-radius:999px; }}
        .tag-good {{ background:#13332b; color:{TEAL}; }}
        .tag-bad {{ background:#3a1d1d; color:{RED}; }}
        .tag-warn {{ background:#33280f; color:{AMBER}; }}
        .exec-card {{ background:{SURFACE}; border:2px solid {TEAL}; border-radius:18px; padding:24px 28px;
            box-shadow:0 6px 24px -12px rgba(63,214,171,0.4); }}
        .exec-card h2 {{ font-size:1.35rem; margin:0 0 4px; }}
        .exec-card .kpi {{ display:flex; gap:26px; flex-wrap:wrap; margin:14px 0 16px; }}
        .exec-card .kpi .n {{ font-family:Manrope; font-weight:800; font-size:1.5rem; }}
        .exec-card .kpi .l {{ font-size:0.76rem; color:{MUTED}; text-transform:uppercase; letter-spacing:0.04em; }}
        .exec-card ul {{ margin:8px 0 0; padding-left:20px; }}
        .exec-card li {{ margin:6px 0; line-height:1.5; }}
        .stTabs [data-baseweb="tab"] {{ color:{MUTED}; }}
        .stTabs [aria-selected="true"] {{ color:{INK}; }}
        .stButton button[kind="primary"] {{ background:{TEAL} !important; color:#06201a !important;
            border:none !important; font-weight:600 !important; }}
        .stButton button[kind="primary"]:hover {{ background:#5fe2bd !important; color:#06201a !important; }}
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background:{SURFACE} !important; border-color:{TEAL} !important; color:{INK} !important; }}
        [data-testid="stSelectbox"] svg {{ fill:{TEAL} !important; }}
        ul[role="listbox"], div[data-baseweb="popover"], div[data-baseweb="menu"] {{ background:{SURFACE} !important; }}
        li[role="option"] {{ background:{SURFACE} !important; color:{INK} !important; }}
        li[role="option"]:hover, li[role="option"][aria-selected="true"] {{ background:{SURFACE2} !important; color:{TEAL} !important; }}
        [data-testid="stExpander"] {{ border:1px solid {BORDER} !important; border-radius:10px; background:{SURFACE}; }}
        [data-testid="stExpander"] summary {{ color:{INK} !important; }}
        /* everything inside any expander stays readable on dark (inline colors still win) */
        [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{ background:{SURFACE} !important; }}
        [data-testid="stExpander"] p,
        [data-testid="stExpander"] li,
        [data-testid="stExpander"] strong {{ color:{INK}; }}
        [data-testid="stExpander"] [data-testid="stMarkdownContainer"],
        [data-testid="stExpander"] [data-testid="stMarkdownContainer"] * {{ color:{INK}; }}
        [data-testid="stExpander"] [data-testid="stCaptionContainer"],
        [data-testid="stExpander"] [data-testid="stCaptionContainer"] * {{ color:{MUTED} !important; }}
        [data-testid="stDataFrame"] {{ background:{SURFACE}; }}
        /* dataframe cells, headers, and grid lines on dark */
        [data-testid="stDataFrame"] div[role="gridcell"],
        [data-testid="stDataFrame"] div[role="columnheader"],
        [data-testid="stDataFrame"] [data-testid="StyledDataFrameDataCell"],
        [data-testid="stDataFrame"] [data-testid="StyledDataFrameHeaderCell"] {{
            background:{SURFACE} !important; color:{INK} !important;
            border-color:{BORDER} !important; }}
        [data-testid="stDataFrame"] [role="columnheader"] {{
            background:{SURFACE2} !important; color:{INK} !important; }}
        [data-testid="stDataFrame"] * {{ color:{INK} !important; }}
        .stDataFrame, .stDataFrame > div {{ background:{SURFACE} !important; }}
        /* code block (executive summary copy box) on dark */
        [data-testid="stCode"], .stCode {{ background:{SURFACE2} !important; }}
        [data-testid="stCode"] pre, .stCode pre {{
            background:{SURFACE2} !important; border:1px solid {BORDER} !important;
            border-radius:10px !important; }}
        [data-testid="stCode"] code, .stCode code,
        [data-testid="stCode"] pre *, .stCode pre * {{
            color:{INK} !important; background:transparent !important; }}
        [data-testid="stCode"] button {{ color:{TEAL} !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def esc(s) -> str:
    return html.escape(str(s))


def psr(grades) -> float:
    return sum(grades) / len(grades) / 3 * 100 if grades else 0.0


def mean(xs) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def pearson(xs, ys) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = mean(xs), mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (sx * sy) if sx and sy else float("nan")


@st.cache_data
def load_json(name: str):
    with open(DATA / name) as f:
        return json.load(f)


def metric_card(label: str, value: str, accent: str = INK) -> str:
    return (
        f"<div class='mcard'><div class='lbl'>{esc(label)}</div>"
        f"<div class='val' style='color:{accent}'>{esc(value)}</div>"
        f"<div class='def'>{esc(METRIC_DEFS.get(label, ''))}</div></div>"
    )


# --------------------------------------------------------------------------- #
# SVG line chart with value labels on every point
# --------------------------------------------------------------------------- #
def svg_line(points, fmt="{:.0f}", height=300, marker_last=True) -> str:
    """points: list of (label, value). Labels every point; last point highlighted."""
    W, H = 640, height
    pad_l, pad_r, pad_t, pad_b = 30, 24, 30, 46
    n = len(points)
    plot_w, plot_h = W - pad_l - pad_r, H - pad_t - pad_b
    vals = [v for _, v in points]
    vmin, vmax = min(vals), max(vals)
    span = (vmax - vmin) or 1
    vmin -= span * 0.25
    vmax += span * 0.22
    span = vmax - vmin

    def X(i):
        return pad_l + (i / (n - 1)) * plot_w if n > 1 else pad_l

    def Y(v):
        return pad_t + plot_h - ((v - vmin) / span) * plot_h

    out = ""
    poly = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(points))
    out += f"<polyline points='{poly}' fill='none' stroke='{TEAL}' stroke-width='3'/>"
    for i, (lab, v) in enumerate(points):
        last = i == n - 1
        col = AMBER if (last and marker_last) else TEAL
        rad = 6 if last else 4
        out += f"<circle cx='{X(i):.1f}' cy='{Y(v):.1f}' r='{rad}' fill='{col}'/>"
        out += (f"<text x='{X(i):.1f}' y='{Y(v) - 12:.1f}' text-anchor='middle' "
                f"font-family='Manrope' font-weight='800' font-size='13' fill='{col}'>{fmt.format(v)}</text>")
        out += (f"<text x='{X(i):.1f}' y='{H - 18:.1f}' text-anchor='middle' "
                f"font-size='11' fill='{MUTED}'>{esc(lab)}</text>")
    return (f"<svg viewBox='0 0 {W} {H}' width='100%' style='max-width:640px' "
            f"xmlns='http://www.w3.org/2000/svg' role='img'>{out}</svg>")


# --------------------------------------------------------------------------- #
# SVG horizontal bars (signed) with value labels — for the intent breakdown
# --------------------------------------------------------------------------- #
def svg_change_bars(items, height=None) -> str:
    """items: list of (label, change_value). Diverging bars around zero, labeled."""
    row_h = 38
    H = height or (len(items) * row_h + 30)
    W = 640
    label_w = 200
    zero_x = label_w + (W - label_w - 40) / 2
    half = (W - label_w - 40) / 2
    vmax = max((abs(v) for _, v in items), default=1) or 1
    out = f"<line x1='{zero_x}' y1='10' x2='{zero_x}' y2='{H - 20}' stroke='{BORDER}' stroke-width='1'/>"
    for i, (label, v) in enumerate(items):
        cy = 20 + i * row_h
        bw = abs(v) / vmax * half
        color = TEAL if v >= 0 else RED
        x = zero_x if v >= 0 else zero_x - bw
        out += (f"<text x='{label_w - 10}' y='{cy + 5:.1f}' text-anchor='end' font-size='12.5' "
                f"fill='{INK}'>{esc(label)}</text>")
        out += f"<rect x='{x:.1f}' y='{cy - 9:.1f}' width='{bw:.1f}' height='18' rx='4' fill='{color}'/>"
        lx = (x + bw + 6) if v >= 0 else (x - 6)
        anchor = "start" if v >= 0 else "end"
        out += (f"<text x='{lx:.1f}' y='{cy + 5:.1f}' text-anchor='{anchor}' font-family='Manrope' "
                f"font-weight='800' font-size='12.5' fill='{color}'>{v:+.0f}</text>")
    return (f"<svg viewBox='0 0 {W} {H}' width='100%' style='max-width:640px' "
            f"xmlns='http://www.w3.org/2000/svg' role='img'>{out}</svg>")


def grade_chip(g: int) -> str:
    if g >= 3:
        bg, fg = "#13332b", TEAL
    elif g == 2:
        bg, fg = "#13332b", TEAL
    elif g == 1:
        bg, fg = "#33280f", AMBER
    else:
        bg, fg = "#3a1d1d", RED
    return (f"<span style='display:inline-block;min-width:24px;text-align:center;padding:2px 7px;"
            f"border-radius:6px;font-weight:700;background:{bg};color:{fg}'>{g}</span>")


def score_color(v: float) -> str:
    return TEAL if v >= 70 else AMBER if v >= 60 else RED


def html_table(headers, rows) -> str:
    """Render a fully dark-themed HTML table (reliable where st.dataframe isn't)."""
    head = "".join(
        f"<th style='text-align:left;padding:9px 12px;font-size:0.78rem;text-transform:uppercase;"
        f"letter-spacing:0.03em;color:{MUTED};border-bottom:1px solid {BORDER};"
        f"background:{SURFACE2}'>{esc(h)}</th>" for h in headers
    )
    body = ""
    for row in rows:
        cells = "".join(
            f"<td style='padding:9px 12px;font-size:0.9rem;color:{INK};"
            f"border-bottom:1px solid {BORDER}'>{c}</td>" for c in row
        )
        body += f"<tr>{cells}</tr>"
    return (f"<table style='width:100%;border-collapse:collapse;background:{SURFACE};"
            f"border:1px solid {BORDER};border-radius:10px;overflow:hidden'>"
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


@st.cache_resource
def get_mock_judge():
    return get_judge(mock=True)


def grade_all(judge, carousels):
    rows, j_all, h_all = [], [], []
    for c in carousels:
        human = [p["human_grade"] for p in c["results"]]
        graded = judge.grade_set(c["query"], c["results"])
        jg = [g.grade for g in graded]
        j_all.extend(jg)
        h_all.extend(human)
        rows.append({"id": c["id"], "week": c["week"], "intent": c["intent"],
                     "query": c["query"], "psr_j": psr(jg), "psr_h": psr(human)})
    return rows, j_all, h_all


# --------------------------------------------------------------------------- #
inject_styles()
judge = get_mock_judge()
carousels = load_json("sample_carousels.json")
rows, j_all, h_all = grade_all(judge, carousels)

weeks = sorted({r["week"] for r in rows})
last, this = weeks[-2], weeks[-1]


def overall(week, key):
    return mean([r[key] for r in rows if r["week"] == week])


last_h, this_h = overall(last, "psr_h"), overall(this, "psr_h")
wow = this_h - last_h
moved_down = wow < 0

# ---- Hero ----------------------------------------------------------------- #
art = (
    "<svg class='hero-art' width='210' height='140' viewBox='0 0 210 140' fill='none'>"
    "<rect x='26' y='40' width='150' height='86' rx='10' fill='rgba(255,255,255,0.12)'/>"
    "<rect x='40' y='54' width='36' height='58' rx='6' fill='rgba(255,255,255,0.9)'/>"
    "<rect x='86' y='54' width='36' height='58' rx='6' fill='rgba(255,255,255,0.55)'/>"
    "<rect x='132' y='54' width='36' height='58' rx='6' fill='rgba(255,255,255,0.3)'/>"
    "<path d='M44 70 l7 7 l13 -15' stroke='#0d766e' stroke-width='4' fill='none' "
    "stroke-linecap='round' stroke-linejoin='round'/></svg>"
)
st.markdown(
    f"""
    <div class="hero">
      {art}
      <span class="pill">Search relevance report · plain-language</span>
      <h1>Product Set Relevance</h1>
      <p>Every time the AI shopping assistant shows a row of products, we check how well those
      products actually match what the customer asked for — then track it weekly and explain any change.</p>
      <div class="verdict" style="color:{RED if moved_down else TEAL}">
      This week: relevance {'dropped' if moved_down else 'rose'} {abs(wow):.0f} points ({last_h:.0f} → {this_h:.0f})</div>
    </div>
    """,
    unsafe_allow_html=True,
)

trend_tab, cause_tab, trust_tab, try_tab = st.tabs(
    ["📈 The trend", "🔍 Why it moved", "🎯 Can we trust the checker", "🧪 Try it yourself"]
)

# ============================ THE TREND ==================================== #
with trend_tab:
    st.markdown('<div class="section-title">How relevance is doing</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-copy">Each box answers a plain question, with its definition '
                'right underneath.</div>', unsafe_allow_html=True)

    m = st.columns(3)
    m[0].markdown(metric_card("Relevance score", f"{this_h:.0f} / 100", score_color(this_h)),
                  unsafe_allow_html=True)
    m[1].markdown(metric_card("Change this week", f"{wow:+.0f} pts", RED if moved_down else TEAL),
                  unsafe_allow_html=True)
    grade_lbl = "Healthy" if this_h >= 70 else "Needs attention" if this_h >= 60 else "Problem"
    m[2].markdown(
        f"<div class='mcard'><div class='lbl'>Status</div>"
        f"<div class='val' style='color:{score_color(this_h)}'>{grade_lbl}</div>"
        f"<div class='def'>A quick read on whether the latest score is in a good place.</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div class='takeaway'>Out of every 100 points of possible relevance, the assistant scored "
        f"<b>{this_h:.0f}</b> this week, {'down' if moved_down else 'up'} from <b>{last_h:.0f}</b> last week — "
        f"a {abs(wow):.0f}-point {'drop' if moved_down else 'gain'}. "
        f"{'That is a real dip worth explaining.' if abs(wow) >= 5 else 'A small, normal-looking move.'}</div>",
        unsafe_allow_html=True,
    )

    st.write("")
    st.markdown('<div class="section-title">Relevance score, week by week</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-copy">Each point is one week, labeled with its score. The latest '
                'week is highlighted in amber.</div>', unsafe_allow_html=True)
    timeline = load_json("psr_timeline.json")
    pts = [(t["week"].replace("2026-", ""), t["psr"]) for t in timeline]
    st.markdown(svg_line(pts, fmt="{:.0f}"), unsafe_allow_html=True)
    with st.expander("What am I looking at?"):
        st.markdown(
            f"- The line is the weekly relevance score (0–100). It sat steadily around **72–73** "
            f"for weeks, then fell to **{this_h:.0f}** this week.\n"
            f"- A score of 72 means that, on average, the products shown were a bit better than "
            f"'good' (a grade of 2 out of 3 maps to about 67).\n"
            f"- A sudden {abs(wow):.0f}-point drop in a single week is the kind of move worth "
            f"chasing down — which is what the next tab does."
        )

# ============================ WHY IT MOVED ================================= #
with cause_tab:
    st.markdown('<div class="section-title">Which kinds of searches slipped?</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-copy">We split the change by what the customer was trying to do. '
                'Bars going left (red) are search types that got worse; right (teal) got better. Each '
                'bar is labeled with its point change.</div>', unsafe_allow_html=True)

    intents = sorted({r["intent"] for r in rows})

    def seg(week, intent, key):
        vals = [r[key] for r in rows if r["week"] == week and r["intent"] == intent]
        return mean(vals)

    breakdown = []
    for it in intents:
        ph_last, ph_this = seg(last, it, "psr_h"), seg(this, it, "psr_h")
        if ph_last == 0 and ph_this == 0:
            continue
        breakdown.append((INTENT_PLAIN.get(it, it), ph_this - ph_last, ph_last, ph_this))
    breakdown.sort(key=lambda b: b[1])

    st.markdown(svg_change_bars([(b[0], b[1]) for b in breakdown]), unsafe_allow_html=True)

    with st.expander("Show the exact numbers"):
        st.markdown(
            html_table(
                ["Search type", "Last week", "This week", "Change"],
                [[esc(b[0]), f"{b[2]:.0f}", f"{b[3]:.0f}", f"{b[1]:+.0f} pts"] for b in breakdown],
            ),
            unsafe_allow_html=True,
        )

    worst = breakdown[0] if breakdown else None
    if worst:
        st.markdown(
            f"<div class='takeaway'>The biggest slip was <b>{esc(worst[0])}</b>, down "
            f"<b>{abs(worst[1]):.0f} points</b> ({worst[2]:.0f} → {worst[3]:.0f}). "
            f"That's where to look first.</div>",
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown('<div class="section-title">What changed in the product that week?</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-copy">Lining the drop up against recent engineering changes and '
                'seasonal effects, to point at a likely cause.</div>', unsafe_allow_html=True)

    change_log = load_json("change_log.json")
    seasonality = load_json("seasonality.json")
    suspects = [c for c in change_log if c.get("impact") == "suspected" and c["week"] == this]

    if suspects:
        st.markdown("**Likely culprits — changes shipped the same week:**")
        for c in suspects:
            st.markdown(
                f"<div class='mcard' style='margin-bottom:8px'>"
                f"<span class='tag tag-bad'>Suspected cause</span> "
                f"<b style='margin-left:6px'>{esc(c['title'])}</b>"
                f"<div style='color:{MUTED};margin-top:6px;font-size:0.92rem'>"
                f"Shipped {esc(c['date'])} · area: {esc(c['area'])}. {esc(c['note'])}</div></div>",
                unsafe_allow_html=True,
            )
    if seasonality:
        st.markdown("**Seasonal context — things happening in the world that week:**")
        for s in seasonality:
            st.markdown(f"- {esc(s['weeks'])} · **{esc(s['event'])}** — {esc(s['effect'])}")

    st.markdown(
        f"<div class='takeaway'>Plain-language read: a ranking change started favouring products whose "
        f"<b>titles</b> matched the words in the search, while a relaxed filter let "
        f"<b>off-diet and off-category</b> items slip into the results. Both landed in {this.replace('2026-','')}, "
        f"the same week relevance dropped — so they're the prime suspects.</div>",
        unsafe_allow_html=True,
    )

# ============================ TRUST THE CHECKER ============================ #
with trust_tab:
    st.markdown('<div class="section-title">Can we trust the automated checker?</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-copy">The score is produced by an automated checker so it can run '
                'on every carousel. To trust it, we compare its grades against grades from human '
                'reviewers on the same products.</div>', unsafe_allow_html=True)

    n = len(j_all)
    exact = sum(1 for a, b in zip(j_all, h_all) if a == b) / n * 100
    within1 = sum(1 for a, b in zip(j_all, h_all) if abs(a - b) <= 1) / n * 100
    mae = sum(abs(a - b) for a, b in zip(j_all, h_all)) / n
    r = pearson(j_all, h_all)

    cards = [
        ("Exact match", f"{exact:.0f}%", TEAL if exact >= 60 else AMBER),
        ("Close enough", f"{within1:.0f}%", TEAL if within1 >= 80 else AMBER),
        ("Typical miss", f"{mae:.2f} of 3", TEAL if mae <= 0.5 else AMBER),
        ("Move together", f"{r:.2f}", TEAL if r >= 0.7 else AMBER),
    ]
    cols = st.columns(4)
    for col, (lbl, val, acc) in zip(cols, cards):
        col.markdown(metric_card(lbl, val, acc), unsafe_allow_html=True)

    st.markdown(
        f"<div class='takeaway'>The simple checker in this demo agrees with humans only about "
        f"<b>{exact:.0f}% of the time exactly</b>, and lands within one grade <b>{within1:.0f}%</b> "
        f"of the time. It's deliberately basic — it matches words and <b>ignores price, size, and "
        f"dietary limits</b> — so it misses exactly the constraint problems that caused this week's "
        f"drop. That's the case for keeping a smarter checker (and human spot-checks) in the loop.</div>",
        unsafe_allow_html=True,
    )

    with st.expander("See the score the checker gave vs the humans, per carousel"):
        trows = []
        for row in rows:
            gap = row["psr_j"] - row["psr_h"]
            gap_col = RED if gap > 5 else TEAL if gap >= -5 else AMBER
            trows.append([
                esc(row["id"]),
                esc(row["week"].replace("2026-", "")),
                esc(INTENT_PLAIN.get(row["intent"], row["intent"])),
                f"{row['psr_j']:.0f}",
                f"{row['psr_h']:.0f}",
                f"<b style='color:{gap_col}'>{gap:+.0f}</b>",
            ])
        st.markdown(
            html_table(["Carousel", "Week", "Search type", "Checker score", "Human score", "Gap"], trows),
            unsafe_allow_html=True,
        )
        st.caption("A positive gap (red) means the checker was too generous — usually because it "
                   "missed a constraint the humans caught.")

# ============================ TRY IT YOURSELF ============================== #
with try_tab:
    st.markdown('<div class="section-title">Grade a real carousel</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-copy">Pick a customer search and see how each product was graded, '
                'with a plain reason — and how the checker compared to the humans.</div>',
                unsafe_allow_html=True)

    options = {f"[{c['week'].replace('2026-','')} · {INTENT_PLAIN.get(c['intent'], c['intent'])}] "
               f"{c['query'][:55]}": c for c in carousels}
    pick = st.selectbox("Pick a customer search", list(options.keys()))
    c = options[pick]
    st.markdown(f"<div class='takeaway'>Customer searched for: <b>{esc(c['query'])}</b></div>",
                unsafe_allow_html=True)

    if st.button("Grade this carousel", type="primary"):
        graded = {g.product_id: g for g in judge.grade_set(c["query"], c["results"])}
        out = []
        for p in c["results"]:
            g = graded.get(p["id"])
            out.append({"p": p, "g": g.grade if g else 0, "h": p["human_grade"]})
        jg = [o["g"] for o in out]
        hg = [o["h"] for o in out]

        cc1, cc2 = st.columns(2)
        cc1.markdown(metric_card("Relevance score", f"{psr(jg):.0f} / 100", score_color(psr(jg))),
                     unsafe_allow_html=True)
        cc2.markdown(
            f"<div class='mcard'><div class='lbl'>Human score</div>"
            f"<div class='val' style='color:{score_color(psr(hg))}'>{psr(hg):.0f} / 100</div>"
            f"<div class='def'>What trained human reviewers gave the same set.</div></div>",
            unsafe_allow_html=True,
        )

        st.write("")
        st.markdown("**Each product in the row:**")
        for o in out:
            p = o["p"]
            price = f"${p['price']:.0f}" if p.get("price") is not None else "—"
            st.markdown(
                f"<div class='mcard' style='margin-bottom:8px'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;gap:12px'>"
                f"<span style='font-weight:700'>{esc(p['title'])}</span>"
                f"<span style='color:{MUTED};font-size:0.9rem;white-space:nowrap'>{esc(p.get('category',''))} · {price}</span>"
                f"</div>"
                f"<div style='display:flex;gap:22px;margin-top:8px;align-items:center;font-size:0.92rem'>"
                f"<span style='color:{MUTED}'>Checker {grade_chip(o['g'])} <span style='color:{INK}'>{esc(GRADE_PLAIN[o['g']])}</span></span>"
                f"<span style='color:{MUTED}'>Human {grade_chip(o['h'])} <span style='color:{INK}'>{esc(GRADE_PLAIN[o['h']])}</span></span>"
                f"</div></div>",
                unsafe_allow_html=True,
            )
        st.caption("Grades: 3 = perfect match · 2 = good · 1 = off (misses something) · 0 = wrong. "
                   "The checker grades on words alone, so watch where it over-rates an item that "
                   "breaks a budget, size, or dietary limit.")

    st.write("")
    st.markdown('<div class="section-title">One-click summary for leadership</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-copy">A short, plain-language snapshot you can paste into an '
                'email or deck.</div>', unsafe_allow_html=True)

    if st.button("📋 Generate executive summary", type="primary"):
        st.session_state["psr_show_exec"] = True

    if st.session_state.get("psr_show_exec"):
        intents_local = sorted({r["intent"] for r in rows})

        def seg2(week, intent):
            return mean([r["psr_h"] for r in rows if r["week"] == week and r["intent"] == intent])

        diffs = []
        for it in intents_local:
            a, b = seg2(last, it), seg2(this, it)
            if a or b:
                diffs.append((INTENT_PLAIN.get(it, it), b - a))
        diffs.sort(key=lambda x: x[1])
        worst_name = diffs[0][0] if diffs else "—"
        worst_chg = diffs[0][1] if diffs else 0.0

        bullets = [
            f"Search relevance {'fell' if moved_down else 'rose'} {abs(wow):.0f} points this week, "
            f"from {last_h:.0f} to {this_h:.0f} out of 100.",
            f"The biggest slip was '{worst_name}' searches, down {abs(worst_chg):.0f} points.",
            "Likely cause: a ranking change that over-weighted title wording, plus a relaxed filter "
            "that let off-diet and off-category products into the results — both shipped this week.",
            "The automated checker under-counts these constraint misses, so a smarter checker and "
            "human spot-checks are recommended before trusting the weekly number alone.",
        ]
        st.markdown(
            f"<div class='exec-card'>"
            f"<span class='tag tag-bad'>Executive summary</span>"
            f"<h2>Product Set Relevance — {this.replace('2026-','')}</h2>"
            f"<div class='kpi'>"
            f"<div><div class='n' style='color:{score_color(this_h)}'>{this_h:.0f}/100</div><div class='l'>This week</div></div>"
            f"<div><div class='n' style='color:{RED if moved_down else TEAL}'>{wow:+.0f}</div><div class='l'>Change</div></div>"
            f"<div><div class='n'>{esc(worst_name)}</div><div class='l'>Worst-hit search</div></div>"
            f"</div><ul>{''.join(f'<li>{esc(b)}</li>' for b in bullets)}</ul></div>",
            unsafe_allow_html=True,
        )
        plain = (
            f"EXECUTIVE SUMMARY — Product Set Relevance ({this.replace('2026-','')})\n\n"
            + "\n".join(f"- {b}" for b in bullets)
        )
        st.write("")
        st.caption("Copy this to share with leadership (use the copy icon, top-right of the box):")
        st.code(plain, language=None)
