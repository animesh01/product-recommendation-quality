# Product Recommendation Quality (PRQ)

**A measurement framework and live report for the quality of an AI shopping assistant's product recommendations.**

When an AI shopping assistant answers a query, it typically returns a *set* of products: a carousel, a row, a ranked list. PRQ answers a deceptively hard product question: how good was that set, really? Not whether the model responded, but whether the products it surfaced actually satisfy what the customer asked for, including the constraints that are easy to honor on the surface and easy to violate underneath.

This repository is a working, deployed demonstration of how to measure that, track it over time, diagnose regressions, and communicate the result to a non-technical audience.

**About this project.** Independent portfolio project built entirely on synthetic, publicly shareable sample data to illustrate an evaluation method. It is not affiliated with any company and contains no proprietary, confidential, or company-specific data, metrics, or systems. All names, numbers, and scenarios are illustrative.

## Why this metric exists (the product problem)

Recommendation quality is intuitively obvious and operationally slippery. A row of products can look reasonable (right category, plausible titles, attractive images) while quietly failing the things a customer actually cares about: a budget ceiling, a dietary restriction, a size, a use case. These constraint misses are the most damaging failures, because they erode trust precisely when the customer was specific about a need.

The product challenges PRQ is built to address:

**Quality is a property of the set, not a single item.** A carousel is only as trustworthy as its weakest credible-looking entry. Per-item accuracy alone misses this; PRQ scores the whole set.

**Regressions are silent.** A ranking tweak or a relaxed filter can degrade relevance for one segment of queries while aggregate engagement metrics barely move. The signal must be sensitive enough to catch this and decomposable enough to localize it.

**A number without a cause is not actionable.** Relevance dropping ten points prompts the only useful follow-up: why? PRQ is designed so the same report that surfaces a drop also attributes it.

**The audience is not all statisticians.** Product managers, ops leads, and category managers need to read the report without a glossary. Plain language is a first-class design requirement here, not a polish step.

## What PRQ measures

Each product in a returned carousel is graded against the customer's query on a 0 to 3 scale:

| Grade | Label | Meaning |
| --- | --- | --- |
| 3 | Perfect | Exactly what they asked for |
| 2 | Good | Fits the request |
| 1 | Off | Right area, but misses something they asked for (for example, over budget) |
| 0 | Wrong | Not what they wanted |

The per-product grades are averaged and rescaled to a 0 to 100 PRQ score for the carousel. A carousel of uniformly "good" (all-2) products maps to about 67; an all-perfect carousel maps to 100. Carousel scores are then aggregated by week to produce the headline trend.

This graded-relevance design is intentionally closer to an NDCG-style relevance judgment than a binary click metric: it captures degrees of wrongness, which is what makes the segment-level diagnosis possible.

## How the report is structured

The app follows a four-part narrative, ordered the way an investigation actually proceeds.

**1. The trend.** The weekly PRQ score and its week-over-week change, with a plain read on whether the current level is healthy. Answers the question: is something wrong?

**2. Why it moved.** The week's change decomposed by search intent (browsing, budget-constrained, dietary-constrained, gifting, reorder, substitution), shown as a diverging bar chart of which segments improved or slipped. This is lined up against a change log of recent engineering releases and a seasonality overlay to triangulate a likely root cause. Answers the question: why, and what probably caused it?

**3. Can we trust the checker?** Because the score must run on every carousel, it is produced by an automated checker, not by humans. This view continuously validates the checker against human grades using four agreement measures: exact-match rate, within-one-grade rate, typical miss, and correlation. Answers the question: should we believe the number?

**4. Try it yourself.** Grade any sample carousel interactively and inspect each product's grade with a plain-language reason, alongside the human grade for comparison.

Each metric carries an always-visible definition (no hover-only tooltips), every chart labels its data points, and a one-click executive summary produces a leadership-ready snapshot with a copyable text block.

## Methodology notes

**Graded relevance over binary.** A 0 to 3 scale preserves the difference between "slightly off" and "completely wrong," which is what lets the report distinguish a broad mild decline from a sharp failure in one segment.

**Segmentation by intent is the diagnostic engine.** Aggregate PRQ tells you that quality moved; the per-intent decomposition tells you where. In the bundled scenario, a 10-point aggregate drop resolves into a large regression concentrated in dietary and substitution queries, a far more actionable finding than the headline alone.

**Root-cause triangulation, not causal proof.** The report aligns a regression with engineering changes shipped the same week and with seasonal effects. This is deliberately framed as suspect identification (narrowing where to look), not a causal claim. Establishing causation would require a controlled experiment.

**Checker calibration is a feature, not an afterthought.** The included checker is intentionally a weak baseline: it matches on title wording and ignores price, size, and dietary constraints. As a result it over-rates exactly the carousels that fail on constraints, visible as a positive checker-minus-human gap. Surfacing this gap is the point: it is the evidence-based argument for investing in a stronger judge (such as an LLM-as-a-judge) and retaining human spot-checks, rather than trusting an automated number blindly.

## The bundled scenario

The sample data tells a coherent, realistic story so the report has something to diagnose. PRQ sits steadily around 72 to 73 for several weeks, then drops to about 62 in a single week. The decomposition concentrates the loss in constraint-heavy intents (dietary and substitution). The change log shows two releases that week, a ranking change that over-weighted title-keyword matching and a relaxed dietary and category filter, which together explain both the magnitude and the segment pattern of the drop. This mirrors a common real-world failure mode: a relevance regression that aggregate engagement metrics would under-report, caught and localized by a purpose-built quality metric.

## Running locally

Install the dependencies and run the app. No API key, credentials, or external services are required; it runs entirely on the bundled checker and synthetic data.

    pip install -r requirements.txt
        streamlit run streamlit_app.py

        ## Technical implementation

        **Stack.** Python, Streamlit, and pandas.

        **Charts.** Rendered as inline SVG with value labels on every point, so there is no plotting-library dependency. This keeps the build reproducible and avoids version-compatibility failures on the hosting platform.

        **Reproducibility.** Python is pinned to 3.12 via runtime.txt, and dependencies are pinned in requirements.txt.

        **No external calls.** The automated checker is a self-contained heuristic; there is no API dependency in the deployed path.

        ## Repository layout

        The streamlit_app.py file is the report application (UI, charts, narrative, and summary). The relevance_judge.py file holds the grading logic (the automated checker). The evaluate.py file is a standalone command-line version of the week-over-week report with the root-cause breakdown. The data folder contains the synthetic carousels, weekly history, change log, and seasonality overlay. The .streamlit folder holds theme configuration, and requirements.txt and runtime.txt pin the dependencies and Python version.

        ## License

        Released under the MIT License. See the LICENSE file for details.
        
