"""
Supabase database layer — jobs table CRUD.
"""

import os
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_ANON_KEY"]

_client: Client = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def upsert_jobs(jobs: list[dict]) -> list[dict]:
    """Insert or update jobs by URL (deduplication key).

    NOTE: `status` is intentionally excluded from the upsert payload so that
    user-set statuses (saved / applied / interview / offer) are never overwritten
    by a re-scrape. New rows get the DB column default ('new') automatically.
    Status changes go through update_job_status() only.
    """
    db = get_client()
    # Deduplicate by URL before upserting — Supabase rejects batches with
    # two rows that share the same conflict key (url).
    seen_urls: set = set()
    jobs = [j for j in jobs if (u := j.get("url") or f"{j.get('title','')}-{j.get('company','')}") and u not in seen_urls and not seen_urls.add(u)]  # type: ignore[func-returns-value]

    rows = []
    for job in jobs:
        row = {
            "url":               job.get("url") or f"{job.get('title','')}-{job.get('company','')}",
            "title":             job.get("title"),
            "company":           job.get("company"),
            "location":          job.get("location"),
            "description":       job.get("description"),
            "source":            job.get("source"),
            "salary":            job.get("salary"),
            "job_type":          job.get("job_type"),
            "posted_date":       job.get("posted_date"),
            "ai_score":          job.get("ai_score"),
            "ai_verdict":        job.get("ai_verdict"),
            "ai_verdict_reason": job.get("ai_verdict_reason"),
            "ai_matches":        job.get("ai_matches"),
            "ai_gaps":           job.get("ai_gaps"),
            "ai_red_flags":      job.get("ai_red_flags"),
            "ai_keywords_present": job.get("ai_keywords_present"),
            "ai_keywords_missing": job.get("ai_keywords_missing"),
            "ai_apply":          job.get("ai_apply"),
            "ai_breakdown":      job.get("ai_breakdown"),
            # status excluded — DB default 'new' for inserts; user edits preserved on updates
        }
        rows.append(row)

    result = db.table("jobs").upsert(rows, on_conflict="url").execute()
    return result.data


def get_jobs(
    min_score: int = 0,
    status: str = None,
    source: str = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    db = get_client()
    query = db.table("jobs").select("*")

    if min_score:
        query = query.gte("ai_score", min_score)
    if status:
        query = query.eq("status", status)
    if source:
        query = query.eq("source", source)

    query = query.order("ai_score", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    return result.data


def get_job(job_id: str) -> dict:
    db = get_client()
    try:
        result = db.table("jobs").select("*").eq("id", job_id).single().execute()
        return result.data
    except Exception:
        return None


def get_already_scored_urls() -> set:
    """Return set of URLs that already have an AI score — skip re-scoring these."""
    db = get_client()
    result = db.table("jobs").select("url").not_.is_("ai_score", "null").execute()
    return {row["url"] for row in (result.data or [])}


def delete_job(job_id: str) -> bool:
    """Permanently delete a job from the database."""
    db = get_client()
    db.table("jobs").delete().eq("id", job_id).execute()
    return True


def purge_bad_jobs() -> int:
    """
    Delete non-engineering / senior / irrelevant jobs from DB.
    Called after each full search to keep the DB clean.
    Returns count of deleted jobs.
    """
    import re
    db = get_client()
    all_jobs = db.table("jobs").select("id,title,description").execute().data or []

    non_eng_words = [
        "account executive", "account manager", "account director", "account development",
        "sales", "marketing", "campaign", "human resources", " hr ", "recruiter",
        "finance manager", "financial analyst", "accounting", "accountant",
        "tax", "treasury", "audit", "regulatory", "compliance",
        "customer success", "customer support", "product manager", "product owner",
        "operations manager", "business analyst", "data analyst",
        "civil engineer", "mechanical engineer", "electrical engineer",
        "highway", "graphic design", "construction", "quantity surveyor",
        # Physical/hardware engineering roles (from Reed Ireland)
        "manufacturing engineer", "design engineer", "field service engineer",
        "commissioning engineer", "process engineer", "quality engineer",
        "maintenance engineer", "service engineer", "hvac", "estimator",
        "biomedical engineer", "validation engineer", "environmental engineer",
        "qa localization", "medical diagnostic", "localization engineer",
        "graduate estimator", "junior structural", "junior mechanical",
        "junior civil", "junior electrical",
    ]
    senior_words = [
        "staff engineer", "principal engineer", "senior engineer", "senior developer",
        "senior software", "lead engineer", "lead developer",
        "engineering manager", "director of", "head of engineering",
        "vp of", "chief technology",
    ]
    senior_exp_re = re.compile(
        r'\b([3-9]|1[0-9])\+?\s*years?\b'
        r'|minimum\s*(of\s*)?([3-9]|1[0-9])\s*years?\b'
        r'|at\s*least\s*([3-9]|1[0-9])\s*years?\b'
        r'|\b([3-9]|1[0-9])\+\s*yrs?\b',
        re.IGNORECASE,
    )
    range_exp_re = re.compile(r'\b\d+\s*[-]\s*(\d+)\+?\s*years?\b', re.IGNORECASE)
    do_not_apply_re = re.compile(
        r'(intern|new\s*grad).*?please\s*do\s*not\s*apply'
        r'|if\s+you\s+are\s+(an?\s+)?(intern|new\s*grad).*?do\s*not\s*apply',
        re.IGNORECASE | re.DOTALL,
    )
    entry_re = re.compile(r'\b(intern|junior|graduate|entry.level|new\s*grad)\b', re.IGNORECASE)

    deleted = 0
    for job in all_jobs:
        title = (job.get("title") or "").lower()
        desc  = (job.get("description") or "")
        title_entry = bool(entry_re.search(title))
        should_delete = False

        if any(w in title for w in non_eng_words):
            should_delete = True
        elif any(w in title for w in senior_words):
            should_delete = True
        elif do_not_apply_re.search(desc[:1000]):
            should_delete = True
        elif senior_exp_re.search(desc) and not title_entry:
            should_delete = True
        else:
            for m in range_exp_re.finditer(desc):
                if int(m.group(1)) >= 5 and not title_entry:
                    should_delete = True
                    break

        if should_delete:
            db.table("jobs").delete().eq("id", job["id"]).execute()
            deleted += 1
            print(f"[db] purged: {job.get('title','?')[:60]}")

    return deleted


def update_job_status(job_id: str, status: str) -> dict:
    """Update application status: new | saved | applied | interview | rejected | offer."""
    db = get_client()
    result = db.table("jobs").update({"status": status}).eq("id", job_id).execute()
    return result.data


SCHEMA_SQL = """
-- Run this in Supabase SQL Editor to create the jobs table

create table if not exists jobs (
  id uuid default gen_random_uuid() primary key,
  url text unique not null,
  title text,
  company text,
  location text,
  description text,
  source text,
  salary text,
  job_type text,
  posted_date text,
  ai_score integer,
  ai_verdict text,
  ai_verdict_reason text,
  ai_matches jsonb,
  ai_gaps jsonb,
  ai_red_flags jsonb,
  ai_keywords_present jsonb,
  ai_keywords_missing jsonb,
  ai_apply text,
  ai_breakdown jsonb,
  status text default 'new',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Auto-update updated_at
create or replace function update_updated_at()
returns trigger as $$
begin new.updated_at = now(); return new; end;
$$ language plpgsql;

create trigger jobs_updated_at
  before update on jobs
  for each row execute function update_updated_at();

-- Index for common queries
create index if not exists jobs_score_idx on jobs(ai_score desc);
create index if not exists jobs_status_idx on jobs(status);
create index if not exists jobs_source_idx on jobs(source);
"""
