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
    if ats_type == "job_board":
        return fetch_job_board(**identifier)
    log.error("Unknown ATS type: %s", ats_type)
    return []


# ---------- JOB BOARDS (UK-specific search scraping) ----------
def fetch_job_board(board: str, query: str, location: str) -> List[Dict[str, Any]]:
    """
    Fetch jobs from UK job boards via their public search pages.
    
    This is the grey-area approach: we're reading public search results at
    the same interval a human would (every 15 minutes), parsing the HTML,
    and normalizing to our schema. We're NOT bypassing auth, hitting
    undocumented APIs, or crawling aggressively.
    
    Risk: if a board blocks scraping or rate-limits us, this fetcher will
    fail gracefully and return []. The poll continues for other sources.
    """
    if board == "totaljobs":
        return _fetch_totaljobs(query, location)
    elif board == "brightnetwork":
        return _fetch_brightnetwork(query)
    else:
        log.warning("Unknown job board: %s", board)
        return []


def _fetch_totaljobs(query: str, location: str) -> List[Dict[str, Any]]:
    """
    Totaljobs search page scraping.
    URL pattern: https://www.totaljobs.com/jobs/{query}/in-{location}
    
    We parse the HTML job cards. If the structure changes, this breaks —
    that's the trade-off with scraping. Check logs if Totaljobs jobs stop
    appearing.
    """
    import re
    from urllib.parse import quote_plus
    
    query_slug = query.replace(" ", "-").lower()
    location_slug = location.replace(" ", "-").lower() if location else ""
    
    if location:
        url = f"https://www.totaljobs.com/jobs/{query_slug}/in-{location_slug}"
    else:
        url = f"https://www.totaljobs.com/jobs/{query_slug}"
    
    try:
        r = requests.get(url, headers={**HEADERS, "User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
        if r.status_code != 200:
            log.warning("Totaljobs search %s -> %s", url, r.status_code)
            return []
    except Exception as e:
        log.warning("Totaljobs fetch failed: %s", e)
        return []
    
    html = r.text
    jobs = []
    
    # Totaljobs uses structured <article> tags with data attributes.
    # This is a simplified parser — real HTML parsing would use BeautifulSoup.
    # For now, regex extraction of job cards.
    pattern = re.compile(
        r'<article[^>]*data-job-id="([^"]+)"[^>]*>.*?'
        r'<h2[^>]*>(.*?)</h2>.*?'
        r'<a[^>]*href="([^"]+)"[^>]*>.*?'
        r'<div[^>]*class="[^"]*company[^"]*"[^>]*>(.*?)</div>.*?'
        r'<span[^>]*class="[^"]*location[^"]*"[^>]*>(.*?)</span>',
        re.DOTALL | re.IGNORECASE
    )
    
    matches = pattern.findall(html)
    for job_id, title, href, company, loc in matches:
        # Clean HTML entities
        import html as htmllib
        title = htmllib.unescape(re.sub(r'<[^>]+>', '', title)).strip()
        company = htmllib.unescape(re.sub(r'<[^>]+>', '', company)).strip()
        loc = htmllib.unescape(re.sub(r'<[^>]+>', '', loc)).strip()
        
        full_url = href if href.startswith("http") else f"https://www.totaljobs.com{href}"
        
        jobs.append({
            "external_id": f"totaljobs-{job_id}",
            "title": title,
            "location": loc,
            "url": full_url,
            "description": "",  # would require fetching each job page
            "posted_at": "",
        })
    
    log.info("Totaljobs '%s' in '%s': found %d jobs", query, location, len(jobs))
    return jobs[:50]  # cap at 50 per search to avoid overwhelming the DB


def _fetch_brightnetwork(query: str) -> List[Dict[str, Any]]:
    """
    Bright Network graduate jobs scraping.
    URL: https://www.brightnetwork.co.uk/search/?content_type=jobs&q={query}
    
    Bright Network is UK grad-focused so location filter is implicit.
    """
    import re
    from urllib.parse import quote_plus
    
    url = f"https://www.brightnetwork.co.uk/search/?content_type=jobs&q={quote_plus(query)}"
    
    try:
        r = requests.get(url, headers={**HEADERS, "User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
        if r.status_code != 200:
            log.warning("Bright Network search %s -> %s", url, r.status_code)
            return []
    except Exception as e:
        log.warning("Bright Network fetch failed: %s", e)
        return []
    
    html = r.text
    jobs = []
    
    # Bright Network uses a card-based layout. This is a simplified regex parser.
    # Real implementation would use BeautifulSoup or lxml.
    pattern = re.compile(
        r'<div[^>]*class="[^"]*job-card[^"]*"[^>]*>.*?'
        r'<a[^>]*href="([^"]+)"[^>]*>.*?'
        r'<h3[^>]*>(.*?)</h3>.*?'
        r'<span[^>]*class="[^"]*company[^"]*"[^>]*>(.*?)</span>',
        re.DOTALL | re.IGNORECASE
    )
    
    matches = pattern.findall(html)
    for href, title, company in matches:
        import html as htmllib
        title = htmllib.unescape(re.sub(r'<[^>]+>', '', title)).strip()
        company = htmllib.unescape(re.sub(r'<[^>]+>', '', company)).strip()
        
        full_url = href if href.startswith("http") else f"https://www.brightnetwork.co.uk{href}"
        
        # Extract a pseudo-ID from the URL
        job_id = href.split("/")[-1] if "/" in href else href
        
        jobs.append({
            "external_id": f"brightnetwork-{job_id}",
            "title": title,
            "location": "UK (graduate scheme)",
            "url": full_url,
            "description": "",
            "posted_at": "",
        })
    
    log.info("Bright Network '%s': found %d jobs", query, len(jobs))
    return jobs[:50]
