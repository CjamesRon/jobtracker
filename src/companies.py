"""
Companies to poll, organised by ATS (Applicant Tracking System).

Each entry: (slug, display_name, [category_hints])

CATEGORIES: WM (Wealth Mgmt), AM (Asset Mgmt), IB (Investment Banking),
            PE (Private Equity), QUANT, AUDIT_TAX (Big 4)

The category_hints are *defaults* — actual category gets refined per-job
by the tagger in tagger.py based on job title and description keywords.

HOW TO ADD A COMPANY:
  - Workday: find their careers page URL, e.g.
      https://goldmansachs.wd1.myworkdayjobs.com/en-US/GS_External
    Extract: tenant="goldmansachs", site_id="GS_External", host="wd1"
  - Greenhouse: their board URL is boards.greenhouse.io/{slug}
  - Lever: jobs.lever.co/{slug}
  - SmartRecruiters: smartrecruiters.com/{slug}

Start small (5-10 companies), expand as you confirm endpoints work.
"""

# Workday endpoints: (host, tenant, site_id, display_name, default_categories)
# URL pattern: https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site_id}/jobs
WORKDAY = [
    # === Investment Banking ===
    ("wd1", "goldmansachs", "GS_EXTERNAL",   "Goldman Sachs",      ["IB", "AM", "WM"]),
    ("wd5", "jpmorganchase", "jpmc",         "JPMorgan Chase",     ["IB", "AM", "WM"]),
    ("wd1", "ms",            "External",     "Morgan Stanley",     ["IB", "AM", "WM"]),
    ("wd1", "citi",          "2",            "Citi",               ["IB", "AM"]),
    ("wd3", "bofa",          "Lateral-US",   "Bank of America",    ["IB"]),

    # === Asset Management ===
    ("wd1", "blackrock",     "BlackRock",    "BlackRock",          ["AM", "WM"]),
    ("wd3", "schroders",     "schrodersexp", "Schroders",          ["AM", "WM"]),
    ("wd3", "mandg",         "MAndGcareers", "M&G",                ["AM", "WM"]),

    # === Big 4 Audit & Tax ===
    ("wd3", "deloitte",      "Deloitte_DCS", "Deloitte UK",        ["AUDIT_TAX"]),
    ("wd3", "pwc",           "Global_Experienced_Careers", "PwC UK", ["AUDIT_TAX"]),
    ("wd3", "ey",            "EYGlobalCareers", "EY UK",           ["AUDIT_TAX"]),
    ("wd3", "kpmg",          "KPMG_Careers", "KPMG UK",            ["AUDIT_TAX"]),
]

# Greenhouse endpoints: (board_slug, display_name, default_categories)
# URL pattern: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
GREENHOUSE = [
    # === Quant / Trading (VERIFIED WORKING) ===
    ("jumptrading",   "Jump Trading",       ["QUANT"]),
    ("imc",           "IMC Trading",        ["QUANT"]),
    ("optiver",       "Optiver",            ["QUANT"]),
    
    # === DISABLED (404ing - firms moved to different ATS or use different slugs) ===
    # ("twosigma",      "Two Sigma",          ["QUANT"]),  # Now uses careers.twosigma.com (custom ATS)
    # ("hudsonrivertrading", "Hudson River Trading", ["QUANT"]),  # Slug wrong or moved
    # ("kkr",           "KKR",                ["PE"]),  # Slug wrong or moved
    # ("blackstone",    "Blackstone",         ["PE", "AM"]),  # Slug wrong or moved
    # ("manfinancial", "Man Group",          ["AM", "QUANT"]),  # Slug wrong or moved
]

# Lever endpoints: (slug, display_name, default_categories)
# URL pattern: https://api.lever.co/v0/postings/{slug}?mode=json
LEVER = [
    # === DISABLED (404ing) ===
    # ("citadel",      "Citadel",            ["QUANT", "PE"]),  # Slug wrong or Citadel moved to different ATS
]

# SmartRecruiters: (slug, display_name, default_categories)
# URL pattern: https://api.smartrecruiters.com/v1/companies/{slug}/postings
SMARTRECRUITERS = [
    # Add as you discover them — many European firms use this
]

# Job Boards (UK-specific, uses search scraping)
# These are public job boards where many smaller WM/AM firms post.
# Format: (board_name, search_query, location, default_categories)
JOB_BOARDS = [
    # === DISABLED (Totaljobs timing out after 20s, Bright Network returning 403 Forbidden) ===
    # Both boards appear to be detecting/blocking automated access as of May 2026.
    # If you want to re-enable, increase TIMEOUT in fetchers.py to 30+ seconds for Totaljobs,
    # and add session cookies for Bright Network.
    
    # ("totaljobs", "wealth management", "London", ["WM"]),
    # ("totaljobs", "asset management", "London", ["AM"]),
    # ("totaljobs", "private banking", "London", ["WM"]),
    # ("brightnetwork", "wealth", "", ["WM"]),
    # ("brightnetwork", "asset management", "", ["AM"]),
    # ("brightnetwork", "investment banking", "", ["IB"]),
]

# Reed.co.uk API (UK's #1 job board - FREE API, 300k+ jobs)
# Format: (api_key, keywords, location, default_categories)
# Get your FREE API key at: https://www.reed.co.uk/developers/Jobseeker
# 
# SETUP: Add your Reed API key as a GitHub secret "REED_API_KEY"
# Then update poll.yml to pass it as an environment variable.
REED_SEARCHES = [
    ("wealth management", "London", ["WM"]),
    ("wealth manager", "London", ["WM"]),
    ("private banking", "London", ["WM"]),
    ("private banker", "London", ["WM"]),
    ("asset management", "London", ["AM"]),
    ("investment management", "London", ["AM"]),
    ("investment banking", "London", ["IB"]),
    ("investment banker", "London", ["IB"]),
    ("private equity", "London", ["PE"]),
    ("audit", "London", ["AUDIT_TAX"]),
    ("tax", "London", ["AUDIT_TAX"]),
]

# Adzuna API (Global aggregator with UK focus - FREE API)
# Format: (app_id, app_key, what, where, default_categories)
# Get your FREE API credentials at: https://developer.adzuna.com/signup
#
# SETUP: Add Adzuna credentials as GitHub secrets:
#   - ADZUNA_APP_ID
#   - ADZUNA_APP_KEY
# Then update poll.yml to pass them as environment variables.
#
# NOTE: Adzuna aggregates from multiple boards, so you may see some duplicates
# with Reed, but it also catches jobs Reed doesn't have. Worth running both.
ADZUNA_SEARCHES = [
    ("wealth management", "London", ["WM"]),
    ("private banking", "London", ["WM"]),
    ("asset management", "London", ["AM"]),
    ("investment banking", "London", ["IB"]),
    ("private equity", "London", ["PE"]),
]


def all_companies():
    """Return a flat list of (ats_type, identifier_dict, name, default_cats)."""
    out = []
    for host, tenant, site_id, name, cats in WORKDAY:
        out.append(("workday", {"host": host, "tenant": tenant, "site_id": site_id}, name, cats))
    for slug, name, cats in GREENHOUSE:
        out.append(("greenhouse", {"slug": slug}, name, cats))
    for slug, name, cats in LEVER:
        out.append(("lever", {"slug": slug}, name, cats))
    for slug, name, cats in SMARTRECRUITERS:
        out.append(("smartrecruiters", {"slug": slug}, name, cats))
    
    # Add job boards (currently disabled)
    for board_name, query, location, cats in JOB_BOARDS:
        display_name = f"{board_name.title()}: {query}"
        if location:
            display_name += f" ({location})"
        out.append(("job_board", {"board": board_name, "query": query, "location": location}, display_name, cats))
    
    # Add Reed API searches
    import os
    reed_api_key = os.environ.get("REED_API_KEY", "")
    if reed_api_key:
        for keywords, location, cats in REED_SEARCHES:
            display_name = f"Reed: {keywords}"
            if location:
                display_name += f" ({location})"
            out.append(("reed", {"api_key": reed_api_key, "keywords": keywords, "location": location}, display_name, cats))
    else:
        # Warn once that Reed is disabled
        import logging
        logging.warning("REED_API_KEY not set — Reed searches disabled. Get free key at https://www.reed.co.uk/developers/Jobseeker")
    
    # Add Adzuna API searches
    adzuna_app_id = os.environ.get("ADZUNA_APP_ID", "")
    adzuna_app_key = os.environ.get("ADZUNA_APP_KEY", "")
    if adzuna_app_id and adzuna_app_key:
        for what, where, cats in ADZUNA_SEARCHES:
            display_name = f"Adzuna: {what}"
            if where:
                display_name += f" ({where})"
            out.append(("adzuna", {"app_id": adzuna_app_id, "app_key": adzuna_app_key, "what": what, "where": where}, display_name, cats))
    else:
        # Warn once that Adzuna is disabled
        import logging
        logging.warning("ADZUNA_APP_ID/ADZUNA_APP_KEY not set — Adzuna searches disabled. Get free API at https://developer.adzuna.com/signup")
    
    return out
