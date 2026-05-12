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
    # === Quant / Trading ===
    ("twosigma",      "Two Sigma",          ["QUANT"]),
    ("jumptrading",   "Jump Trading",       ["QUANT"]),
    ("hudsonrivertrading", "Hudson River Trading", ["QUANT"]),
    ("imc",           "IMC Trading",        ["QUANT"]),
    ("optiver",       "Optiver",            ["QUANT"]),
    # === PE / HF ===
    ("kkr",           "KKR",                ["PE"]),
    ("blackstone",    "Blackstone",         ["PE", "AM"]),
    # === Asset Mgmt ===
    ("manfinancial", "Man Group",          ["AM", "QUANT"]),
]

# Lever endpoints: (slug, display_name, default_categories)
# URL pattern: https://api.lever.co/v0/postings/{slug}?mode=json
LEVER = [
    ("citadel",      "Citadel",            ["QUANT", "PE"]),
    # Add as you discover them
]

# SmartRecruiters: (slug, display_name, default_categories)
# URL pattern: https://api.smartrecruiters.com/v1/companies/{slug}/postings
SMARTRECRUITERS = [
    # Add as you discover them — many European firms use this
]


# Adzuna UK search queries: (query, where, display_name, default_categories)
# These catch smaller UK firms and job-board postings that do not have clean ATS APIs.
# Keep this targeted; broad searches create noise and may use API quota quickly.
ADZUNA = [
    ("graduate investment analyst",        "London",          "Adzuna — Graduate Investment Analyst",      ["AM", "PE", "IB"]),
    ("asset management graduate",          "United Kingdom",  "Adzuna — Asset Management Graduate",        ["AM"]),
    ("wealth management graduate",         "United Kingdom",  "Adzuna — Wealth Management Graduate",       ["WM"]),
    ("trainee financial adviser",          "United Kingdom",  "Adzuna — Trainee Financial Adviser",        ["WM"]),
    ("corporate finance graduate",         "United Kingdom",  "Adzuna — Corporate Finance Graduate",       ["IB", "AUDIT_TAX"]),
    ("m&a analyst",                        "London",          "Adzuna — M&A Analyst",                      ["IB", "PE"]),
    ("private equity analyst",             "London",          "Adzuna — Private Equity Analyst",           ["PE"]),
    ("junior equity analyst",              "London",          "Adzuna — Junior Equity Analyst",            ["AM"]),
    ("audit graduate",                     "United Kingdom",  "Adzuna — Audit Graduate",                   ["AUDIT_TAX"]),
    ("tax graduate",                       "United Kingdom",  "Adzuna — Tax Graduate",                     ["AUDIT_TAX"]),
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
    for query, where, name, cats in ADZUNA:
        out.append(("adzuna", {"query": query, "where": where, "results_per_page": 25, "pages": 1}, name, cats))
    return out
