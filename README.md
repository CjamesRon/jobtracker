# Job Tracker (v2.2 — multi-user + prep briefs)

Polls public job APIs of major IB / AM / WM / PE / Quant / Big 4 firms every 15 minutes, tags each role to your six CV variants, dedupes, and pings each user's phone via Telegram with **their** preferred categories. A Streamlit dashboard gives each user a private view of their own applications layered over the shared discovery feed.

**New in v2.2: HireVue prep briefs.** One click on any job generates a structured research brief — company snapshot, recent news, role analysis, likely interview themes, "why this firm" angles, and questions to ask them — powered by the Claude API with web search. Each brief takes ~30 seconds and costs ~$0.10. Briefs are cached per-user per-job so subsequent views are free.

Runs on free infrastructure (GitHub Actions + Supabase + Streamlit Community Cloud + Telegram). The only paid component is the Claude API for prep briefs — about £4-5 across a full application season of 50+ briefs.

---

## Architecture (v2.2)

```
   ┌───────────────────────────────────────────────┐
   │  GH Actions cron (every 15m)                  │
   │   poll.py                                     │
   │    ↓                                          │
   │    fetchers / tagger                          │
   │    ↓                                          │
   │    upsert into JOBS (shared)                  │
   │    ↓                                          │
   │    alerter — per-user fan-out → Telegram      │
   └───────────────────────────────────────────────┘

   ┌───────────────────────────────────────────────┐
   │  Dashboard (Streamlit, on-demand per user)    │
   │   login via user_token                        │
   │    ↓                                          │
   │    shared JOBS  +  this user's APPLICATIONS   │
   │    (left-joined)                              │
   │    ↓                                          │
   │    click "Generate prep brief" on any job:    │
   │      prep.py → Claude API + web search        │
   │      result cached in PREP_NOTES              │
   └───────────────────────────────────────────────┘
```

**Tables**: `jobs` (shared) · `users` · `applications` (per-user) · `prep_notes` (per-user-per-job) · `alert_log` (per-user-per-job) · `application_events` (per-application)

---

## Setup (≈30 minutes one-time)

### 1. Supabase

1. Sign up at https://supabase.com, create a project (EU-West region recommended for UK users).
2. SQL Editor → paste `sql/schema.sql` → Run.
3. Generate a random login token for each user. On any machine with Python:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(16))"
   ```
   Do this once per user. Note the tokens down — you'll share them privately.
4. Add your users via the SQL Editor. Run something like:
   ```sql
   insert into users (name, user_token, telegram_chat_id, watch_categories) values
     ('You',    'PASTE_YOUR_TOKEN',    'YOUR_TELEGRAM_CHAT_ID',    '{IB,PE,QUANT,AUDIT_TAX}'),
     ('Friend', 'PASTE_FRIEND_TOKEN',  'FRIENDS_TELEGRAM_CHAT_ID', '{WM,AM,IB}');
   ```
5. Project Settings → API → copy:
   - **Project URL**
   - **service_role key** (KEEP SECRET — bypasses all security)

### 2. Telegram

Each user needs their own `telegram_chat_id` but you can share **one bot** across everyone.

1. You (the admin) message `@BotFather` → `/newbot` → copy the **bot token**.
2. Each user (including you) sends any message to the new bot.
3. For each user, after they've messaged the bot, open in a browser:
   `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
   Find their `"chat":{"id":<NUMBER>}` — that's their chat_id. Paste it into their row in the `users` table.

### 3. GitHub

1. Create a private repo. Push this folder to it.
2. Settings → Secrets → Actions. Add:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `TELEGRAM_BOT_TOKEN`
3. Actions tab → "poll-jobs" → "Run workflow" to test once.

From now on, GitHub runs the poll every 15 minutes for everyone.

### 4. Dashboard

**Option A — Streamlit Community Cloud (one shared URL)**
1. https://share.streamlit.io → connect repo → entry point `dashboard.py`.
2. Secrets:
   ```
   SUPABASE_URL = "https://....supabase.co"
   SUPABASE_SERVICE_KEY = "ey..."
   ```
3. Deploy. Share the URL with your friends. Each person logs in with their own token.

**Option B — Run locally** (per-user, more private)
```bash
pip install -r requirements.txt
export SUPABASE_URL="https://....supabase.co"
export SUPABASE_SERVICE_KEY="ey..."
streamlit run dashboard.py
```

---

## Trust model — read this before adding friends

This is **a small-group tool**, not a hardened multi-tenant SaaS. Specifically:

- The dashboard uses `SUPABASE_SERVICE_KEY` to talk to Supabase, which bypasses row-level security. Filtering by user is enforced *in the dashboard code*, not by the database. A friend who knows your project URL and gets hold of the service key could read everyone's data.
- The `user_token` is closer to a password than to proper auth — long random strings are fine for friends, not for strangers.
- The Supabase project owner (whoever signed up) can see all users' data via the Supabase dashboard. **Make sure your friends are OK with that** before adding them.
- Add friends one at a time and only people you'd genuinely share a flat with. For a wider audience, switch to Supabase Auth with row-level security policies (a couple hours of work — happy to add if needed).

If any of those are problems, go back to Option 1 (each person runs their own copy).

---

## Adding companies

Edit `src/companies.py`. Same as v1:

- **Workday**: extract `host`, `tenant`, `site_id` from the careers URL.
- **Greenhouse**: slug after `boards.greenhouse.io/`.
- **Lever**: slug after `jobs.lever.co/`.
- **SmartRecruiters**: slug after `smartrecruiters.com/`.

Push to GitHub — next poll picks them up.

---

## HireVue prep briefs (v2.2)

Each job in the dashboard has a "Prep brief" expander. First click generates a structured research brief; the result is cached per-user-per-job in the `prep_notes` table so reopening is free.

### Setup (one-time, ~5 min)

1. **Get an Anthropic API key.** https://console.anthropic.com → API Keys → Create. Add ~£10 of credit (covers hundreds of briefs).
2. **Add it as a Streamlit secret**:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   Add the same key to your local environment if running the dashboard locally.
3. **Reload the dashboard.** The prep-brief feature lights up.

You do NOT add this secret to GitHub — the poll script doesn't use it. Briefs are generated on-demand from the dashboard only.

### What a brief contains

- **Company snapshot** — what the firm does, scale, segments, strategic priorities
- **Recent news** — 4-8 items from the last ~60 days with source URLs and dates
- **Role analysis** — what the JD reveals about the specific role and group
- **Likely interview themes** — generic competency areas to expect (no scraped questions)
- **"Why this firm" angles** — 3-5 specific, defensible hooks grounded in recent news/strategy
- **Questions to ask them** — thoughtful questions tied to the firm's current developments
- **Sources** — every URL cited

### Cost

Each brief uses Sonnet 4.6 with web search enabled:
- ~2-3k input tokens × $3/M = ~$0.01
- ~1.5-2k output tokens × $15/M = ~$0.03
- ~5 web searches × $0.01 = ~$0.05
- **Total: ~$0.09-0.12 per brief**

Across 50 applications in a full cycle: roughly **£4-5**. Tracked in the `prep_notes.cost_usd` column so you can audit.

### Design philosophy

Briefs are deliberately structured as **research starting points**, not interview scripts. Reading auto-generated answers verbatim in a HireVue or AC is detectable and will torpedo a candidacy. Use the brief to accelerate your research, then internalise the firm narrative in your own voice. The "why this firm" angles are phrased as starting points to draw on, not lines to read.

The brief generator deliberately does NOT scrape Glassdoor or WallStreetOasis for specific past interview questions — that's the line between "researched well" and "had the questions in advance," and grad recruiters genuinely care. The "likely themes" section gives you generic competency areas to expect (e.g. "valuation methodologies", "deal walk-throughs"), not specific scraped questions.

---

Each user's row in the `users` table controls their experience:

- `watch_categories`: which CV-variant categories trigger alerts. Subset of `{WM, AM, IB, PE, QUANT, AUDIT_TAX}`.
- `alert_seniority`: which levels to alert about. Default `{grad, mid}` (skips VP / Director / MD).
- `telegram_chat_id`: where Telegram alerts go.

Edit directly in the Supabase SQL editor:

```sql
update users
set watch_categories = '{IB,PE}'
where name = 'Friend';
```

---

## What's NOT in this version

- **Auto-form-fill** — browser extension would be the v3 build.
- **LinkedIn scraping** — ToS-banned, will get accounts flagged.
- **Proper auth** — token-based, fine for a small trusted group.
- **Sharing applications between users** — deliberately not. You each track your own.
- **Scraped HireVue questions from Glassdoor/WSO** — deliberately not. Prep briefs cover firm research and likely *themes*, not specific past questions.

---

## Costs

Same as v1 — £0/month at this scale. Supabase free tier handles 5 users with hundreds of jobs comfortably; you'd need to be polling thousands of companies to come close to limits.

---

## Adding a third friend later

```sql
insert into users (name, user_token, telegram_chat_id, watch_categories) values
  ('NewFriend', 'NEW_RANDOM_TOKEN', 'THEIR_CHAT_ID', '{IB,QUANT}');
```

Send them the token + dashboard URL. They log in. Done. No code changes, no redeploy.
