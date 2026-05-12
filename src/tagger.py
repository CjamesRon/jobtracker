"""
Tag jobs into one of six categories matching your CV variants:
  WM         - Wealth Management
  AM         - Asset Management
  IB         - Investment Banking
  PE         - Private Equity
  QUANT      - Quantitative / Trading / Systematic
  AUDIT_TAX  - Big 4 Audit & Tax

A job can have multiple tags (e.g. "Investment Banking Analyst, M&A"
gets only IB; "Quant Researcher, Equities" gets QUANT).

Rules engine: keyword hits in title get weight 3, in description get weight 1.
Tags above threshold (2) are assigned. Title keywords almost always win on
their own — descriptions are the tiebreaker.
"""
from typing import List

# Keyword sets — lowercased substrings.
# Tune these once you see what the polls actually return.
KEYWORDS = {
    "WM": [
        "wealth management", "private bank", "private wealth",
        "financial planner", "financial advisor", "client advisor",
        "private client", "high net worth", "hnw",
    ],
    "AM": [
        "asset management", "portfolio manag", "investment manager",
        "fund manager", "multi-asset", "fixed income", "equities analyst",
        "credit analyst", "buy-side", "buy side",
    ],
    "IB": [
        "investment banking", "m&a", "mergers and acquisitions",
        "leveraged finance", "lev fin", "ecm", "dcm", "capital markets",
        "sponsors group", "coverage", "industrials group", "tmt",
        "ibd", "ib analyst", "ib summer", "spring week", "spring insight",
    ],
    "PE": [
        "private equity", "growth equity", "buyout", "lbo",
        "venture capital", "vc associate", "secondaries",
    ],
    "QUANT": [
        "quant", "quantitative", "systematic", "algorithmic trading",
        "trading strategist", "researcher", "machine learning",
        "trader", "execution trader", "low latency", "hft",
        "data scientist",  # filtered if it's a generic non-finance role — see overrides
    ],
    "AUDIT_TAX": [
        "audit", "external audit", "internal audit", "assurance",
        "tax advisor", "tax consultant", "tax graduate", "tax manager",
        "transfer pricing", "indirect tax",
        "corporate tax", "personal tax",
        # NB: kept "tax" out as a bare word to avoid catching "after-tax returns"
        # in unrelated JDs; "vat" removed for same reason (acronym noise).
    ],
}

# Words that DISQUALIFY a category even if a keyword matches.
# e.g. "Audit IT Manager" is IT, not Audit; "Software Engineer" with "trader"
# in the desc shouldn't be tagged QUANT.
NEGATIVE_OVERRIDES = {
    "QUANT": ["software engineer", "front end", "frontend", "devops",
              "site reliability", "platform engineer"],
    "AUDIT_TAX": ["it audit", "cyber", "information security"],
}

# Roles that count as graduate / entry-level. Used by the dashboard to filter
# but also useful for alerts (don't ping me about VPs).
GRAD_HINTS = [
    "graduate", "grad ", "intern", "internship", "summer analyst",
    "spring", "off-cycle", "off cycle", "analyst",  # "analyst" is bottom rung in IB
    "associate",  # entry-level in some firms (consulting, audit)
    "trainee", "apprentice", "entry level", "entry-level",
    "junior", "campus",
]

SENIOR_HINTS = [
    "vp", "vice president", "director", "managing director",
    "head of", "senior manager", "principal", "partner",
]


def tag_job(title: str, description: str = "") -> List[str]:
    """Return all matching category tags (lowercased substrings)."""
    t = title.lower()
    d = description.lower()
    scores = {}

    for cat, kws in KEYWORDS.items():
        score = 0
        for kw in kws:
            if kw in t:
                score += 3
            elif kw in d:
                score += 1
        # Apply negative overrides
        for neg in NEGATIVE_OVERRIDES.get(cat, []):
            if neg in t:
                score = 0
                break
        if score >= 2:
            scores[cat] = score

    # Return tags sorted by score desc
    return [c for c, _ in sorted(scores.items(), key=lambda x: -x[1])]


def seniority(title: str) -> str:
    """Return 'grad', 'senior', or 'mid'."""
    t = title.lower()
    if any(h in t for h in SENIOR_HINTS):
        return "senior"
    if any(h in t for h in GRAD_HINTS):
        return "grad"
    return "mid"


def is_uk(location: str) -> bool:
    """Crude UK filter — extend as needed."""
    if not location:
        return False
    l = location.lower()
    return any(x in l for x in [
        "london", "edinburgh", "glasgow", "manchester", "birmingham",
        "leeds", "bristol", "reading", "cambridge", "oxford",
        "united kingdom", "uk", "england", "scotland", "wales",
    ])
