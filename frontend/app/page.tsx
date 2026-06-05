"use client";

import { useState, useEffect, useCallback } from "react";

const API = "http://localhost:8000";

type Job = {
  id: string;
  title: string;
  company: string;
  location: string;
  source: string;
  url: string;
  salary?: string;
  job_type?: string;
  posted_date?: string;
  description?: string;
  ai_score: number | null;
  ai_verdict: string | null;
  ai_verdict_reason: string | null;
  ai_matches: string[];
  ai_gaps: string[];
  ai_red_flags: string[];
  ai_keywords_present: string[];
  ai_keywords_missing: string[];
  ai_apply: string | null;
  ai_breakdown: { required_skills: number; preferred_skills: number; cultural_fit: number; ats_coverage: number } | null;
  status: string;
};

/** Safely render any field that might be a raw JSON object or string from older scraper runs. */
function safeStr(val: unknown): string {
  if (!val) return "";
  if (typeof val === "string") {
    const t = val.trim();
    if (t.startsWith("{") || t.startsWith("[")) {
      try {
        const parsed = JSON.parse(t);
        if (parsed && typeof parsed === "object") {
          const o = parsed as Record<string, unknown>;
          return String(o.name || o.display_name || o.cityName || o.city || "");
        }
      } catch {}
    }
    return val;
  }
  if (typeof val === "object" && val !== null) {
    const o = val as Record<string, unknown>;
    return String(o.name || o.display_name || o.cityName || o.city || "");
  }
  return String(val);
}

/** Safely parse any field that should be a string array (JSONB can come back as string). */
function safeArr(val: unknown): string[] {
  if (!val) return [];
  if (Array.isArray(val)) return val.map(String);
  if (typeof val === "string") {
    const t = val.trim();
    if (t.startsWith("[")) {
      try { const p = JSON.parse(t); if (Array.isArray(p)) return p.map(String); } catch {}
    }
  }
  return [];
}

/** Parse a date string defensively — handles ISO (YYYY-MM-DD) and DD/MM/YYYY. */
function parseDate(raw: string): Date | null {
  if (!raw) return null;
  // Try ISO first (standard)
  let d = new Date(raw);
  if (!isNaN(d.getTime())) return d;
  // Fallback: DD/MM/YYYY (Reed legacy format before we fixed the scraper)
  const m = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (m) { d = new Date(`${m[3]}-${m[2]}-${m[1]}`); if (!isNaN(d.getTime())) return d; }
  return null;
}

/** Format a posted_date string as a short relative label like "2d ago", "Today", "Jun 3". */
function formatDate(raw: string | null | undefined): string {
  if (!raw) return "";
  try {
    const d = parseDate(raw);
    if (!d) return "";
    const diffMs = Date.now() - d.getTime();
    if (diffMs < 0) return d.toLocaleDateString("en-IE", { day: "numeric", month: "short" }); // future = show date
    const diffH = diffMs / 3_600_000;
    const diffD = Math.floor(diffMs / 86_400_000);
    if (diffH < 2) return "Just now";
    if (diffH < 24) return `${Math.floor(diffH)}h ago`;
    if (diffD === 1) return "Yesterday";
    if (diffD <= 6) return `${diffD}d ago`;
    return d.toLocaleDateString("en-IE", { day: "numeric", month: "short" });
  } catch { return ""; }
}

/** Return true if the job was posted within the last 24 hours. */
function isRecent(raw: string | null | undefined): boolean {
  if (!raw) return false;
  try {
    const d = parseDate(raw);
    if (!d) return false;
    const diff = Date.now() - d.getTime();
    return diff >= 0 && diff < 86_400_000;  // must be past, not future
  } catch { return false; }
}

const VERDICT_COLOR: Record<string, string> = {
  "Strong Apply": "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  Apply:          "bg-sky-500/15 text-sky-300 border-sky-500/30",
  Maybe:          "bg-amber-500/15 text-amber-300 border-amber-500/30",
  Skip:           "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

const SCORE_COLOR = (score: number | null) => {
  if (!score) return "text-slate-500";
  if (score >= 8) return "text-emerald-400 font-bold";
  if (score >= 6) return "text-sky-400 font-bold";
  if (score >= 4) return "text-amber-400 font-bold";
  return "text-rose-400 font-bold";
};

const GOOD_VERDICTS = new Set(["Strong Apply", "Apply", "Maybe"]);

/** Normalise source string → short display label + colour */
function sourceInfo(raw: string): { label: string; color: string } {
  const s = (raw || "").toLowerCase();
  if (s.includes("linkedin"))    return { label: "LinkedIn",    color: "bg-sky-500/15 text-sky-300 border border-sky-500/25" };
  if (s.includes("indeed"))      return { label: "Indeed",      color: "bg-indigo-500/15 text-indigo-300 border border-indigo-500/25" };
  if (s.includes("glassdoor"))   return { label: "Glassdoor",   color: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25" };
  if (s.includes("jobs.ie"))     return { label: "Jobs.ie",     color: "bg-orange-500/15 text-orange-300 border border-orange-500/25" };
  if (s.includes("irishjobs"))   return { label: "IrishJobs",   color: "bg-rose-500/15 text-rose-300 border border-rose-500/25" };
  if (s.includes("adzuna"))      return { label: "Adzuna",      color: "bg-purple-500/15 text-purple-300 border border-purple-500/25" };
  if (s.includes("reed"))        return { label: "Reed",        color: "bg-pink-500/15 text-pink-300 border border-pink-500/25" };
  if (s.includes("lever"))            return { label: "Career Site", color: "bg-slate-700/50 text-slate-300 border border-slate-600/50" };
  if (s.includes("smartrecruiters")) return { label: "Career Site", color: "bg-slate-700/50 text-slate-300 border border-slate-600/50" };
  if (s.includes("workday"))          return { label: "Career Site", color: "bg-cyan-500/15 text-cyan-300 border border-cyan-500/25" };
  if (s.includes("workable"))         return { label: "Career Site", color: "bg-teal-500/15 text-teal-300 border border-teal-500/25" };
  if (s.includes("greenhouse") || s.includes("company career")) return { label: "Career Site", color: "bg-slate-700/50 text-slate-300 border border-slate-600/50" };
  if (s.includes("totaljobs")) return { label: "TotalJobs",  color: "bg-amber-500/15 text-amber-300 border border-amber-500/25" };
  if (s.includes("monster"))   return { label: "Monster",    color: "bg-violet-500/15 text-violet-300 border border-violet-500/25" };
  if (s.includes("jooble"))    return { label: "Jooble",     color: "bg-lime-500/15 text-lime-300 border border-lime-500/25" };
  if (s.includes("google jobs") || s.includes("via google")) return { label: "Google Jobs", color: "bg-yellow-500/15 text-yellow-300 border border-yellow-500/25" };
  return { label: raw || "Job Board", color: "bg-slate-700/50 text-slate-400 border border-slate-600/50" };
}

const STATUS_OPTIONS = ["new", "saved", "applied", "interview", "rejected", "offer"];
const STATUS_LABELS: Record<string, string> = {
  new: "New", saved: "Saved", applied: "Applied",
  interview: "Interview", rejected: "Rejected", offer: "Offer",
};

export default function Home() {
  const [allJobs, setAllJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Job | null>(null);
  const [loading, setLoading] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState<{
    running: boolean; progress: string; last_run: string | null; total_found: number;
  } | null>(null);

  // Filters — default: scored matches only
  const [minScore, setMinScore] = useState(6);
  const [matchedOnly, setMatchedOnly] = useState(true);  // hide Skip verdicts
  const [filterStatus, setFilterStatus] = useState("");
  const [filterSource, setFilterSource] = useState("");

  // Right-panel tabs
  const [tab, setTab] = useState<"analysis" | "resume" | "cover">("analysis");
  const [resumeResult, setResumeResult] = useState<{
    filename: string; download_url: string;
    keyword_matches: { keyword: string; status: string; evidence: string }[];
  } | null>(null);
  const [coverLetter, setCoverLetter] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");

  // Gap analysis
  type GapSuggestion = {
    gap: string;
    impact: string;
    suggestion: string;
    new_text: string;
    section: string;
    risk: "safe" | "stretch";
    rationale: string;
    accepted: boolean;
  };
  const [gapSuggestions, setGapSuggestions] = useState<GapSuggestion[]>([]);
  const [gapLoading, setGapLoading] = useState(false);

  // Keyword search
  const [keyword, setKeyword] = useState("");

  // Custom JD scorer
  const [customJD, setCustomJD] = useState("");
  const [customScore, setCustomScore] = useState<Partial<Job> | null>(null);

  // ── Derived: apply client-side filters + sort recent first ──
  const kw = keyword.trim().toLowerCase();
  const jobs = allJobs
    .filter((j) => {
      // Live keyword filter — matches title, company, or location
      if (kw) {
        const hay = `${j.title || ""} ${safeStr(j.company)} ${safeStr(j.location)}`.toLowerCase();
        if (!hay.includes(kw)) return false;
      }
      // Always hide applied/rejected unless user explicitly filters for them
      if (!filterStatus && (j.status === "applied" || j.status === "rejected")) return false;
      if (matchedOnly && j.ai_verdict && !GOOD_VERDICTS.has(j.ai_verdict)) return false;
      if (filterStatus && j.status !== filterStatus) return false;
      if (filterSource && safeStr(j.source) !== filterSource) return false;
      return true;
    })
    .sort((a, b) => {
      // Past-24h jobs always first
      const aR = isRecent(a.posted_date) ? 1 : 0;
      const bR = isRecent(b.posted_date) ? 1 : 0;
      if (aR !== bR) return bR - aR;
      // Then newest posted_date first (jobs with no date go last)
      const aT = a.posted_date ? (parseDate(a.posted_date)?.getTime() ?? 0) : 0;
      const bT = b.posted_date ? (parseDate(b.posted_date)?.getTime() ?? 0) : 0;
      if (bT !== aT) return bT - aT;
      // Tiebreak by score
      return (b.ai_score ?? 0) - (a.ai_score ?? 0);
    });

  const sources = [...new Set(allJobs.map((j) => safeStr(j.source)).filter(Boolean))];

  // ── Data fetching ────────────────────────────────────────────
  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch scored jobs only (min_score=1 excludes nulls on the server)
      const params = new URLSearchParams({ min_score: String(minScore), limit: "200" });
      const res = await fetch(`${API}/jobs?${params}`);
      const data = await res.json();
      setAllJobs(data.jobs || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [minScore]);

  const fetchScrapeStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/search/status`);
      const data = await res.json();
      setScrapeStatus((prev) => {
        if (prev?.running && !data.running) fetchJobs();
        return data;
      });
    } catch {}
  }, [fetchJobs]);

  useEffect(() => {
    fetchJobs();
    fetchScrapeStatus();
    const iv = setInterval(fetchScrapeStatus, 3000);
    return () => clearInterval(iv);
  }, [fetchJobs, fetchScrapeStatus]);

  // ── Actions ──────────────────────────────────────────────────
  const startFullSearch = async () => {
    await fetch(`${API}/search/full`, { method: "POST" });
    setScrapeStatus({ running: true, progress: "Starting…", last_run: null, total_found: 0 });
  };

  const searchKeyword = async () => {
    if (!keyword.trim()) return;
    await fetch(`${API}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, location: "Ireland", max_per_source: 10 }),
    });
    setScrapeStatus({ running: true, progress: `Searching '${keyword}'…`, last_run: null, total_found: 0 });
  };

  const updateStatus = async (jobId: string, status: string) => {
    await fetch(`${API}/jobs/${jobId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    setAllJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status } : j)));
    if (selected?.id === jobId) setSelected((s) => s ? { ...s, status } : s);
  };

  const analyzeGaps = async () => {
    if (!selected) return;
    setGapLoading(true);
    setGapSuggestions([]);
    setGenError("");
    setTab("resume");
    setResumeResult(null);
    try {
      const res = await fetch(`${API}/tailor/gap-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: selected.id }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Server error");
      }
      const data = await res.json();
      setGapSuggestions((data.suggestions || []).map((s: Omit<GapSuggestion, "accepted">) => ({ ...s, accepted: true })));
    } catch (e: unknown) {
      setGenError(e instanceof Error ? e.message : "Gap analysis failed");
    }
    setGapLoading(false);
  };

  const toggleSuggestion = (index: number) => {
    setGapSuggestions(prev => prev.map((s, i) => i === index ? { ...s, accepted: !s.accepted } : s));
  };

  const acceptAll = () => setGapSuggestions(prev => prev.map(s => ({ ...s, accepted: true })));
  const rejectAll = () => setGapSuggestions(prev => prev.map(s => ({ ...s, accepted: false })));

  const generateResume = async () => {
    if (!selected) return;
    setGenerating(true);
    setGenError("");
    setTab("resume");
    setResumeResult(null);
    try {
      const accepted = gapSuggestions.filter(s => s.accepted);
      const res = await fetch(`${API}/tailor/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: selected.id,
          approved_suggestions: accepted.length > 0 ? accepted : null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Server error");
      }
      setResumeResult(await res.json());
    } catch (e: unknown) {
      setGenError(e instanceof Error ? e.message : "Unknown error generating resume");
    }
    setGenerating(false);
  };

  const generateCover = async () => {
    if (!selected) return;
    setGenerating(true);
    setGenError("");
    setTab("cover");
    setCoverLetter("");
    try {
      const res = await fetch(`${API}/tailor/cover-letter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: selected.id }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Server error");
      }
      const data = await res.json();
      setCoverLetter(data.cover_letter || "");
    } catch (e: unknown) {
      setGenError(e instanceof Error ? e.message : "Unknown error generating cover letter");
    }
    setGenerating(false);
  };

  const downloadResume = () => {
    if (!resumeResult) return;
    const a = document.createElement("a");
    a.href = `${API}${resumeResult.download_url}`;
    a.download = resumeResult.filename;
    a.click();
  };

  const hideJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    // Set status=rejected instead of deleting — this prevents re-surfacing on next scrape
    // because upsert_jobs preserves status. Actual DELETE from DB lets the job come back.
    await fetch(`${API}/jobs/${jobId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "rejected" }),
    });
    setAllJobs((prev) => prev.map((j) => j.id === jobId ? { ...j, status: "rejected" } : j));
    if (selected?.id === jobId) setSelected(null);
  };

  const applyJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await fetch(`${API}/jobs/${jobId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "applied" }),
    });
    setAllJobs((prev) => prev.map((j) => j.id === jobId ? { ...j, status: "applied" } : j));
    if (selected?.id === jobId) setSelected((s) => s ? { ...s, status: "applied" } : s);
  };

  const restoreJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await fetch(`${API}/jobs/${jobId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "new" }),
    });
    setAllJobs((prev) => prev.map((j) => j.id === jobId ? { ...j, status: "new" } : j));
    if (selected?.id === jobId) setSelected((s) => s ? { ...s, status: "new" } : s);
  };

  const scoreCustomJD = async () => {
    if (!customJD.trim()) return;
    setGenerating(true);
    try {
      const res = await fetch(`${API}/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_description: customJD }),
      });
      setCustomScore(await res.json());
    } catch {}
    setGenerating(false);
  };

  // ── Render ───────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 flex flex-col font-sans antialiased">
      {/* Header */}
      <header className="bg-slate-900/80 backdrop-blur border-b border-slate-800 px-6 py-3 flex items-center justify-between sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold text-lg shadow-lg shadow-indigo-500/20">
            J
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">Job Hunter <span className="text-indigo-400">·</span> Ireland</h1>
            <p className="text-xs text-slate-500">Geet Bhute · SDE / AI / Java / Full Stack</p>
          </div>
        </div>
        <div className="flex gap-3 items-center">
          {scrapeStatus?.running && (
            <span className="text-sm text-indigo-300 bg-indigo-500/10 px-3 py-1.5 rounded-full border border-indigo-500/30 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-indigo-400 animate-pulse" />
              {scrapeStatus.progress}
            </span>
          )}
          {scrapeStatus?.last_run && !scrapeStatus.running && (
            <span className="text-xs text-slate-500">
              Last run {scrapeStatus.last_run} · {scrapeStatus.total_found} found
            </span>
          )}
          <button onClick={startFullSearch} disabled={scrapeStatus?.running}
            className="bg-gradient-to-r from-indigo-500 to-violet-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:from-indigo-400 hover:to-violet-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-indigo-500/20 transition-all">
            Full Search
          </button>
          <button onClick={fetchJobs}
            className="bg-slate-800 text-slate-300 px-3 py-2 rounded-lg text-sm hover:bg-slate-700 border border-slate-700 transition-colors">
            Refresh
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Sidebar ── */}
        <div className="w-88 min-w-[22rem] bg-slate-900 border-r border-slate-800 flex flex-col overflow-hidden">
          {/* Filters */}
          <div className="p-3 border-b border-slate-800 space-y-2">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input value={keyword} onChange={(e) => setKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && searchKeyword()}
                  placeholder="Filter loaded jobs (title, company…)"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-3 pr-7 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500" />
                {keyword && (
                  <button onClick={() => setKeyword("")}
                    title="Clear filter"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-sm">✕</button>
                )}
              </div>
              <button onClick={searchKeyword} title="Scrape job boards for this keyword (slower)"
                className="bg-indigo-500 text-white px-3 py-1.5 rounded-lg text-sm hover:bg-indigo-400 transition-colors whitespace-nowrap">Scrape</button>
            </div>

            <div className="flex gap-2">
              <select value={minScore} onChange={(e) => setMinScore(Number(e.target.value))}
                className="bg-slate-800 border border-slate-700 text-slate-300 rounded-lg px-2 py-1.5 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-indigo-500/50">
                <option value={6}>Score 6+ (Good)</option>
                <option value={7}>Score 7+ (Strong)</option>
                <option value={8}>Score 8+ (Excellent)</option>
                <option value={1}>All scored</option>
              </select>
              <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
                className="bg-slate-800 border border-slate-700 text-slate-300 rounded-lg px-2 py-1.5 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-indigo-500/50">
                <option value="">All statuses</option>
                {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
              </select>
            </div>

            <div className="flex gap-2 items-center">
              {sources.length > 0 && (
                <select value={filterSource} onChange={(e) => setFilterSource(e.target.value)}
                  className="bg-slate-800 border border-slate-700 text-slate-300 rounded-lg px-2 py-1.5 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-indigo-500/50">
                  <option value="">All sources</option>
                  {sources.map((s) => <option key={s} value={s}>{sourceInfo(s).label} ({s.length > 20 ? s.slice(0,20)+"…" : s})</option>)}
                </select>
              )}
              <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer whitespace-nowrap">
                <input type="checkbox" checked={matchedOnly}
                  onChange={(e) => setMatchedOnly(e.target.checked)}
                  className="rounded bg-slate-800 border-slate-600 text-indigo-500 focus:ring-indigo-500/50" />
                Hide Skip
              </label>
            </div>

            <p className="text-xs text-slate-500">
              <span className="text-slate-300 font-semibold">{jobs.length}</span> matched job{jobs.length !== 1 ? "s" : ""}
              {allJobs.length !== jobs.length ? ` (of ${allJobs.length} scored)` : ""}
            </p>
          </div>

          {/* Job list */}
          <div className="flex-1 overflow-y-auto">
            {loading && (
              <div className="p-4 text-center text-slate-500 text-sm">Loading…</div>
            )}
            {!loading && jobs.length === 0 && (
              <div className="p-6 text-center text-slate-500 space-y-2">
                <p className="text-sm font-medium text-slate-400">No matched jobs yet</p>
                <p className="text-xs">Click &quot;Full Search&quot; to scrape and score jobs.<br />
                  Scoring takes a few minutes — jobs appear as they&apos;re scored.</p>
              </div>
            )}
            {jobs.map((job) => (
              <div key={job.id} role="button" tabIndex={0}
                onClick={() => { setSelected(job); setTab("analysis"); setResumeResult(null); setCoverLetter(""); setGenError(""); setGapSuggestions([]); }}
                className={`w-full text-left px-3 py-3 border-b border-slate-800/60 hover:bg-slate-800/50 transition-colors cursor-pointer ${
                  selected?.id === job.id ? "bg-indigo-500/10 border-l-2 border-l-indigo-400" : "border-l-2 border-l-transparent"
                }`}>
                {/* Row 1: title + date posted */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm text-slate-100 truncate">{job.title || "Untitled"}</p>
                    <p className="text-xs text-slate-400 truncate">{safeStr(job.company)}</p>
                    <p className="text-xs text-slate-500 truncate">{safeStr(job.location)}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {/* Date posted top-right */}
                    {job.posted_date && (
                      <span className={`text-[10px] font-medium ${isRecent(job.posted_date) ? "text-emerald-400" : "text-slate-500"}`}>
                        {isRecent(job.posted_date) ? "● " : ""}{formatDate(job.posted_date)}
                      </span>
                    )}
                    <span className={`text-lg leading-none ${SCORE_COLOR(job.ai_score)}`}>
                      {job.ai_score ?? "—"}<span className="text-xs font-normal text-slate-500">/10</span>
                    </span>
                    {job.ai_verdict && (
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${VERDICT_COLOR[job.ai_verdict] || "bg-slate-700/50 text-slate-300"}`}>
                        {job.ai_verdict}
                      </span>
                    )}
                  </div>
                </div>
                {/* Row 2: source badge + action buttons */}
                <div className="flex items-center justify-between mt-2">
                  <div className="flex items-center gap-1.5">
                    {(() => { const si = sourceInfo(safeStr(job.source)); return (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${si.color}`}>{si.label}</span>
                    ); })()}
                    {job.salary && <span className="text-[10px] text-emerald-400">{safeStr(job.salary)}</span>}
                  </div>
                  {/* Action buttons — Restore for applied/rejected, else Applied+Delete */}
                  <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    {(job.status === "applied" || job.status === "rejected") ? (
                      <button
                        onClick={(e) => restoreJob(job.id, e)}
                        title="Restore to New — undo applied/deleted"
                        className="text-[10px] px-2 py-0.5 rounded-md bg-sky-500/15 text-sky-300 border border-sky-500/30 hover:bg-sky-500/25 transition-colors font-medium">
                        ↺ Restore
                      </button>
                    ) : (
                      <>
                        <button
                          onClick={(e) => applyJob(job.id, e)}
                          title="Mark as Applied — hides from list, won't reappear in scrapes"
                          className="text-[10px] px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 transition-colors font-medium">
                          ✓ Applied
                        </button>
                        <button
                          onClick={(e) => hideJob(job.id, e)}
                          title="Delete — hides from list, won't reappear in scrapes"
                          className="text-[10px] px-2 py-0.5 rounded-md bg-rose-500/10 text-rose-300 border border-rose-500/25 hover:bg-rose-500/20 transition-colors font-medium">
                          ✕ Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Custom JD scorer */}
          <div className="border-t border-slate-800 p-3 bg-slate-900/50">
            <p className="text-xs font-semibold text-slate-400 mb-1 uppercase tracking-wide">Score a JD from anywhere</p>
            <p className="text-xs text-slate-500 mb-2">Copy a job description from any site and paste below for AI scoring + tailored resume.</p>
            <textarea value={customJD} onChange={(e) => setCustomJD(e.target.value)}
              placeholder="Paste job description here…" rows={3}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg text-xs p-2 resize-none text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50" />
            <button onClick={scoreCustomJD} disabled={generating}
              className="mt-1.5 w-full bg-slate-700 text-slate-100 text-sm py-1.5 rounded-lg hover:bg-slate-600 disabled:opacity-40 transition-colors">
              {generating ? "Scoring…" : "Score this JD"}
            </button>
            {customScore && (
              <div className="mt-2 p-2.5 bg-slate-800 border border-slate-700 rounded-lg text-xs space-y-1">
                <p>
                  <span className="font-semibold text-slate-300">Score:</span>{" "}
                  <span className={SCORE_COLOR(customScore.ai_score ?? null)}>{customScore.ai_score}/10</span>
                  <span className="text-slate-500">{" · "}{customScore.ai_verdict}</span>
                </p>
                <p className="text-slate-400">{customScore.ai_verdict_reason}</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Main panel ── */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-950">
          {!selected && (
            <div className="h-full flex items-center justify-center text-slate-600 flex-col gap-3">
              <div className="h-16 w-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-3xl">◎</div>
              <p className="text-lg text-slate-400">Select a job to see AI analysis</p>
              <p className="text-sm text-slate-600">Score · matches · gaps · keywords · resume tailoring</p>
            </div>
          )}

          {selected && (
            <div className="max-w-3xl mx-auto space-y-4">
              {/* Job header card */}
              <div className="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl shadow-black/20">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h2 className="text-xl font-bold text-white">{safeStr(selected.title)}</h2>
                    <p className="text-slate-400 mt-0.5">
                      {safeStr(selected.company)}
                      {selected.location ? ` · ${safeStr(selected.location)}` : ""}
                    </p>
                    <div className="flex gap-2 mt-2.5 flex-wrap items-center">
                      {selected.source && (() => { const si = sourceInfo(safeStr(selected.source)); return (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${si.color}`}>{si.label}</span>
                      ); })()}
                      {selected.job_type && (
                        <span className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded-full border border-slate-700">{safeStr(selected.job_type)}</span>
                      )}
                      {selected.salary && (
                        <span className="text-xs bg-emerald-500/15 text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-500/25">{safeStr(selected.salary)}</span>
                      )}
                      {selected.posted_date && (
                        <span className={`text-xs ${isRecent(selected.posted_date) ? "text-emerald-400" : "text-slate-500"}`}>
                          {isRecent(selected.posted_date) ? "● " : ""}{formatDate(selected.posted_date)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`text-5xl leading-none ${SCORE_COLOR(selected.ai_score)}`}>
                      {selected.ai_score ?? "—"}
                      <span className="text-base font-normal text-slate-600">/10</span>
                    </div>
                    {selected.ai_verdict && (
                      <span className={`mt-2 inline-block text-sm px-2.5 py-0.5 rounded-full border ${VERDICT_COLOR[selected.ai_verdict] || ""}`}>
                        {selected.ai_verdict}
                      </span>
                    )}
                    {selected.ai_apply && (
                      <p className="text-xs text-slate-500 mt-1.5">Rec: {selected.ai_apply}</p>
                    )}
                  </div>
                </div>

                {/* One-line AI summary */}
                {selected.ai_verdict_reason && (
                  <p className="mt-4 text-sm text-slate-400 italic border-t border-slate-800 pt-3">
                    &ldquo;{selected.ai_verdict_reason}&rdquo;
                  </p>
                )}

                {/* Actions */}
                <div className="flex gap-2 mt-4 flex-wrap items-center">
                  <select value={selected.status}
                    onChange={(e) => updateStatus(selected.id, e.target.value)}
                    className="bg-slate-800 border border-slate-700 text-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50">
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                    ))}
                  </select>
                  {selected.url && (
                    <a href={selected.url} target="_blank" rel="noopener noreferrer"
                      className="bg-gradient-to-r from-indigo-500 to-violet-600 text-white px-4 py-1.5 rounded-lg text-sm hover:from-indigo-400 hover:to-violet-500 shadow-lg shadow-indigo-500/20 transition-all">
                      Apply ↗
                    </a>
                  )}
                  <button onClick={analyzeGaps} disabled={generating || gapLoading}
                    className="bg-amber-500/90 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-amber-500 disabled:opacity-40 transition-colors">
                    {gapLoading ? "Analysing…" : "Analyse Gaps"}
                  </button>
                  <button onClick={generateResume} disabled={generating || gapLoading}
                    className="bg-emerald-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-emerald-500 disabled:opacity-40 transition-colors">
                    {generating && tab === "resume" ? "Generating…" : gapSuggestions.some(s => s.accepted) ? `Tailor Resume (${gapSuggestions.filter(s=>s.accepted).length} fixes)` : "Tailor Resume"}
                  </button>
                  <button onClick={generateCover} disabled={generating}
                    className="bg-violet-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-violet-500 disabled:opacity-40 transition-colors">
                    {generating && tab === "cover" ? "Generating…" : "Cover Letter"}
                  </button>
                </div>

                {/* Error banner */}
                {genError && (
                  <div className="mt-3 p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-sm text-rose-300">
                    ⚠ {genError}
                  </div>
                )}
              </div>

              {/* Tabs */}
              <div className="flex gap-1 border-b border-slate-800">
                {(["analysis", "resume", "cover"] as const).map((t) => (
                  <button key={t} onClick={() => setTab(t)}
                    className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors ${
                      tab === t ? "border-indigo-400 text-indigo-300" : "border-transparent text-slate-500 hover:text-slate-300"
                    }`}>
                    {t === "analysis" ? "Analysis" : t === "resume" ? "Resume" : "Cover Letter"}
                  </button>
                ))}
              </div>

              {/* ── Analysis tab ── */}
              {tab === "analysis" && (
                <div className="space-y-4">
                  {/* Score breakdown */}
                  {selected.ai_breakdown && (
                    <div className="bg-slate-900 rounded-2xl border border-slate-800 p-4 shadow-lg shadow-black/20">
                      <h3 className="font-semibold text-slate-200 mb-3 text-sm uppercase tracking-wide">Score Breakdown</h3>
                      <div className="space-y-2.5">
                        {[
                          { label: "Required Skills",  val: selected.ai_breakdown.required_skills,  max: 50 },
                          { label: "Preferred Skills", val: selected.ai_breakdown.preferred_skills, max: 25 },
                          { label: "Cultural Fit",     val: selected.ai_breakdown.cultural_fit,     max: 10 },
                          { label: "ATS Keywords",     val: selected.ai_breakdown.ats_coverage,     max: 15 },
                        ].map(({ label, val, max }) => (
                          <div key={label}>
                            <div className="flex justify-between text-xs text-slate-400 mb-1">
                              <span>{label}</span>
                              <span className="font-medium text-slate-300">{val ?? 0}/{max}</span>
                            </div>
                            <div className="bg-slate-800 rounded-full h-2">
                              <div className="bg-gradient-to-r from-indigo-500 to-violet-500 h-2 rounded-full transition-all"
                                style={{ width: `${Math.min(100, ((val ?? 0) / max) * 100)}%` }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Matches & Gaps */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-slate-900 rounded-2xl border border-slate-800 p-4 shadow-lg shadow-black/20">
                      <h3 className="font-semibold text-emerald-400 mb-2 text-sm">
                        ✓ Matches ({safeArr(selected.ai_matches).length})
                      </h3>
                      {safeArr(selected.ai_matches).length === 0
                        ? <p className="text-xs text-slate-500">None identified</p>
                        : (
                          <ul className="space-y-1.5">
                            {safeArr(selected.ai_matches).map((m, i) => (
                              <li key={i} className="text-sm text-slate-300 flex gap-1.5">
                                <span className="text-emerald-400 shrink-0">+</span>{m}
                              </li>
                            ))}
                          </ul>
                        )}
                    </div>
                    <div className="bg-slate-900 rounded-2xl border border-slate-800 p-4 shadow-lg shadow-black/20">
                      <h3 className="font-semibold text-rose-400 mb-2 text-sm">
                        ✗ Gaps ({safeArr(selected.ai_gaps).length})
                      </h3>
                      {safeArr(selected.ai_gaps).length === 0
                        ? <p className="text-xs text-slate-500">No gaps found</p>
                        : (
                          <ul className="space-y-1.5">
                            {safeArr(selected.ai_gaps).map((g, i) => (
                              <li key={i} className="text-sm text-slate-300 flex gap-1.5">
                                <span className="text-rose-400 shrink-0">–</span>{g}
                              </li>
                            ))}
                          </ul>
                        )}
                    </div>
                  </div>

                  {/* Red flags */}
                  {safeArr(selected.ai_red_flags).length > 0 && (
                    <div className="bg-rose-500/10 rounded-2xl border border-rose-500/25 p-4">
                      <h3 className="font-semibold text-rose-300 mb-2 text-sm">⚠ Red Flags</h3>
                      <ul className="space-y-1">
                        {safeArr(selected.ai_red_flags).map((f, i) => (
                          <li key={i} className="text-sm text-rose-200/90">• {f}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* ATS Keywords */}
                  <div className="bg-slate-900 rounded-2xl border border-slate-800 p-4 shadow-lg shadow-black/20">
                    <h3 className="font-semibold text-slate-200 mb-3 text-sm">ATS Keywords</h3>
                    {safeArr(selected.ai_keywords_present).length > 0 && (
                      <>
                        <p className="text-xs text-slate-500 mb-1.5">Present in your profile:</p>
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {safeArr(selected.ai_keywords_present).map((k) => (
                            <span key={k} className="text-xs bg-emerald-500/15 text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-500/25">
                              {k}
                            </span>
                          ))}
                        </div>
                      </>
                    )}
                    {safeArr(selected.ai_keywords_missing).length > 0 && (
                      <>
                        <p className="text-xs text-slate-500 mb-1.5">Missing — add to resume:</p>
                        <div className="flex flex-wrap gap-1.5">
                          {safeArr(selected.ai_keywords_missing).map((k) => (
                            <span key={k} className="text-xs bg-rose-500/10 text-rose-300 px-2 py-0.5 rounded-full border border-rose-500/25">
                              {k}
                            </span>
                          ))}
                        </div>
                      </>
                    )}
                    {!safeArr(selected.ai_keywords_present).length && !safeArr(selected.ai_keywords_missing).length && (
                      <p className="text-xs text-slate-500">No keyword data yet — re-score this job to populate.</p>
                    )}
                  </div>

                  {/* Full JD */}
                  {selected.description && (
                    <details className="bg-slate-900 rounded-2xl border border-slate-800 shadow-lg shadow-black/20">
                      <summary className="p-4 cursor-pointer font-semibold text-slate-200 text-sm select-none hover:text-white">
                        Full Job Description
                      </summary>
                      <pre className="p-4 text-xs text-slate-400 whitespace-pre-wrap border-t border-slate-800 overflow-auto max-h-80 leading-relaxed">
                        {selected.description}
                      </pre>
                    </details>
                  )}
                </div>
              )}

              {/* ── Resume tab ── */}
              {tab === "resume" && (
                <div className="space-y-4">

                  {/* Gap loading state */}
                  {gapLoading && (
                    <div className="bg-slate-900 rounded-2xl border border-slate-800 p-6 text-center shadow-lg shadow-black/20">
                      <div className="text-amber-400 animate-pulse font-medium">Analysing gaps between your resume and this JD…</div>
                      <p className="text-slate-500 text-sm mt-1">Comparing requirements, identifying missing keywords, suggesting honest fixes</p>
                    </div>
                  )}

                  {/* Gap suggestions */}
                  {!gapLoading && gapSuggestions.length > 0 && !resumeResult && (
                    <div className="bg-slate-900 rounded-2xl border border-slate-800 shadow-lg shadow-black/20 overflow-hidden">
                      <div className="p-4 border-b border-slate-800 bg-amber-500/10 flex items-center justify-between">
                        <div>
                          <h3 className="font-semibold text-amber-300">
                            {gapSuggestions.length} Gap{gapSuggestions.length !== 1 ? "s" : ""} Found
                          </h3>
                          <p className="text-xs text-amber-400/80 mt-0.5">
                            Review each suggestion. Accept the ones you want included, then click &ldquo;Tailor Resume&rdquo;.
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button onClick={acceptAll} className="text-xs bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 px-3 py-1 rounded-md hover:bg-emerald-500/25">Accept All</button>
                          <button onClick={rejectAll} className="text-xs bg-rose-500/10 text-rose-300 border border-rose-500/25 px-3 py-1 rounded-md hover:bg-rose-500/20">Reject All</button>
                        </div>
                      </div>

                      <div className="divide-y divide-slate-800">
                        {gapSuggestions.map((s, i) => (
                          <div key={i} className={`p-4 transition-colors ${s.accepted ? "bg-slate-900" : "bg-slate-950/50 opacity-50"}`}>
                            <div className="flex items-start gap-3">
                              <input type="checkbox" checked={s.accepted} onChange={() => toggleSuggestion(i)}
                                className="mt-1 h-4 w-4 rounded bg-slate-800 border-slate-600 text-indigo-500 focus:ring-indigo-500/50 cursor-pointer shrink-0" />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{s.section}</span>
                                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                                    s.risk === "safe"
                                      ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25"
                                      : "bg-orange-500/15 text-orange-300 border border-orange-500/25"
                                  }`}>
                                    {s.risk === "safe" ? "✓ Safe" : "⚠ Stretch"}
                                  </span>
                                </div>

                                <p className="text-sm font-medium text-slate-100 mt-1.5">{s.gap}</p>
                                <p className="text-xs text-rose-400 mt-0.5">{s.impact}</p>

                                <div className="mt-2 p-2.5 bg-indigo-500/10 border border-indigo-500/25 rounded-lg text-xs">
                                  <span className="font-semibold text-indigo-300">Suggested fix: </span>
                                  <span className="text-indigo-100">{s.suggestion}</span>
                                </div>

                                <div className="mt-2 p-2.5 bg-emerald-500/10 border border-emerald-500/25 rounded-lg">
                                  <p className="text-xs font-semibold text-emerald-300 mb-0.5">Exact text to use:</p>
                                  <p className="text-xs text-emerald-100 font-mono leading-relaxed">{s.new_text}</p>
                                </div>

                                <p className="text-xs text-slate-500 mt-1.5 italic">{s.rationale}</p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>

                      <div className="p-4 border-t border-slate-800 bg-slate-950/50 flex items-center justify-between">
                        <p className="text-sm text-slate-400">
                          <span className="font-semibold text-emerald-400">{gapSuggestions.filter(s => s.accepted).length}</span> accepted ·{" "}
                          <span className="font-semibold text-slate-500">{gapSuggestions.filter(s => !s.accepted).length}</span> rejected
                        </p>
                        <button onClick={generateResume} disabled={generating}
                          className="bg-emerald-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 transition-colors">
                          {generating ? "Generating…" : `Generate Resume with ${gapSuggestions.filter(s=>s.accepted).length} Fix${gapSuggestions.filter(s=>s.accepted).length !== 1 ? "es" : ""}`}
                        </button>
                      </div>
                    </div>
                  )}

                  {!gapLoading && gapSuggestions.length === 0 && !resumeResult && !generating && (
                    <div className="bg-slate-900 rounded-2xl border border-slate-800 p-8 text-center text-slate-500 shadow-lg shadow-black/20">
                      <p className="font-medium text-slate-200">Step 1 — Analyse Gaps</p>
                      <p className="text-sm mt-1.5">Click <span className="text-amber-400 font-medium">&ldquo;Analyse Gaps&rdquo;</span> to see what&apos;s missing from your resume for this role.</p>
                      <p className="text-sm mt-1 text-slate-500">Accept the suggested fixes, then click <span className="text-emerald-400 font-medium">&ldquo;Tailor Resume&rdquo;</span> to generate a DOCX with all improvements applied.</p>
                    </div>
                  )}
                  {generating && tab === "resume" && (
                    <div className="bg-slate-900 rounded-2xl border border-slate-800 p-8 text-center shadow-lg shadow-black/20">
                      <div className="text-indigo-400 animate-pulse text-base font-medium">Tailoring resume with Claude…</div>
                      <p className="text-slate-500 text-sm mt-2">Analysing JD · rewriting bullets · optimising ATS keywords</p>
                    </div>
                  )}
                  {resumeResult && (
                    <>
                      <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-5 shadow-lg shadow-black/20 flex items-center justify-between">
                        <div>
                          <p className="font-semibold text-emerald-300">Resume ready ✓</p>
                          <p className="text-sm text-emerald-400/80 mt-0.5">{resumeResult.filename}</p>
                        </div>
                        <button onClick={downloadResume}
                          className="bg-emerald-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-emerald-500 transition-colors">
                          Download DOCX
                        </button>
                      </div>
                      {resumeResult.keyword_matches?.length > 0 && (
                        <div className="bg-slate-900 rounded-2xl border border-slate-800 p-4 shadow-lg shadow-black/20">
                          <h3 className="font-semibold text-slate-200 mb-3 text-sm">ATS Keyword Match</h3>
                          <div className="overflow-auto max-h-64">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b border-slate-800 text-left text-slate-500">
                                  <th className="pb-2 pr-4">Keyword</th>
                                  <th className="pb-2 pr-4">Status</th>
                                  <th className="pb-2">Evidence</th>
                                </tr>
                              </thead>
                              <tbody>
                                {resumeResult.keyword_matches.map((km, i) => (
                                  <tr key={i} className="border-b border-slate-800/50">
                                    <td className="py-1.5 pr-4 font-medium text-slate-300">{km.keyword}</td>
                                    <td className="py-1.5 pr-4">
                                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                                        km.status === "found"   ? "bg-emerald-500/15 text-emerald-300" :
                                        km.status === "implied" ? "bg-amber-500/15 text-amber-300" :
                                                                  "bg-rose-500/15 text-rose-300"
                                      }`}>{km.status}</span>
                                    </td>
                                    <td className="py-1.5 text-slate-500">{km.evidence}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* ── Cover letter tab ── */}
              {tab === "cover" && (
                <div className="bg-slate-900 rounded-2xl border border-slate-800 shadow-lg shadow-black/20">
                  {!coverLetter && !generating && (
                    <div className="p-8 text-center text-slate-500">
                      Click &ldquo;Cover Letter&rdquo; to generate a tailored letter.
                    </div>
                  )}
                  {generating && tab === "cover" && (
                    <div className="p-8 text-center text-indigo-400 animate-pulse font-medium">
                      Writing cover letter with Claude…
                    </div>
                  )}
                  {coverLetter && (
                    <>
                      <div className="p-3 border-b border-slate-800 flex justify-between items-center">
                        <span className="text-sm font-medium text-slate-300">Cover Letter</span>
                        <button onClick={() => navigator.clipboard.writeText(coverLetter)}
                          className="text-xs bg-slate-800 text-slate-300 border border-slate-700 px-3 py-1 rounded-md hover:bg-slate-700">
                          Copy
                        </button>
                      </div>
                      <pre className="p-5 text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">{coverLetter}</pre>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
