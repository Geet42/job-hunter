"""
Resume and cover letter tailoring using Claude.
Resume output: structured JSON → DOCX via Node.js generator.
Cover letter output: plain text.
"""

import os
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

RESUME_STRUCTURED_PROMPT = """You are a senior technical resume writer and ATS optimization expert.

Analyze the job description and candidate resume below. Produce a tailored resume as VALID JSON only — no markdown, no explanation, no code fences.

Analysis rules (apply before writing):
- Identify top 5 hard skills from JD. Top 3 soft skills/methodologies.
- Extract exact verb phrases from JD responsibilities.
- Identify the 2 strongest experiences + 2-3 strongest projects most relevant to the JD.
- Every bullet must map to a JD keyword. Remove bullets that do not.
- Mirror JD language exactly where truthful.
- Top 3 JD hard skills must appear at least 3 times across the resume.
- Use past tense. Action-Result format with metrics. Max 2 bullets per entry.
- Bold terms should be the primary tech and metrics in each bullet.

Output EXACTLY this JSON schema:
{{
  "name": "GEET PRASHANT BHUTE",
  "contact": "Dublin, Ireland | +353 894 991 592 | geetbhute18@gmail.com | github.com/Geet42 | linkedin.com/in/geetbhute | geetbhute.vercel.app",
  "summary": "<two-line summary: top 3 JD keywords, strongest credential, location, availability — no buzzwords>",
  "skills": {{
    "Languages": "<comma-separated, JD primary stack first>",
    "Frameworks": "<comma-separated>",
    "Databases": "<comma-separated>",
    "DevOps / Cloud": "<comma-separated>",
    "Tools": "<comma-separated>",
    "Concepts": "<comma-separated>"
  }},
  "experience": [
    {{
      "title": "<job title>",
      "company": "<company>",
      "dates": "<dates>",
      "location": "<location>",
      "bullets": ["<bullet 1>", "<bullet 2>"],
      "bold_terms": ["<term to bold>", "<metric to bold>"]
    }}
  ],
  "projects": [
    {{
      "name": "<project name>",
      "tech": ["<tech1>", "<tech2>"],
      "context": "<course/context>",
      "bullets": ["<bullet 1>", "<bullet 2>"],
      "bold_terms": ["<term to bold>"]
    }}
  ],
  "education": [
    {{
      "degree": "<degree>",
      "institution": "<institution>",
      "dates": "<dates>"
    }}
  ],
  "certifications": ["<cert1>", "<cert2>"],
  "keyword_matches": [
    {{"keyword": "<JD keyword>", "status": "<found|implied|missing>", "evidence": "<where on resume>"}}
  ]
}}

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{candidate_resume}

GITHUB: github.com/Geet42
"""


def tailor_resume(job_description: str, job_title: str = "", company: str = "") -> dict:
    """
    Generate a tailored resume as a DOCX file.
    Returns: dict with docx_path, keyword_matches, and resume_json.
    """
    prompt = RESUME_STRUCTURED_PROMPT.format(
        job_description=f"Title: {job_title}\nCompany: {company}\n\n{job_description[:4000]}",
        candidate_resume=CANDIDATE_RESUME_TEXT,
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    resume_data = json.loads(raw)

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
