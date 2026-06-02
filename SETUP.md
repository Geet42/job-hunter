# Job Hunter — Setup Guide

## Step 1: Supabase — Create the database table

1. Go to https://supabase.com → your project → SQL Editor
2. Paste and run this SQL (also in `backend/db.py` under `SCHEMA_SQL`):

```sql
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

create or replace function update_updated_at()
returns trigger as $$
begin new.updated_at = now(); return new; end;
$$ language plpgsql;

create trigger jobs_updated_at
  before update on jobs
  for each row execute function update_updated_at();

create index if not exists jobs_score_idx on jobs(ai_score desc);
create index if not exists jobs_status_idx on jobs(status);
create index if not exists jobs_source_idx on jobs(source);
```

3. Get your credentials: Settings → API → copy `URL` and `anon public` key

## Step 2: Backend — Set up environment

```bash
cd C:\Users\HP\job-hunter\backend

# Create .env file from template
copy .env.example .env
```

Edit `.env` and fill in:
- `APIFY_TOKEN` — from https://console.apify.com → Settings → Integrations → API tokens
- `ANTHROPIC_API_KEY` — from https://console.anthropic.com → API Keys
- `SUPABASE_URL` — from Supabase Settings → API
- `SUPABASE_ANON_KEY` — from Supabase Settings → API

## Step 2.5: Start Ollama (do this every time before running the backend)

Ollama is installed at: `C:\Users\HP\AppData\Local\Programs\Ollama\`

Just open the **Ollama app** from Start menu — it runs in the system tray.
OR run in terminal:
```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
```

Verify it's running:
```powershell
ollama list
# Should show: llama3.2:3b
```

## Step 3: Backend — Install and run

```bash
cd C:\Users\HP\job-hunter\backend

# Install dependencies
pip install -r requirements.txt

# Load .env and start server
# On Windows PowerShell:
Get-Content .env | ForEach-Object {
  if ($_ -match '^([^#][^=]*)=(.*)$') {
    [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2])
  }
}
uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

## Step 4: Frontend — Run

```bash
cd C:\Users\HP\job-hunter\frontend
npm install
npm run dev
```

Open: http://localhost:3000

## Step 5: Use it!

1. Open http://localhost:3000
2. Click **"Full Search (All Roles)"** — runs all 8 search queries across 4 Ireland job boards
3. Wait ~5-10 minutes for scraping + AI scoring to complete
4. Jobs appear sorted by score (1-10)
5. Click any job → see Analysis tab:
   - Score out of 10
   - Verdict (Strong Apply / Apply / Maybe / Skip)
   - Matches (what you have)
   - Gaps (what you're missing)
   - Red flags
   - ATS keywords present/missing
6. Click **"Tailor Resume"** → Claude generates a job-specific resume
7. Click **"Cover Letter"** → Claude writes a tailored cover letter
8. Use the dropdown to track status (Applied, Interview, etc.)
9. Use "Paste any JD to score" panel for jobs you find elsewhere

## Updating your profile

Edit `backend/profile.py` to update:
- Skills (as you learn new ones)
- Experience (after each internship)
- Target roles (add/remove)
- Search queries (tune keywords)
