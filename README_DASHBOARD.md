# Premium Dashboard Replacement

Replace your existing `dashboard.py` with this file.

## What this adds

- Cleaner premium dashboard layout
- Login screen
- Sidebar filters
- KPI cards
- Opportunity feed with job cards
- Application status / CV variant / notes saving
- Application pipeline view
- Source and category analytics
- Clean table view + CSV download

## How to install

1. Copy `dashboard.py` into the root of your existing project folder.
2. Commit and push:

```bash
git add dashboard.py
git commit -m "Upgrade Streamlit dashboard"
git push
```

3. Deploy/redeploy on Streamlit Community Cloud using:

```text
Main file path: dashboard.py
```

4. Add Streamlit secrets:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_KEY = "your-service-role-key"
```

Do not put these values directly in the file.
