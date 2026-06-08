# Product Set Relevance (PSR) — Streamlit dashboard

A relevance metric and an **automated root-cause dashboard** for the product
carousels an AI shopping assistant shows. An **LLM-as-a-judge** grades each
product 0–3 against the query; the carousel's **PSR** is the average rescaled to
0–100. PSR is tracked week over week, and when it moves the change is decomposed
by search intent and lined up against deploys and seasonality to explain *why*.

All carousels, grades, and numbers here are synthetic. No proprietary code or
data is included.

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The app opens in **Mock** mode (a keyword heuristic that deliberately ignores
budget/size/diet constraints) and runs with no API key. Pick **Real LLM judge**
in the sidebar and paste an Anthropic API key to use the calibrated judge.

## Tabs

- **Overview** — PSR timeline and the week-over-week headline (judge vs human).
- **Root cause** — WOW change decomposed by search intent, plus a plain-language
  root cause tied to suspected deploys and seasonality.
- **Calibration** — judge↔human agreement (exact, within ±1, MAE, correlation,
  PSR MAE per carousel).
- **Grade a carousel** — pick any carousel and grade it live.

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repo.
2. https://share.streamlit.io → **New app** → select repo/branch, main file
   `streamlit_app.py`.
3. (Optional) **Settings → Secrets** to store your key instead of pasting it:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   Never commit a key — `.streamlit/secrets.toml` is git-ignored.

## Files

```
streamlit_app.py        # the dashboard
relevance_judge.py      # grading rubric, mock judge, real Anthropic judge
evaluate.py             # original command-line WOW report
data/
  sample_carousels.json # queries + products + human grades
  psr_timeline.json     # weekly PSR series
  change_log.json       # deploys (for root-cause correlation)
  seasonality.json      # seasonal context
```
