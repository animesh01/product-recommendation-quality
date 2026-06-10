"""LLM-as-a-judge for Product Recommendation Quality.

Given a customer query and the ranked set of products the assistant returned,
the judge assigns each product a graded relevance score:

    0 = irrelevant      1 = marginal      2 = relevant      3 = perfect match

Those grades feed the ranking metrics in evaluate.py (NDCG@k, Precision@k, MRR).

Two modes:
  - real:  uses the Anthropic API (set ANTHROPIC_API_KEY, `pip install anthropic`)
  - mock:  a deterministic, text-only heuristic that needs no API key, so the
           demo runs out of the box. It is intentionally weak: it scores by
           keyword overlap and ignores constraints like budget, size, and
           dietary needs -- exactly the cases a real LLM (or human) judge catches.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

GRADES = {
    0: "irrelevant - does not satisfy the query",
    1: "marginal - same broad area but misses the intent or a stated constraint",
    2: "relevant - satisfies the query",
    3: "perfect - fully satisfies the query and every stated constraint",
}
REL_THRESHOLD = 2  # grade >= this counts as "relevant" for Precision@k / MRR


@dataclass
class ProductGrade:
    product_id: str
    grade: int
    rationale: str = ""


def product_to_text(p) -> str:
    price = f"${p['price']:.2f}" if p.get("price") is not None else "n/a"
    return f"{p['title']} (category: {p.get('category', 'n/a')}, price: {price})"


# --------------------------------------------------------------------------- #
# Real judge: a frontier LLM grades each product against the query.
# --------------------------------------------------------------------------- #
_PROMPT = """You are an evaluation judge scoring how relevant each product in a carousel is to a customer's shopping query. The per-product grades are averaged into a single Product Recommendation Quality (PRQ) score for the carousel.

Grade every product from 0 to 3:
{grades}

Honor EVERY constraint stated in the query -- budget ("under $X"), size, quantity,
dietary needs (e.g. gluten-free), and category. A product that ignores a stated
constraint is at most marginal (1), even if it is the right kind of item.

Query: "{query}"

Products:
{products}

Return ONLY a JSON array (no prose, no code fences), one object per product, in the same order:
[{{"product_id": "...", "grade": 0-3, "rationale": "one short sentence"}}]"""


def build_prompt(query, products) -> str:
    grades = "\n".join(f"  {k} = {v}" for k, v in GRADES.items())
    listing = "\n".join(f"  {i+1}. [{p['id']}] {product_to_text(p)}" for i, p in enumerate(products))
    return _PROMPT.format(grades=grades, query=query, products=listing)


def _parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)


def _clamp_grade(x) -> int:
    g = int(round(float(x)))
    return max(0, min(3, g))


class LLMJudge:
    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        from anthropic import Anthropic  # lazy import so mock mode needs no install

        self.model = model
        # Use a key passed from the UI if provided, else fall back to the env var.
        self.client = Anthropic(api_key=api_key) if api_key else Anthropic()

    def grade_set(self, query, products) -> list[ProductGrade]:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=700,
            temperature=0,  # an evaluation judge must be reproducible
            messages=[{"role": "user", "content": build_prompt(query, products)}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        rows = {r["product_id"]: r for r in _parse_json(text)}
        out = []
        for p in products:  # preserve the returned ranking order
            r = rows.get(p["id"], {})
            out.append(ProductGrade(p["id"], _clamp_grade(r.get("grade", 0)), str(r.get("rationale", ""))))
        return out


# --------------------------------------------------------------------------- #
# Mock judge: deterministic keyword-overlap heuristic (a weak baseline).
# It never sees the human grades, and it deliberately ignores numeric/dietary
# constraints, so it over-grades over-budget, wrong-size, and wrong-diet items.
# --------------------------------------------------------------------------- #
_STOP = {"under", "over", "with", "your", "that", "this", "from", "more", "less",
         "than", "size", "pack", "count", "bought", "last", "month", "reorder", "need"}
_WORD = re.compile(r"[a-z]+")


def _words(s: str) -> set:
    return {w for w in _WORD.findall(s.lower()) if len(w) > 3 and w not in _STOP}


class MockJudge:
    """Deterministic, text-only heuristic. A weak baseline by design."""

    model = "mock-heuristic"

    def grade_set(self, query, products) -> list[ProductGrade]:
        q = _words(query)
        out = []
        for p in products:
            text = _words(p["title"] + " " + p.get("category", ""))
            ratio = len(q & text) / max(1, len(q))
            grade = 3 if ratio >= 0.45 else 2 if ratio >= 0.30 else 1 if ratio >= 0.15 else 0
            out.append(ProductGrade(
                p["id"], grade,
                "Matched on words in the title only — this simple checker doesn't read price, size, or dietary limits.",
            ))
        return out


def get_judge(mock: bool = False, model: str = "claude-sonnet-4-6", api_key: str | None = None):
    return MockJudge() if mock else LLMJudge(model=model, api_key=api_key)
