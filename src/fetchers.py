"""
Fetchers for each ATS type.

Each fetcher returns a list of dicts with the same schema:
  {
    "external_id": str,    # ATS's own ID for this job (used for dedup)
    "title": str,
    "location": str,
    "url": str,            # direct apply URL
    "description": str,    # plain text JD (may be empty for some ATS)
    "posted_at": str|None, # ISO date string if available
  }

If an endpoint is unreachable, the fetcher logs and returns [] —
we never want one bad company to crash the whole poll.
"""
import logging
import os
import requests
from typing import List, Dict, Any

log = logging.getLogger(__name__)

# Polite user-agent — we want firms to see this as a real browser-equivalent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PersonalJobTracker/1.0)",
    "Accept": "application/json",
}
TIMEOUT = 20


def _safe_get(url: str, **kwargs) -> Dict[str, Any] | None:
    """GET with error handling — returns parsed JSON or None on failure."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
        if r.status_code != 200:
            log.warning("GET %s -> %s", url, r.status_code)
            return None
        return r.json()
    except Exception as e:
        log.warning("GET %s failed: %s", url, e)
        return None


def _safe_post(url: str, json_body: dict) -> Dict[str, Any] | None:
    """POST with error handling — Workday uses POST for its job search API."""
    try:
        r = requests.post(url, headers={**HEADERS, "Content-Type": "application/json"},
                          json=json_body, timeout=TIMEOUT)
        if r.status_code != 200:
            log.warning("POST %s -> %s", url, r.status_code)
            return None
        return r.json()
    except Exception as e:
        log.warning("POST %s failed: %s", url, e)
        return None


# ---------- WORKDAY ----------
def fetch_workday(host: str, tenant: str, site_id: str) -> List[Dict[str, Any]]:
    """
    Workday's public job-search endpoint. Tenant + site_id come from the
    careers page URL. We page through up to 500 jobs (10 pages * 50).
    """
    base = f"https://{tenant}.{host}.myworkdayjobs.com"
    url = f"{base}/wday/cxs/{tenant}/{site_id}/jobs"

    jobs = []
    offset = 0
    while offset < 500:
        body = {"appliedFacets": {}, "limit": 50, "offset": offset, "searchText": ""}
        data = _safe_post(url, body)
        if not data or "jobPostings" not in data:
            break
        postings = data["jobPostings"]
        if not postings:
            break
        for p in postings:
            external_path = p.get("externalPath", "")
            jobs.append({
                "external_id": external_path or p.get("bulletFields", [""])[0],
                "title": p.get("title", "").strip(),
                "location": p.get("locationsText", "").strip(),
                "url": f"{base}{external_path}" if external_path else "",
                "description": "",  # would need a second call per job; skip for speed
                "posted_at": p.get("postedOn", ""),  # often "Posted Today" etc, not ISO
            })
        offset += 50
        if len(postings) < 50:
            break
    return jobs


# ---------- GREENHOUSE ----------
def fetch_greenhouse(slug: str) -> List[Dict[str, Any]]:
    """Greenhouse public job board API. Returns all jobs in one call."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = _safe_get(url)
    if not data or "jobs" not in data:
        return []
    jobs = []
    for j in data["jobs"]:
        # content field is HTML; strip tags crudely for keyword matching
        content = j.get("content", "") or ""
        import re, html
        plain = html.unescape(re.sub(r"<[^>]+>", " ", content))
        jobs.append({
            "external_id": str(j.get("id", "")),
            "title": j.get("title", "").strip(),
            "location": (j.get("location") or {}).get("name", "").strip(),
            "url": j.get("absolute_url", ""),
            "description": plain[:4000],  # truncate to keep DB rows small
            "posted_at": j.get("updated_at", ""),
        })
    return jobs


# ---------- LEVER ----------
def fetch_lever(slug: str) -> List[Dict[str, Any]]:
    """Lever public postings API."""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = _safe_get(url)
    if not isinstance(data, list):
        return []
    jobs = []
    for j in data:
        cats = j.get("categories", {}) or {}
        jobs.append({
            "external_id": j.get("id", ""),
            "title": j.get("text", "").strip(),
            "location": cats.get("location", "").strip(),
            "url": j.get("hostedUrl", ""),
            "description": (j.get("descriptionPlain", "") or "")[:4000],
            "posted_at": j.get("createdAt", ""),  # epoch ms
        })
    return jobs


# ---------- SMARTRECRUITERS ----------
def fetch_smartrecruiters(slug: str) -> List[Dict[str, Any]]:
    """SmartRecruiters public postings API."""
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
    data = _safe_get(url)
    if not data or "content" not in data:
        return []
    jobs = []
    for j in data["content"]:
        loc = j.get("location", {}) or {}
        loc_str = ", ".join(filter(None, [loc.get("city"), loc.get("country")]))
        jobs.append({
            "external_id": j.get("id", ""),
            "title": j.get("name", "").strip(),
            "location": loc_str,
            "url": j.get("ref", ""),
            "description": "",
            "posted_at": j.get("releasedDate", ""),
        })
    return jobs


# ---------- ADZUNA UK ----------
def fetch_adzuna(query: str, where: str = "United Kingdom", results_per_page: int = 25, pages: int = 1) -> List[Dict[str, Any]]:
    """
    Adzuna public jobs API for UK-wide job board searches.

    This is used to catch smaller firms and roles that are not exposed through
    a clean company ATS endpoint. Credentials are read from environment vars:
      ADZUNA_APP_ID, ADZUNA_APP_KEY
    """
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()

    if not app_id or not app_key:
        log.warning("ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping Adzuna query: %s", query)
        return []

    jobs: List[Dict[str, Any]] = []
    for page in range(1, pages + 1):
        url = f"https://api.adzuna.com/v1/api/jobs/gb/search/{page}"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": results_per_page,
            "what": query,
            "where": where,
            "content-type": "application/json",
        }
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
            if r.status_code != 200:
                log.warning("ADZUNA %s -> %s %s", query, r.status_code, r.text[:200])
                break
            data = r.json()
        except Exception as e:
            log.warning("ADZUNA %s failed: %s", query, e)
            break

        results = data.get("results", []) or []
        if not results:
            break

        for j in results:
            company = ((j.get("company") or {}).get("display_name") or "Unknown Company").strip()
            location = ((j.get("location") or {}).get("display_name") or "").strip()
            title = (j.get("title") or "").strip()
            url = j.get("redirect_url") or j.get("adref") or ""
            external_id = str(j.get("id") or url or title)

            if not title or not external_id:
                continue

            desc = j.get("description") or ""
            jobs.append({
                "external_id": external_id,
                "company": company,
                "title": title,
                "location": location,
                "url": url,
                "description": desc[:4000],
                "posted_at": j.get("created", ""),
            })

        if len(results) < results_per_page:
            break

    return jobs


def dispatch(ats_type: str, identifier: dict) -> List[Dict[str, Any]]:
    """Route to the right fetcher."""
    if ats_type == "workday":
        return fetch_workday(**identifier)
    if ats_type == "greenhouse":
        return fetch_greenhouse(**identifier)
    if ats_type == "lever":
        return fetch_lever(**identifier)
    if ats_type == "smartrecruiters":
        return fetch_smartrecruiters(**identifier)
    if ats_type == "adzuna":
        return fetch_adzuna(**identifier)
    log.error("Unknown ATS type: %s", ats_type)
    return []
