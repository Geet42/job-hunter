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

RESUME_STRUCTURED_PROMPT = """You are an elite technical resume writer who has helped hundreds of candidates land offers at FAANG and top-tier tech companies. Your task: produce a resume that passes ATS screening AND impresses a senior engineer interviewer — for this specific job description.

STRICT RULES — violate any of these and the resume fails:
1. Output ONLY valid JSON — zero markdown, zero code fences, zero explanation.
2. Never invent experience. Only use facts from the candidate resume below.
3. Every bullet = Action verb + specific technology/method + quantified result. No vague statements.
4. Bullets must NOT contain **markdown** — plain text only. Bold terms go in bold_terms[] array only.
5. Top 3 hard skills from JD must appear in Skills section AND at least twice across bullets.
6. Mirror JD language exactly where truthful (copy verb phrases, not synonyms).
7. Summary: 2 tight sentences max. Lead with the top JD requirement. End with "Dublin, available immediately."
8. Remove any experience/project bullet that does not map to a JD keyword. No filler.
9. Skills section: put JD's primary tech stack first in each category.
10. Reframe project bullets to highlight the same problems the JD describes.

ANALYSIS PHASE (do this silently before writing JSON):
- Extract top 5 hard skills + top 3 methodologies from JD.
- Extract exact verb phrases from JD responsibilities section.
- Identify which 2 experiences and 2-3 projects from candidate's resume best match JD requirements.
- Map every candidate bullet to a JD keyword — drop bullets with no mapping.
- Identify metrics that can be linked to JD pain points (latency, scale, reliability, error rates).

Output EXACTLY this JSON schema — all fields required:
{{
  "name": "GEET PRASHANT BHUTE",
  "contact": "Dublin, Ireland | +353 894 991 592 | geetbhute18@gmail.com | github.com/Geet42 | linkedin.com/in/geetbhute | geetbhute.vercel.app",
  "summary": "<2 sentences max: sentence 1 = top 3 JD keywords + candidate's strongest matching credential; sentence 2 = value prop + location + availability>",
  "skills": {{
    "Languages": "<JD primary language first, then others from candidate>",
    "Frameworks": "<JD frameworks first>",
    "Databases": "<relevant DBs>",
    "DevOps / Cloud": "<relevant DevOps tools>",
    "Tools": "<relevant tools>",
    "Concepts": "<JD methodology terms first>"
  }},
  "experience": [
    {{
      "title": "<exact job title from candidate resume>",
      "company": "<company>",
      "dates": "<dates>",
      "location": "<location>",
      "bullets": [
        "<Action verb> <specific tech/method from JD> <quantified result — must have a number or % or scale>",
        "<Action verb> <different JD keyword> <quantified result>"
      ],
      "bold_terms": ["<primary JD tech to bold>", "<metric to bold e.g. 30%>", "<scale number to bold>"]
    }}
  ],
  "projects": [
    {{
      "name": "<project name>",
      "tech": ["<JD-relevant tech from project>"],
      "context": "<course/context>",
      "bullets": [
        "<Action verb> <JD-relevant architecture/pattern> <quantified or concrete outcome>",
        "<Action verb> <JD-relevant reliability/scale/API concept> <concrete result>"
      ],
      "bold_terms": ["<JD tech term to bold>", "<metric or scale to bold>"]
    }}
  ],
  "education": [
    {{"degree": "<degree>", "institution": "<institution>", "dates": "<dates>"}}
  ],
  "certifications": ["<most relevant certs first>"],
  "keyword_matches": [
    {{"keyword": "<exact JD keyword>", "status": "<found|implied|missing>", "evidence": "<exactly where on resume — section + which bullet>"}}
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
