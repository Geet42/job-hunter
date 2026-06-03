"""
Free job scraping — Apify-level results, zero cost forever.

Sources:
  1. JSearch (RapidAPI) — Google for Jobs aggregator. Same data as paid Apify scrapers.
                          Covers LinkedIn, Indeed, Glassdoor, and ALL company career pages.
                          Free: 200 req/month (plenty for personal use).
                          https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

  2. Adzuna API          — Ireland-specific job board aggregator. Free 250 req/day.
                          https://developer.adzuna.com

  3. Reed API            — UK/Ireland jobs. Free, unlimited.
                          https://www.reed.co.uk/developers

  4. Greenhouse API      — Direct company career pages, no key needed, unlimited free.
                          Covers: Stripe, Intercom, Cloudflare, MongoDB, Datadog, Zendesk...
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
    text = _html.unescape(text)                     # &lt; → <, &amp; → &, etc.
    text = re.sub(r"<[^>]+>", " ", text)            # strip remaining <tags>
    text = re.sub(r"&[a-z#0-9]+;", " ", text)       # any leftover entities
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Title-level filters ──────────────────────────────────────

# Titles containing these → not engineering roles
_NON_ENGINEERING = [
    "account executive", "account manager", "account director",
    "sales representative", "sales manager", "sales engineer",
    "business development", "business analyst",
    "marketing manager", "marketing executive", "marketing specialist",
    "human resources", " hr ", "recruiter", "talent acquisition",
    "customer success", "customer support", "customer experience",
    "legal counsel", "paralegal", "finance manager", "financial analyst",
    "operations manager", "office manager", "project manager",
    "product manager", "product owner",
    "account specialist", "partnership manager", "growth manager",
    "commercial graduate", "solution consultant", "pre-sales",
    "data analyst", "business intelligence", "scrum master",
    "technical writer", "it support", "systems administrator",
    "network engineer", "security analyst", "penetration tester",
]

# Titles containing these → too senior for entry-level candidate
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

# Matches: "3+ years", "4 years of experience", "minimum 5 years", "at least 3 years"
_SENIOR_EXP_RE = re.compile(
    r'\b([3-9]|1[0-9])\+?\s*years?\s*(of\s*)?(professional\s*)?(industry\s*)?(work\s*)?(software\s*)?'
    r'(engineering\s*)?(development\s*)?(experience|exp)\b'
    r'|minimum\s*(of\s*)?([3-9]|1[0-9])\s*years?\b'
    r'|at\s*least\s*([3-9]|1[0-9])\s*years?\b'
    r'|\b([3-9]|1[0-9])\+\s*yrs?\b',
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
      1. Title contains non-engineering keywords → reject
      2. Title contains senior/lead/architect keywords → reject
      3. Description requires 3+ years professional experience → reject
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

    # Layer 3a — description says 3+ years required
    if _SENIOR_EXP_RE.search(desc) and not _ENTRY_SIGNALS_RE.search(title + " " + desc[:500]):
        print(f"[scraper] Filtered (3+ yrs required): {job.get('title')}")
        return False

    # Layer 3b — range pattern like "2-12+ years", "2-10+ years": reject if upper bound >= 5
    for m in _EXP_RANGE_RE.finditer(desc):
        upper = int(m.group(1))
        if upper >= 5 and not _ENTRY_SIGNALS_RE.search(title + " " + desc[:500]):
            print(f"[scraper] Filtered (range {m.group(0)}): {job.get('title')}")
            return False

    # Layer 3c — explicitly excludes internship/co-op experience counting
    if _EXCL_INTERN_RE.search(desc) and not _ENTRY_SIGNALS_RE.search(title):
        print(f"[scraper] Filtered (excludes intern exp): {job.get('title')}")
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

# Ireland-based companies on Greenhouse ATS — public API, no auth needed
IRELAND_GREENHOUSE_SLUGS = [
    "stripe", "intercom", "zendesk", "mongodb", "cloudflare", "datadog",
    "gitlab", "squarespace", "twilio", "shopify", "notion", "figma",
    "coinbase", "hubspot", "asana", "brex", "airtable", "anthropic",
]


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
                    "query":          f"{keyword} in {location}",
                    "page":           str(page),
                    "num_pages":      "1",
                    "date_posted":    "month",
                    "country":        "ie",
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

    print(f"[scraper] JSearch → {len(results)} jobs for '{keyword}'")
    return results[:max_results]


def _jsearch_source(job: dict) -> str:
    publisher = job.get("job_publisher") or ""
    if "linkedin" in publisher.lower():
        return "LinkedIn (via Google Jobs)"
    if "indeed" in publisher.lower():
        return "Indeed (via Google Jobs)"
    if "glassdoor" in publisher.lower():
        return "Glassdoor (via Google Jobs)"
    return f"Company Career Site ({publisher})" if publisher else "Company Career Site"


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
    """Adzuna free API — Ireland jobs. Free 250 req/day."""
    if not ADZUNA_APP_ID or not ADZUNA_API_KEY:
        print("[scraper] Adzuna: no credentials, skipping. Register free at developer.adzuna.com")
        return []

    results = []
    try:
        resp = httpx.get(
            "https://api.adzuna.com/v1/api/jobs/ie/search/1",
            params={
                "app_id":           ADZUNA_APP_ID,
                "app_key":          ADZUNA_API_KEY,
                "what":             keyword,
                "where":            location,
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

    print(f"[scraper] Adzuna → {len(results)} jobs for '{keyword}'")
    return results[:max_results]


def _adzuna_salary(job):
    mn, mx = job.get("salary_min"), job.get("salary_max")
    if mn and mx:
        return f"€{int(mn):,}–€{int(mx):,}"
    return None


# ─── 3. Reed API ──────────────────────────────────────────────

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
                "posted_date": job.get("date"),
            })
    except Exception as e:
        print(f"[scraper] Reed failed for '{keyword}': {e}")

    print(f"[scraper] Reed → {len(results)} jobs for '{keyword}'")
    return results[:max_results]


def _reed_salary(job):
    mn, mx = job.get("minimumSalary"), job.get("maximumSalary")
    if mn and mx:
        return f"£{int(mn):,}–£{int(mx):,}"
    return None


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
                loc_ok   = any(t in loc_name for t in ireland_terms)
                kw_ok    = any(t in title for t in kw_terms)
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

    print(f"[scraper] Greenhouse → {len(results)} jobs for '{keyword}'")
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
        "jsearch":    scrape_jsearch,
        "adzuna":     scrape_adzuna,
        "reed":       scrape_reed,
        "greenhouse": scrape_greenhouse,
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

    API call budget per full search:
      JSearch   : 1 broad call  (saves 7 of 8 monthly calls)
      Adzuna    : 8 calls       (250/day limit, fine)
      Reed      : 8 calls       (unlimited)
      Greenhouse: 18 calls      (unlimited, no auth)

    All Adzuna + Reed + Greenhouse queries run in PARALLEL — 8x faster.
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

    # ── JSearch: ONE broad call (1 API credit) ────────────────
    print("[scraper] ── JSearch broad search (1 API call) ──")
    try:
        jsearch_jobs = scrape_jsearch(
            keyword="software engineer intern OR graduate software engineer OR java developer entry level OR backend engineer intern OR AI engineer intern OR junior developer OR new grad software engineer",
            location="Ireland",
            max_results=50,
        )
        n = _add(jsearch_jobs)
        print(f"[scraper] JSearch → {n} new jobs")
    except Exception as e:
        print(f"[scraper] JSearch broad failed: {e}")

    # ── Adzuna + Reed + Greenhouse: all 8 queries IN PARALLEL ─
    print(f"[scraper] ── Running {len(SEARCH_QUERIES)} queries in parallel (Adzuna + Reed + Greenhouse) ──")

    def _scrape_query(query):
        keyword  = query["keyword"]
        location = query.get("location", "Ireland")
        results  = []
        for source in ["adzuna", "reed", "greenhouse"]:
            try:
                scrapers = {"adzuna": scrape_adzuna, "reed": scrape_reed, "greenhouse": scrape_greenhouse}
                jobs = scrapers[source](keyword, location, max_per_source)
                results.extend(jobs)
                print(f"[scraper] {source} '{keyword}' → {len(jobs)} jobs")
            except Exception as e:
                print(f"[scraper] {source} '{keyword}' failed: {e}")
        return results

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_scrape_query, q): q for q in SEARCH_QUERIES}
        for future in as_completed(futures):
            try:
                _add(future.result())
            except Exception as e:
                print(f"[scraper] Query thread failed: {e}")

    print(f"[scraper] ══ Total unique jobs: {len(all_jobs)} ══")
    return all_jobs
