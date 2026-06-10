# Case study: Product Recommendation Quality (PRQ)

**About this project.** Independent portfolio project built entirely on synthetic, publicly shareable sample data to illustrate an evaluation method. It is not affiliated with any company and contains no proprietary, confidential, or company-specific data, metrics, or systems. All names, numbers, and scenarios are illustrative.

## The problem

An AI shopping assistant recommends a row (a "carousel") of products in response to a customer's query. Recommendation quality is easy to feel but hard to measure: a row can look fine yet quietly ignore a budget cap, a dietary need, or a size, which are exactly the things a customer cares about most. Teams need a single, trustworthy number that tracks over time and, when it moves, points at why.

## The approach

**Grade each product, then the set.** Every product in a carousel is graded 0 to 3 against the query (3 = perfect, 0 = wrong). The grades are averaged and rescaled to a 0 to 100 PRQ score for the carousel. Scoring the whole set, not single results, is the point: a row is only as good as its weakest credible-looking item.

**Track it week over week.** PRQ is aggregated weekly so a regression shows up as a clear dip rather than scattered anecdotes.

**Explain the moves.** When PRQ drops, the report decomposes the change by what the customer was trying to do (browsing, budget limit, dietary need, gifting, reorder, substitution) to show which searches slipped, then lines the drop up against recent engineering changes and seasonal effects to surface a likely root cause.

**Keep the automated checker honest.** Because the score runs on every carousel, it is produced by an automated checker. The report continuously compares that checker against human reviewers (exact-match rate, within-one-grade rate, typical miss, correlation). The demo's checker is deliberately simple: it matches on wording and ignores price, size, and dietary limits, which is exactly why it under-counts constraint misses. That gap is the argument for a smarter checker plus human spot-checks, rather than trusting an automated number blindly.

## What the demo illustrates

A realistic regression. PRQ holds steady around 72 for several weeks, then drops to about 62 in one week. The breakdown shows the biggest slip is in constraint-heavy searches (dietary and substitution), and the timeline lines that up with two changes shipped that week: a ranking tweak that over-weighted title wording, and a relaxed filter that let off-diet and off-category items into results. The plain-language report walks a non-expert from "the number dropped" to "here is the likely cause and what to do," ending in a copyable executive summary.

## Why it matters

Relevance and recommendation quality regressions are common, costly, and easy to miss. A metric that is tracked over time, decomposable to a root cause, and validated against humans is far more actionable than a single opaque score, and the plain-language framing makes it usable by people who never run experiments themselves.

---

*All carousels, grades, and numbers in this repository are synthetic and exist only to demonstrate the design.*
