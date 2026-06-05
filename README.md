# Job Hunter — Ireland 🇮🇪

An AI-powered job search assistant I built specifically for the **Irish job market**.

## Why I built this

While job hunting in Ireland, I ran into a real problem: **entry-level, graduate, intern, and apprenticeship opportunities are scarce and easily lost** in the noise. The big job boards bury them under senior roles, recruiter spam, and non-software listings, and no single board has good Ireland coverage on its own.

So I built my own pipeline. Based on **my own profile** (MSc Computer Science @ UCD, Java / Python / Spring Boot / AI-ML / Full Stack), it:

1. **Scrapes jobs across every major source** — LinkedIn, Indeed, Glassdoor, IrishJobs, Reed (UK/IE), plus direct **company career sites** (Workday, Greenhouse, SmartRecruiters, Lever, Workable) — all filtered down to **genuinely entry-level Irish roles**.
2. **Scores every job out of 10** using a strong, profile-aware AI prompt — with a verdict (Strong Apply / Apply / Maybe / Skip) and a breakdown.
3. **Analyses the gaps** between my saved resume and each job description.
4. **Tailors my resume** into an ATS-optimised one-page DOCX, applying only the fixes I accept.
5. **Writes a tailored cover letter** for the role.

My resume lives in the DB/profile once, so every job gets scored and tailored against it automatically.

---

## Features

### Job aggregation (free, no paid scraping)
- **LinkedIn** — public guest jobs API (no login), real Ireland listings with posting dates
- **Indeed · Glassdoor · IrishJobs** — via the **Jooble** aggregator API (free key), labelled by their origin board
- **Reed** — UK/Ireland job board API
- **Workday** — direct CXS API for 27 verified Ireland-office employers (Mastercard, Cisco, State Street, Stryker, Medtronic, Accenture, Intel, AstraZeneca, Pfizer…)
- **Greenhouse** — public ATS API for ~78 Dublin-office tech companies (Stripe, Intercom, Cloudflare, MongoDB…)
- **SmartRecruiters · Lever · Workable** — more direct company career sites
- _BambooHR is supported but needs a per-company list, so it's low-yield and off by default._

### Smart filtering (the core of it)
- **Entry-level only** — a word-boundary regex rejects `senior / staff / principal / lead / director / manager / architect / Engineer II-III` etc., while keeping genuine `junior / graduate / intern / associate` roles
- **Experience filter** — rejects descriptions requiring "3+ years", "5+ years" ranges, or intern-exclusion clauses
- **Software-only** — drops sales, marketing, HR, finance, physical/hardware engineering, pharma/medtech, and support roles
- Filters run **twice**: at scrape time (before saving) and as a post-search DB purge, so junk never re-appears

### AI scoring & tailoring
- **Score out of 10** with verdict, one-line reason, and a breakdown (required skills / preferred skills / cultural fit / ATS keyword coverage)
- **Matches, gaps, and red flags** per job
- **ATS keyword analysis** — which keywords from the JD are present vs missing in my profile
- **Gap analysis** — honest, profile-grounded suggestions (each tagged Safe or Stretch) for closing the gap
- **Resume tailoring** — generates a one-page ATS-optimised **DOCX** applying only the gap fixes I accept
- **Cover letter** — tailored, human-sounding letter for the specific role
- **Paste-any-JD** — paste a description from anywhere to score + tailor against it instantly

### Workflow UI (dark theme)
- Jobs sorted **past-24h first, then newest**, with the **posting date** (not scrape date) shown on each card
- **Source badges**, score, and verdict on every card
- **Applied / Delete** buttons that hide a job and stop it reappearing on future scrapes (status is preserved across re-scrapes)
- **↺ Restore** to undo a mis-clicked Applied/Delete
- **Live keyword filter** over loaded jobs + score/status/source filters

---

## How I did it

**Architecture**

```
┌────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Next.js (TS)  │────▶│   FastAPI backend    │────▶│  Supabase (PG)  │
│  dark-theme UI │◀────│  scrape · score · AI │◀────│  jobs table     │
└────────────────┘     └──────────┬───────────┘     └─────────────────┘
                                   │
            ┌──────────────────────┼───────────────────────────┐
            ▼                      ▼                            ▼
   Job sources (free)      Scoring engine              Tailoring (Claude)
   LinkedIn · Jooble       Ollama (local, free)        gap analysis
   Reed · Workday          → Claude Haiku fallback      resume DOCX (Node/docx)
   Greenhouse · etc.                                    cover letter
```

**The pieces**

- **`backend/scraper.py`** — one `scrape_*()` per source, all normalised to a common job shape, run in parallel/sequential as each API tolerates. `_is_engineering_role()` is the three-layer entry-level + software-only filter applied before anything is saved.
- **`backend/profile.py`** — my candidate profile, resume text, target roles, search queries, and the exact scoring/resume/cover-letter prompts.
- **`backend/scorer.py`** — scores each job 0–10. Uses **Ollama locally for free** when available, and **falls back to Claude Haiku** otherwise. Returns verdict, reasons, matches/gaps, keywords, and a weighted breakdown.
- **`backend/tailor.py`** — Claude (Sonnet) for gap analysis, resume JSON, and cover letters. The resume JSON is rendered to a real `.docx` by a small **Node.js `docx` generator** (`backend/docx_gen/generate.js`).
- **`backend/db.py`** — Supabase CRUD. Upserts dedupe by URL and **preserve user-set status** (applied/rejected) so hidden jobs never resurface. `purge_bad_jobs()` re-applies the filters after each search.
- **`backend/main.py`** — FastAPI endpoints (search, jobs, status, scoring, tailoring).
- **`frontend/app/page.tsx`** — the entire single-page dark-theme UI.

**Design decisions**
- **Free-first**: every source is a free/public API; scoring prefers local Ollama; Claude is used only where quality matters (tailoring). Jooble's free key is used sparingly (≈6 requests per full search).
- **Filter twice**: bad jobs are filtered both before insert and after search, because new sources keep finding new ways to sneak senior/non-software roles in.
- **Posting date, not scrape date**: each source's real posted date is parsed and normalised to ISO so "past 24h" sorting is meaningful.

---

## How to run

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** (for the frontend and the DOCX generator)
- A free **[Supabase](https://supabase.com)** project (Postgres)
- An **[Anthropic API key](https://console.anthropic.com)** (for tailoring; scoring can run free on Ollama)
- _Optional but recommended:_ **[Ollama](https://ollama.com)** running locally with `llama3.2` for free scoring
- _Optional:_ free API keys for **[Reed](https://www.reed.co.uk/developers)** and **[Jooble](https://jooble.org/api/about)**

### 1. Database
Create the `jobs` table — run the SQL in [`SETUP.md`](./SETUP.md) (or `SCHEMA_SQL` in `backend/db.py`) in the Supabase SQL Editor.

### 2. Backend
```bash
cd backend
pip install -r requirements.txt

# Node deps for the DOCX generator
cd docx_gen && npm install && cd ..

# Create backend/.env (this file is gitignored — never commit it)
```

`backend/.env`:
```env
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=...
REED_API_KEY=...          # optional
JOOBLE_API_KEY=...        # optional (free, unlocks Indeed/IrishJobs/Glassdoor)
ADZUNA_APP_ID=...         # optional
ADZUNA_API_KEY=...        # optional
RAPIDAPI_KEY=...          # optional
```

Run it:
```bash
uvicorn main:app --port 8000
```

_(Optional) free local scoring:_
```bash
ollama pull llama3.2
ollama serve
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:3000**.

### 4. Use it
1. Click **Full Search** in the header — it scrapes every source, filters to entry-level Irish roles, and scores them (browse as they populate).
2. Click a job to see its **score breakdown, matches, gaps, and ATS keywords**.
3. Hit **Analyse Gaps** → accept the fixes you want → **Tailor Resume** to download an ATS DOCX.
4. Hit **Cover Letter** for a tailored letter.
5. Use **✓ Applied** / **✕ Delete** to keep your list clean (they won't reappear on re-scrapes); **↺ Restore** to undo.
6. Or paste any JD into the sidebar box to score + tailor against it instantly.

---

## Tech stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js (App Router) · React · TypeScript · Tailwind CSS |
| Backend | FastAPI · httpx · Pydantic |
| Database | Supabase (PostgreSQL) |
| Scoring | Ollama (local, free) → Claude Haiku fallback |
| Tailoring | Claude Sonnet + Node.js `docx` generator |
| Sources | LinkedIn · Jooble · Reed · Workday · Greenhouse · SmartRecruiters · Lever · Workable |

---

## Notes & honesty

- **LinkedIn/Indeed/Glassdoor/IrishJobs block direct free scraping.** I get them legitimately via LinkedIn's public guest API and the Jooble aggregator. There's no paid scraping in the default flow.
- This is built around **my** profile and resume. To use it for yourself, edit `backend/profile.py` (profile, resume text, target roles, search queries).
- `backend/.env` holds secrets and is **gitignored** — never commit it.

Built by **Geet Bhute** · Dublin, Ireland.
