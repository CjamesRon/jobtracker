"""
Main poll script. Runs on schedule via GitHub Actions.

Flow:
  1. Iterate companies in companies.py
  2. Fetch all jobs via the right ATS fetcher
  3. Tag each job (WM / AM / IB / PE / QUANT / AUDIT_TAX)
  4. Upsert into Supabase jobs table; capture newly-inserted rows (with their ids)
  5. Fan out alerts: each user gets a Telegram message filtered to their prefs

Idempotent: running it twice produces no duplicate jobs and no duplicate alerts
(alert_log is checked per-user before sending).
"""
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from companies import all_companies
from fetchers import dispatch
from tagger import tag_job, seniority, is_uk
from db import upsert_jobs
from alerter import alert_new_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("poll")


def main():
    started = datetime.now(timezone.utc)
    log.info("=== Poll starting at %s ===", started.isoformat())

    all_rows = []
    per_company_counts = {}

    for ats_type, identifier, name, default_cats in all_companies():
        log.info("Fetching %s (%s)…", name, ats_type)
        try:
            jobs = dispatch(ats_type, identifier)
        except Exception as e:
            log.error("Fetcher crashed for %s: %s", name, e)
            jobs = []
        per_company_counts[name] = len(jobs)

        for j in jobs:
            tags = tag_job(j["title"], j.get("description", ""))
            if not tags:
                tags = list(default_cats)

            row = {
                "company": name,
                "external_id": j["external_id"],
                "title": j["title"],
                "location": j.get("location", ""),
                "url": j["url"],
                "description": j.get("description", "")[:4000],
                "posted_at_raw": str(j.get("posted_at") or "")[:50],
                "tags": tags,
                "seniority": seniority(j["title"]),
                "is_uk": is_uk(j.get("location", "")),
                "ats_type": ats_type,
                "first_seen_at": started.isoformat(),
            }
            all_rows.append(row)

    log.info("Total jobs fetched: %d across %d companies",
             len(all_rows), len(per_company_counts))

    # upsert_jobs returns the rows that were newly inserted, INCLUDING the
    # DB-assigned `id` field — alerter needs this for alert_log.
    new_rows = upsert_jobs(all_rows)
    log.info("Newly inserted: %d", len(new_rows))

    alert_new_jobs(new_rows)

    log.info("=== Poll done ===")


if __name__ == "__main__":
    main()
