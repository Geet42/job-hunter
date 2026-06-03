"""
Geet's candidate profile — extracted from resume.
Edit this file to update skills, experience, or target roles.
"""

CANDIDATE_PROFILE = {
    "name": "Geet Prashant Bhute",
    "location": "Dublin, Ireland",
    "email": "geetbhute18@gmail.com",
    "github": "github.com/Geet42",
    "linkedin": "linkedin.com/in/geetbhute",
    "portfolio": "geetbhute.vercel.app",
    "availability": "Available full-time in Dublin",
    "education": [
        {
            "degree": "MSc Computer Science (Negotiated Learning)",
            "institution": "University College Dublin",
            "dates": "Sep 2025 - Present",
        },
        {
            "degree": "B.Tech Computer Science, First Class Honours",
            "institution": "RCOEM Nagpur",
            "dates": "Dec 2021 - May 2025",
        },
    ],
    "skills": {
        "languages": ["Java", "Python", "TypeScript", "JavaScript", "SQL"],
        "frameworks": ["Spring Boot", "FastAPI", "Flask", "React", "Next.js", "LangChain"],
        "databases": ["PostgreSQL", "MySQL", "ChromaDB", "Supabase"],
        "devops_cloud": ["Docker", "Kubernetes", "GitHub Actions", "Azure", "AWS", "Linux", "Vercel"],
        "tools": ["Git", "Postman", "Swagger", "REST APIs"],
        "concepts": ["OOP", "Microservices", "CI/CD", "REST API Design", "Agile"],
    },
    "experience": [
        {
            "title": "Software Engineering Intern",
            "company": "Tajshree Autowheels Pvt. Ltd.",
            "dates": "May 2025 - Aug 2025",
            "bullets": [
                "Developed, tested, and maintained Java and Spring Boot payment/booking backend with auth and refund logic, processing 100+ validated transactions across 3 service modules.",
                "Troubleshot 12+ reproducible defects via structured logging, reducing API error rate by 30%; automated deployments via Docker and GitHub Actions CI/CD cutting release time under 10 minutes.",
            ],
        },
        {
            "title": "Software Engineering Intern",
            "company": "RCOEM",
            "dates": "Dec 2024 - May 2025",
            "bullets": [
                "Built and maintained Flask REST API endpoints for backend inference service, cutting prediction latency by 35% and achieving consistent sub-second response times.",
                "Containerised full backend stack with Docker and configured GitHub Actions CI/CD, reducing environment setup to under 5 minutes; work published in JISEM 2025.",
            ],
        },
    ],
    "projects": [
        {
            "name": "Distributed University Event Booking System",
            "tech": ["Java 17", "Spring Boot", "Spring Cloud Gateway", "PostgreSQL", "Docker", "Resilience4j"],
            "context": "UCD COMP41720",
            "bullets": [
                "Designed Booking Service across 4-microservice architecture enforcing PENDING_PAYMENT state transitions using OOP and REST API coordination.",
                "Integrated Resilience4j circuit breakers across all inter-service calls; zero cascading failures in payment-failure and seat-exhaustion stress tests.",
            ],
        },
        {
            "name": "BankingApp-Resilience",
            "tech": ["Java 17", "Spring Boot", "Resilience4j", "Docker", "Kubernetes", "Chaos Toolkit"],
            "context": "UCD Distributed Systems",
            "bullets": [
                "Built resilient banking microservices with circuit breakers, retry logic, deployed via Docker Compose and Kubernetes manifests.",
                "Validated fault tolerance through Chaos Toolkit experiments confirming zero cascading failures and full-service recovery.",
            ],
        },
    ],
    "certifications": [
        "Spring Boot Development (Coding Shuttle)",
        "Microsoft Azure (Cloud, Security, Data Storage)",
        "AWS Cloud Practitioner",
        "Kubernetes and Linux (Linux Foundation)",
    ],
}

# Target roles for Ireland market
TARGET_ROLES = [
    "SDE Intern",
    "Software Engineer Intern",
    "Software Engineer Entry Level",
    "AI SDE Intern",
    "AI Software Engineer",
    "AI ML Intern",
    "Machine Learning Engineer Entry Level",
    "AI Intern",
    "Java Developer Entry Level",
    "Junior Java Developer",
    "Full Stack Intern",
    "Full Stack Developer Entry Level",
    "Graduate Software Engineer",
    "Junior Software Engineer",
]

# Search queries — broad enough to match Reed/Greenhouse results, specific enough to target roles
# Ireland's job market uses terms like "junior", "graduate", "developer" more than "intern"
SEARCH_QUERIES = [
    # Core software engineering
    {"keyword": "software engineer",         "location": "Ireland"},
    {"keyword": "junior software engineer",  "location": "Ireland"},
    {"keyword": "graduate software engineer","location": "Ireland"},
    # Java / Spring Boot (Geet's primary stack)
    {"keyword": "java developer",            "location": "Ireland"},
    {"keyword": "junior java developer",     "location": "Ireland"},
    # Python / AI / ML
    {"keyword": "python developer",          "location": "Ireland"},
    {"keyword": "machine learning engineer", "location": "Ireland"},
    {"keyword": "AI engineer",               "location": "Ireland"},
    # Backend / Full Stack
    {"keyword": "backend developer",         "location": "Ireland"},
    {"keyword": "full stack developer",      "location": "Ireland"},
    # Graduate / Intern specifically
    {"keyword": "graduate engineer",         "location": "Ireland"},
    {"keyword": "software intern",           "location": "Ireland"},
]

# Scoring weights (must sum to 100)
SCORE_WEIGHTS = {
    "required_skills": 50,
    "preferred_skills": 25,
    "cultural_soft_fit": 10,
    "ats_keyword_coverage": 15,
}

# Resume prompt (user's exact format)
RESUME_PROMPT_TEMPLATE = """You are a senior technical resume writer and ATS optimization expert. Your task is to create a highly effective, one-page, print-ready resume that scores exceptionally well with both applicant tracking systems (ATS) and human reviewers.

Analysis Phase (do this silently before writing):
- Identify the top 5 most frequently mentioned hard skills in the JD.
- Identify the top 3 most frequently mentioned soft skills or methodologies in the JD.
- Extract exact verb phrases used in JD responsibilities.
- Note any non-negotiable requirements such as degrees, years of experience, or work authorization.
- Determine the seniority level signaled by the JD and adjust tone accordingly.
From the candidate's resume and GitHub:
- List every technology the candidate has used, categorized by evidence tier: (1) professional experience, (2) shipped project, (3) academic or lab project.
- Identify the 2 strongest experiences most relevant to the JD.
- Identify the 2-3 strongest projects most relevant to the JD.
- Extract any metrics or results that can be directly tied to JD responsibilities.

Content Creation Rules:
- Every line must map to at least one JD keyword; remove any lines that do not.
- Reorder skills so JD's primary technical stack is listed first, grouped logically.
- Write a concise two-line summary including the top 3 JD keywords, candidate's strongest credential, location, and availability. Avoid buzzwords.
- Use the JD's exact verb phrases in experience bullets wherever truthful.
- Select and reframe project bullets to showcase the JD's required tech stack.

Formatting Constraints (strictly enforce):
- Exactly one page, A4 size.
- Two bullets per experience entry; two bullets per project entry.
- Each bullet no longer than two lines at A4 width, font size 10-11pt.
- Bullets must follow Action-Result format and include metrics if available.
- Bold all metrics and primary technologies mentioned in each bullet.
- Use only plain ASCII punctuation — no em dashes, tildes, or Unicode punctuation.
- Single-column layout only; no tables, columns, or text boxes.
- Use past tense for all experience and project bullets.
- Section order: Summary, Skills, Experience, Projects, Education, Certifications.

ATS Optimization Rules:
- Mirror JD language exactly where truthful.
- Top 3 hard skills from JD must appear at least three times each across the entire resume.
- Use standard section headers only.
- Spell out acronyms at least once if the JD spells them out.

Output Instructions:
First, output a keyword match table listing each JD keyword, whether it appears on the resume, and the evidence tier.
Then output the full resume as clean plain text following the exact layout below.

Layout:
CANDIDATE NAME
City, Country | phone | email | github | linkedin | portfolio

One-sentence or two-line summary here tightly tied to the JD.

Skills
Languages: ...
Frameworks: ...
Databases: ...
DevOps / Cloud: ...
Tools: ...
Concepts: ...

Experience
Job Title | Company | Date Range | Location
- Bullet one using JD verb phrase, metric bolded, primary technology bolded.
- Bullet two with different opening verb, result with metric, secondary technology bolded.

Projects
Project Name | Tech stack | Context
- Bullet one.
- Bullet two.

Education
Degree | Institution | Date Range

Certifications
Cert 1 | Cert 2 | Cert 3

---
JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{candidate_resume}

GITHUB: github.com/Geet42
"""

COVER_LETTER_PROMPT_TEMPLATE = """You are an expert cover letter writer who produces genuine, human-feeling, technically strong cover letters.

SILENT ANALYSIS (do this before writing):
- Review JD for: top technical requirements, team culture signals (how they describe collaboration, autonomy, impact), seniority level, and company mission language.
- Review candidate resume for: the 2-3 experiences that most directly address JD requirements, specific metrics that demonstrate impact, any unique angle that differentiates them.
- Identify: what pain is this team trying to solve? What evidence from the candidate directly addresses that pain?

WRITING RULES:
- Four focused paragraphs only: (1) hook — specific to this company/role, not generic; (2) technical fit — cite real experience with JD-matched tech and a metric; (3) culture/mission fit — show you understand what this team cares about; (4) confident close — clear ask, no grovelling.
- Banned phrases (never use): "I am writing to apply", "I am a passionate", "Please find attached", "I am excited to", "I believe I would be a great fit", "To whom it may concern", "I have always been fascinated by".
- Every sentence must add information — no filler, no repetition of what the resume already says.
- Tone: confident, direct, technically credible. Reads like an engineer wrote it, not a template.
- Strict word count: 250-320 words (not counting subject line).
- Use company/product-specific language from the JD to show genuine research.
- Plain text output only.

OUTPUT FORMAT:
Subject: [concise application email subject line]

[Four paragraphs, separated by blank lines]

---
JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{candidate_resume}

ADDITIONAL CONTEXT:
{context}

GITHUB: github.com/Geet42
"""
