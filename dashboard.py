"""
Premium Streamlit dashboard for the UK Finance Job Tracker.

Replace your existing dashboard.py with this file.

Requires existing tables:
- users
- jobs
- applications
- alert_log

Uses Supabase service_role key server-side via Streamlit secrets/env vars.
"""

import os
import sys
import html
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Config
# -----------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}

CATEGORIES = ["WM", "AM", "IB", "PE", "QUANT", "AUDIT_TAX"]
STATUSES = ["new", "saved", "applied", "oa", "hirevue", "final", "offer", "rejected", "withdrew"]
STATUS_LABELS = {
    "new": "New",
    "saved": "Saved",
    "applied": "Applied",
    "oa": "Online Assessment",
    "hirevue": "HireVue",
    "final": "Final Round",
    "offer": "Offer",
    "rejected": "Rejected",
    "withdrew": "Withdrew",
}

st.set_page_config(
    page_title="UK Finance Job Tracker",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    :root {
        --navy: #0F172A;
        --muted: #64748B;
        --card: #FFFFFF;
        --line: #E2E8F0;
        --soft: #F8FAFC;
        --teal: #0F766E;
        --coral: #EA580C;
        --purple: #6D28D9;
    }

    .main .block-container {
        padding-top: 1.35rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    .hero {
        background: radial-gradient(circle at 10% 20%, rgba(45, 212, 191, 0.18), transparent 30%),
                    radial-gradient(circle at 90% 10%, rgba(124, 58, 237, 0.16), transparent 32%),
                    linear-gradient(135deg, #0F172A 0%, #111827 55%, #1E1B4B 100%);
        color: white;
        border-radius: 24px;
        padding: 26px 30px;
        margin-bottom: 18px;
        box-shadow: 0 20px 50px rgba(15, 23, 42, 0.18);
    }

    .hero h1 {
        margin: 0 0 8px 0;
        font-size: 2.05rem;
        letter-spacing: -0.04em;
        line-height: 1.05;
    }

    .hero p {
        color: #CBD5E1;
        margin: 0;
        font-size: 0.98rem;
    }

    .metric-card {
        border: 1px solid var(--line);
        background: var(--card);
        border-radius: 18px;
        padding: 16px 16px;
        box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06);
    }

    .metric-label {
        color: var(--muted);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 700;
        margin-bottom: 4px;
    }

    .metric-value {
        color: var(--navy);
        font-size: 1.72rem;
        font-weight: 800;
        line-height: 1;
    }

    .job-card {
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 18px 18px 14px 18px;
        margin-bottom: 14px;
        background: white;
        box-shadow: 0 8px 30px rgba(15, 23, 42, 0.055);
    }

    .job-topline {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 18px;
        margin-bottom: 8px;
    }

    .job-title {
        font-size: 1.05rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #0F172A;
        margin-bottom: 2px;
    }

    .job-company {
        color: #475569;
        font-size: 0.92rem;
    }

    .pill {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 4px 9px;
        margin: 2px 4px 2px 0;
        font-size: 0.75rem;
        font-weight: 700;
        border: 1px solid #E2E8F0;
        background: #F8FAFC;
        color: #334155;
        white-space: nowrap;
    }

    .pill-teal { background: #ECFDF5; color: #047857; border-color: #A7F3D0; }
    .pill-purple { background: #F5F3FF; color: #6D28D9; border-color: #DDD6FE; }
    .pill-orange { background: #FFF7ED; color: #C2410C; border-color: #FED7AA; }
    .pill-blue { background: #EFF6FF; color: #1D4ED8; border-color: #BFDBFE; }
    .pill-red { background: #FEF2F2; color: #B91C1C; border-color: #FECACA; }
    .pill-grey { background: #F1F5F9; color: #475569; border-color: #E2E8F0; }

    .small-muted {
        color: #64748B;
        font-size: 0.84rem;
    }

    .section-title {
        margin-top: 6px;
        margin-bottom: 8px;
        color: #0F172A;
        font-weight: 850;
        letter-spacing: -0.025em;
        font-size: 1.2rem;
    }

    .sidebar-note {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 12px 13px;
        font-size: 0.88rem;
        color: #475569;
    }

    a {
        text-decoration: none;
    }

    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #E2E8F0;
        padding: 14px 14px;
        border-radius: 18px;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Helpers
# -----------------------------
def require_config() -> bool:
    if not SUPABASE_URL or not SERVICE_KEY:
        st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY. Add them to Streamlit secrets/environment variables.")
        st.code(
            """
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_KEY = "your-service-role-key"
            """.strip(),
            language="toml",
        )
        return False
    return True


def safe_text(value, fallback="—"):
    if value is None:
        return fallback
    s = str(value).strip()
    return s if s else fallback


def esc(value):
    return html.escape(safe_text(value, ""))


def parse_dt(value):
    if not value:
        return None
    try:
        return pd.to_datetime(value, utc=True)
    except Exception:
        return None


def relative_time(value):
    dt = parse_dt(value)
    if dt is None:
        return "unknown"
    now = pd.Timestamp.now(tz="UTC")
    delta = now - dt
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = int(delta.total_seconds() // 3600)
    if hours >= 1:
        return f"{hours}h ago"
    mins = max(1, int(delta.total_seconds() // 60))
    return f"{mins}m ago"


def status_class(status):
    if status in {"offer"}:
        return "pill-teal"
    if status in {"final", "hirevue", "oa"}:
        return "pill-purple"
    if status in {"applied", "saved"}:
        return "pill-blue"
    if status in {"rejected", "withdrew"}:
        return "pill-red"
    return "pill-grey"


def category_pills(tags):
    tags = tags or []
    if not isinstance(tags, list):
        tags = []
    return " ".join(f'<span class="pill pill-teal">{esc(t)}</span>' for t in tags)


def supabase_get(path, timeout=30):
    url = f"{SUPABASE_URL}{path}"
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    return r


def supabase_post(path, payload, prefer="return=minimal,resolution=merge-duplicates", timeout=20):
    url = f"{SUPABASE_URL}{path}"
    headers = {**HEADERS, "Prefer": prefer}
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    return r


# -----------------------------
# Auth
# -----------------------------
@st.cache_data(ttl=300, show_spinner=False)
def authenticate(token: str):
    if not token:
        return None
    token_q = quote(token.strip(), safe="")
    r = supabase_get(f"/rest/v1/users?user_token=eq.{token_q}&select=*&limit=1", timeout=15)
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None


def login_screen():
    st.markdown(
        """
        <div class="hero">
            <h1>UK Finance Job Tracker</h1>
            <p>Private opportunity radar for graduate roles, boutique firms, job-board searches, and your application pipeline.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1.1, 1, 1.1])
    with c2:
        st.subheader("Log in")
        token = st.text_input("Access token", type="password", placeholder="Paste your private user token")
        if st.button("Enter dashboard", use_container_width=True):
            user = authenticate(token)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid token. Check your users table in Supabase.")


if "user" not in st.session_state:
    st.session_state.user = None

if not require_config():
    st.stop()

if st.session_state.user is None:
    login_screen()
    st.stop()

user = st.session_state.user
USER_ID = user["id"]


# -----------------------------
# Data
# -----------------------------
@st.cache_data(ttl=60, show_spinner=False)
def fetch_jobs(
    user_id: int,
    days: int = 14,
    uk_only: bool = True,
    category: str = "(all)",
    ats_type: str = "(all)",
    limit: int = 1000,
):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    params = [
        "select=*,applications(id,status,cv_variant,applied_at,notes,updated_at)",
        f"applications.user_id=eq.{user_id}",
        "order=first_seen_at.desc",
        f"limit={limit}",
        f"first_seen_at=gte.{quote(since)}",
    ]

    if uk_only:
        params.append("is_uk=eq.true")

    if category and category != "(all)":
        params.append(f"tags=cs.{{{quote(category)}}}")

    if ats_type and ats_type != "(all)":
        params.append(f"ats_type=eq.{quote(ats_type)}")

    r = supabase_get("/rest/v1/jobs?" + "&".join(params), timeout=40)

    if r.status_code != 200:
        st.error(f"Supabase fetch failed: {r.status_code}")
        st.code(r.text[:1000])
        return pd.DataFrame()

    rows = r.json()
    for row in rows:
        apps = row.get("applications") or []
        if apps:
            app = apps[0]
            row["application_id"] = app.get("id")
            row["status"] = app.get("status") or "new"
            row["cv_variant"] = app.get("cv_variant")
            row["applied_at"] = app.get("applied_at")
            row["notes"] = app.get("notes")
            row["application_updated_at"] = app.get("updated_at")
        else:
            row["application_id"] = None
            row["status"] = "new"
            row["cv_variant"] = None
            row["applied_at"] = None
            row["notes"] = ""
            row["application_updated_at"] = None

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    if "tags" not in df:
        df["tags"] = [[] for _ in range(len(df))]

    df["first_seen_dt"] = pd.to_datetime(df["first_seen_at"], errors="coerce", utc=True)
    df["company_clean"] = df["company"].fillna("Unknown")
    df["title_clean"] = df["title"].fillna("Untitled role")
    df["location_clean"] = df["location"].fillna("Location not listed")
    df["source_clean"] = df["ats_type"].fillna("unknown")
    return df


@st.cache_data(ttl=120, show_spinner=False)
def fetch_user_stats(user_id: int):
    # Minimal read of applications for pipeline stats
    r = supabase_get(f"/rest/v1/applications?user_id=eq.{user_id}&select=status,cv_variant,applied_at,updated_at", timeout=20)
    if r.status_code == 200:
        return pd.DataFrame(r.json())
    return pd.DataFrame()


def save_application(user_id: int, job_id: int, status: str, cv_variant: str | None, notes: str | None):
    body = {
        "user_id": user_id,
        "job_id": int(job_id),
        "status": status,
        "cv_variant": None if cv_variant in (None, "—", "") else cv_variant,
        "notes": notes or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if status == "applied":
        body["applied_at"] = datetime.now(timezone.utc).isoformat()

    r = supabase_post(
        "/rest/v1/applications?on_conflict=user_id,job_id",
        body,
        prefer="return=minimal,resolution=merge-duplicates",
        timeout=20,
    )

    if r.status_code not in (200, 201, 204):
        st.error(f"Save failed: {r.status_code}")
        st.code(r.text[:1000])
        return False

    st.cache_data.clear()
    return True


def refresh_user():
    # Re-read user preferences if updated in Supabase
    token = user.get("user_token", "")
    st.session_state.user = authenticate(token)
    st.cache_data.clear()


# -----------------------------
# Header + Sidebar
# -----------------------------
st.markdown(
    f"""
    <div class="hero">
        <h1>UK Finance Job Tracker</h1>
        <p>Logged in as <strong>{esc(user.get("name"))}</strong>. Track jobs, filter by CV variant, and keep your application pipeline clean.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Filters")

    search_text = st.text_input("Search", placeholder="Company, role, keyword...")
    days = st.selectbox("Seen within", [1, 3, 7, 14, 30, 60, 90], index=3)
    uk_only = st.checkbox("UK only", value=True)

    category = st.selectbox("Category", ["(all)"] + CATEGORIES)
    status_filter = st.selectbox("Application status", ["(all)"] + STATUSES)

    st.markdown("---")
    st.markdown("### View")
    card_limit = st.slider("Max cards shown", 10, 200, 60, step=10)

    st.markdown("---")
    st.markdown(
        f"""
        <div class="sidebar-note">
        <strong>Your alert categories</strong><br>
        {", ".join(user.get("watch_categories") or [])}<br><br>
        <strong>Alert seniority</strong><br>
        {", ".join(user.get("alert_seniority") or [])}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    if st.button("Log out", use_container_width=True):
        st.session_state.user = None
        st.cache_data.clear()
        st.rerun()


df = fetch_jobs(USER_ID, days=days, uk_only=uk_only, category=category)

if not df.empty:
    source_options = ["(all)"] + sorted([x for x in df["source_clean"].dropna().unique().tolist() if x])
else:
    source_options = ["(all)"]

with st.sidebar:
    source_filter = st.selectbox("Source / ATS", source_options)

if source_filter != "(all)" and not df.empty:
    df = df[df["source_clean"] == source_filter]

if status_filter != "(all)" and not df.empty:
    df = df[df["status"] == status_filter]

if search_text.strip() and not df.empty:
    q = search_text.strip().lower()
    search_cols = ["company_clean", "title_clean", "location_clean", "description"]
    mask = pd.Series(False, index=df.index)
    for col in search_cols:
        if col in df:
            mask = mask | df[col].fillna("").str.lower().str.contains(q, na=False)
    df = df[mask]


# -----------------------------
# Dashboard KPIs
# -----------------------------
if df.empty:
    st.info("No jobs match the current filters. Try widening the date range or turning off UK-only.")
    st.stop()

new_count = int((df["status"] == "new").sum())
saved_count = int((df["status"] == "saved").sum())
applied_count = int((df["status"] == "applied").sum())
interview_count = int(df["status"].isin(["oa", "hirevue", "final"]).sum())

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Visible jobs", f"{len(df):,}")
m2.metric("New", f"{new_count:,}")
m3.metric("Saved", f"{saved_count:,}")
m4.metric("Applied", f"{applied_count:,}")
m5.metric("Interview stage", f"{interview_count:,}")

tabs = st.tabs(["Opportunity feed", "Application pipeline", "Source analytics", "Table view"])


# -----------------------------
# Opportunity Feed
# -----------------------------
with tabs[0]:
    st.markdown('<div class="section-title">Opportunity feed</div>', unsafe_allow_html=True)
    st.caption("Use the card controls to save roles, choose the CV variant, and add notes.")

    shown = df.head(card_limit).copy()

    for _, row in shown.iterrows():
        job_id = int(row["id"])
        title = esc(row.get("title_clean"))
        company = esc(row.get("company_clean"))
        location = esc(row.get("location_clean"))
        url = safe_text(row.get("url"), "")
        source = esc(row.get("source_clean"))
        status = safe_text(row.get("status"), "new")
        seniority = esc(row.get("seniority") or "unknown")
        seen = relative_time(row.get("first_seen_at"))
        tags_html = category_pills(row.get("tags"))

        link_html = f'<a href="{esc(url)}" target="_blank">{title}</a>' if url else title

        st.markdown(
            f"""
            <div class="job-card">
                <div class="job-topline">
                    <div>
                        <div class="job-title">{link_html}</div>
                        <div class="job-company">{company} · {location}</div>
                    </div>
                    <div>
                        <span class="pill {status_class(status)}">{esc(STATUS_LABELS.get(status, status))}</span>
                    </div>
                </div>
                <div style="margin-top: 8px;">
                    {tags_html}
                    <span class="pill pill-purple">{source}</span>
                    <span class="pill pill-orange">{seniority}</span>
                    <span class="pill pill-grey">Seen {esc(seen)}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("Update this role", expanded=False):
            with st.form(f"job_form_{job_id}", clear_on_submit=False):
                c1, c2, c3 = st.columns([1, 1, 2])

                with c1:
                    current_status = row.get("status") if row.get("status") in STATUSES else "new"
                    new_status = st.selectbox(
                        "Status",
                        STATUSES,
                        index=STATUSES.index(current_status),
                        format_func=lambda s: STATUS_LABELS.get(s, s),
                        key=f"status_{job_id}",
                    )

                with c2:
                    current_cv = row.get("cv_variant") if row.get("cv_variant") in CATEGORIES else "—"
                    new_cv = st.selectbox(
                        "CV variant",
                        ["—"] + CATEGORIES,
                        index=(["—"] + CATEGORIES).index(current_cv),
                        key=f"cv_{job_id}",
                    )

                with c3:
                    notes = st.text_area(
                        "Notes",
                        value=safe_text(row.get("notes"), ""),
                        height=92,
                        placeholder="Deadline, application angle, recruiter name, next step...",
                        key=f"notes_{job_id}",
                    )

                c4, c5 = st.columns([1, 5])
                submitted = c4.form_submit_button("Save", use_container_width=True)
                if url:
                    c5.markdown(f"[Open job posting]({url})")

                if submitted:
                    ok = save_application(USER_ID, job_id, new_status, new_cv, notes)
                    if ok:
                        st.success("Saved.")
                        st.rerun()

    if len(df) > card_limit:
        st.info(f"Showing {card_limit} of {len(df)} matching jobs. Increase 'Max cards shown' in the sidebar to see more.")


# -----------------------------
# Application Pipeline
# -----------------------------
with tabs[1]:
    st.markdown('<div class="section-title">Application pipeline</div>', unsafe_allow_html=True)

    pipeline_df = df[df["status"] != "new"].copy()
    if pipeline_df.empty:
        st.info("No saved/applied roles yet. Save roles from the Opportunity feed to build your pipeline.")
    else:
        status_counts = pipeline_df["status"].value_counts().reindex(STATUSES, fill_value=0)
        st.bar_chart(status_counts)

        for status in STATUSES:
            chunk = pipeline_df[pipeline_df["status"] == status]
            if chunk.empty:
                continue
            with st.expander(f"{STATUS_LABELS.get(status, status)} · {len(chunk)}", expanded=status in ["saved", "applied", "oa", "hirevue", "final"]):
                table = chunk[["company_clean", "title_clean", "location_clean", "cv_variant", "applied_at", "notes", "url"]].rename(
                    columns={
                        "company_clean": "Company",
                        "title_clean": "Role",
                        "location_clean": "Location",
                        "cv_variant": "CV",
                        "applied_at": "Applied at",
                        "notes": "Notes",
                        "url": "URL",
                    }
                )
                st.dataframe(table, use_container_width=True, hide_index=True)


# -----------------------------
# Source Analytics
# -----------------------------
with tabs[2]:
    st.markdown('<div class="section-title">Source analytics</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Jobs by source")
        source_counts = df["source_clean"].value_counts()
        st.bar_chart(source_counts)

    with c2:
        st.subheader("Jobs by category")
        tag_counts = {cat: int(df["tags"].apply(lambda tags: cat in (tags or [])).sum()) for cat in CATEGORIES}
        st.bar_chart(pd.Series(tag_counts))

    st.subheader("Companies appearing most often")
    company_counts = df["company_clean"].value_counts().head(20)
    st.dataframe(
        company_counts.rename("Jobs").reset_index().rename(columns={"index": "Company", "company_clean": "Company"}),
        use_container_width=True,
        hide_index=True,
    )


# -----------------------------
# Table View
# -----------------------------
with tabs[3]:
    st.markdown('<div class="section-title">Clean table view</div>', unsafe_allow_html=True)

    table_cols = [
        "company_clean",
        "title_clean",
        "location_clean",
        "status",
        "cv_variant",
        "source_clean",
        "seniority",
        "first_seen_at",
        "url",
    ]

    available_cols = [c for c in table_cols if c in df.columns]
    table = df[available_cols].rename(
        columns={
            "company_clean": "Company",
            "title_clean": "Role",
            "location_clean": "Location",
            "status": "Status",
            "cv_variant": "CV",
            "source_clean": "Source",
            "seniority": "Seniority",
            "first_seen_at": "First seen",
            "url": "URL",
        }
    )

    st.dataframe(table, use_container_width=True, hide_index=True)

    csv = table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download current view as CSV",
        data=csv,
        file_name="job_tracker_view.csv",
        mime="text/csv",
        use_container_width=False,
    )
