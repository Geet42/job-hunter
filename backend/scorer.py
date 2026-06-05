"""
AI scoring engine — Claude-minimized.

Strategy:
  1. Ollama (llama3.2:3b) — primary scorer, FREE, local, zero Claude cost
  2. Claude Haiku         — fallback only, 10x cheaper than Sonnet
  3. Batch scoring        — 5 jobs per Claude call (5x fewer API calls)
  4. Skip already-scored  — jobs with existing scores are never re-scored
  5. Short descriptions   — 1500 chars max fed to AI (vs 4000 before)

Claude Haiku cost: ~$0.25/M tokens input vs Sonnet $3/M = 12x cheaper.
Batching 5 jobs per call = 5x fewer calls.
Combined: ~60x cheaper than original implementation.
"""

import os
import re
import json
import httpx
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

OLLAMA_BASE  = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:3b"

# Use Haiku for scoring (cheap), keep Sonnet only for resume/cover letter
SCORE_MODEL = "claude-haiku-4-5"

# Scoring engine: "claude" (default — far better gap/match extraction, ~cents
# per full search) or "ollama" (free local, but the 3B model leaves gaps empty
# ~70% of the time). Set SCORING_ENGINE=ollama in .env to use free local scoring.
SCORING_ENGINE = os.environ.get("SCORING_ENGINE", "claude").lower()
PREFER_OLLAMA  = SCORING_ENGINE == "ollama"

CANDIDATE_RESUME = """
Geet Prashant Bhute | Dublin, Ireland | geetbhute18@gmail.com | github.com/Geet42 | linkedin.com/in/geetbhute

MSc Computer Science (Negotiated Learning) — University College Dublin, Sep 2025–Present
B.Tech Computer Science, First Class Honours — RCOEM Nagpur, Dec 2021–May 2025

Skills: Java, Python, TypeScript, JavaScript, SQL | Spring Boot, FastAPI, Flask, React, Next.js, LangChain
Databases: PostgreSQL, MySQL, ChromaDB, Supabase
DevOps/Cloud: Docker, Kubernetes, GitHub Actions, Azure (Certified), AWS, Linux, Vercel
Tools: Git, Postman, Swagger, REST APIs
Concepts: OOP, Microservices, CI/CD, REST API Design, Agile, Resilience4j, Circuit Breakers

Experience:
Software Engineering Intern | Tajshree Autowheels Pvt. Ltd. | May–Aug 2025
- Developed, tested, and maintained Java and Spring Boot payment/booking backend with auth and refund logic,
  processing 100+ validated transactions across 3 service modules.
- Troubleshot 12+ defects via structured logging, reducing API error rate by 30%; automated deployments
  via Docker and GitHub Actions CI/CD cutting release time under 10 minutes.

Software Engineering Intern | RCOEM | Dec 2024–May 2025
- Built Flask REST API endpoints for backend inference service, cutting prediction latency by 35%
  through preprocessing optimisation with consistent sub-second response times.
- Containerised full backend stack with Docker and configured GitHub Actions CI/CD, reducing environment
  setup to under 5 minutes; published in JISEM 2025.

Projects:
Nora Comply — EU AI Act RAG Compliance Chatbot | TypeScript, Next.js, RAG, LangChain, Vector Search, LLM, ChromaDB
- RAG chatbot answering EU AI Act compliance questions via semantic vector retrieval + LLM generation with source-grounded, citation-backed answers.
CorpFin AI — Agentic Corporate Finance Autopilot | Python, LangChain, RAG, Monte Carlo Simulation, Observability
- Agentic finance assistant combining RAG over financial docs with Monte Carlo simulation and observable AI traces for multi-step reasoning.
Job Hunter — AI Job Search & Resume Tailoring Platform | Python, FastAPI, Next.js, Supabase (PostgreSQL), Claude API, Web Scraping
- Full-stack platform aggregating jobs from 8+ sources into Supabase via FastAPI; AI prompts score, gap-analyse, and tailor resumes; Next.js dashboard.
Distributed University Event Booking System | Java 17, Spring Boot, Spring Cloud Gateway, PostgreSQL, Docker, Resilience4j
- 4-microservice architecture enforcing transactional state transitions; Resilience4j circuit breakers, zero cascading failures in stress tests.
BankingApp-Resilience | Java 17, Spring Boot, Resilience4j, Docker, Kubernetes, Chaos Toolkit
- Resilient banking microservices with circuit breakers/retry via Docker + Kubernetes; Chaos Toolkit validated zero cascading failures.
Angular Portfolio SPA | Angular, TypeScript, HTML5, CSS3, Vercel
- Component-driven Angular SPA deployed to Vercel with automated builds, sub-3-minute deploys.

Certifications: Spring Boot (Coding Shuttle) | Azure (Cloud, Security, Data Storage) | AWS Cloud Practitioner | Kubernetes & Linux (Linux Foundation)
GitHub: github.com/Geet42
Target: entry-level / intern / graduate software engineering, AI/ML, backend, full-stack roles in Ireland.
NOT a match: sales, account executive, marketing, HR, finance, legal, customer success, product manager.
"""

SCORE_PROMPT_SINGLE = """You are a technical recruiter and ATS expert. Analyze the match between the candidate's resume (and GitHub github.com/Geet42, as evidenced in the resume) and the job description. Respond ONLY with valid JSON — no markdown, no prose.

Work through these reasoning steps silently, then emit the JSON:

STEP 1 — ROLE CHECK (check title first): "{title}"
If the title is clearly non-technical (sales, account exec/manager, business development, marketing, recruiter, HR, legal, finance, operations manager, program/product manager, customer success/support, regulatory, compliance, non-technical analyst/consultant, representative, coordinator, administrator), return the Skip JSON:
{{"score":1,"verdict":"Skip","verdict_reason":"Not a software engineering role — '{title}' is non-technical","matches":[],"gaps":[],"red_flags":["Not a technical role"],"ats_keywords_present":[],"ats_keywords_missing":[],"required_skills_score":0,"preferred_skills_score":0,"cultural_fit_score":0,"ats_score":0,"apply_recommendation":"No"}}

STEP 2 — EXTRACT FROM JD: list the hard requirements (must-haves), preferred skills (nice-to-haves), and ATS keywords (tools, languages, methodologies).

STEP 3 — ASSESS EACH against the candidate's resume + GitHub, classifying each as Explicitly Mentioned, Implied (strong contextual evidence from experience/projects), or Missing. Only count Implied when the evidence is strong.

STEP 4 — WEIGHTED SCORE (be precise, do not inflate):
- Required Skills/Experience (50 pts): % of hard requirements met (explicit or strongly implied)
- Preferred/Desirable Skills (25 pts): % of preferred skills met
- Cultural/Soft Fit (10 pts): teamwork, collaboration, CI/CD discipline, initiative (personal/open-source projects)
- ATS Keyword Coverage (15 pts): % of JD keywords present in resume + GitHub
Sum = score/100, then divide by 10 for the final 1-10 score.

STEP 5 — VERDICT: 8-10 = Strong Apply, 6-7 = Apply, 4-5 = Maybe, 1-3 = Skip.

STEP 6 — GAPS (MANDATORY — never empty for an engineering role): list every required/preferred skill, keyword, or experience that is Missing or weakly represented, and why it hurts the application. Always include: any years-of-experience requirement this entry-level candidate (<1 yr professional) fails to meet; any specific technology/language/framework/protocol/domain named in the JD but absent from the profile (e.g. Angular, Go, BGP/ISIS, large-scale infra); any required degree/cert. Almost every real JD yields 2-4 genuine gaps.

CANDIDATE RESUME + GITHUB (github.com/Geet42):
{candidate}

JOB: {title} at {company}
{description}

Respond with exactly this JSON:
{{"score":<1-10>,"verdict":"<Strong Apply|Apply|Maybe|Skip>","verdict_reason":"<one precise sentence citing specific match or gap>","matches":["<explicit/implied evidence>","<evidence>","<evidence>"],"gaps":["<specific missing requirement + why it matters>","<gap>"],"red_flags":["<dealbreaker if any>"],"ats_keywords_present":["<exact JD keyword found in profile>"],"ats_keywords_missing":["<JD keyword absent>"],"required_skills_score":<0-50>,"preferred_skills_score":<0-25>,"cultural_fit_score":<0-10>,"ats_score":<0-15>,"apply_recommendation":"<Yes|Borderline|No>"}}"""


def _desc(job: dict, max_chars: int = 1500) -> str:
    """Trim description to save tokens."""
    d = job.get("description") or ""
    # Strip HTML tags if present
    import re
    d = re.sub(r"<[^>]+>", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    return d[:max_chars]


def _parse_json(raw: str) -> dict | list:
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        for p in parts:
            p = p.strip().lstrip("json").strip()
            if p.startswith("{") or p.startswith("["):
                raw = p
                break
    start = raw.find("[") if raw.find("[") != -1 and (raw.find("{") == -1 or raw.find("[") < raw.find("{")) else raw.find("{")
    # prefer array if present
    arr_start = raw.find("[")
    obj_start = raw.find("{")
    if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
        end = raw.rfind("]") + 1
        frag = raw[arr_start:end]
    else:
        end = raw.rfind("}") + 1
        frag = raw[obj_start:end]
    try:
        return json.loads(frag)
    except json.JSONDecodeError:
        # Truncated mid-structure — trim to last complete value and close brackets
        salvage = re.sub(r"[,\s]+$", "", frag)
        m = list(re.finditer(r'"(?:[^"\\]|\\.)*"\s*(?=[,\]}])', salvage))
        if m:
            salvage = salvage[: m[-1].end()]
        salvage = re.sub(r"[,\s]+$", "", salvage)
        salvage += ("]" * max(salvage.count("[") - salvage.count("]"), 0))
        salvage += ("}" * max(salvage.count("{") - salvage.count("}"), 0))
        return json.loads(salvage)


def _ollama_available() -> bool:
    try:
        r = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        return any(OLLAMA_MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False


def _score_with_ollama(job: dict) -> dict:
    prompt = SCORE_PROMPT_SINGLE.format(
        candidate=CANDIDATE_RESUME,
        title=job.get("title") or "",
        company=job.get("company") or "",
        description=_desc(job),
    )
    resp = httpx.post(
        f"{OLLAMA_BASE}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.1, "num_predict": 600}},
        timeout=120,
    )
    resp.raise_for_status()
    return _parse_json(resp.json()["response"])


def _score_single_with_claude(job: dict) -> dict:
    """Score one job with Claude Haiku using the full recruiter analysis prompt."""
    prompt = SCORE_PROMPT_SINGLE.format(
        candidate=CANDIDATE_RESUME,
        title=job.get("title") or "",
        company=job.get("company") or "",
        description=_desc(job),
    )
    msg = client.messages.create(
        model=SCORE_MODEL,
        max_tokens=1200,
        system="You are a technical recruiter and ATS expert. Output ONLY one JSON object, no reasoning text.",
        messages=[
            {"role": "user", "content": prompt},
            # Prefill the assistant turn with "{" so Claude is forced to emit JSON
            # immediately (no reasoning preamble) — guarantees a parseable object.
            {"role": "assistant", "content": "{"},
        ],
    )
    text = "{" + msg.content[0].text  # re-add the prefilled brace
    result = _parse_json(text)
    if isinstance(result, list):
        result = result[0]
    return result


_NON_ENGINEERING_TITLE_WORDS = [
    "account executive", "account manager", "account development",
    "business development", "sales", "marketing", "recruiter", "recruitment",
    "human resources", " hr ", "legal", "finance", "financial",
    "operations manager", "program manager", "product manager",
    "customer success", "customer support", "regulatory", "compliance",
    "representative", "coordinator", "administrator",
]

def _is_non_engineering(job: dict) -> bool:
    title = (job.get("title") or "").lower()
    return any(phrase in title for phrase in _NON_ENGINEERING_TITLE_WORDS)


def score_job(job: dict) -> dict:
    """Score a single job. Uses Ollama (free) -> Claude Haiku fallback."""
    if not _desc(job) or len(_desc(job)) < 50:
        return {**job, "ai_score": None, "ai_error": "No description"}

    # Hard skip non-engineering roles without spending any AI tokens
    if _is_non_engineering(job):
        return {**job,
                "ai_score": 1, "ai_verdict": "Skip",
                "ai_verdict_reason": f"Non-engineering role: {job.get('title','')}",
                "ai_matches": [], "ai_gaps": [], "ai_red_flags": ["Not a technical role"],
                "ai_keywords_present": [], "ai_keywords_missing": [],
                "ai_apply": "No",
                "ai_breakdown": {"required_skills": 0, "preferred_skills": 0, "cultural_fit": 0, "ats_coverage": 0},
                "ai_engine": "pre-filter", "ai_error": None}

    try:
        if PREFER_OLLAMA and _ollama_available():
            analysis = _score_with_ollama(job)
            engine   = "ollama"
        else:
            analysis = _score_single_with_claude(job)
            engine   = "claude-haiku"
    except Exception as e:
        try:
            analysis = _score_single_with_claude(job)
            engine   = "claude-haiku-fallback"
        except Exception as e2:
            return {**job, "ai_score": None, "ai_error": str(e2)}

    return _merge(job, analysis, engine)


def score_jobs_batch(jobs: list[dict]) -> list[dict]:
    """
    Score all jobs — one job per AI call for guaranteed correctness.
    Batching was removed because zip(batch, analyses) silently mismatches
    jobs when Claude returns analyses out of order or short-counts.

    Priority: Ollama (free/local) -> Claude Haiku (cheap fallback)
    """
    scorable = [j for j in jobs if len(_desc(j)) >= 50]
    no_desc  = [{**j, "ai_score": None, "ai_error": "No description"}
                for j in jobs if len(_desc(j)) < 50]

    print(f"[scorer] {len(scorable)} jobs to score, {len(no_desc)} skipped (no description)")

    use_ollama = PREFER_OLLAMA and _ollama_available()
    print(f"[scorer] Engine: {'Ollama (FREE, local)' if use_ollama else 'Claude Haiku'}")

    scored = []
    for i, job in enumerate(scorable):
        try:
            result = score_job(job)
            scored.append(result)
            print(f"[scorer] {i+1}/{len(scorable)} scored: {job.get('title','?')[:40]} -> {result.get('ai_score')}/10 ({result.get('ai_engine','?')})")
        except Exception as e:
            print(f"[scorer] Failed to score '{job.get('title','?')}': {e}")
            scored.append({**job, "ai_score": None, "ai_error": str(e)})

    all_results = scored + no_desc
    all_results.sort(key=lambda j: j.get("ai_score") or 0, reverse=True)
    return all_results


def _merge(job: dict, analysis: dict, engine: str) -> dict:
    return {
        **job,
        "ai_score":           analysis.get("score"),
        "ai_verdict":         analysis.get("verdict"),
        "ai_verdict_reason":  analysis.get("verdict_reason"),
        "ai_matches":         analysis.get("matches", []),
        "ai_gaps":            analysis.get("gaps", []),
        "ai_red_flags":       analysis.get("red_flags", []),
        "ai_keywords_present": analysis.get("ats_keywords_present", []),
        "ai_keywords_missing": analysis.get("ats_keywords_missing", []),
        "ai_apply":           analysis.get("apply_recommendation"),
        "ai_breakdown": {
            "required_skills":  analysis.get("required_skills_score"),
            "preferred_skills": analysis.get("preferred_skills_score"),
            "cultural_fit":     analysis.get("cultural_fit_score"),
            "ats_coverage":     analysis.get("ats_score"),
        },
        "ai_engine": engine,
        "ai_error":  None,
    }
