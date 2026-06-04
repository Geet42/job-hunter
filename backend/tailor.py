"""
Resume and cover letter tailoring using Claude.
Resume output: structured JSON → DOCX via Node.js generator.
Cover letter output: plain text.
"""

import os
import re
import json
import subprocess
import tempfile
import time
import anthropic
from profile import COVER_LETTER_PROMPT_TEMPLATE

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

DOCX_GEN = os.path.join(os.path.dirname(__file__), "docx_gen", "generate.js")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CANDIDATE_RESUME_TEXT = """GEET PRASHANT BHUTE
Dublin, Ireland | +353 894 991 592 | geetbhute18@gmail.com | github.com/Geet42 | linkedin.com/in/geetbhute | geetbhute.vercel.app

Java developer (MSc UCD, 2025-26) with hands-on experience building, testing, and maintaining Spring Boot REST APIs and microservices in professional settings. Available full-time in Dublin, Agile-familiar, and eager to contribute within a collaborative development team.

Skills
Languages: Java, Python, TypeScript, JavaScript, SQL
Frameworks: Spring Boot, FastAPI, Flask, React, Next.js, LangChain
Databases: PostgreSQL, MySQL, ChromaDB, Supabase
DevOps / Cloud: Docker, Kubernetes, GitHub Actions, Azure (Certified), AWS, Linux, Vercel
Tools: Git, Postman, Swagger, REST APIs
Concepts: OOP, Microservices, CI/CD, REST API Design, Agile

Experience
Software Engineering Intern | Tajshree Autowheels Pvt. Ltd. | May 2025 - Aug 2025 | Nagpur, India
- Developed, tested, and maintained Java and Spring Boot payment/booking backend with auth and refund logic, processing 100+ validated transactions across 3 service modules.
- Troubleshot 12+ defects via structured logging, reducing API error rate by 30%; automated deployments via Docker and GitHub Actions CI/CD cutting release time under 10 minutes.

Software Engineering Intern | RCOEM | Dec 2024 - May 2025 | Nagpur, India
- Built Flask REST API endpoints for backend inference service, cutting prediction latency by 35% through preprocessing optimisation with consistent sub-second response times.
- Containerised full backend stack with Docker and configured GitHub Actions CI/CD, reducing environment setup to under 5 minutes; published in JISEM 2025.

Projects
Distributed University Event Booking System | Java 17, Spring Boot, Spring Cloud Gateway, PostgreSQL, Docker, Resilience4j | UCD COMP41720
- Designed Booking Service across 4-microservice architecture enforcing PENDING_PAYMENT state transitions using OOP and REST API coordination.
- Integrated Resilience4j circuit breakers across all inter-service calls; zero cascading failures in payment-failure and seat-exhaustion stress tests (team of 3).

BankingApp-Resilience | Java 17, Spring Boot, Resilience4j, Docker, Kubernetes, Chaos Toolkit | UCD Distributed Systems
- Built resilient banking microservices with circuit breakers, retry logic, deployed via Docker Compose and Kubernetes manifests.
- Validated fault tolerance via Chaos Toolkit experiments confirming zero cascading failures and full-service recovery.

Education
MSc Computer Science (Negotiated Learning) | University College Dublin | Sep 2025 - Present
B.Tech Computer Science, First Class Honours | RCOEM Nagpur | Dec 2021 - May 2025

Certifications
Spring Boot Development (Coding Shuttle) | Microsoft Azure (Cloud, Security, Data Storage) | AWS Cloud Practitioner | Kubernetes and Linux (Linux Foundation)
"""

RESUME_STRUCTURED_PROMPT = """You are a senior technical resume writer and ATS optimization expert. Your task: produce a one-page, print-ready resume that scores exceptionally well with both ATS and human reviewers for this specific job.

ANALYSIS PHASE (do this silently before writing JSON):
1. Identify the top 5 most frequently mentioned hard skills in the JD.
2. Identify the top 3 soft skills or methodologies in the JD.
3. Extract exact verb phrases used in JD responsibilities (e.g. "develop, test, and maintain").
4. Note non-negotiable requirements (degrees, years of experience, work authorization).
5. Determine seniority level signaled by JD and adjust tone accordingly.
6. From the candidate resume and GitHub (github.com/Geet42):
   - Categorise every technology by evidence tier: (1) professional experience, (2) shipped project, (3) academic project.
   - Identify the 2 strongest experiences most relevant to the JD.
   - Identify the 2-3 strongest projects most relevant to the JD.
   - Extract metrics that can be directly tied to JD responsibilities.

CONTENT RULES (apply before writing):
- Every line must map to at least one JD keyword — remove any line that does not.
- Reorder skills so JD's primary technical stack is listed first, grouped logically.
- Summary: 2 tight lines — top 3 JD keywords, candidate's strongest credential, location, availability. No buzzwords.
- Use the JD's exact verb phrases in bullets wherever truthful.
- If candidate has a gap vs JD, frame the closest real evidence toward that skill without exaggeration.
- Bold terms are primary technologies and metrics — list them in bold_terms[] only, NOT in bullet text.
- Bullet text must be plain ASCII — no em dashes, no **markdown**, no unicode punctuation.
- Top 3 JD hard skills must appear at least 3 times each across the full resume.
- ATS: mirror JD language exactly; spell out acronyms if JD does; use standard section headers only.
- Human readability: no two bullets start with the same verb; vary sentence rhythm; bullets must sound like a competent engineer, not keyword stuffing.
- Exactly 2 bullets per experience entry; exactly 2 bullets per project entry.
- Each bullet: Action verb + JD-matched technology/method + quantified result (must include a number, %, or concrete scale).

Output ONLY valid JSON — no markdown, no code fences, no explanation:
{{
  "name": "GEET PRASHANT BHUTE",
  "contact": "Dublin, Ireland | +353 894 991 592 | geetbhute18@gmail.com | github.com/Geet42 | linkedin.com/in/geetbhute | geetbhute.vercel.app",
  "summary": "<2-line summary: line 1 = top 3 JD hard skills + strongest matching credential; line 2 = availability, location, value prop>",
  "skills": {{
    "Languages": "<JD primary language first, comma-separated>",
    "Frameworks": "<JD frameworks first>",
    "Databases": "<relevant databases>",
    "DevOps / Cloud": "<relevant DevOps/cloud tools>",
    "Tools": "<relevant tools>",
    "Concepts": "<JD methodology terms first>"
  }},
  "experience": [
    {{
      "title": "<exact title from candidate resume>",
      "company": "<company>",
      "dates": "<dates>",
      "location": "<location>",
      "bullets": [
        "<Action verb> <JD verb phrase + tech> <quantified result with number or %>",
        "<Different action verb> <different JD keyword + method> <quantified result>"
      ],
      "bold_terms": ["<JD primary tech>", "<metric e.g. 30%>", "<scale e.g. 100+>"]
    }}
  ],
  "projects": [
    {{
      "name": "<project name>",
      "tech": ["<JD-relevant tech from this project>"],
      "context": "<course or context>",
      "bullets": [
        "<Action verb> <JD-relevant architecture/pattern> <concrete quantified outcome>",
        "<Action verb> <JD-relevant reliability/scale/API concept> <concrete result>"
      ],
      "bold_terms": ["<JD tech term>", "<metric or scale>"]
    }}
  ],
  "education": [
    {{"degree": "<degree>", "institution": "<institution>", "dates": "<dates>"}}
  ],
  "certifications": ["<most JD-relevant cert first>"],
  "keyword_matches": [
    {{
      "keyword": "<exact JD keyword>",
      "status": "<found|implied|missing>",
      "evidence": "<which section and bullet — be specific>"
    }}
  ]
}}

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{candidate_resume}

GITHUB: github.com/Geet42
"""


GAP_ANALYSIS_PROMPT = """You are a senior technical recruiter and resume strategist.

Analyze the gaps between the candidate's resume and this job description. Then suggest SPECIFIC, HONEST changes that close those gaps — only based on real experience the candidate already has.

RULES:
- Never suggest inventing experience. Suggestions must be grounded in the candidate's actual background.
- Each suggestion must be actionable and specific (exact new bullet text, exact skill to add, exact reframing).
- Categorise risk: "safe" = truthful reframing of existing experience; "stretch" = implied skill from related work (be honest about this).
- Prioritise suggestions by impact — put highest-impact ones first.
- Max 8 suggestions total.

For each gap, output ONE suggestion object. Respond ONLY with a valid JSON array, no markdown.

Each object MUST have exactly these fields:
{{
  "gap": "<specific thing missing from the resume vs JD requirement>",
  "impact": "<why this gap hurts the application — one sentence>",
  "suggestion": "<exactly what to change: add/reframe/reorder — be specific about section and text>",
  "new_text": "<the exact new bullet, skill entry, or summary sentence to use — ready to paste>",
  "section": "<Skills | Summary | Experience bullet | Project bullet>",
  "risk": "<safe | stretch>",
  "rationale": "<why the candidate actually has this or can honestly claim it>"
}}

JOB DESCRIPTION:
Title: {job_title}
Company: {company}

{job_description}

CANDIDATE RESUME:
{candidate_resume}

GITHUB: github.com/Geet42

Return a JSON array of suggestion objects. No other text.
"""


def analyze_gaps(job_description: str, job_title: str = "", company: str = "") -> list[dict]:
    """
    Identify gaps between candidate resume and JD, return specific actionable suggestions.
    Each suggestion has: gap, impact, suggestion, new_text, section, risk, rationale.
    """
    prompt = GAP_ANALYSIS_PROMPT.format(
        job_title=job_title,
        company=company,
        job_description=job_description[:4000],
        candidate_resume=CANDIDATE_RESUME_TEXT,
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    suggestions = json.loads(raw)
    if isinstance(suggestions, dict):
        suggestions = [suggestions]
    return suggestions


def tailor_resume(job_description: str, job_title: str = "", company: str = "",
                  approved_suggestions: list[dict] = None) -> dict:
    """
    Generate a tailored resume as a DOCX file.
    Returns: dict with docx_path, keyword_matches, and resume_json.
    """
    # Build approved suggestions block if any
    suggestions_block = ""
    if approved_suggestions:
        suggestions_block = "\n\nAPPROVED RESUME IMPROVEMENTS (candidate has accepted these — incorporate all of them):\n"
        for i, s in enumerate(approved_suggestions, 1):
            suggestions_block += f"\n{i}. Section: {s.get('section','')}\n"
            suggestions_block += f"   Gap covered: {s.get('gap','')}\n"
            suggestions_block += f"   Use this text: {s.get('new_text','')}\n"
        suggestions_block += "\nEnsure every approved improvement appears in the final resume.\n"

    prompt = RESUME_STRUCTURED_PROMPT.format(
        job_description=f"Title: {job_title}\nCompany: {company}\n\n{job_description[:4000]}{suggestions_block}",
        candidate_resume=CANDIDATE_RESUME_TEXT,
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    # Handle truncated JSON (max_tokens hit mid-response) — close open structures
    try:
        resume_data = json.loads(raw)
    except json.JSONDecodeError:
        # Count unclosed brackets/braces and close them
        open_b = raw.count("{") - raw.count("}")
        open_s = raw.count("[") - raw.count("]")
        patch = ("]" * max(open_s, 0)) + ("}" * max(open_b, 0))
        try:
            resume_data = json.loads(raw + patch)
        except json.JSONDecodeError as e:
            raise ValueError(f"Resume JSON truncated and unrecoverable: {e}. Try again.") from e

    # Strip **bold** markdown from all text fields — the DOCX generator
    # handles bolding via bold_terms[], so literal asterisks must be removed.
    def _strip_bold(text: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"\1", text) if text else text

    resume_data["summary"] = _strip_bold(resume_data.get("summary", ""))
    for exp in resume_data.get("experience", []):
        exp["bullets"] = [_strip_bold(b) for b in exp.get("bullets", [])]
    for proj in resume_data.get("projects", []):
        proj["bullets"] = [_strip_bold(b) for b in proj.get("bullets", [])]

    # Set output path
    safe_title = (job_title or "resume").replace(" ", "_").replace("/", "-")[:40]
    safe_company = (company or "company").replace(" ", "_").replace("/", "-")[:20]
    timestamp = int(time.time())
    filename = f"Geet_Bhute_{safe_title}_{safe_company}_{timestamp}.docx"
    out_path = os.path.join(OUTPUT_DIR, filename)
    resume_data["output_path"] = out_path

    # Write JSON to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(resume_data, f)
        tmp_path = f.name

    # Call Node.js generator
    result = subprocess.run(
        ["node", DOCX_GEN, tmp_path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    os.unlink(tmp_path)

    if result.returncode != 0:
        raise RuntimeError(f"DOCX generation failed: {result.stderr}")

    stdout = result.stdout.strip()
    if not stdout.startswith("OK:"):
        raise RuntimeError(f"Unexpected generator output: {stdout}")

    docx_path = stdout[3:]

    return {
        "docx_path": docx_path,
        "filename": filename,
        "keyword_matches": resume_data.get("keyword_matches", []),
        "resume_json": resume_data,
    }


def generate_cover_letter(
    job_description: str,
    job_title: str = "",
    company: str = "",
    extra_context: str = "",
) -> str:
    """Generate a tailored cover letter. Returns plain text."""
    context = f"Role: {job_title} at {company}. {extra_context}".strip()

    prompt = COVER_LETTER_PROMPT_TEMPLATE.format(
        job_description=f"Title: {job_title}\nCompany: {company}\n\n{job_description[:3000]}",
        candidate_resume=CANDIDATE_RESUME_TEXT,
        context=context,
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text
