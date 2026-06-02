"""
FastAPI backend — job search, scoring, tailoring endpoints.
"""

# Load .env FIRST — before any local imports that read os.environ at module level
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import time
import os

from scraper import scrape_all_sources, run_all_search_queries
from scorer import score_jobs_batch, score_job
from tailor import tailor_resume, generate_cover_letter, analyze_gaps
from db import upsert_jobs, get_jobs, get_job, update_job_status, get_already_scored_urls, delete_job

app = FastAPI(title="Job Hunter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track background scrape progress
_scrape_status = {"running": False, "progress": "", "last_run": None, "total_found": 0}


# ─────────────────────────── MODELS ───────────────────────────

class SearchRequest(BaseModel):
    keyword: str
    location: str = "Ireland"
    max_per_source: int = 10
    sources: Optional[list[str]] = None


class TailorRequest(BaseModel):
    job_id: Optional[str] = None
    job_description: Optional[str] = None
    job_title: Optional[str] = ""
    company: Optional[str] = ""
    approved_suggestions: Optional[list[dict]] = None   # gap-analysis suggestions user accepted


class CoverLetterRequest(BaseModel):
    job_id: Optional[str] = None
    job_description: Optional[str] = None
    job_title: Optional[str] = ""
    company: Optional[str] = ""
    extra_context: Optional[str] = ""


class StatusUpdate(BaseModel):
    status: str  # new | saved | applied | interview | rejected | offer


# ─────────────────────────── ROUTES ───────────────────────────

@app.get("/")
def root():
    return {"status": "Job Hunter API running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/debug/db")
def debug_db():
    """Test Supabase connection and show table stats."""
    try:
        jobs = get_jobs(min_score=0, limit=5)
        from db import get_client
        total = get_client().table("jobs").select("id", count="exact").execute()
        return {
            "supabase": "connected",
            "total_jobs": total.count,
            "sample": [{"title": j.get("title"), "source": j.get("source"), "score": j.get("ai_score")} for j in jobs]
        }
    except Exception as e:
        return {"supabase": "ERROR", "error": str(e), "hint": "Did you run the SQL in Supabase SQL Editor?"}


@app.post("/search")
async def search_jobs(req: SearchRequest, background_tasks: BackgroundTasks):
    """Scrape jobs for a keyword, score them, save to DB. Kicks off in background."""
    if _scrape_status["running"]:
        return {"message": "Scrape already running", "status": _scrape_status}

    background_tasks.add_task(
        _scrape_and_score,
        req.keyword,
        req.location,
        req.max_per_source,
        req.sources,
    )
    return {"message": f"Scraping started for '{req.keyword}'", "status": "started"}


@app.post("/search/full")
async def full_search(background_tasks: BackgroundTasks):
    """Run all configured search queries (all role types for Ireland)."""
    if _scrape_status["running"]:
        return {"message": "Scrape already running", "status": _scrape_status}

    background_tasks.add_task(_full_scrape_and_score)
    return {"message": "Full search started for all target roles", "status": "started"}


@app.get("/search/status")
def scrape_status():
    return _scrape_status


@app.get("/jobs")
def list_jobs(
    min_score: int = Query(0, ge=0, le=10),
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """Get all scored jobs, sorted by score desc."""
    jobs = get_jobs(min_score=min_score, status=status, source=source, limit=limit, offset=offset)
    return {"jobs": jobs, "count": len(jobs)}


@app.get("/jobs/{job_id}")
def get_job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.delete("/jobs/{job_id}")
def delete_job_endpoint(job_id: str):
    """Permanently delete a job (hide irrelevant ones)."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    delete_job(job_id)
    return {"deleted": True, "id": job_id}


@app.patch("/jobs/{job_id}/status")
def update_status(job_id: str, body: StatusUpdate):
    """Update application tracking status."""
    valid = {"new", "saved", "applied", "interview", "rejected", "offer"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {valid}")
    return update_job_status(job_id, body.status)


@app.post("/tailor/gap-analysis")
def gap_analysis_endpoint(req: TailorRequest):
    """Analyse gaps between candidate resume and job, return actionable suggestions."""
    description, title, company = _resolve_job(req.job_id, req.job_description, req.job_title, req.company)
    suggestions = analyze_gaps(description, title, company)
    return {"suggestions": suggestions}


@app.post("/tailor/resume")
def tailor_resume_endpoint(req: TailorRequest):
    """Generate tailored resume → returns metadata + download URL for DOCX.
    Optionally accepts approved_suggestions from gap-analysis to incorporate."""
    description, title, company = _resolve_job(req.job_id, req.job_description, req.job_title, req.company)
    result = tailor_resume(description, title, company, req.approved_suggestions or [])
    return {
        "filename": result["filename"],
        "download_url": f"/tailor/resume/download/{result['filename']}",
        "keyword_matches": result["keyword_matches"],
        "resume_json": result["resume_json"],
    }


@app.get("/tailor/resume/download/{filename}")
def download_resume(filename: str):
    """Stream the generated DOCX resume file."""
    out_dir = os.path.join(os.path.dirname(__file__), "outputs")
    file_path = os.path.join(out_dir, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found or expired")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.post("/tailor/cover-letter")
def cover_letter_endpoint(req: CoverLetterRequest):
    """Generate a tailored cover letter for a job."""
    description, title, company = _resolve_job(req.job_id, req.job_description, req.job_title, req.company)
    text = generate_cover_letter(description, title, company, req.extra_context or "")
    return {"cover_letter": text}


@app.post("/score")
def score_single(req: TailorRequest):
    """Score a custom job description (paste any JD to get a score)."""
    if not req.job_description:
        raise HTTPException(status_code=400, detail="job_description required")
    job = {
        "title": req.job_title,
        "company": req.company,
        "description": req.job_description,
        "url": f"manual-{int(time.time())}",
    }
    return score_job(job)


# ─────────────────────────── HELPERS ───────────────────────────

def _resolve_job(job_id, description, title, company):
    if job_id:
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job["description"], job["title"], job["company"]
    if description:
        return description, title or "", company or ""
    raise HTTPException(status_code=400, detail="Provide job_id or job_description")


def _scrape_and_score(keyword: str, location: str, max_per_source: int, sources):
    global _scrape_status
    _scrape_status = {"running": True, "progress": f"Scraping '{keyword}'...", "last_run": None, "total_found": 0}
    try:
        jobs = scrape_all_sources(keyword, location, max_per_source, sources)
        # Save unscored immediately so jobs appear in UI right away
        upsert_jobs(jobs)
        _scrape_status["total_found"] = len(jobs)
        already_scored = get_already_scored_urls()
        new_jobs = [j for j in jobs if j.get("url") not in already_scored]
        _scrape_status["progress"] = f"AI scoring {len(new_jobs)} new jobs (browse now)..."
        scored = score_jobs_batch(new_jobs)
        upsert_jobs(scored)
        _scrape_status = {
            "running": False,
            "progress": f"Done — {len(scored)} jobs scored",
            "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_found": len(scored),
        }
    except Exception as e:
        _scrape_status = {"running": False, "progress": f"Error: {e}", "last_run": None, "total_found": 0}


def _full_scrape_and_score():
    global _scrape_status
    _scrape_status = {"running": True, "progress": "Searching all sources...", "last_run": None, "total_found": 0}
    try:
        jobs = run_all_search_queries(max_per_source=10)
        print(f"[main] Scraped {len(jobs)} total jobs")

        # Filter out jobs with no URL or no title — Supabase requires URL not null
        jobs = [j for j in jobs if j.get("url") and j.get("title")]
        print(f"[main] {len(jobs)} jobs have valid URL+title, upserting...")

        # Save unscored immediately — jobs visible in UI NOW
        try:
            upsert_jobs(jobs)
            print(f"[main] Upserted {len(jobs)} jobs to Supabase OK")
        except Exception as db_err:
            print(f"[main] Supabase upsert error: {db_err}")
            raise

        _scrape_status["total_found"] = len(jobs)
        _scrape_status["progress"] = f"Found {len(jobs)} jobs — scoring new ones (browse now)..."

        # Skip jobs already scored — saves Claude API calls
        already_scored = get_already_scored_urls()
        new_jobs = [j for j in jobs if j.get("url") not in already_scored]
        print(f"[main] Scoring {len(new_jobs)} new jobs ({len(jobs)-len(new_jobs)} already scored, skipped)")

        if new_jobs:
            scored = score_jobs_batch(new_jobs)
            upsert_jobs(scored)
            print(f"[main] Scored and saved {len(scored)} jobs")

        _scrape_status = {
            "running": False,
            "progress": f"Done — {len(jobs)} jobs found, {len(new_jobs)} scored",
            "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_found": len(jobs),
        }
    except Exception as e:
        import traceback
        print(f"[main] Full search error: {traceback.format_exc()}")
        _scrape_status = {"running": False, "progress": f"Error: {e}", "last_run": None, "total_found": 0}
