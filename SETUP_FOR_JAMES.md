# Job Tracker Setup — Do This In Order

## 0. Use this folder as the repo root

Your repo must contain these paths:

- `src/poll.py`
- `sql/schema.sql`
- `.github/workflows/poll.yml`
- `dashboard.py`
- `requirements.txt`

Do not upload the flattened outer ZIP by mistake.

## 1. Supabase

1. Create a Supabase project.
2. Open SQL Editor.
3. Open `sql/schema.sql` locally.
4. Copy the contents of the file.
5. Paste the actual SQL into Supabase and run it.

Do not paste the text `sql/schema.sql`; that is only a file path.

## 2. Create your login token

Run locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(16))"
```

Save the output privately.

## 3. Create a Telegram bot

1. Message `@BotFather` on Telegram.
2. Run `/newbot`.
3. Copy the bot token.
4. Send any message to your new bot.
5. Open this in a browser, replacing the token:

```text
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

Find your chat id in the JSON under `chat.id`.

## 4. Insert yourself into Supabase

Run this in Supabase SQL Editor after replacing the placeholders:

```sql
insert into users (name, user_token, telegram_chat_id, watch_categories)
values (
  'James',
  'PASTE_YOUR_RANDOM_LOGIN_TOKEN',
  'PASTE_YOUR_TELEGRAM_CHAT_ID',
  '{IB,PE,QUANT,AUDIT_TAX,WM,AM}'
)
on conflict (user_token) do nothing;
```

## 5. Push to GitHub

Create a private GitHub repo, then from this folder:

```bash
git init
git add .
git commit -m "Initial job tracker"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

## 6. Add GitHub Actions secrets

In GitHub:

Settings → Secrets and variables → Actions → New repository secret

Add:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `TELEGRAM_BOT_TOKEN`

Do not add the Supabase service key to public code.

## 7. Test the poller

GitHub → Actions → `poll-jobs` → Run workflow.

If it works, it will insert jobs into the `jobs` table and send Telegram alerts only for matching jobs.

## 8. Deploy Streamlit dashboard

Streamlit Community Cloud:

1. Connect the GitHub repo.
2. Entry point: `dashboard.py`.
3. Add secrets:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SERVICE_KEY = "YOUR_SUPABASE_SERVICE_ROLE_KEY"
ANTHROPIC_API_KEY = "OPTIONAL_FOR_PREP_BRIEFS"
```

4. Deploy.
5. Log in using your random `user_token`.

## 9. Local test option

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SUPABASE_URL="https://YOUR_PROJECT.supabase.co"
export SUPABASE_SERVICE_KEY="YOUR_SERVICE_KEY"
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
python src/poll.py
streamlit run dashboard.py
```

## Important security note

This version uses the Supabase service role key server-side. Keep the repo private. Keep Streamlit secrets private. Do not put the service role key in browser JavaScript or anywhere a friend can see it.
