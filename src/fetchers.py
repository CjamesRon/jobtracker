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
    
    IMPORTANT: Workday requires specific headers (Accept-Language, Referer)
    or it returns 422/400 errors. These headers mimic what the actual
    careers page sends.
    """
    base = f"https://{tenant}.{host}.myworkdayjobs.com"
    url = f"{base}/wday/cxs/{tenant}/{site_id}/jobs"
    
    # Workday-specific headers — required as of 2026
    workday_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "en-US",
        "Referer": f"{base}/en-US/{site_id}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    jobs = []
    offset = 0
    while offset < 500:
        body = {"appliedFacets": {}, "limit": 50, "offset": offset, "searchText": ""}
        
        try:
            r = requests.post(url, headers=workday_headers, json=body, timeout=TIMEOUT)
            if r.status_code != 200:
                log.warning("POST %s -> %s", url, r.status_code)
                break
            data = r.json()
        except Exception as e:
            log.warning("POST %s failed: %s", url, e)
            break
            
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


# ---------- REED.CO.UK API ----------
def fetch_reed(api_key: str, keywords: str, location: str = "") -> List[Dict[str, Any]]:
    """
    Reed.co.uk is the UK's #1 job board with 300,000+ jobs.
    FREE API with no rate limits.
    
    API Docs: https://www.reed.co.uk/developers/Jobseeker
    Sign up for free API key: https://www.reed.co.uk/developers/Jobseeker
    
    The API uses Basic Auth with the API key as username (password empty).
    """
    import base64
    
    url = "https://www.reed.co.uk/api/1.0/search"
    params = {
        "keywords": keywords,
        "resultsToTake": 100,  # Max per request
        "resultsToSkip": 0,
    }
    
    if location:
        params["locationName"] = location
        params["distanceFromLocation"] = 30  # 30 miles radius
    
    # Reed uses Basic Auth with API key as username, empty password
    auth_string = f"{api_key}:".encode()
    b64_auth = base64.b64encode(auth_string).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "User-Agent": "PersonalJobTracker/1.0",
    }
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            log.warning("GET Reed API %s -> %s", url, r.status_code)
            return []
        data = r.json()
    except Exception as e:
        log.warning("Reed API fetch failed: %s", e)
        return []
    
    results = data.get("results", [])
    jobs = []
    
    for job in results:
        job_id = job.get("jobId")
        if not job_id:
            continue
            
        jobs.append({
            "external_id": f"reed-{job_id}",
            "title": job.get("jobTitle", ""),
            "location": job.get("locationName", ""),
            "url": job.get("jobUrl", f"https://www.reed.co.uk/jobs/{job_id}"),
            "description": job.get("jobDescription", ""),  # brief description from search
            "posted_at": "",  # Not in search results, would need details API
        })
    
    log.info("Reed '%s' in '%s': found %d jobs", keywords, location, len(jobs))
    return jobs


# ---------- ADZUNA API ----------
def fetch_adzuna(app_id: str, app_key: str, what: str, where: str = "UK") -> List[Dict[str, Any]]:
    """
    Adzuna job search API - global aggregator with UK focus.
    FREE API with rate limits (contact Adzuna if you hit limits).
    
    API Docs: https://developer.adzuna.com/overview
    Sign up: https://developer.adzuna.com/signup
    
    Adzuna aggregates from multiple job boards, so you may see duplicates
    with Reed/Indeed, but it also catches jobs they don't have.
    """
    url = "https://api.adzuna.com/v1/api/jobs/gb/search/1"  # page 1, UK (gb)
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 50,  # Max 50 per request
        "what": what,  # keywords
        "where": where,  # location
        "sort_by": "date",  # newest first
    }
    
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            log.warning("GET Adzuna API %s -> %s", url, r.status_code)
            return []
        data = r.json()
    except Exception as e:
        log.warning("Adzuna API fetch failed: %s", e)
        return []
    
    results = data.get("results", [])
    jobs = []
    
    for job in results:
        job_id = job.get("id")
        if not job_id:
            continue
        
        # Adzuna provides redirect URLs, not direct apply links
        redirect_url = job.get("redirect_url", "")
        
        jobs.append({
            "external_id": f"adzuna-{job_id}",
            "title": job.get("title", ""),
            "location": job.get("location", {}).get("display_name", ""),
            "url": redirect_url,
            "description": job.get("description", ""),
            "posted_at": job.get("created", ""),  # ISO date string
        })
    
    log.info("Adzuna '%s' in '%s': found %d jobs", what, where, len(jobs))
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
    if ats_type == "reed":
        return fetch_reed(**identifier)
    if ats_type == "adzuna":
        return fetch_adzuna(**identifier)
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
