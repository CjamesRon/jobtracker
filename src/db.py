"""
Supabase database layer (multi-user version).

The jobs table is shared across all users. Per-user state lives in
the applications table. The alert_log table tracks which jobs we've
already pinged each user about, so re-running the poll doesn't spam.
"""
import os
import logging
import requests
from typing import List, Dict, Any
from urllib.parse import quote

log = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    log.warning("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — DB calls will fail")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def _hdr(prefer: str = "return=representation") -> Dict[str, str]:
    return {**_HEADERS, "Prefer": prefer}


# ---------- JOBS (shared) ----------
def upsert_jobs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Insert new jobs. Returns the rows actually inserted (used by alerter).
    Strategy: query existing (company, external_id) pairs, insert only new.
    """
    if not rows:
        return []

    existing = set()
    companies = list({r["company"] for r in rows})
    for company in companies:
        ext_ids = [r["external_id"] for r in rows if r["company"] == company]
        if not ext_ids:
            continue
        in_list = ",".join(f'"{eid}"' for eid in ext_ids)
        url = (f"{SUPABASE_URL}/rest/v1/jobs"
               f"?company=eq.{quote(company)}"
               f"&external_id=in.({in_list})"
               f"&select=id,company,external_id")
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
            if r.status_code == 200:
                for row in r.json():
                    existing.add((row["company"], row["external_id"]))
        except Exception as e:
            log.warning("Existing-check exception: %s", e)

    new_rows = [r for r in rows if (r["company"], r["external_id"]) not in existing]
    if not new_rows:
        return []

    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/jobs",
                          headers=_hdr("return=representation"),
                          json=new_rows, timeout=60)
        if r.status_code in (200, 201):
            inserted = r.json()
            log.info("Inserted %d new jobs", len(inserted))
            return inserted
        log.error("Insert failed: %s %s", r.status_code, r.text[:500])
        return []
    except Exception as e:
        log.error("Insert exception: %s", e)
        return []


# ---------- USERS ----------
def get_all_users() -> List[Dict[str, Any]]:
    """Return all users (called by alerter to fan out alerts)."""
    url = f"{SUPABASE_URL}/rest/v1/users?select=*"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.error("get_all_users failed: %s", e)
    return []


def get_user_by_token(token: str) -> Dict[str, Any] | None:
    """Used by the dashboard to authenticate a user_token."""
    if not token:
        return None
    url = f"{SUPABASE_URL}/rest/v1/users?user_token=eq.{quote(token)}&select=*&limit=1"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception as e:
        log.error("get_user_by_token failed: %s", e)
    return None


# ---------- APPLICATIONS (per-user) ----------
def upsert_application(user_id: int, job_id: int, **fields) -> bool:
    """
    Upsert this user's application row for this job.
    fields can include: status, cv_variant, applied_at, notes
    """
    body = {"user_id": user_id, "job_id": job_id, **fields}
    url = (f"{SUPABASE_URL}/rest/v1/applications"
           f"?on_conflict=user_id,job_id")
    try:
        r = requests.post(url,
                          headers=_hdr("return=minimal,resolution=merge-duplicates"),
                          json=body, timeout=15)
        return r.status_code in (200, 201, 204)
    except Exception as e:
        log.error("upsert_application failed: %s", e)
        return False


# ---------- ALERT LOG (per-user) ----------
def filter_unalerted(user_id: int, job_ids: List[int]) -> List[int]:
    """
    Return only the job_ids we haven't yet alerted this user about.
    Used by the alerter before sending Telegram messages.
    """
    if not job_ids:
        return []
    in_list = ",".join(str(j) for j in job_ids)
    url = (f"{SUPABASE_URL}/rest/v1/alert_log"
           f"?user_id=eq.{user_id}&job_id=in.({in_list})&select=job_id")
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        if r.status_code == 200:
            already = {row["job_id"] for row in r.json()}
            return [j for j in job_ids if j not in already]
    except Exception as e:
        log.warning("filter_unalerted exception: %s", e)
    return job_ids  # fail-open: better to alert than miss


def record_alerts(user_id: int, job_ids: List[int]) -> None:
    """Record that we've alerted this user about these jobs."""
    if not job_ids:
        return
    rows = [{"user_id": user_id, "job_id": j} for j in job_ids]
    url = f"{SUPABASE_URL}/rest/v1/alert_log"
    try:
        requests.post(url,
                      headers=_hdr("return=minimal,resolution=ignore-duplicates"),
                      json=rows, timeout=15)
    except Exception as e:
        log.warning("record_alerts exception: %s", e)


# ---------- PREP NOTES (per-user, per-job) ----------
def get_prep_note(user_id: int, job_id: int) -> Dict[str, Any] | None:
    """Return the cached prep note for (user, job), or None if not generated."""
    url = (f"{SUPABASE_URL}/rest/v1/prep_notes"
           f"?user_id=eq.{user_id}&job_id=eq.{job_id}&select=*&limit=1")
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception as e:
        log.error("get_prep_note failed: %s", e)
    return None


def upsert_prep_note(user_id: int, job_id: int, brief: dict, stats: dict) -> bool:
    """Save a generated prep note. stats: input_tokens, output_tokens, web_searches, cost_usd, model_used."""
    from datetime import datetime, timezone
    body = {
        "user_id":       user_id,
        "job_id":        job_id,
        "brief":         brief,
        "model_used":    stats.get("model_used"),
        "input_tokens":  stats.get("input_tokens"),
        "output_tokens": stats.get("output_tokens"),
        "web_searches":  stats.get("web_searches"),
        "cost_usd":      stats.get("cost_usd"),
        "refreshed_at":  datetime.now(timezone.utc).isoformat(),
    }
    url = f"{SUPABASE_URL}/rest/v1/prep_notes?on_conflict=user_id,job_id"
    try:
        r = requests.post(url,
                          headers=_hdr("return=minimal,resolution=merge-duplicates"),
                          json=body, timeout=30)
        return r.status_code in (200, 201, 204)
    except Exception as e:
        log.error("upsert_prep_note failed: %s", e)
        return False
