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

const VERDICT_COLOR: Record<string, string> = {
  "Strong Apply": "bg-green-100 text-green-800 border-green-300",
  Apply: "bg-blue-100 text-blue-800 border-blue-300",
  Maybe: "bg-yellow-100 text-yellow-800 border-yellow-300",
  Skip: "bg-red-100 text-red-700 border-red-300",
};

const SCORE_COLOR = (score: number | null) => {
  if (!score) return "text-gray-400";
  if (score >= 8) return "text-green-600 font-bold";
  if (score >= 6) return "text-blue-600 font-bold";
  if (score >= 4) return "text-yellow-600 font-bold";
  return "text-red-500 font-bold";
};

const STATUS_OPTIONS = ["new", "saved", "applied", "interview", "rejected", "offer"];
const STATUS_LABELS: Record<string, string> = {
  new: "New",
  saved: "Saved",
  applied: "Applied",
  interview: "Interview",
  rejected: "Rejected",
  offer: "Offer",
};

export default function Home() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Job | null>(null);
  const [loading, setLoading] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState<{ running: boolean; progress: string; last_run: string | null; total_found: number } | null>(null);
  const [minScore, setMinScore] = useState(0);
  const [filterStatus, setFilterStatus] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [tab, setTab] = useState<"analysis" | "resume" | "cover">("analysis");
  const [resumeResult, setResumeResult] = useState<{ filename: string; download_url: string; keyword_matches: {keyword: string; status: string; evidence: string}[] } | null>(null);
  const [coverLetter, setCoverLetter] = useState("");
  const [generating, setGenerating] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [customJD, setCustomJD] = useState("");
  const [customScore, setCustomScore] = useState<Partial<Job> | null>(null);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ min_score: String(minScore), limit: "100" });
      if (filterStatus) params.set("status", filterStatus);
      if (filterSource) params.set("source", filterSource);
      const res = await fetch(`${API}/jobs?${params}`);
      const data = await res.json();
      setJobs(data.jobs || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [minScore, filterStatus, filterSource]);

  const fetchScrapeStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/search/status`);
      const data = await res.json();
      setScrapeStatus(prev => {
        // Auto-refresh jobs when scraping just finished
        if (prev?.running && !data.running) {
          fetchJobs();
        }
        return data;
      });
    } catch {}
  }, [fetchJobs]);

  useEffect(() => {
    fetchJobs();
    fetchScrapeStatus();
    const iv = setInterval(fetchScrapeStatus, 3000); // poll every 3s
    return () => clearInterval(iv);
  }, [fetchJobs, fetchScrapeStatus]);

  const startFullSearch = async () => {
    await fetch(`${API}/search/full`, { method: "POST" });
    setScrapeStatus({ running: true, progress: "Starting...", last_run: null, total_found: 0 });
  };

  const searchKeyword = async () => {
    if (!keyword.trim()) return;
    await fetch(`${API}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, location: "Ireland", max_per_source: 10 }),
    });
    setScrapeStatus({ running: true, progress: `Searching '${keyword}'...`, last_run: null, total_found: 0 });
  };

  const updateStatus = async (jobId: string, status: string) => {
    await fetch(`${API}/jobs/${jobId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    setJobs(jobs.map((j) => (j.id === jobId ? { ...j, status } : j)));
    if (selected?.id === jobId) setSelected({ ...selected, status });
  };

  const generateResume = async () => {
    if (!selected) return;
    setGenerating(true);
    setTab("resume");
    try {
      const res = await fetch(`${API}/tailor/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: selected.id }),
      });
      const data = await res.json();
      setResumeResult(data);
    } catch {
      setResumeResult(null);
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

  const generateCover = async () => {
    if (!selected) return;
    setGenerating(true);
    setTab("cover");
    try {
      const res = await fetch(`${API}/tailor/cover-letter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: selected.id }),
      });
      const data = await res.json();
      setCoverLetter(data.cover_letter || "");
    } catch {
      setCoverLetter("Error generating cover letter.");
    }
    setGenerating(false);
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

  const sources = [...new Set(jobs.map((j) => j.source).filter(Boolean))];

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between shadow-sm">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Job Hunter — Ireland</h1>
          <p className="text-sm text-gray-500">Geet Bhute · SDE / AI / Java / Full Stack roles</p>
        </div>
        <div className="flex gap-2 items-center">
          {scrapeStatus?.running && (
            <span className="text-sm text-blue-600 animate-pulse bg-blue-50 px-3 py-1 rounded-full border border-blue-200">
              {scrapeStatus.progress}
            </span>
          )}
          {scrapeStatus?.last_run && !scrapeStatus.running && (
            <span className="text-xs text-gray-400">Last: {scrapeStatus.last_run} · {scrapeStatus.total_found} jobs</span>
          )}
          <button onClick={startFullSearch} disabled={scrapeStatus?.running}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
            Full Search (All Roles)
          </button>
          <button onClick={fetchJobs} className="bg-gray-100 text-gray-700 px-3 py-2 rounded-lg text-sm hover:bg-gray-200">
            Refresh
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-96 bg-white border-r flex flex-col overflow-hidden">
          <div className="p-3 border-b space-y-2">
            <div className="flex gap-2">
              <input value={keyword} onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && searchKeyword()}
                placeholder="Search keyword..." className="flex-1 border rounded-lg px-3 py-1.5 text-sm" />
              <button onClick={searchKeyword} className="bg-indigo-600 text-white px-3 py-1.5 rounded-lg text-sm hover:bg-indigo-700">Go</button>
            </div>
            <div className="flex gap-2">
              <select value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} className="border rounded px-2 py-1 text-sm flex-1">
                <option value={0}>All scores</option>
                <option value={6}>Score 6+</option>
                <option value={7}>Score 7+</option>
                <option value={8}>Score 8+</option>
              </select>
              <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)} className="border rounded px-2 py-1 text-sm flex-1">
                <option value="">All statuses</option>
                {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
              </select>
            </div>
            {sources.length > 0 && (
              <select value={filterSource} onChange={(e) => setFilterSource(e.target.value)} className="border rounded px-2 py-1 text-sm w-full">
                <option value="">All sources</option>
                {sources.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading && <div className="p-4 text-center text-gray-400 text-sm">Loading...</div>}
            {!loading && jobs.length === 0 && (
              <div className="p-6 text-center text-gray-400">
                <p className="text-sm">No jobs yet. Click &quot;Full Search&quot; to start.</p>
              </div>
            )}
            {jobs.map((job) => (
              <button key={job.id} onClick={() => { setSelected(job); setTab("analysis"); setResumeResult(null); setCoverLetter(""); }}
                className={`w-full text-left p-3 border-b hover:bg-gray-50 transition-colors ${selected?.id === job.id ? "bg-indigo-50 border-l-4 border-l-indigo-500" : ""}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm text-gray-900 truncate">{job.title || "Untitled"}</p>
                    <p className="text-xs text-gray-500 truncate">{job.company}</p>
                    <p className="text-xs text-gray-400">{job.source} · {job.location}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className={`text-lg ${SCORE_COLOR(job.ai_score)}`}>
                      {job.ai_score ?? "—"}<span className="text-xs font-normal text-gray-400">/10</span>
                    </span>
                    {job.ai_verdict && (
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${VERDICT_COLOR[job.ai_verdict] || "bg-gray-100 text-gray-600"}`}>
                        {job.ai_verdict}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-xs text-gray-400">{STATUS_LABELS[job.status] || job.status}</span>
                  {job.salary && <span className="text-xs text-green-600">{job.salary}</span>}
                </div>
              </button>
            ))}
          </div>

          <div className="border-t p-3">
            <p className="text-xs font-semibold text-gray-500 mb-1">PASTE ANY JD TO SCORE</p>
            <textarea value={customJD} onChange={(e) => setCustomJD(e.target.value)}
              placeholder="Paste job description here..." rows={3}
              className="w-full border rounded text-xs p-2 resize-none" />
            <button onClick={scoreCustomJD} disabled={generating}
              className="mt-1 w-full bg-gray-800 text-white text-sm py-1.5 rounded hover:bg-gray-700 disabled:opacity-50">
              {generating ? "Scoring..." : "Score this JD"}
            </button>
            {customScore && (
              <div className="mt-2 p-2 bg-gray-50 rounded text-xs space-y-1">
                <p><span className="font-semibold">Score:</span> <span className={SCORE_COLOR(customScore.ai_score ?? null)}>{customScore.ai_score}/10</span> · {customScore.ai_verdict}</p>
                <p className="text-gray-500">{customScore.ai_verdict_reason}</p>
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {!selected && (
            <div className="h-full flex items-center justify-center text-gray-300 flex-col gap-3">
              <p className="text-lg">Select a job to see full analysis</p>
            </div>
          )}

          {selected && (
            <div className="max-w-3xl mx-auto space-y-4">
              <div className="bg-white rounded-xl border p-5 shadow-sm">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">{selected.title}</h2>
                    <p className="text-gray-600">{selected.company} · {selected.location}</p>
                    <div className="flex gap-2 mt-1 flex-wrap">
                      {selected.source && <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">{selected.source}</span>}
                      {selected.job_type && <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">{selected.job_type}</span>}
                      {selected.salary && <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded">{selected.salary}</span>}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-4xl ${SCORE_COLOR(selected.ai_score)}`}>{selected.ai_score ?? "—"}<span className="text-base text-gray-400">/10</span></div>
                    {selected.ai_verdict && (
                      <span className={`text-sm px-2 py-0.5 rounded border ${VERDICT_COLOR[selected.ai_verdict] || ""}`}>{selected.ai_verdict}</span>
                    )}
                  </div>
                </div>
                <div className="flex gap-2 mt-4 flex-wrap items-center">
                  <select value={selected.status} onChange={(e) => updateStatus(selected.id, e.target.value)} className="border rounded-lg px-3 py-1.5 text-sm">
                    {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
                  </select>
                  {selected.url && (
                    <a href={selected.url} target="_blank" rel="noopener noreferrer"
                      className="bg-indigo-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-indigo-700">Apply</a>
                  )}
                  <button onClick={generateResume} disabled={generating}
                    className="bg-emerald-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-emerald-700 disabled:opacity-50">
                    {generating && tab === "resume" ? "Generating..." : "Tailor Resume"}
                  </button>
                  <button onClick={generateCover} disabled={generating}
                    className="bg-violet-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-violet-700 disabled:opacity-50">
                    {generating && tab === "cover" ? "Generating..." : "Cover Letter"}
                  </button>
                </div>
              </div>

              <div className="flex gap-1 border-b">
                {(["analysis", "resume", "cover"] as const).map((t) => (
                  <button key={t} onClick={() => setTab(t)}
                    className={`px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors ${tab === t ? "border-indigo-600 text-indigo-600" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
                    {t === "analysis" ? "Analysis" : t === "resume" ? "Resume" : "Cover Letter"}
                  </button>
                ))}
              </div>

              {tab === "analysis" && (
                <div className="space-y-4">
                  {selected.ai_verdict_reason && (
                    <div className="bg-white rounded-xl border p-4 shadow-sm">
                      <p className="text-sm text-gray-700 italic">&ldquo;{selected.ai_verdict_reason}&rdquo;</p>
                    </div>
                  )}
                  {selected.ai_breakdown && (
                    <div className="bg-white rounded-xl border p-4 shadow-sm">
                      <h3 className="font-semibold text-gray-800 mb-3">Score Breakdown</h3>
                      <div className="space-y-2">
                        {[
                          { label: "Required Skills", val: selected.ai_breakdown.required_skills, max: 50 },
                          { label: "Preferred Skills", val: selected.ai_breakdown.preferred_skills, max: 25 },
                          { label: "Cultural Fit", val: selected.ai_breakdown.cultural_fit, max: 10 },
                          { label: "ATS Keywords", val: selected.ai_breakdown.ats_coverage, max: 15 },
                        ].map(({ label, val, max }) => (
                          <div key={label}>
                            <div className="flex justify-between text-xs text-gray-600 mb-1">
                              <span>{label}</span><span>{val ?? 0}/{max}</span>
                            </div>
                            <div className="bg-gray-100 rounded-full h-2">
                              <div className="bg-indigo-500 h-2 rounded-full" style={{ width: `${((val ?? 0) / max) * 100}%` }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white rounded-xl border p-4 shadow-sm">
                      <h3 className="font-semibold text-green-700 mb-2">Matches ({selected.ai_matches?.length || 0})</h3>
                      <ul className="space-y-1">
                        {(selected.ai_matches || []).map((m, i) => (
                          <li key={i} className="text-sm text-gray-700 flex gap-1.5"><span className="text-green-500 shrink-0">+</span>{m}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="bg-white rounded-xl border p-4 shadow-sm">
                      <h3 className="font-semibold text-red-600 mb-2">Gaps ({selected.ai_gaps?.length || 0})</h3>
                      <ul className="space-y-1">
                        {(selected.ai_gaps || []).map((g, i) => (
                          <li key={i} className="text-sm text-gray-700 flex gap-1.5"><span className="text-red-400 shrink-0">-</span>{g}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  {(selected.ai_red_flags || []).length > 0 && (
                    <div className="bg-red-50 rounded-xl border border-red-200 p-4">
                      <h3 className="font-semibold text-red-700 mb-2">Red Flags</h3>
                      <ul className="space-y-1">
                        {selected.ai_red_flags.map((f, i) => <li key={i} className="text-sm text-red-700">• {f}</li>)}
                      </ul>
                    </div>
                  )}
                  <div className="bg-white rounded-xl border p-4 shadow-sm">
                    <h3 className="font-semibold text-gray-800 mb-3">ATS Keywords</h3>
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {(selected.ai_keywords_present || []).map((k) => (
                        <span key={k} className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded-full border border-green-200">{k}</span>
                      ))}
                    </div>
                    {(selected.ai_keywords_missing || []).length > 0 && (
                      <>
                        <p className="text-xs text-gray-400 mb-1">Missing:</p>
                        <div className="flex flex-wrap gap-1.5">
                          {selected.ai_keywords_missing.map((k) => (
                            <span key={k} className="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded-full border border-red-200">{k}</span>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                  {selected.description && (
                    <details className="bg-white rounded-xl border shadow-sm">
                      <summary className="p-4 cursor-pointer font-semibold text-gray-800 text-sm">Full Job Description</summary>
                      <pre className="p-4 text-xs text-gray-600 whitespace-pre-wrap border-t overflow-auto max-h-80">{selected.description}</pre>
                    </details>
                  )}
                </div>
              )}

              {tab === "resume" && (
                <div className="space-y-4">
                  {!resumeResult && !generating && (
                    <div className="bg-white rounded-xl border p-8 text-center text-gray-400 shadow-sm">
                      Click &quot;Tailor Resume&quot; above — Claude will rewrite your resume specifically for this job and generate a DOCX file ready to submit.
                    </div>
                  )}
                  {generating && tab === "resume" && (
                    <div className="bg-white rounded-xl border p-8 text-center shadow-sm">
                      <div className="text-indigo-500 animate-pulse text-base font-medium">Tailoring resume with Claude...</div>
                      <p className="text-gray-400 text-sm mt-2">Analyzing JD, rewriting bullets, optimizing ATS keywords</p>
                    </div>
                  )}
                  {resumeResult && (
                    <>
                      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 shadow-sm flex items-center justify-between">
                        <div>
                          <p className="font-semibold text-emerald-800">Resume ready</p>
                          <p className="text-sm text-emerald-600">{resumeResult.filename}</p>
                        </div>
                        <button
                          onClick={downloadResume}
                          className="bg-emerald-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-emerald-700 flex items-center gap-2"
                        >
                          Download DOCX
                        </button>
                      </div>
                      {resumeResult.keyword_matches && resumeResult.keyword_matches.length > 0 && (
                        <div className="bg-white rounded-xl border p-4 shadow-sm">
                          <h3 className="font-semibold text-gray-800 mb-3">ATS Keyword Match Table</h3>
                          <div className="overflow-auto max-h-64">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b text-left text-gray-500">
                                  <th className="pb-2 pr-4">Keyword</th>
                                  <th className="pb-2 pr-4">Status</th>
                                  <th className="pb-2">Evidence</th>
                                </tr>
                              </thead>
                              <tbody>
                                {resumeResult.keyword_matches.map((km, i) => (
                                  <tr key={i} className="border-b border-gray-50">
                                    <td className="py-1.5 pr-4 font-medium">{km.keyword}</td>
                                    <td className="py-1.5 pr-4">
                                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                                        km.status === "found" ? "bg-green-100 text-green-700" :
                                        km.status === "implied" ? "bg-yellow-100 text-yellow-700" :
                                        "bg-red-100 text-red-600"
                                      }`}>{km.status}</span>
                                    </td>
                                    <td className="py-1.5 text-gray-500">{km.evidence}</td>
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

              {tab === "cover" && (
                <div className="bg-white rounded-xl border shadow-sm">
                  {!coverLetter && !generating && (
                    <div className="p-8 text-center text-gray-400">Click &quot;Cover Letter&quot; to generate a tailored cover letter.</div>
                  )}
                  {generating && tab === "cover" && (
                    <div className="p-8 text-center text-indigo-500 animate-pulse">Writing cover letter with Claude...</div>
                  )}
                  {coverLetter && (
                    <>
                      <div className="p-3 border-b flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">Cover Letter</span>
                        <button onClick={() => navigator.clipboard.writeText(coverLetter)} className="text-xs bg-gray-100 px-3 py-1 rounded hover:bg-gray-200">Copy</button>
                      </div>
                      <pre className="p-4 text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{coverLetter}</pre>
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
