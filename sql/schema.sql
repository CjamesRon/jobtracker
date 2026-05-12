-- ===================================================================
-- Job Tracker — Multi-user schema (v2)
-- Run this in Supabase: Dashboard → SQL Editor → New query → paste → Run
--
-- TRUST MODEL:
--   * jobs table is shared — every user sees the same discovered jobs
--   * applications table is per-user — your applied/status/CV/notes
--   * users table holds telegram + category preferences per person
--
-- This is appropriate for a small trusted group (2-5 friends). For a
-- wider audience, swap to Supabase Auth with row-level security.
-- ===================================================================

-- ---------- USERS ----------
create table if not exists users (
    id              bigserial primary key,
    name            text not null,
    user_token      text not null unique,  -- random string used as a simple auth key
    telegram_chat_id text,                 -- per-user Telegram destination
    watch_categories text[] not null default '{WM,AM,IB,PE,QUANT,AUDIT_TAX}',
    alert_seniority text[] not null default '{grad,mid}',  -- skip senior by default
    created_at      timestamptz not null default now()
);

-- ---------- JOBS (shared) ----------
create table if not exists jobs (
    id              bigserial primary key,
    company         text not null,
    external_id     text not null,
    ats_type        text not null,

    title           text not null,
    location        text,
    url             text,
    description     text,
    posted_at_raw   text,

    tags            text[] not null default '{}',
    seniority       text,
    is_uk           boolean default false,

    first_seen_at   timestamptz not null default now(),

    unique (company, external_id)
);

create index if not exists idx_jobs_first_seen on jobs (first_seen_at desc);
create index if not exists idx_jobs_tags       on jobs using gin (tags);
create index if not exists idx_jobs_uk         on jobs (is_uk) where is_uk = true;

-- ---------- APPLICATIONS (per-user) ----------
-- One row per (user, job) once the user engages with that job.
-- If no row exists for you on a job, status is implicitly "new".
create table if not exists applications (
    id          bigserial primary key,
    user_id     bigint not null references users(id) on delete cascade,
    job_id      bigint not null references jobs(id) on delete cascade,

    status      text not null default 'saved',  -- saved / applied / oa / hirevue / final / offer / rejected / withdrew
    cv_variant  text,                            -- WM / AM / IB / PE / QUANT / AUDIT_TAX
    applied_at  timestamptz,
    notes       text,

    updated_at  timestamptz not null default now(),

    unique (user_id, job_id)
);

create index if not exists idx_apps_user   on applications (user_id, updated_at desc);
create index if not exists idx_apps_status on applications (user_id, status);

-- ---------- APPLICATION EVENTS ----------
create table if not exists application_events (
    id              bigserial primary key,
    application_id  bigint not null references applications(id) on delete cascade,
    event_type      text not null,
    event_at        timestamptz not null default now(),
    notes           text,
    attachments     jsonb
);

create index if not exists idx_events_app on application_events (application_id, event_at desc);

-- ---------- PREP NOTES (per-application HireVue briefs) ----------
-- One brief per (user, job). Generated on-demand from the dashboard.
-- We cache aggressively — regenerate only if the user clicks "refresh".
create table if not exists prep_notes (
    id              bigserial primary key,
    user_id         bigint not null references users(id) on delete cascade,
    job_id          bigint not null references jobs(id) on delete cascade,

    -- The structured brief, stored as JSON for flexibility:
    --   { "company_snapshot": "...",
    --     "recent_news": [{"title":"...","url":"...","date":"...","summary":"..."}],
    --     "role_analysis": "...",
    --     "likely_themes": ["...", "..."],
    --     "why_this_firm_angles": ["...", "..."],
    --     "questions_to_ask": ["...", "..."],
    --     "sources": ["url1", "url2"]
    --   }
    brief           jsonb not null,

    -- Metadata for cost/freshness tracking
    model_used      text,             -- e.g. "claude-sonnet-4-6"
    input_tokens    int,
    output_tokens   int,
    web_searches    int,
    cost_usd        numeric(8,4),     -- approximate, computed at generation time

    generated_at    timestamptz not null default now(),
    refreshed_at    timestamptz,      -- updated when the user clicks "refresh"

    unique (user_id, job_id)
);

create index if not exists idx_prep_user on prep_notes (user_id, generated_at desc);

-- ---------- ALERT LOG ----------
-- Per-user record of which jobs we've already pinged about,
-- so we don't double-alert if the same user runs the poll twice.
create table if not exists alert_log (
    user_id     bigint not null references users(id) on delete cascade,
    job_id      bigint not null references jobs(id) on delete cascade,
    alerted_at  timestamptz not null default now(),
    primary key (user_id, job_id)
);

-- ===================================================================
-- Seed your users. EDIT BEFORE RUNNING.
-- Generate a random user_token per person — they'll need it to log in.
-- (You can use: python -c "import secrets; print(secrets.token_urlsafe(16))")
-- ===================================================================
-- insert into users (name, user_token, telegram_chat_id, watch_categories) values
--   ('You',    'PASTE_RANDOM_TOKEN_HERE', '123456789', '{IB,PE,QUANT,AUDIT_TAX}'),
--   ('Friend', 'PASTE_RANDOM_TOKEN_HERE', '987654321', '{WM,AM,IB}')
-- on conflict (user_token) do nothing;

-- ---------- BASIC RLS HARDENING ----------
-- This app currently uses the Supabase service_role key server-side, which bypasses RLS.
-- Enabling RLS here still protects you if the anon/publishable key is ever used accidentally.
alter table users enable row level security;
alter table jobs enable row level security;
alter table applications enable row level security;
alter table application_events enable row level security;
alter table prep_notes enable row level security;
alter table alert_log enable row level security;
