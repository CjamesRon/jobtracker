"""
Streamlit dashboard — multi-user version with HireVue prep briefs.

Login: user types their personal user_token (from the users table).
Each job row gets a 'Prep brief' expander. First click generates the brief
via the Claude API (web search enabled, ~30s, ~$0.10). Subsequent views
read from cache. A 'Refresh' button regenerates if needed.
"""
import os
import sys
import json
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from urllib.parse import quote

# Make src/ importable so we can use the prep generator and db helpers
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from prep import generate_brief  # noqa: E402
from db import get_prep_note, upsert_prep_note  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY  = os.environ.get("SUPABASE_SERVICE_KEY", "")

CATEGORIES = ["WM", "AM", "IB", "PE", "QUANT", "AUDIT_TAX"]
STATUSES   = ["new", "saved", "applied", "oa", "hirevue", "final", "offer", "rejected", "withdrew"]

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}

st.set_page_config(page_title="Job Tracker", layout="wide", page_icon="🎯")


# ---------- Auth ----------
def authenticate(token: str):
    if not token or not SUPABASE_URL or not SERVICE_KEY:
        return None
    url = f"{SUPABASE_URL}/rest/v1/users?user_token=eq.{quote(token)}&select=*&limit=1"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception as e:
        st.error(f"Auth error: {e}")
    return None


if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🎯 Job Tracker")
    st.write("Enter your access token to log in.")
    token = st.text_input("Token", type="password", key="login_token")
    if st.button("Log in"):
        user = authenticate(token.strip())
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Invalid token.")
    st.stop()

user = st.session_state.user
USER_ID = user["id"]


# ---------- Data fetch ----------
@st.cache_data(ttl=60)
def fetch_jobs(user_id: int, status_filter=None, category_filter=None, days=7, uk_only=True):
    params = [
        "select=*,applications(status,cv_variant,applied_at,notes,id)",
        f"applications.user_id=eq.{user_id}",
        "order=first_seen_at.desc",
        "limit=500",
    ]
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    params.append(f"first_seen_at=gte.{since}")
    if uk_only:
        params.append("is_uk=eq.true")
    if category_filter and category_filter != "(all)":
        params.append(f"tags=cs.{{{category_filter}}}")

    url = f"{SUPABASE_URL}/rest/v1/jobs?" + "&".join(params)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            st.error(f"Fetch failed: {r.status_code} {r.text[:200]}")
            return pd.DataFrame()
        rows = r.json()
    except Exception as e:
        st.error(f"Fetch exception: {e}")
        return pd.DataFrame()

    for row in rows:
        apps = row.get("applications") or []
        if apps:
            a = apps[0]
            row["status"]     = a.get("status") or "new"
            row["cv_variant"] = a.get("cv_variant")
            row["applied_at"] = a.get("applied_at")
            row["notes"]      = a.get("notes")
        else:
            row["status"]     = "new"
            row["cv_variant"] = None
            row["applied_at"] = None
            row["notes"]      = None

    df = pd.DataFrame(rows)
    if not df.empty and status_filter and status_filter != "(all)":
        df = df[df["status"] == status_filter]
    return df


def save_application(user_id: int, job_id: int, **fields):
    body = {"user_id": user_id, "job_id": job_id, **fields,
            "updated_at": datetime.utcnow().isoformat()}
    url = f"{SUPABASE_URL}/rest/v1/applications?on_conflict=user_id,job_id"
    try:
        r = requests.post(url,
                          headers={**HEADERS,
                                   "Prefer": "return=minimal,resolution=merge-duplicates"},
                          json=body, timeout=15)
        return r.status_code in (200, 201, 204)
    except Exception as e:
        st.error(f"Save failed: {e}")
        return False


# ---------- Prep brief rendering ----------
def render_brief(brief: dict, meta: dict | None = None):
    """Render a structured prep brief in the dashboard."""
    if not isinstance(brief, dict):
        st.warning("Brief is malformed.")
        st.json(brief)
        return

    if brief.get("company_snapshot"):
        st.markdown("##### Company snapshot")
        st.write(brief["company_snapshot"])

    news = brief.get("recent_news") or []
    if news:
        st.markdown("##### Recent news")
        for item in news:
            title = item.get("title", "(untitled)")
            url = item.get("url", "")
            date = item.get("date", "")
            summary = item.get("summary", "")
            if url:
                st.markdown(f"- **[{title}]({url})** · *{date}* — {summary}")
            else:
                st.markdown(f"- **{title}** · *{date}* — {summary}")

    if brief.get("role_analysis"):
        st.markdown("##### What this role appears to involve")
        st.write(brief["role_analysis"])

    themes = brief.get("likely_themes") or []
    if themes:
        st.markdown("##### Likely interview themes")
        for t in themes:
            st.markdown(f"- {t}")

    angles = brief.get("why_this_firm_angles") or []
    if angles:
        st.markdown("##### 'Why this firm' angles to consider")
        st.caption("Use as starting points — phrase in your own voice for the interview.")
        for a in angles:
            st.markdown(f"- {a}")

    qs = brief.get("questions_to_ask") or []
    if qs:
        st.markdown("##### Questions you could ask them")
        for q in qs:
            st.markdown(f"- {q}")

    sources = brief.get("sources") or []
    if sources:
        with st.expander(f"Sources ({len(sources)})"):
            for s in sources:
                st.markdown(f"- {s}")

    if meta:
        cost = meta.get("cost_usd") or 0
        ws = meta.get("web_searches") or 0
        ts = meta.get("refreshed_at") or meta.get("generated_at") or ""
        st.caption(f"Generated {ts[:16]} · {ws} web searches · cost ${cost:.3f}")


def maybe_generate_brief(user_id: int, job: dict, force: bool = False) -> dict | None:
    """Get cached brief or generate a new one. Returns the full prep_note row."""
    if not force:
        cached = get_prep_note(user_id, job["id"])
        if cached:
            return cached

    with st.spinner("Generating brief — web search + analysis (~30s)…"):
        result = generate_brief(job)
    if not result:
        st.error("Brief generation failed. Check ANTHROPIC_API_KEY and logs.")
        return None

    saved = upsert_prep_note(user_id, job["id"], result["brief"], result)
    if not saved:
        st.warning("Brief generated but failed to save to DB. Showing anyway.")
    # Re-fetch to get the canonical row (with timestamps)
    return get_prep_note(user_id, job["id"]) or {
        "brief": result["brief"],
        "cost_usd": result["cost_usd"],
        "web_searches": result["web_searches"],
        "generated_at": datetime.utcnow().isoformat(),
    }


# ---------- UI ----------
col_h1, col_h2 = st.columns([5, 1])
col_h1.title(f"🎯 Job Tracker — {user['name']}")
if col_h2.button("Log out"):
    st.session_state.user = None
    st.rerun()

col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
with col1:
    sel_cat = st.selectbox("Category", ["(all)"] + CATEGORIES)
with col2:
    sel_status = st.selectbox("Status", ["(all)"] + STATUSES, index=1)
with col3:
    sel_days = st.selectbox("Posted within (days)", [1, 3, 7, 14, 30], index=2)
with col4:
    uk_only = st.checkbox("UK only", value=True)

df = fetch_jobs(USER_ID, status_filter=sel_status, category_filter=sel_cat,
                days=sel_days, uk_only=uk_only)

if df.empty:
    st.info("No jobs match. Either the poll hasn't run yet, or filters are too tight.")
    st.stop()

cols = st.columns(len(CATEGORIES) + 1)
cols[0].metric("Total", len(df))
for i, cat in enumerate(CATEGORIES, start=1):
    count = df["tags"].apply(lambda t: cat in (t or [])).sum() if "tags" in df else 0
    cols[i].metric(cat, count)

st.divider()

# Track which jobs have their prep expander open in this session
if "prep_open" not in st.session_state:
    st.session_state.prep_open = set()

for _, row in df.iterrows():
    job_id = row["id"]
    with st.container(border=True):
        c1, c2, c3 = st.columns([4, 1, 1])
        with c1:
            tags_str = " ".join(f"`{t}`" for t in (row.get("tags") or []))
            st.markdown(f"**[{row['title']}]({row['url']})** · {row['company']}")
            st.caption(
                f"{row.get('location') or '—'}  ·  {tags_str}  ·  "
                f"seen {str(row['first_seen_at'])[:16]}"
            )
        with c2:
            new_status = st.selectbox(
                "Status", STATUSES,
                index=STATUSES.index(row["status"]) if row["status"] in STATUSES else 0,
                key=f"st_{job_id}",
                label_visibility="collapsed",
            )
        with c3:
            cv_idx = (CATEGORIES.index(row["cv_variant"]) + 1) if row.get("cv_variant") in CATEGORIES else 0
            cv = st.selectbox(
                "CV", ["—"] + CATEGORIES,
                index=cv_idx,
                key=f"cv_{job_id}",
                label_visibility="collapsed",
            )
        changed = (new_status != row["status"]) or (cv != (row.get("cv_variant") or "—"))
        if changed:
            fields = {"status": new_status}
            if cv != "—":
                fields["cv_variant"] = cv
            if new_status == "applied" and not row.get("applied_at"):
                fields["applied_at"] = datetime.utcnow().isoformat()
            if save_application(USER_ID, job_id, **fields):
                st.cache_data.clear()
                st.rerun()

        # --- Prep brief section ---
        cached_brief = get_prep_note(USER_ID, job_id)
        has_brief = cached_brief is not None
        expander_label = "📝 Prep brief" + (" ✓" if has_brief else "")
        with st.expander(expander_label, expanded=False):
            if not has_brief:
                st.caption("No brief yet. Click below to generate (uses Claude API + web search, ~30s, ~$0.10).")
                if st.button("Generate prep brief", key=f"gen_{job_id}"):
                    note = maybe_generate_brief(USER_ID, row.to_dict(), force=False)
                    if note:
                        render_brief(note["brief"], meta=note)
            else:
                render_brief(cached_brief["brief"], meta=cached_brief)
                if st.button("🔄 Regenerate", key=f"regen_{job_id}", help="Re-run with fresh web search (will overwrite cache)"):
                    note = maybe_generate_brief(USER_ID, row.to_dict(), force=True)
                    if note:
                        st.rerun()
