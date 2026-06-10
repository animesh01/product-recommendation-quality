"""Product Recommendation Quality (PRQ) -- week-over-week leadership report with root-cause analysis.

PRQ for a carousel = average product relevance grade (0-3), scaled to 0-100.
The report aggregates PRQ by week, computes the week-over-week (WOW) change, and
decomposes that change by intent so you can see which segments moved it. The LLM
judge produces the grades and is calibrated against human grades.

Examples:
  python evaluate.py --mock                      # no API key needed
  python evaluate.py --model claude-sonnet-4-6   # real judge; needs ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict

from relevance_judge import get_judge


def prq(grades) -> float:
    """Average product relevance (0-3 grades) scaled to 0-100."""
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


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="PRQ week-over-week report with root-cause breakdown.")
    ap.add_argument("--data", default=os.path.join(here, "data", "sample_carousels.json"))
    ap.add_argument("--mock", action="store_true", help="use the no-API heuristic baseline")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    args = ap.parse_args()

    with open(args.data) as f:
        carousels = json.load(f)

    judge = get_judge(mock=args.mock, model=args.model)
    weeks = sorted({c["week"] for c in carousels})
    if len(weeks) < 2:
        raise SystemExit("Need at least two weeks of carousels for a WOW report.")
    last, this = weeks[-2], weeks[-1]

    # grade every carousel; store PRQ (judge + human) and pooled per-product grades
    rows = []
    jg_all, hg_all = [], []
    print(f"\nJudge: {judge.model}   |   {len(carousels)} carousels   |   {last} -> {this}\n")
    for c in carousels:
        human = [p["human_grade"] for p in c["results"]]
        graded = judge.grade_set(c["query"], c["results"])
        jg = [g.grade for g in graded]
        jg_all.extend(jg); hg_all.extend(human)
        rows.append({"week": c["week"], "intent": c["intent"],
                     "prq_j": prq(jg), "prq_h": prq(human)})

    def overall(week, key):
        vals = [r[key] for r in rows if r["week"] == week]
        return mean(vals)

    last_h, this_h = overall(last, "prq_h"), overall(this, "prq_h")
    last_j, this_j = overall(last, "prq_j"), overall(this, "prq_j")
    wow_h, wow_j = this_h - last_h, this_j - last_j

    print("Aggregate PRQ (0-100, average product relevance per carousel)")
    print(f"{'':22}{'judge':>9}{'human':>9}")
    print(f"  {last} (last):    {last_j:>9.1f}{last_h:>9.1f}")
    print(f"  {this} (this):    {this_j:>9.1f}{this_h:>9.1f}")
    print(f"  WOW change:        {wow_j:>+9.1f}{wow_h:>+9.1f}")

    # ---- root-cause decomposition (human ground truth) ---------------------- #
    intents = sorted({r["intent"] for r in rows})
    n_last = sum(1 for r in rows if r["week"] == last)
    n_this = sum(1 for r in rows if r["week"] == this)

    def seg_prq(week, intent, key):
        vals = [r[key] for r in rows if r["week"] == week and r["intent"] == intent]
        return mean(vals)

    def seg_count(week, intent):
        return sum(1 for r in rows if r["week"] == week and r["intent"] == intent)

    breakdown = []
    for it in intents:
        ph_last, ph_this = seg_prq(last, it, "prq_h"), seg_prq(this, it, "prq_h")
        pj_last, pj_this = seg_prq(last, it, "prq_j"), seg_prq(this, it, "prq_j")
        w_last = seg_count(last, it) / n_last
        w_this = seg_count(this, it) / n_this
        contribution = w_this * ph_this - w_last * ph_last  # sums to WOW (human)
        breakdown.append({"intent": it, "h_last": ph_last, "h_this": ph_this,
                          "h_delta": ph_this - ph_last, "j_delta": pj_this - pj_last,
                          "contribution": contribution})
    breakdown.sort(key=lambda b: b["contribution"])

    print("\nRoot-cause breakdown -- WOW change by intent (human ground truth)")
    print(f"  {'intent':<20}{'last':>7}{'this':>7}{'change':>9}{'share':>8}{'judge dl':>10}")
    for b in breakdown:
        share = (b["contribution"] / wow_h * 100) if abs(wow_h) > 1e-9 else 0.0
        share = max(0.0, share)  # show share of the move it explains
        print(f"  {b['intent']:<20}{b['h_last']:>7.1f}{b['h_this']:>7.1f}"
              f"{b['h_delta']:>+9.1f}{share:>7.0f}%{b['j_delta']:>+10.1f}")
    print(f"  {'-'*60}")
    print(f"  {'Overall':<20}{last_h:>7.1f}{this_h:>7.1f}{wow_h:>+9.1f}")

    drivers = [b for b in breakdown if b["h_delta"] < -0.05]
    if drivers:
        names = ", ".join(f"{b['intent']} ({b['h_delta']:+.1f})" for b in drivers)
        print(f"\n  Top drivers of the WOW move: {names}")

    # ---- judge calibration -------------------------------------------------- #
    n = len(jg_all)
    exact = sum(1 for a, b in zip(jg_all, hg_all) if a == b) / n * 100
    within1 = sum(1 for a, b in zip(jg_all, hg_all) if abs(a - b) <= 1) / n * 100
    grade_mae = sum(abs(a - b) for a, b in zip(jg_all, hg_all)) / n
    grade_r = pearson(jg_all, hg_all)
    prq_mae = mean([abs(r["prq_j"] - r["prq_h"]) for r in rows])

    print("\nJudge calibration vs human grades")
    print(f"  Per-product graded:    {n}")
    print(f"  Exact grade match:     {exact:5.0f}%")
    print(f"  Within +/- 1 grade:    {within1:5.0f}%")
    print(f"  Grade MAE (0-3):       {grade_mae:5.2f}")
    print(f"  PRQ MAE per carousel:  {prq_mae:5.1f} pts")
    print(f"  Grade correlation r:   {grade_r:5.2f}")
    print(f"  WOW estimate:          judge {wow_j:+.1f} vs human {wow_h:+.1f}  (gap {abs(wow_j - wow_h):.1f})")
    print("\n(With --mock this is the keyword baseline: it ignores budget, size, and")
    print(" dietary constraints, so it under-detects the relevance regression and its")
    print(" RCA can miss the segments a calibrated LLM judge correctly flags.)\n")


if __name__ == "__main__":
    main()
