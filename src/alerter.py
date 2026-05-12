"""
Multi-user Telegram alerter.

One shared bot (single TELEGRAM_BOT_TOKEN in env) sends messages to
multiple chat_ids — one per user, stored in the users table.

For each newly-inserted job we:
  1. Determine which users care about it (category match, seniority, UK)
  2. Filter out (user, job) pairs that have already been alerted
  3. Send a per-user Telegram message grouped by category
  4. Record the alerts so we don't double-ping
"""
import os
import logging
import requests
from typing import List, Dict, Any
from collections import defaultdict

from db import get_all_users, filter_unalerted, record_alerts

log = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _send(chat_id: str, text: str) -> bool:
    """Send a Telegram message. Chunks if too long. Returns success."""
    if not BOT_TOKEN or not chat_id:
        print(f"[ALERT — no Telegram for chat_id={chat_id}]\n" + text)
        return False
    ok = True
    for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown",
                      "disable_web_page_preview": True},
                timeout=15,
            )
            if r.status_code != 200:
                log.warning("Telegram send to %s failed: %s %s",
                            chat_id, r.status_code, r.text[:200])
                ok = False
        except Exception as e:
            log.warning("Telegram exception for %s: %s", chat_id, e)
            ok = False
    return ok


def _matches_user(job: Dict[str, Any], user: Dict[str, Any]) -> bool:
    """Does this job match this user's alert preferences?"""
    if not job.get("is_uk", False):
        return False
    watch_cats = set(user.get("watch_categories") or [])
    if not any(t in watch_cats for t in (job.get("tags") or [])):
        return False
    allowed_seniority = set(user.get("alert_seniority") or ["grad", "mid"])
    if job.get("seniority") not in allowed_seniority:
        return False
    return True


def _format_message(jobs: List[Dict[str, Any]], user_name: str) -> str:
    """Format the Telegram message body for one user."""
    by_cat = defaultdict(list)
    for j in jobs:
        primary = (j.get("tags") or ["OTHER"])[0]
        by_cat[primary].append(j)

    lines = [f"🎯 *{len(jobs)} new jobs for {user_name}*"]
    for cat, cat_jobs in sorted(by_cat.items()):
        lines.append(f"\n*— {cat} ({len(cat_jobs)}) —*")
        for j in cat_jobs[:10]:
            title = j["title"][:80]
            loc = j.get("location", "") or "—"
            url = j.get("url", "")
            lines.append(f"• [{title}]({url})\n  {j['company']} · {loc}")
        if len(cat_jobs) > 10:
            lines.append(f"  …and {len(cat_jobs) - 10} more")
    return "\n".join(lines)


def alert_new_jobs(new_jobs: List[Dict[str, Any]]) -> None:
    """Fan out alerts: for each user, filter to their preferences and send."""
    if not new_jobs:
        return

    users = get_all_users()
    if not users:
        log.warning("No users found — nothing to alert")
        return

    for user in users:
        user_id = user["id"]
        user_name = user["name"]
        chat_id = user.get("telegram_chat_id")

        matched = [j for j in new_jobs if _matches_user(j, user)]
        if not matched:
            continue

        # Don't re-alert jobs we already pinged this user about
        matched_ids = [j["id"] for j in matched]
        unalerted_ids = set(filter_unalerted(user_id, matched_ids))
        to_send = [j for j in matched if j["id"] in unalerted_ids]
        if not to_send:
            log.info("All %d matches for %s were already alerted",
                     len(matched), user_name)
            continue

        text = _format_message(to_send, user_name)
        if chat_id and _send(chat_id, text):
            record_alerts(user_id, [j["id"] for j in to_send])
            log.info("Alerted %s about %d jobs", user_name, len(to_send))
        elif not chat_id:
            log.info("User %s has no telegram_chat_id — skipping", user_name)
