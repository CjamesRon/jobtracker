"""
HireVue prep brief generator.

Given a job (title, company, JD, tags), uses the Claude API with web search
enabled to produce a structured research brief. Caches the result in Supabase
so repeated views are free.

The brief is deliberately structured as a *research starting point*, not a
script. Auto-generated answers read like auto-generated answers in interviews;
the value here is accelerating the prep, not replacing it.

Approximate cost per brief: $0.09-0.12 with Sonnet 4.6 + ~5 web searches.
"""
import os
import json
import logging
import requests
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

# Pricing per million tokens (USD) — Sonnet 4.6 as of mid-2026
INPUT_PRICE_PER_M  = 3.00
OUTPUT_PRICE_PER_M = 15.00
WEB_SEARCH_PRICE   = 0.01  # per search


SYSTEM_PROMPT = """You are a research analyst preparing a candidate for a graduate-scheme interview at a major financial-services firm. Your job is to produce a concise, accurate research brief — not a script. The candidate will use this to inform their own preparation, then internalise it in their own voice.

You will receive a job posting (title, company, location, description, tags). Use web search to find current information about the firm and the role. Prioritise reputable sources: Financial Times, Reuters, Bloomberg, Wall Street Journal, the firm's own newsroom and annual report, and authoritative trade press (eFinancialNews, Risk.net, IFR for IB, etc.). Avoid Glassdoor, WallStreetOasis, and student forums for content (their question banks raise integrity concerns), though general firm-culture overview from them is acceptable.

Return ONLY a JSON object with this exact structure — no preamble, no markdown fences, no commentary:

{
  "company_snapshot": "2-3 paragraph plain-text overview: what the firm does, scale, key segments, headquarters, current strategic priorities. UK context where relevant.",
  "recent_news": [
    {"title": "headline", "url": "source url", "date": "YYYY-MM-DD or 'recent'", "summary": "1-2 sentence summary"}
  ],
  "role_analysis": "What this specific role appears to involve based on the JD. What skills/competencies they're testing for. Which group/desk if identifiable. 1-2 paragraphs.",
  "likely_themes": [
    "Competency or technical area the candidate should expect to be tested on (generic themes only — NOT specific scraped questions)"
  ],
  "why_this_firm_angles": [
    "A specific, defensible 'why this firm' angle the candidate could draw on — each tied to recent news or strategy, not generic platitudes"
  ],
  "questions_to_ask": [
    "A thoughtful question for the candidate to ask the interviewer, ideally tied to a recent firm development"
  ],
  "sources": ["url1", "url2", "..."]
}

Quality rules:
- recent_news: 4-8 items, prefer last 60 days, must include URLs
- likely_themes: 3-6 generic competency areas; NEVER include specific interview questions scraped from forums
- why_this_firm_angles: 3-5 items, each grounded in a specific factual hook (a deal, a strategy, a hire, a result)
- questions_to_ask: 3-5 items, each one that would only make sense if you'd done the research
- All factual claims must be supported by a source in `sources`
- If web search returns thin results, say so honestly in company_snapshot rather than fabricating
- Be concise. The candidate is busy. Aim for ~600-1000 words total across all fields combined."""


def _build_user_prompt(job: Dict[str, Any]) -> str:
    """Format the job into a user message for the brief generator."""
    tags = ", ".join(job.get("tags") or []) or "(none)"
    jd = (job.get("description") or "").strip()
    if not jd:
        jd = "(no description available from ATS — research the firm and infer role context from the title)"
    elif len(jd) > 3000:
        jd = jd[:3000] + " […truncated]"

    return f"""Produce a HireVue prep brief for this role:

Company: {job['company']}
Role title: {job['title']}
Location: {job.get('location') or 'unspecified'}
Category tags: {tags}
ATS URL: {job.get('url') or 'n/a'}

Job description:
{jd}

Return the JSON brief only."""


def generate_brief(job: Dict[str, Any], max_searches: int = 6) -> Optional[Dict[str, Any]]:
    """
    Call the Claude API to generate a structured prep brief.

    Returns a dict with:
      - brief: parsed JSON brief
      - input_tokens, output_tokens, web_searches: usage stats
      - cost_usd: approximate cost
      - model_used: which model

    Returns None on failure (logged).
    """
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY not set — cannot generate brief")
        return None

    body = {
        "model": MODEL,
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": _build_user_prompt(job)}
        ],
        "tools": [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_searches,
            }
        ],
    }

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        r = requests.post(ANTHROPIC_API_URL, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            log.error("Claude API error %s: %s", r.status_code, r.text[:500])
            return None
        data = r.json()
    except Exception as e:
        log.error("Claude API request failed: %s", e)
        return None

    # Extract the assistant text — last text block (after any tool_use)
    text_parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    if not text_parts:
        log.error("No text in Claude response: %s", str(data)[:500])
        return None
    text = text_parts[-1].strip()

    # Strip code fences if the model wrapped it despite instructions
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    try:
        brief = json.loads(text)
    except json.JSONDecodeError as e:
        log.error("Failed to parse brief JSON: %s\nText was: %s", e, text[:1000])
        return None

    # Pull usage stats for cost calc
    usage = data.get("usage", {}) or {}
    input_tokens   = usage.get("input_tokens", 0)
    output_tokens  = usage.get("output_tokens", 0)
    # Count web searches by inspecting server_tool_use blocks or usage stats
    web_searches = usage.get("server_tool_use", {}).get("web_search_requests", 0)
    if not web_searches:
        # Fallback: count tool_use blocks in content
        web_searches = sum(
            1 for b in data.get("content", [])
            if b.get("type") == "server_tool_use" and b.get("name") == "web_search"
        )

    cost_usd = (
        (input_tokens  / 1_000_000) * INPUT_PRICE_PER_M  +
        (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_M +
        web_searches * WEB_SEARCH_PRICE
    )

    return {
        "brief":         brief,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "web_searches":  web_searches,
        "cost_usd":      round(cost_usd, 4),
        "model_used":    MODEL,
    }
