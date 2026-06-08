"""Product Set Relevance (PSR) — automated root-cause dashboard (Streamlit).

PSR grades each product in an AI shopping assistant's carousel 0-3 against the
query (an LLM-as-a-judge), averages to a 0-100 score, tracks it week over week,
and — when it moves — decomposes the change by search intent and lines it up
against deploys and seasonality to explain *why*.

Runs out of the box with a deterministic MOCK judge (no API key). Paste an
Anthropic API key in the sidebar to switch to the real LLM judge.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st

from relevance_judge import REL_THRESHOLD, get_judge

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

COLORS = {
    "ink": "#12221f",
    "muted": "#62706d",
    "teal": "#0d766e",
    "mint": "#dff4ef",
    "amber": "#b66a16",
    "red": "#b84040",
}

st.set_page_config(
    page_title="PSR — Product Set Relevance",
    page_icon="P",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
        html, body, [class*="css"] {{ font-family:"DM Sans",sans-serif; color:{COLORS["ink"]}; }}
        h1,h2,h3 {{ font-family:"Manrope",sans-serif !important; letter-spacing:-0.03em; }}
        .psr-pill {{ display:inline-block; padding:2px 10px; border-radius:999px;
            background:{COLORS["mint"]}; color:{COLORS["teal"]}; font-size:0.8rem;
            font-weight:600; margin-bottom:8px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


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


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar_config():
    st.sidebar.markdown("### Judge configuration")
    mode = st.sidebar.radio(
        "Judge mode",
        ["Mock (no API key, free)", "Real LLM judge (Anthropic)"],
        help="Mock is a keyword heuristic that ignores price/size/diet constraints "
        "(a weak baseline by design). The real judge honours every stated constraint.",
    )
    use_mock = mode.startswith("Mock")
    api_key, model = None, "claude-sonnet-4-6"
    if not use_mock:
        secret_key = None
        try:
            secret_key = st.secrets.get("ANTHROPIC_API_KEY")  # type: ignore[attr-defined]
        except Exception:
            secret_key = None
        api_key = st.sidebar.text_input(
            "Anthropic API key", value="", type="password",
            help="Used only for this session; never commit a key to the repo.",
        ) or secret_key
        model = st.sidebar.text_input("Model", value="claude-sonnet-4-6")
        if not api_key:
            st.sidebar.warning("Enter an API key, or switch to Mock mode to run free.")
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f"<span style='color:{COLORS['muted']};font-size:0.85rem'>"
        "PSR = average product grade (0–3) per carousel, rescaled to 0–100.</span>",
        unsafe_allow_html=True,
    )
    return use_mock, model, api_key


def build_judge(use_mock, model, api_key):
    if use_mock:
        return get_judge(mock=True)
    if not api_key:
        return None
    try:
        return get_judge(mock=False, model=model, api_key=api_key)
    except Exception as exc:
        st.error(f"Could not initialise the LLM judge: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Grade everything (cached per judge type)
# --------------------------------------------------------------------------- #
def grade_all(judge, carousels):
    rows, j_all, h_all = [], [], []
    for c in carousels:
        human = [p["human_grade"] for p in c["results"]]
        graded = judge.grade_set(c["query"], c["results"])
        jg = [g.grade for g in graded]
        j_all.extend(jg)
        h_all.extend(human)
        rows.append(
            {
                "id": c["id"],
                "week": c["week"],
                "intent": c["intent"],
                "query": c["query"],
                "psr_j": psr(jg),
                "psr_h": psr(human),
            }
        )
    return rows, j_all, h_all


# --------------------------------------------------------------------------- #
# Tab 1: Overview — timeline + WOW headline
# --------------------------------------------------------------------------- #
def render_overview(rows):
    timeline = load_json("psr_timeline.json")
    st.markdown("#### PSR over time")
    tdf = pd.DataFrame(timeline).set_index("week")
    st.line_chart(tdf, y="psr", height=260)

    weeks = sorted({r["week"] for r in rows})
    last, this = weeks[-2], weeks[-1]

    def overall(week, key):
        return mean([r[key] for r in rows if r["week"] == week])

    last_h, this_h = overall(last, "psr_h"), overall(this, "psr_h")
    last_j, this_j = overall(last, "psr_j"), overall(this, "psr_j")

    st.markdown(f"#### Week-over-week: {last} → {this}")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"PSR (human) {this}", f"{this_h:.1f}", f"{this_h - last_h:+.1f}")
    c2.metric(f"PSR (judge) {this}", f"{this_j:.1f}", f"{this_j - last_j:+.1f}")
    gap = abs((this_j - last_j) - (this_h - last_h))
    c3.metric("Judge vs human WOW gap", f"{gap:.1f} pts")


# --------------------------------------------------------------------------- #
# Tab 2: Root-cause decomposition
# --------------------------------------------------------------------------- #
def render_rca(rows):
    weeks = sorted({r["week"] for r in rows})
    last, this = weeks[-2], weeks[-1]
    intents = sorted({r["intent"] for r in rows})
    n_last = sum(1 for r in rows if r["week"] == last)
    n_this = sum(1 for r in rows if r["week"] == this)

    def seg(week, intent, key):
        return mean([r[key] for r in rows if r["week"] == week and r["intent"] == intent])

    def cnt(week, intent):
        return sum(1 for r in rows if r["week"] == week and r["intent"] == intent)

    wow_h = mean([r["psr_h"] for r in rows if r["week"] == this]) - mean(
        [r["psr_h"] for r in rows if r["week"] == last]
    )

    breakdown = []
    for it in intents:
        ph_last, ph_this = seg(last, it, "psr_h"), seg(this, it, "psr_h")
        pj_last, pj_this = seg(last, it, "psr_j"), seg(this, it, "psr_j")
        contribution = (cnt(this, it) / n_this) * ph_this - (cnt(last, it) / n_last) * ph_last
        breakdown.append(
            {
                "intent": it,
                "last": round(ph_last, 1),
                "this": round(ph_this, 1),
                "change": round(ph_this - ph_last, 1),
                "judge change": round(pj_this - pj_last, 1),
                "share of move": round(max(0.0, contribution / wow_h * 100), 0)
                if abs(wow_h) > 1e-9
                else 0.0,
            }
        )
    breakdown.sort(key=lambda b: b["change"])
    bdf = pd.DataFrame(breakdown)

    st.markdown("#### WOW change by search intent (human ground truth)")
    st.caption("Which segments moved the overall PSR, and how the judge tracked each.")
    st.dataframe(bdf, use_container_width=True, hide_index=True)

    chart_df = bdf[["intent", "change"]].set_index("intent")
    st.bar_chart(chart_df, height=280)

    drivers = [b for b in breakdown if b["change"] < -0.05]
    change_log = load_json("change_log.json")
    seasonality = load_json("seasonality.json")

    st.markdown("#### Plain-language root cause")
    if drivers:
        names = ", ".join(f"**{b['intent']}** ({b['change']:+.1f})" for b in drivers)
        st.markdown(f"The WOW move was driven mainly by: {names}.")
    suspected = [c for c in change_log if c.get("impact") == "suspected" and c["week"] == this]
    if suspected:
        st.markdown("**Suspected deploys this week:**")
        for c in suspected:
            st.markdown(f"- `{c['date']}` · *{c['area']}* — {c['title']}. {c['note']}")
    if seasonality:
        st.markdown("**Seasonality context:**")
        for s in seasonality:
            st.markdown(f"- {s['weeks']} · {s['event']} ({s['direction']}) — {s['effect']}")


# --------------------------------------------------------------------------- #
# Tab 3: Calibration
# --------------------------------------------------------------------------- #
def render_calibration(rows, j_all, h_all):
    st.markdown("#### Judge calibration vs human grades")
    n = len(j_all)
    exact = sum(1 for a, b in zip(j_all, h_all) if a == b) / n * 100
    within1 = sum(1 for a, b in zip(j_all, h_all) if abs(a - b) <= 1) / n * 100
    mae = sum(abs(a - b) for a, b in zip(j_all, h_all)) / n
    r = pearson(j_all, h_all)
    psr_mae = mean([abs(row["psr_j"] - row["psr_h"]) for row in rows])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Exact grade match", f"{exact:.0f}%")
    c2.metric("Within ±1 grade", f"{within1:.0f}%")
    c3.metric("Grade MAE (0–3)", f"{mae:.2f}")
    c4.metric("Correlation r", f"{r:.2f}")
    st.metric("PSR MAE per carousel", f"{psr_mae:.1f} pts")

    st.caption(
        "With the mock judge these numbers are deliberately weak — it scores by keyword "
        "overlap and ignores budget, size, and dietary constraints, so it under-detects "
        "the relevance regression a calibrated LLM judge would catch."
    )
    df = pd.DataFrame(rows)[["id", "week", "intent", "psr_j", "psr_h"]]
    df["gap"] = (df["psr_j"] - df["psr_h"]).round(1)
    st.dataframe(df, use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# Tab 4: Grade a carousel
# --------------------------------------------------------------------------- #
def render_grader(judge, carousels):
    st.markdown("#### Grade a single carousel")
    options = {f"[{c['week']} · {c['intent']}] {c['query'][:60]}": c for c in carousels}
    pick = st.selectbox("Pick a carousel", list(options.keys()))
    c = options[pick]
    st.caption(f"Query: *{c['query']}*")

    if st.button("Grade this carousel", type="primary"):
        graded = judge.grade_set(c["query"], c["results"])
        gmap = {g.product_id: g for g in graded}
        out = []
        for p in c["results"]:
            g = gmap.get(p["id"])
            out.append(
                {
                    "product": p["title"],
                    "category": p.get("category", ""),
                    "price": p.get("price"),
                    "judge grade": g.grade if g else None,
                    "human grade": p["human_grade"],
                    "rationale": g.rationale if g else "",
                }
            )
        odf = pd.DataFrame(out)
        jg = [r["judge grade"] for r in out]
        hg = [r["human grade"] for r in out]
        c1, c2 = st.columns(2)
        c1.metric("PSR (judge)", f"{psr(jg):.1f}")
        c2.metric("PSR (human)", f"{psr(hg):.1f}")
        st.dataframe(odf, use_container_width=True, hide_index=True)


def main():
    inject_styles()
    st.markdown("<span class='psr-pill'>LLM-as-a-judge · RCA</span>", unsafe_allow_html=True)
    st.title("Product Set Relevance")
    st.markdown(
        f"<p style='color:{COLORS['muted']};font-size:1.05rem;margin-top:-6px'>"
        "Measure carousel relevance, track it week over week, and explain why it moved."
        "</p>",
        unsafe_allow_html=True,
    )

    use_mock, model, api_key = sidebar_config()
    judge = build_judge(use_mock, model, api_key)
    carousels = load_json("sample_carousels.json")

    if judge is None:
        st.info("Configure the judge in the sidebar to grade carousels.")
        return

    judge_key = "mock" if use_mock else f"llm::{model}"
    if st.session_state.get("psr_judge_key") != judge_key or "psr_rows" not in st.session_state:
        with st.spinner("Grading carousels…"):
            rows, j_all, h_all = grade_all(judge, carousels)
        st.session_state["psr_rows"] = rows
        st.session_state["psr_j"] = j_all
        st.session_state["psr_h"] = h_all
        st.session_state["psr_judge_key"] = judge_key

    rows = st.session_state["psr_rows"]
    j_all = st.session_state["psr_j"]
    h_all = st.session_state["psr_h"]

    t1, t2, t3, t4 = st.tabs(["Overview", "Root cause", "Calibration", "Grade a carousel"])
    with t1:
        render_overview(rows)
    with t2:
        render_rca(rows)
    with t3:
        render_calibration(rows, j_all, h_all)
    with t4:
        render_grader(judge, carousels)


if __name__ == "__main__":
    main()
