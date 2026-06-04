"""
Free job scraping — zero cost, multiple Ireland sources.

Sources:
  1. JSearch (RapidAPI)  — Google for Jobs aggregator. Covers LinkedIn, Indeed, Glassdoor,
                           and ALL company career pages. Free: 200 req/month.
                           https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

  2. Adzuna API           — Ireland-specific job board aggregator. Free 250 req/day.
                           https://developer.adzuna.com

  3. Reed API             — UK/Ireland jobs. Free, unlimited.
                           https://www.reed.co.uk/developers

  4. Greenhouse API       — Direct company career pages, no key needed, unlimited free.
                           Covers: Stripe, Intercom, Cloudflare, MongoDB, Datadog, Zendesk...

  5. Indeed Ireland RSS   — Direct feed from ie.indeed.com. Free, no key needed.

  6. Jobs.ie              — Ireland's largest job board. Free HTML scraping.

  7. IrishJobs.ie         — Ireland-specific job board. Free HTML scraping.

  8. Lever ATS            — Career pages for companies using Lever ATS. Free, no key.
"""

import os
import re
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from profile import SEARCH_QUERIES


def _strip_html(text: str) -> str:
    """Remove HTML tags, decode entities, and clean up whitespace."""
    if not text:
        return ""
    import html as _html
    text = _html.unescape(text)                     # &lt; -> <, &amp; -> &, etc.
    text = re.sub(r"<[^>]+>", " ", text)            # strip remaining <tags>
    text = re.sub(r"&[a-z#0-9]+;", " ", text)       # any leftover entities
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Title-level filters ──────────────────────────────────────

# Titles containing these -> not engineering roles
_NON_ENGINEERING = [
    # Sales
    "account executive", "account manager", "account director", "account development",
    "sales representative", "sales manager", "sales engineer", "sales specialist",
    "business development", "pre-sales", "commercial",
    # Marketing
    "marketing manager", "marketing executive", "marketing specialist",
    "campaign manager", "campaign operations", "growth manager", "partnership manager",
    # HR / Recruiting
    "human resources", " hr ", "recruiter", "talent acquisition",
    # Finance / Legal / Compliance
    "finance manager", "financial analyst", "accounting", "accountant",
    "tax", "treasury", "audit", "auditor", "legal counsel", "paralegal",
    "regulatory", "compliance manager", "risk manager",
    # Customer / Support
    "customer success", "customer support", "customer experience",
    # Product / Operations / Management
    "product manager", "product owner", "project manager",
    "operations manager", "office manager",
    # Other non-eng
    "business analyst", "business intelligence", "data analyst",
    "solution consultant", "scrum master", "technical writer",
    "it support", "systems administrator",
    # Non-software engineering disciplines (hardware/physical/domain)
    "civil engineer", "mechanical engineer", "electrical engineer",
    "structural engineer", "highway", "graphic design", "graphic designer",
    "quantity surveyor", "site engineer", "construction",
    # Physical/hardware engineering roles that appear on Reed Ireland
    "manufacturing engineer", "design engineer", "field service engineer",
    "commissioning engineer", "process engineer", "quality engineer",
    "maintenance engineer", "service engineer", "hvac", "estimator",
    "biomedical engineer", "validation engineer", "environmental engineer",
    "qa localization", "medical diagnostic", "localization engineer",
    # Non-software graduate/entry-level roles
    "graduate estimator", "junior structural", "junior mechanical",
    "junior civil", "junior electrical",
]

# Titles containing these -> too senior for entry-level candidate
_TOO_SENIOR = [
    "staff engineer", "staff software", "staff backend", "staff frontend",
    "principal engineer", "principal software", "principal developer",
    "senior engineer", "senior software", "senior backend", "senior frontend",
    "senior developer", "senior java", "senior python", "senior full stack",
    "senior data", "senior ml", "senior ai",
    "lead engineer", "lead developer", "lead software",
    "engineering manager", "director of engineering", "vp of engineering",
    "head of engineering", "head of software", "chief technology",
    "architect ", "solution architect", "enterprise architect",
    "tech lead", "technical lead",
]

# ── Description-level experience requirement filter ──────────

# Matches: "3+ years", "5 years of experience", "5 years of software development",
# "minimum 5 years", "at least 4 years", "5+ yrs", etc.
# Intentionally broad — if a JD says "5+ years" in any context, it's not entry-level.
_SENIOR_EXP_RE = re.compile(
    r'\b([3-9]|1[0-9])\+?\s*years?\b'      # "3 years", "5+ years", "10 years"
    r'|minimum\s*(of\s*)?([3-9]|1[0-9])\s*years?\b'   # "minimum 4 years"
    r'|at\s*least\s*([3-9]|1[0-9])\s*years?\b'        # "at least 5 years"
    r'|\b([3-9]|1[0-9])\+\s*yrs?\b',                  # "5+ yrs"
    re.IGNORECASE,
)

# Range patterns like "2-12+ years", "2-10+ years", "3-5 years"
# Reject if the upper bound is >= 5 (clearly not entry-level)
_EXP_RANGE_RE = re.compile(
    r'\b\d+\s*[-–]\s*(\d+)\+?\s*years?\b',
    re.IGNORECASE,
)

# Stripe-style: "does not include internships/co-op"
_EXCL_INTERN_RE = re.compile(
    r'\bdoes\s*not\s*include\s*(internship|co.?op)\b',
    re.IGNORECASE,
)

# Entry-level positive signals — if present, keep regardless of year count
_ENTRY_SIGNALS_RE = re.compile(
    r'\b(intern|internship|entry.level|entry\s+level|graduate|new\s+grad|fresh(er)?|'
    r'0[-–]2\s*years?|junior|associate\s+engineer|associate\s+developer)\b',
    re.IGNORECASE,
)


def _is_engineering_role(job: dict) -> bool:
    """
    Three-layer filter:
      1. Title contains non-engineering keywords -> reject
      2. Title contains senior/lead/architect keywords -> reject
      3. Description requires 3+ years professional experience -> reject
         (unless the title/description has strong entry-level signals)
    """
    title = (job.get("title") or "").lower()
    desc  = (job.get("description") or "")

    # Layer 1 — non-engineering title
    for phrase in _NON_ENGINEERING:
        if phrase in title:
            print(f"[scraper] Filtered (non-eng title): {job.get('title')}")
            return False

    # Layer 2 — too-senior title
    for phrase in _TOO_SENIOR:
        if phrase in title:
            print(f"[scraper] Filtered (too senior title): {job.get('title')}")
            return False

    # Entry-level override: only from the TITLE — never from description,
    # because descriptions often say "if you're an intern, do NOT apply here"
    # which would falsely look like a positive entry-level signal.
    title_is_entry_level = bool(_ENTRY_SIGNALS_RE.search(title))

    # Layer 3a — description says 3+ years required
    if _SENIOR_EXP_RE.search(desc) and not title_is_entry_level:
        print(f"[scraper] Filtered (3+ yrs required): {job.get('title')}")
        return False

    # Layer 3b — range pattern like "2-12+ years", "2-10+ years": reject if upper bound >= 5
    for m in _EXP_RANGE_RE.finditer(desc):
        upper = int(m.group(1))
        if upper >= 5 and not title_is_entry_level:
            print(f"[scraper] Filtered (range {m.group(0)}): {job.get('title')}")
            return False

    # Layer 3c — description warns interns/new grads not to apply here
    if _EXCL_INTERN_RE.search(desc) and not title_is_entry_level:
        print(f"[scraper] Filtered (excludes intern exp): {job.get('title')}")
        return False

    # Layer 3d — "do not apply" disclaimer for interns/new grads (Stripe-style)
    _DO_NOT_APPLY_RE = re.compile(
        r'(intern|new\s*grad|entry.level).*?please\s*do\s*not\s*apply'
        r'|if\s+you\s+are\s+(an?\s+)?(intern|new\s*grad).*?do\s*not\s*apply',
        re.IGNORECASE | re.DOTALL,
    )
    if _DO_NOT_APPLY_RE.search(desc[:1000]):
        print(f"[scraper] Filtered (do-not-apply disclaimer): {job.get('title')}")
        return False

    return True


def _to_str(val) -> str:
    """Safely coerce any API value to a plain string.
    Some APIs (JSearch, Indeed) return company/location as dicts."""
    if not val:
        return ""
    if isinstance(val, dict):
        return (
            val.get("name")
            or val.get("display_name")
            or val.get("cityName")
            or ", ".join(str(v) for v in val.values() if v)
        )
    return str(val).strip()

RAPIDAPI_KEY   = os.environ.get("RAPIDAPI_KEY", "")
ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_API_KEY = os.environ.get("ADZUNA_API_KEY", "")
REED_API_KEY   = os.environ.get("REED_API_KEY", "")
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY", "")

# Ireland-based companies on Greenhouse ATS — public API, no auth needed
# These companies have significant Dublin/Ireland engineering offices
IRELAND_GREENHOUSE_SLUGS = [
    # Established Dublin engineering hubs
    "stripe", "intercom", "zendesk", "mongodb", "cloudflare", "datadog",
    "gitlab", "squarespace", "twilio", "shopify", "notion", "figma",
    "coinbase", "hubspot", "asana", "brex", "airtable", "anthropic",
    # More Dublin/Ireland tech companies
    "salesforce", "workday", "splunk", "fastly", "okta",
    "hashicorp", "elastic", "confluent", "dbt-labs", "airbyte",
    "vercel", "render", "linear", "retool", "mercury",
    "benchling", "ramp", "rippling", "deel", "remote",
    # Additional companies with Dublin engineering presence
    "pagerduty", "dynatrace", "mimecast", "wayflyer", "flipdish",
    "kitman-labs", "workhuman", "fenergo", "fire", "personio",
    "slack", "zoom", "dropbox", "box", "atlassian",
    "qualtrics", "surveymonkey", "hootsuite", "freshworks", "servicenow",
    "docusign", "zenefits", "greenhouse", "lever", "lattice",
    "amplitude", "mixpanel", "segment", "braze", "iterable",
    "postman", "snyk", "harness", "launchdarkly", "split",
    "samsara", "fleetio", "geotab", "trimble", "esri",
]

# Companies using Lever ATS — active slugs verified
IRELAND_LEVER_SLUGS = [
    "highspot",       # has roles (check location filter)
]

# Multiple targeted JSearch queries to maximise LinkedIn/Indeed/Glassdoor coverage.
# IMPORTANT: Do NOT include "Ireland"/"Dublin" in the query string — it returns 0 results.
# Instead use the `geoid` param for Dublin, and post-filter by location.
# Each query = 1 API credit. Free tier = 200/month (enough for daily full searches).
JSEARCH_QUERIES = [
    "software engineer intern",
    "graduate software engineer",
    "junior java developer",
    "AI engineer intern",
    "backend engineer entry level",
    "full stack developer graduate",
    "new grad software engineer",
    "junior python developer",
]

# Google Geo IDs for filtering to Ireland/Dublin
_IRELAND_GEOIDS = ["2963597", "1014756", "2964179"]  # Dublin, Cork, Ireland
_IRELAND_TERMS = {"ireland", "dublin", "cork", "limerick", "galway", "remote", "emea"}


# ─── 1. JSearch — Google for Jobs (PRIMARY) ───────────────────

def scrape_jsearch(keyword: str, location: str = "Ireland", max_results: int = 20) -> list[dict]:
    """
    JSearch scrapes Google for Jobs — the same aggregated index that Apify uses.
    Returns jobs from LinkedIn, Indeed, Glassdoor, and direct company career pages.
    Free tier: 200 requests/month on RapidAPI.
    """
    if not RAPIDAPI_KEY:
        print("[scraper] JSearch: no RAPIDAPI_KEY, skipping. Get free key at rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch")
        return []

    results = []
    pages   = max(1, max_results // 10)

    for page in range(1, pages + 1):
        try:
            resp = httpx.get(
                "https://jsearch.p.rapidapi.com/search",
                headers={
                    "x-rapidapi-key":  RAPIDAPI_KEY,
                    "x-rapidapi-host": "jsearch.p.rapidapi.com",
                },
                params={
                    "query":          keyword,
                    "page":           str(page),
                    "num_pages":      "1",
                    "date_posted":    "month",
                    "geoid":          "2963597",   # Dublin, Ireland geoid
                    "language":       "en",
                },
                timeout=15,
            )
            resp.raise_for_status()
            jobs = resp.json().get("data", [])
            if not jobs:
                break

            for job in jobs:
                # JSearch returns the direct employer/apply URL — not a portal link
                apply_url = (
                    job.get("job_apply_link")
                    or job.get("job_google_link")
                )
                results.append({
                    "source":      _jsearch_source(job),
                    "title":       _to_str(job.get("job_title")),
                    "company":     _to_str(job.get("employer_name")),
                    "location":    _jsearch_location(job),
                    "description": _strip_html(job.get("job_description") or ""),
                    "url":         apply_url,
                    "salary":      _jsearch_salary(job),
                    "job_type":    job.get("job_employment_type"),
                    "posted_date": job.get("job_posted_at_datetime_utc"),
                })

        except Exception as e:
            print(f"[scraper] JSearch failed for '{keyword}': {e}")
            break

    print(f"[scraper] JSearch -> {len(results)} jobs for '{keyword}'")
    return results[:max_results]


def _jsearch_source(job: dict) -> str:
    publisher = (job.get("job_publisher") or "").lower()
    if "linkedin" in publisher:
        return "LinkedIn"
    if "indeed" in publisher:
        return "Indeed"
    if "glassdoor" in publisher:
        return "Glassdoor"
    if "irishjobs" in publisher:
        return "IrishJobs.ie"
    if "jobs.ie" in publisher:
        return "Jobs.ie"
    raw = job.get("job_publisher") or ""
    return raw if raw else "Company Career Site"


def _jsearch_location(job: dict) -> str:
    parts = [_to_str(job.get("job_city")), _to_str(job.get("job_state")), _to_str(job.get("job_country"))]
    return ", ".join(p for p in parts if p)


def _jsearch_salary(job: dict) -> str:
    mn = job.get("job_min_salary")
    mx = job.get("job_max_salary")
    period = job.get("job_salary_period") or ""
    currency = job.get("job_salary_currency") or "€"
    if mn and mx:
        return f"{currency}{int(mn):,}–{currency}{int(mx):,} {period}".strip()
    return None


# ─── 2. Adzuna API ────────────────────────────────────────────

def scrape_adzuna(keyword: str, location: str = "ireland", max_results: int = 20) -> list[dict]:
    """
    Adzuna free API — UK/Ireland jobs. Free 250 req/day.
    NOTE: Adzuna does not support 'ie' (Ireland) as a country code.
    We use 'gb' (UK) with 'Ireland' as the where param — Adzuna indexes UK+Ireland jobs together.
    """
    if not ADZUNA_APP_ID or not ADZUNA_API_KEY:
        print("[scraper] Adzuna: no credentials, skipping. Register free at developer.adzuna.com")
        return []

    # Adzuna supported countries: at, au, be, br, ca, ch, de, es, fr, gb, in, it, mx, nl, nz, pl, sg, us, za
    # Ireland is covered under 'gb' with a location filter
    results = []
    try:
        resp = httpx.get(
            "https://api.adzuna.com/v1/api/jobs/gb/search/1",
            params={
                "app_id":           ADZUNA_APP_ID,
                "app_key":          ADZUNA_API_KEY,
                "what":             keyword,
                "where":            "Ireland",
                "results_per_page": min(max_results, 50),
                "content-type":     "application/json",
                "sort_by":          "date",
            },
            timeout=15,
        )
        resp.raise_for_status()
        for job in resp.json().get("results", []):
            results.append({
                "source":      "Adzuna",
                "title":       _to_str(job.get("title")),
                "company":     _to_str((job.get("company") or {}).get("display_name")),
                "location":    _to_str((job.get("location") or {}).get("display_name")),
                "description": _strip_html(job.get("description") or ""),
                "url":         job.get("redirect_url"),
                "salary":      _adzuna_salary(job),
                "job_type":    job.get("contract_type"),
                "posted_date": job.get("created"),
            })
    except Exception as e:
        print(f"[scraper] Adzuna failed for '{keyword}': {e}")

    print(f"[scraper] Adzuna -> {len(results)} jobs for '{keyword}'")
    return results[:max_results]


def _adzuna_salary(job):
    mn, mx = job.get("salary_min"), job.get("salary_max")
    if mn and mx:
        return f"€{int(mn):,}–€{int(mx):,}"
    return None


# ─── 3. Reed API ──────────────────────────────────────────────

def _jooble_source_label(src: str) -> str:
    """Map Jooble's originating-board domain to a friendly source label."""
    s = (src or "").lower()
    if "indeed" in s:      return "Indeed"
    if "glassdoor" in s:   return "Glassdoor"
    if "irishjobs" in s:   return "IrishJobs"
    if "jobs.ie" in s:     return "Jobs.ie"
    if "linkedin" in s:    return "LinkedIn"
    if "totaljobs" in s:   return "TotalJobs"
    if "monster" in s:     return "Monster"
    # Otherwise show the originating board name via Jooble
    return f"Jooble ({src})" if src else "Jooble"


def scrape_jooble(keyword: str, location: str = "Ireland", max_results: int = 30) -> list[dict]:
    """
    Jooble aggregator API — covers Indeed, IrishJobs, Glassdoor-syndicated,
    and many other Ireland job boards in one call. FREE but limited to 500
    requests total, so we make ONE request per keyword (no pagination).
    """
    if not JOOBLE_API_KEY:
        return []
    results = []
    try:
        resp = httpx.post(
            f"https://jooble.org/api/{JOOBLE_API_KEY}",
            json={"keywords": keyword, "location": location},
            headers={"Content-type": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"[scraper] Jooble {resp.status_code} for '{keyword}'")
            return []
        for job in (resp.json().get("jobs") or [])[:max_results]:
            results.append({
                "source":      _jooble_source_label(job.get("source") or ""),
                "title":       _strip_html(job.get("title") or ""),
                "company":     _strip_html(job.get("company") or ""),
                "location":    _strip_html(job.get("location") or location),
                "description": _strip_html(job.get("snippet") or ""),
                "url":         job.get("link") or "",
                "salary":      job.get("salary") or None,
                "job_type":    job.get("type") or None,
                "posted_date": (job.get("updated") or "")[:10] or None,  # ISO date part
            })
    except Exception as e:
        print(f"[scraper] Jooble failed for '{keyword}': {e}")
    print(f"[scraper] Jooble -> {len(results)} jobs for '{keyword}'")
    return results


def scrape_reed(keyword: str, location: str = "Ireland", max_results: int = 20) -> list[dict]:
    """Reed free API — UK/Ireland jobs, no rate limit."""
    if not REED_API_KEY:
        print("[scraper] Reed: no API key, skipping. Register free at reed.co.uk/developers")
        return []

    results = []
    try:
        resp = httpx.get(
            "https://www.reed.co.uk/api/1.0/search",
            params={"keywords": keyword, "locationName": location, "resultsToTake": max_results},
            auth=(REED_API_KEY, ""),
            timeout=15,
        )
        resp.raise_for_status()
        for job in resp.json().get("results", []):
            results.append({
                "source":      "Reed",
                "title":       _to_str(job.get("jobTitle")),
                "company":     _to_str(job.get("employerName")),
                "location":    _to_str(job.get("locationName")),
                "description": _strip_html(job.get("jobDescription") or ""),
                "url":         job.get("jobUrl"),
                "salary":      _reed_salary(job),
                "job_type":    job.get("jobType"),
                "posted_date": _reed_date(job.get("date")),
            })
    except Exception as e:
        print(f"[scraper] Reed failed for '{keyword}': {e}")

    print(f"[scraper] Reed -> {len(results)} jobs for '{keyword}'")
    return results[:max_results]


def _reed_salary(job):
    mn, mx = job.get("minimumSalary"), job.get("maximumSalary")
    if mn and mx:
        return f"£{int(mn):,}–£{int(mx):,}"
    return None


def _reed_date(date_str: str | None) -> str | None:
    """Convert Reed's DD/MM/YYYY to ISO YYYY-MM-DD so JS Date() parses it correctly."""
    if not date_str:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return date_str  # return as-is if parse fails


# ─── 4. Greenhouse Direct API (no key) ───────────────────────

def scrape_greenhouse(keyword: str, location: str = "ireland", max_results: int = 20) -> list[dict]:
    """
    Greenhouse public API — no key, no cost, no limits.
    Returns direct links to company career pages (not portals).
    """
    kw_terms      = set(keyword.lower().split())
    ireland_terms = {"ireland", "dublin", "cork", "limerick", "galway", "remote", "emea", "anywhere"}
    results       = []

    for slug in IRELAND_GREENHOUSE_SLUGS:
        if len(results) >= max_results:
            break
        try:
            resp = httpx.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                params={"content": "true"},
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            for job in resp.json().get("jobs", []):
                title    = (job.get("title") or "").lower()
                loc_name = (job.get("location") or {}).get("name", "").lower()
                kw_ok    = any(t in title for t in kw_terms)

                # Location check: must mention Ireland/Dublin/EMEA/Anywhere
                # BUT exclude "Remote in US/UK/Canada" — pure US/UK remote jobs are not Ireland-relevant
                loc_ok = False
                if any(t in loc_name for t in ["ireland", "dublin", "cork", "limerick", "galway"]):
                    loc_ok = True
                elif any(t in loc_name for t in ["emea", "anywhere", "worldwide", "global"]):
                    loc_ok = True
                elif "remote" in loc_name:
                    # Only accept remote if it's not tied to a specific non-Ireland country.
                    # Reject: "Remote in US", "Remote, India", "US-Remote", "Remote (US/Canada)"
                    # Accept: "Remote", "Remote - EMEA", bare "Remote"
                    excluded = [
                        "united states", "u.s.", "us-remote", "remote in us", "remote (us",
                        "canada", "india", "germany", "france", "spain", "australia",
                        "brazil", "japan", "china", "singapore", "poland",
                        "united kingdom", "uk-remote", "remote in uk",
                        ", us", "/us", "us/",  # "us/canada", "remote, us"
                    ]
                    if not any(ex in loc_name for ex in excluded):
                        loc_ok = True

                if not (loc_ok and kw_ok):
                    continue
                results.append({
                    "source":      "Company Career Site",
                    "title":       job.get("title"),
                    "company":     slug.capitalize(),
                    "location":    (job.get("location") or {}).get("name"),
                    "description": _strip_html(job.get("content", "")),
                    "url":         job.get("absolute_url"),
                    "salary":      None,
                    "job_type":    None,
                    "posted_date": job.get("updated_at"),
                })
        except Exception:
            pass

    print(f"[scraper] Greenhouse -> {len(results)} jobs for '{keyword}'")
    return results[:max_results]


# ─── 5. Indeed Ireland RSS (free, no key) ────────────────────

def scrape_linkedin(keyword: str, location: str = "Ireland", max_results: int = 25) -> list[dict]:
    """
    LinkedIn jobs via the public guest jobs API — no login, no key required.
    LinkedIn exposes a public job search endpoint used by non-logged-in visitors.
    Paginates in batches of 10.

    URL: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
    Detail: https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}
    """
    import time
    results: list[dict] = []
    seen_ids: set = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }

    pages = (max_results + 9) // 10  # how many pages of 10 we need
    for page in range(pages):
        start = page * 10
        try:
            resp = httpx.get(
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                params={"keywords": keyword, "location": location, "start": start, "f_TPR": "r604800"},  # past week
                headers=headers,
                timeout=12,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                break
            html = resp.text

            # Extract job IDs and basic metadata from card HTML
            job_ids  = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html)
            titles   = re.findall(r'<h3[^>]*class="[^"]*base-search-card__title[^"]*"[^>]*>\s*(.*?)\s*</h3>', html, re.DOTALL)
            companies = re.findall(r'<h4[^>]*class="[^"]*base-search-card__subtitle[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
            locations = re.findall(r'<span[^>]*class="[^"]*job-search-card__location[^"]*"[^>]*>\s*(.*?)\s*</span>', html)
            # Posted dates from <time datetime="YYYY-MM-DD"> elements (one per card)
            dates    = re.findall(r'<time[^>]*datetime="([^"]*)"', html)

            if not job_ids:
                break

            for i, jid in enumerate(job_ids):
                if jid in seen_ids or len(results) >= max_results:
                    continue
                seen_ids.add(jid)
                title    = _strip_html(titles[i])   if i < len(titles)    else keyword
                company  = _strip_html(companies[i]) if i < len(companies) else ""
                loc_str  = _strip_html(locations[i]) if i < len(locations) else location
                posted   = dates[i] if i < len(dates) else None
                job_url  = f"https://www.linkedin.com/jobs/view/{jid}"

                # Fetch full description from detail endpoint
                desc = ""
                try:
                    dr = httpx.get(
                        f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}",
                        headers=headers,
                        timeout=8,
                    )
                    if dr.status_code == 200:
                        m = re.search(
                            r'<div[^>]*class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>',
                            dr.text, re.DOTALL,
                        )
                        if m:
                            desc = _strip_html(m.group(1))
                except Exception:
                    pass

                results.append({
                    "source":      "LinkedIn",
                    "title":       title,
                    "company":     company,
                    "location":    loc_str,
                    "description": desc,
                    "url":         job_url,
                    "salary":      None,
                    "job_type":    None,
                    "posted_date": posted,
                })

            time.sleep(0.8)  # be polite, avoid 429
        except Exception as e:
            print(f"[scraper] LinkedIn page {page} error: {e}")
            break

    print(f"[scraper] LinkedIn -> {len(results)} jobs for '{keyword}'")
    return results


def scrape_indeed(keyword: str, location: str = "Ireland", max_results: int = 20) -> list[dict]:
    """Indeed blocks all automated access (429 / Cloudflare). Returns empty list."""
    print(f"[scraper] Indeed -> 0 jobs (blocked)")
    return []


# ─── 6. Jobs.ie (HTML scraping) ──────────────────────────────

def scrape_jobsie(keyword: str, location: str = "ireland", max_results: int = 20) -> list[dict]:
    """
    Jobs.ie — Ireland's largest job board. Scrapes their JSON search endpoint.
    No API key required.
    """
    results = []
    try:
        # Jobs.ie uses a structured search — try their JSON API endpoint
        resp = httpx.get(
            "https://www.jobs.ie/api/jobs/search/",
            params={
                "q":        keyword,
                "l":        "Ireland",
                "pageSize": min(max_results, 20),
                "page":     1,
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept":     "application/json, */*",
                "Referer":    "https://www.jobs.ie/",
            },
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                jobs_list = data.get("results") or data.get("jobs") or data.get("data") or []
                for job in jobs_list[:max_results]:
                    results.append({
                        "source":      "Jobs.ie",
                        "title":       _to_str(job.get("title") or job.get("jobTitle")),
                        "company":     _to_str(job.get("company") or job.get("employer") or job.get("companyName")),
                        "location":    _to_str(job.get("location") or job.get("city") or "Ireland"),
                        "description": _strip_html(job.get("description") or job.get("summary") or ""),
                        "url":         job.get("url") or job.get("link") or job.get("applyUrl") or "",
                        "salary":      _to_str(job.get("salary") or ""),
                        "job_type":    _to_str(job.get("jobType") or job.get("contractType") or ""),
                        "posted_date": _to_str(job.get("posted") or job.get("date") or ""),
                    })
            except Exception:
                pass  # fall through to RSS attempt

        # Fallback: Jobs.ie RSS feed
        if not results:
            import xml.etree.ElementTree as ET
            rss_resp = httpx.get(
                "https://www.jobs.ie/cgi-bin/jobs/rss.cgi",
                params={"q": keyword, "l": "Ireland"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
                follow_redirects=True,
            )
            if rss_resp.status_code == 200:
                try:
                    root = ET.fromstring(rss_resp.text)
                    for item in root.findall(".//item")[:max_results]:
                        link = item.findtext("link") or ""
                        if not link:
                            continue
                        results.append({
                            "source":      "Jobs.ie",
                            "title":       _strip_html(item.findtext("title") or ""),
                            "company":     _strip_html(item.findtext("company") or ""),
                            "location":    "Ireland",
                            "description": _strip_html(item.findtext("description") or ""),
                            "url":         link,
                            "salary":      None,
                            "job_type":    None,
                            "posted_date": item.findtext("pubDate") or "",
                        })
                except Exception:
                    pass

    except Exception as e:
        print(f"[scraper] Jobs.ie failed for '{keyword}': {e}")

    print(f"[scraper] Jobs.ie -> {len(results)} jobs for '{keyword}'")
    return results


# ─── 7. IrishJobs.ie (HTML / JSON scraping) ──────────────────

def scrape_irishjobs(keyword: str, location: str = "ireland", max_results: int = 20) -> list[dict]:
    """
    IrishJobs.ie — Ireland-specific board (part of Cpl/Saongroup).
    Scrapes their search results.
    """
    import xml.etree.ElementTree as ET
    results = []
    try:
        # Try JSON API first
        resp = httpx.get(
            "https://www.irishjobs.ie/SearchResults.aspx",
            params={
                "Keywords": keyword,
                "Location": "1",   # 1 = All Ireland
                "ResultsPage": 1,
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept":     "text/html,application/xhtml+xml,*/*",
            },
            timeout=15,
            follow_redirects=True,
        )

        if resp.status_code == 200:
            # Extract JSON-LD structured data from HTML (most stable across redesigns)
            import json
            ld_matches = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', resp.text, re.DOTALL)
            for ld_str in ld_matches:
                try:
                    ld = json.loads(ld_str.strip())
                    # Could be single job or ItemList
                    if isinstance(ld, list):
                        items = ld
                    elif ld.get("@type") == "ItemList":
                        items = [el.get("item", el) for el in ld.get("itemListElement", [])]
                    elif ld.get("@type") == "JobPosting":
                        items = [ld]
                    else:
                        continue
                    for job in items[:max_results]:
                        if job.get("@type") != "JobPosting":
                            continue
                        org = job.get("hiringOrganization") or {}
                        loc = job.get("jobLocation") or {}
                        addr = loc.get("address") or {}
                        results.append({
                            "source":      "IrishJobs.ie",
                            "title":       job.get("title") or job.get("name") or "",
                            "company":     org.get("name") or "",
                            "location":    addr.get("addressLocality") or addr.get("addressRegion") or "Ireland",
                            "description": _strip_html(job.get("description") or ""),
                            "url":         job.get("url") or job.get("@id") or "",
                            "salary":      _to_str(job.get("baseSalary") or ""),
                            "job_type":    job.get("employmentType") or "",
                            "posted_date": job.get("datePosted") or "",
                        })
                except Exception:
                    pass

        # Fallback: IrishJobs RSS
        if not results:
            rss_resp = httpx.get(
                "https://www.irishjobs.ie/rss/jobs.aspx",
                params={"Keywords": keyword, "Location": "1"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
                follow_redirects=True,
            )
            if rss_resp.status_code == 200:
                try:
                    root = ET.fromstring(rss_resp.text)
                    for item in root.findall(".//item")[:max_results]:
                        link = item.findtext("link") or ""
                        if not link:
                            continue
                        results.append({
                            "source":      "IrishJobs.ie",
                            "title":       _strip_html(item.findtext("title") or ""),
                            "company":     "",
                            "location":    "Ireland",
                            "description": _strip_html(item.findtext("description") or ""),
                            "url":         link,
                            "salary":      None,
                            "job_type":    None,
                            "posted_date": item.findtext("pubDate") or "",
                        })
                except Exception:
                    pass

    except Exception as e:
        print(f"[scraper] IrishJobs.ie failed for '{keyword}': {e}")

    print(f"[scraper] IrishJobs.ie -> {len(results)} jobs for '{keyword}'")
    return results


# ─── 8. Lever ATS (free, no key) ─────────────────────────────

def scrape_lever(keyword: str, location: str = "ireland", max_results: int = 20) -> list[dict]:
    """
    Lever ATS public postings API — no auth needed.
    Endpoint: https://api.lever.co/v0/postings/{slug}?mode=json&location=<loc>
    """
    kw_terms      = set(keyword.lower().split())
    ireland_terms = {"ireland", "dublin", "cork", "limerick", "galway", "remote", "emea", "anywhere", "hybrid"}
    results       = []

    for slug in IRELAND_LEVER_SLUGS:
        if len(results) >= max_results:
            break
        try:
            resp = httpx.get(
                f"https://api.lever.co/v0/postings/{slug}",
                params={"mode": "json"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            for job in resp.json():
                title    = (job.get("text") or "").lower()
                loc_name = (job.get("categories", {}).get("location") or "").lower()
                team     = (job.get("categories", {}).get("team") or "").lower()
                loc_ok   = any(t in loc_name for t in ireland_terms) or any(t in (job.get("country") or "").lower() for t in ireland_terms)
                kw_ok    = any(t in title or t in team for t in kw_terms)
                if not (loc_ok and kw_ok):
                    continue
                desc_html = ""
                if job.get("description"):
                    desc_html = job["description"]
                elif job.get("descriptionPlain"):
                    desc_html = job["descriptionPlain"]
                # Also grab lists (requirements etc)
                for lst in (job.get("lists") or []):
                    desc_html += " " + (lst.get("content") or "")

                results.append({
                    "source":      "Company Career Site (Lever)",
                    "title":       job.get("text") or "",
                    "company":     slug.replace("-", " ").title(),
                    "location":    job.get("categories", {}).get("location") or "Ireland",
                    "description": _strip_html(desc_html),
                    "url":         job.get("hostedUrl") or job.get("applyUrl") or "",
                    "salary":      None,
                    "job_type":    job.get("categories", {}).get("commitment") or None,
                    "posted_date": None,
                })
        except Exception:
            pass  # silently skip missing slugs

    print(f"[scraper] Lever -> {len(results)} jobs for '{keyword}'")
    return results


# ─── 9. SmartRecruiters (free public API) ────────────────────
# Many Irish/European companies use SmartRecruiters ATS — public jobs API, no auth.

IRELAND_SMARTRECRUITERS_SLUGS = [
    "Intercom", "HubSpot", "Workday", "Zendesk", "Dropbox",
    "Stripe", "Shopify", "Salesforce", "Datadog", "MongoDB",
    "Cloudflare", "GitLab", "Twilio", "Figma", "Notion",
    "PagerDuty", "Splunk", "Okta", "HashiCorp", "Elastic",
    "Personio", "Pleo", "Paddle", "Wayflyer", "Flipdish",
    "Workhuman", "Fenergo", "Version1", "Ergo", "Ward",
]


def scrape_smartrecruiters(keyword: str, location: str = "ireland", max_results: int = 20) -> list[dict]:
    """
    SmartRecruiters public jobs API — no auth needed.
    Used by many Irish/European tech companies.
    """
    kw_lower      = keyword.lower()
    ireland_terms = {"ireland", "dublin", "cork", "limerick", "galway", "remote", "emea", "anywhere"}
    results       = []

    for company in IRELAND_SMARTRECRUITERS_SLUGS:
        if len(results) >= max_results:
            break
        try:
            resp = httpx.get(
                f"https://api.smartrecruiters.com/v1/companies/{company}/postings",
                params={"limit": 100, "offset": 0},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for job in (data.get("content") or []):
                title    = (job.get("name") or "").lower()
                location_obj = job.get("location") or {}
                city     = (location_obj.get("city") or "").lower()
                country  = (location_obj.get("country") or "").lower()
                remote   = job.get("typeOfWork", {}).get("id", "") == "remote"
                loc_ok   = (
                    any(t in city    for t in ireland_terms) or
                    any(t in country for t in ireland_terms) or
                    (remote and "ireland" in (job.get("location") or {}).get("country", "").lower()) or
                    remote  # include fully remote globally posted roles
                )
                kw_ok    = kw_lower in title
                if not (loc_ok and kw_ok):
                    continue
                job_url = f"https://jobs.smartrecruiters.com/{company}/{job.get('id', '')}"
                results.append({
                    "source":      "Company Career Site (SmartRecruiters)",
                    "title":       job.get("name") or "",
                    "company":     job.get("company", {}).get("name") or company,
                    "location":    f"{location_obj.get('city','')} {location_obj.get('country','')}".strip() or location,
                    "description": _strip_html(job.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text") or ""),
                    "url":         job_url,
                    "salary":      None,
                    "job_type":    (job.get("typeOfWork") or {}).get("label"),
                    "posted_date": job.get("releasedDate"),
                })
        except Exception:
            pass

    print(f"[scraper] SmartRecruiters -> {len(results)} jobs for '{keyword}'")
    return results[:max_results]


# ─── 10. Workable (free public API) ──────────────────────────
# Many Irish startups and SMEs use Workable. Public job listings endpoint.

IRELAND_WORKABLE_SLUGS = [
    "teamwork", "esri-ireland", "fexco", "ergo-group",
    "demonware", "intercom", "squarespace",
]

# ─── 10b. Workday ATS (free public career page API) ──────────
# Many large enterprise tech companies with Dublin offices use Workday.
# Each entry: (tenant_slug, workday_num, jobsite_name)
# The jobsite name is company-specific — "External" is most common default.
#
# Companies with significant Ireland/Dublin presence:
#   Oracle, Salesforce, ServiceNow, Cisco, Accenture, LinkedIn,
#   VMware, Zendesk, Autodesk, Fidelity, Mastercard, Visa,
#   DocuSign, NCR, State Street, Northern Trust, BNY Mellon, JPMorgan
#
IRELAND_WORKDAY_TENANTS = [
    # (tenant, "wdN", jobsite) — VERIFIED working public endpoints (probed live).
    # The jobsite path varies per company; these were confirmed to return jobs.
    ("mastercard",  "wd1",  "CorporateCareers"),
    ("salesforce",  "wd12", "External_Career_Site"),
    ("medtronic",   "wd1",  "medtronicCareers"),
    ("stryker",     "wd1",  "strykerCareers"),
    ("autodesk",    "wd1",  "Ext"),
    ("nvidia",      "wd5",  "NVIDIAExternalCareerSite"),
    ("workday",     "wd5",  "Workday"),
    ("statestreet", "wd1",  "Global"),
    ("comcast",     "wd5",  "comcast_Careers"),
    ("tmobile",     "wd1",  "External"),
    ("cisco",       "wd5",  "cisco_Careers"),
    ("hp",          "wd5",  "ExternalCareerSite"),
    ("novartis",    "wd3",  "novartis_Careers"),
    ("pfizer",      "wd1",  "pfizerCareers"),
    ("abbott",      "wd5",  "abbottCareers"),
    ("edwards",     "wd5",  "edwardsCareers"),
]


def scrape_workable(keyword: str, location: str = "ireland", max_results: int = 20) -> list[dict]:
    """
    Workable public jobs widget API — no auth needed.
    Used by many Irish SMEs and startups.
    """
    kw_lower = keyword.lower()
    results  = []
    ireland_terms = {"ireland", "dublin", "cork", "limerick", "galway", "remote", "emea"}

    for slug in IRELAND_WORKABLE_SLUGS:
        if len(results) >= max_results:
            break
        try:
            resp = httpx.get(
                f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
                params={"details": "true"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            for job in (resp.json().get("results") or []):
                title    = (job.get("title") or "").lower()
                city     = (job.get("city") or "").lower()
                country  = (job.get("country") or "").lower()
                loc_ok   = any(t in city or t in country for t in ireland_terms)
                kw_ok    = kw_lower in title
                if not (loc_ok and kw_ok):
                    continue
                results.append({
                    "source":      "Company Career Site (Workable)",
                    "title":       job.get("title") or "",
                    "company":     job.get("account", {}).get("name") or slug,
                    "location":    f"{job.get('city', '')} {job.get('country', '')}".strip(),
                    "description": _strip_html(job.get("description") or ""),
                    "url":         job.get("url") or f"https://apply.workable.com/{slug}/j/{job.get('id','')}",
                    "salary":      None,
                    "job_type":    job.get("employment_type"),
                    "posted_date": job.get("published_on"),
                })
        except Exception:
            pass

    print(f"[scraper] Workable -> {len(results)} jobs for '{keyword}'")
    return results[:max_results]


# ─── 11. Workday ATS (free public career page API) ───────────
# Large enterprise companies expose a public JSON search endpoint.
# No auth, no API key needed.

def scrape_workday(keyword: str, location: str = "ireland", max_results: int = 30) -> list[dict]:
    """
    Scrape Workday ATS career pages for major companies with Ireland offices.
    Workday exposes a public POST endpoint:
      POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{jobsite}/jobs
    Response: { jobPostings: [ { title, postedOn, locationsText, externalPath } ] }
    """
    ireland_terms = {"ireland", "dublin", "cork", "limerick", "galway", "remote", "emea"}
    results: list[dict] = []

    def _fetch_tenant(tenant, wd_num, jobsite):
        """Fetch one company's Workday jobs, return matching list."""
        # wd_num may be int (legacy) or str like "wd1"
        wd = wd_num if isinstance(wd_num, str) else f"wd{wd_num}"
        base_url = f"https://{tenant}.{wd}.myworkdayjobs.com"
        endpoint  = f"{base_url}/wday/cxs/{tenant}/{jobsite}/jobs"
        hdr = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json", "Accept": "application/json"}
        # Workday caps limit at 20 per page — paginate up to 3 pages (60 results).
        postings = []
        for offset in (0, 20, 40):
            try:
                resp = httpx.post(
                    endpoint,
                    json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": keyword},
                    headers=hdr,
                    timeout=10,
                )
                if resp.status_code not in (200, 201):
                    break
                page = resp.json().get("jobPostings") or []
                if not page:
                    break
                postings.extend(page)
                if len(page) < 20:
                    break
            except Exception:
                break
        try:
            found = []
            for job in postings:
                loc_text = (job.get("locationsText") or "").lower()
                # Must explicitly mention Ireland/Irish city. "Remote" alone is NOT
                # enough — it pulls in Vietnam/Canada/India remote roles.
                ireland_only = {"ireland", "dublin", "cork", "limerick", "galway"}
                loc_ok = any(t in loc_text for t in ireland_only)
                if not loc_ok:
                    continue
                ext_path = job.get("externalPath") or ""
                job_url  = f"{base_url}/{jobsite}{ext_path}" if ext_path else f"{base_url}/{jobsite}"
                # Fetch job description if available
                desc = ""
                if ext_path:
                    try:
                        detail_url = f"{base_url}/wday/cxs/{tenant}/{jobsite}{ext_path}"
                        dr = httpx.get(detail_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                        if dr.status_code == 200:
                            dj = dr.json()
                            desc = _strip_html(
                                dj.get("jobPostingInfo", {}).get("jobDescription") or
                                dj.get("jobDescription") or ""
                            )
                    except Exception:
                        pass
                found.append({
                    "source":      "Company Career Site (Workday)",
                    "title":       job.get("title") or "",
                    "company":     tenant.capitalize(),
                    "location":    job.get("locationsText") or location,
                    "description": desc,
                    "url":         job_url,
                    "salary":      None,
                    "job_type":    None,
                    "posted_date": job.get("postedOn"),
                })
            return found
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_fetch_tenant, tenant, wd_num, jobsite): (tenant, jobsite)
            for tenant, wd_num, jobsite in IRELAND_WORKDAY_TENANTS
        }
        for future in as_completed(futures):
            tenant, jobsite = futures[future]
            try:
                jobs = future.result()
                if jobs:
                    print(f"[scraper] Workday {tenant} -> {len(jobs)} jobs")
                results.extend(jobs)
            except Exception:
                pass
            if len(results) >= max_results * 3:  # enough, stop early
                break

    print(f"[scraper] Workday total -> {len(results)} jobs for '{keyword}'")
    return results[:max_results]


# ─── Combined scraper ─────────────────────────────────────────

def scrape_all_sources(
    keyword: str,
    location: str = "Ireland",
    max_per_source: int = 10,
    sources: list[str] = None,
) -> list[dict]:
    if sources is None:
        sources = ["jsearch", "adzuna", "reed", "greenhouse"]

    scrapers = {
        "jsearch":          scrape_jsearch,
        "adzuna":           scrape_adzuna,
        "reed":             scrape_reed,
        "greenhouse":       scrape_greenhouse,
        "smartrecruiters":  scrape_smartrecruiters,
        "workable":         scrape_workable,
        "workday":          scrape_workday,
        "linkedin":         scrape_linkedin,
        "jooble":           scrape_jooble,    # aggregates Indeed/IrishJobs/Glassdoor
        "indeed":           scrape_indeed,    # blocked by Indeed
        "jobsie":           scrape_jobsie,    # site blocks scraping
        "irishjobs":        scrape_irishjobs, # site blocks scraping
        "lever":            scrape_lever,
    }

    results = []
    for source in sources:
        if source not in scrapers:
            continue
        try:
            jobs = scrapers[source](keyword, location, max_per_source)
            results.extend(jobs)
        except Exception as e:
            print(f"[scraper] {source} error: {e}")

    # Deduplicate by URL, then filter non-engineering titles
    seen, unique = set(), []
    for job in results:
        key = job.get("url") or f"{job.get('title','')}-{job.get('company','')}"
        if key and key not in seen:
            seen.add(key)
            if (job.get("title") or job.get("description")) and _is_engineering_role(job):
                unique.append(job)
    return unique


def run_all_search_queries(max_per_source: int = 10) -> list[dict]:
    """
    Parallel scraping across all queries and sources.

    Sources used (all free):
      Reed       : Ireland jobs board — unlimited, best Ireland-specific coverage
      Greenhouse : Direct career pages for 70+ Dublin-office tech companies (Stripe, Intercom...)
      Adzuna     : UK/Ireland jobs via GB endpoint — sequential to avoid 429 rate limits

    Note on LinkedIn/Indeed/Jobs.ie/IrishJobs:
    These boards DO NOT have free APIs and actively block scraping.
    Their data is only accessible via paid services (LinkedIn Talent API, Apify actors, etc.).
    For best results, copy interesting roles from LinkedIn/Indeed and use the
    "Paste any JD to score" feature in the app.
    """
    all_jobs, seen = [], set()

    def _add(jobs):
        added = 0
        for job in jobs:
            if not _is_engineering_role(job):
                continue
            key = job.get("url") or f"{job.get('title','')}-{job.get('company','')}"
            if key and key not in seen:
                seen.add(key)
                all_jobs.append(job)
                added += 1
        return added

    # ── Jooble: aggregator covering Indeed, IrishJobs, Glassdoor & more ──────────
    # FREE but capped at 500 requests total, so use a SMALL set of broad keywords
    # (one request each). Jooble already aggregates many boards, so few queries
    # give wide coverage. ~6 requests per full search.
    JOOBLE_QUERIES = [
        "software engineer", "java developer", "python developer",
        "graduate software engineer", "machine learning engineer", "full stack developer",
    ]
    if JOOBLE_API_KEY:
        print(f"[scraper] -- Jooble (Indeed/IrishJobs/Glassdoor aggregator): {len(JOOBLE_QUERIES)} queries --")
        for kw in JOOBLE_QUERIES:
            try:
                n = _add(scrape_jooble(kw, "Ireland", 40))
                if n > 0:
                    print(f"[scraper] Jooble '{kw}' -> {n} new")
            except Exception as e:
                print(f"[scraper] Jooble '{kw}' failed: {e}")
    else:
        print("[scraper] -- Jooble: no API key (set JOOBLE_API_KEY in .env) --")

    # ── LinkedIn: public guest API — real LinkedIn Ireland jobs, no login needed ──
    # LinkedIn exposes job listings to non-logged-in visitors via a guest API.
    # Rate limit: add 0.8s between detail fetches (built into scrape_linkedin).
    # Run only selected high-signal queries to avoid hitting rate limits.
    LINKEDIN_QUERIES = [
        {"keyword": "software engineer",          "location": "Ireland"},
        {"keyword": "junior software engineer",   "location": "Ireland"},
        {"keyword": "graduate software engineer", "location": "Ireland"},
        {"keyword": "java developer",             "location": "Ireland"},
        {"keyword": "python developer",           "location": "Ireland"},
        {"keyword": "machine learning engineer",  "location": "Ireland"},
        {"keyword": "AI engineer",                "location": "Ireland"},
        {"keyword": "backend developer",          "location": "Ireland"},
        {"keyword": "full stack developer",       "location": "Ireland"},
        {"keyword": "software intern",            "location": "Ireland"},
    ]
    print(f"[scraper] -- LinkedIn (public guest API): {len(LINKEDIN_QUERIES)} queries --")
    import time
    for query in LINKEDIN_QUERIES:
        try:
            jobs = scrape_linkedin(query["keyword"], query.get("location", "Ireland"), 15)
            n = _add(jobs)
            if n > 0:
                print(f"[scraper] LinkedIn '{query['keyword']}' -> {n} new")
            time.sleep(1.5)  # avoid LinkedIn rate-limiting between queries
        except Exception as e:
            print(f"[scraper] LinkedIn '{query['keyword']}' failed: {e}")

    # ── Reed: sequential to avoid rate limiting ───────────────────────────────────
    # Reed Ireland is our most direct free source for Republic of Ireland jobs.
    # Run sequentially with a small delay to avoid 429s.
    print(f"[scraper] -- Reed (Ireland): {len(SEARCH_QUERIES)} queries --")
    import time
    for query in SEARCH_QUERIES:
        try:
            jobs = scrape_reed(query["keyword"], "Ireland", max_per_source)
            n = _add(jobs)
            if n > 0:
                print(f"[scraper] Reed '{query['keyword']}' -> {n}")
            time.sleep(0.5)  # gentle rate limiting
        except Exception as e:
            print(f"[scraper] Reed '{query['keyword']}' failed: {e}")

    # ── SmartRecruiters: parallel queries ────────────────────────────────────────
    print(f"[scraper] -- SmartRecruiters ({len(IRELAND_SMARTRECRUITERS_SLUGS)} companies) --")

    def _sr_query(query):
        try:
            return scrape_smartrecruiters(query["keyword"], query.get("location", "Ireland"), max_per_source)
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=4) as pool:
        for jobs in pool.map(_sr_query, SEARCH_QUERIES):
            n = _add(jobs)
            if n > 0:
                print(f"[scraper] SmartRecruiters -> {n} new jobs")

    # ── Workable: parallel queries ────────────────────────────────────────────────
    print(f"[scraper] -- Workable ({len(IRELAND_WORKABLE_SLUGS)} companies) --")

    def _workable_query(query):
        try:
            return scrape_workable(query["keyword"], query.get("location", "Ireland"), max_per_source)
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=4) as pool:
        for jobs in pool.map(_workable_query, SEARCH_QUERIES):
            n = _add(jobs)
            if n > 0:
                print(f"[scraper] Workable -> {n} new jobs")

    # ── Greenhouse: all SEARCH_QUERIES IN PARALLEL ───────────────────────────────
    # Greenhouse is our best source for big-tech Dublin career pages (Stripe, Intercom, etc.)
    print(f"[scraper] -- Greenhouse ({len(IRELAND_GREENHOUSE_SLUGS)} companies): {len(SEARCH_QUERIES)} queries --")

    def _greenhouse_query(query):
        try:
            jobs = scrape_greenhouse(query["keyword"], query.get("location", "Ireland"), max_per_source)
            if jobs:
                print(f"[scraper] Greenhouse '{query['keyword']}' -> {len(jobs)}")
            return jobs
        except Exception as e:
            print(f"[scraper] Greenhouse '{query['keyword']}' failed: {e}")
            return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_greenhouse_query, q): q for q in SEARCH_QUERIES}
        for future in as_completed(futures):
            try:
                _add(future.result())
            except Exception as e:
                print(f"[scraper] Greenhouse thread failed: {e}")

    # ── Workday ATS: direct company career sites (Mastercard, Cisco, State St...) ─
    # Free public CXS API — verified working per-tenant endpoints. One call per
    # keyword covers all tenants in parallel inside scrape_workday().
    print(f"[scraper] -- Workday ATS ({len(IRELAND_WORKDAY_TENANTS)} companies) --")
    for query in SEARCH_QUERIES:
        try:
            jobs = scrape_workday(query["keyword"], "ireland", max_per_source * 3)
            n = _add(jobs)
            if n > 0:
                print(f"[scraper] Workday '{query['keyword']}' -> {n} new")
        except Exception as e:
            print(f"[scraper] Workday '{query['keyword']}' failed: {e}")

    # ── Adzuna: sequential, GB endpoint (covers UK+Ireland jobs) ─────────────────
    # Adzuna does not support 'ie' but GB endpoint covers Northern Ireland and
    # many companies that list UK/Ireland positions. Run sequentially to avoid 429.
    print(f"[scraper] -- Adzuna (GB): {len(SEARCH_QUERIES)} queries --")
    for query in SEARCH_QUERIES:
        try:
            jobs = scrape_adzuna(query["keyword"], "Ireland", max_per_source)
            n = _add(jobs)
            if n > 0:
                print(f"[scraper] Adzuna '{query['keyword']}' -> {n}")
            time.sleep(0.3)
        except Exception as e:
            print(f"[scraper] Adzuna '{query['keyword']}' failed: {e}")

    print(f"[scraper] == Total unique jobs: {len(all_jobs)} ==")
    return all_jobs
