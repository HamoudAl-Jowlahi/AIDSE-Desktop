"use client";
/**
 * AIDSE Platform — Evaluations (Phases 13-14)
 *
 * Run AI evaluations against golden datasets with four scoring strategies,
 * inspect per-case results, mark baselines, and read regression verdicts
 * (PASS/WARN/FAIL) with flaky-case detection.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  datasets as datasetsApi,
  evaluations as evalApi,
  projects as projectsApi,
  type EvaluationRunFull,
  type EvaluationRunSummary,
  type GoldenDatasetResponse,
  type ProjectOut,
  type RegressionVerdict,
  type ScoringStrategy,
} from "@/lib/api";

const STRATEGIES: { id: ScoringStrategy; label: string; hint: string }[] = [
  { id: "exact", label: "Exact match", hint: "Case-insensitive string equality" },
  { id: "regex", label: "Regex rule", hint: "Expected field holds the pattern" },
  { id: "semantic", label: "Semantic (offline)", hint: "TF-IDF similarity ≥ threshold" },
  { id: "llm_judge", label: "LLM as judge", hint: "Provider-graded; offline fallback if unset" },
];

function Select({ value, onChange, children, disabled }: {
  value: string; onChange: (v: string) => void; children: React.ReactNode; disabled?: boolean;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}
      className="rounded-lg px-3 py-2 text-sm mono"
      style={{ background: "rgba(35,43,44,0.5)", border: "1px solid rgba(255,255,255,0.07)", color: "var(--color-on-surface)" }}>
      {children}
    </select>
  );
}

export default function EvaluationsPage() {
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [goldens, setGoldens] = useState<GoldenDatasetResponse[]>([]);
  const [goldenId, setGoldenId] = useState<string>("");

  // Run form
  const [strategy, setStrategy] = useState<ScoringStrategy>("exact");
  const [threshold, setThreshold] = useState("0.8");
  const [outputsText, setOutputsText] = useState("{}");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  // Data
  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<EvaluationRunFull | null>(null);
  const [verdict, setVerdict] = useState<RegressionVerdict | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    projectsApi.list(1, 50).then((d) => {
      setProjectList(d.items);
      if (d.items.length > 0) setProjectId(d.items[0].id);
    }).catch(() => {});
  }, []);

  const loadRuns = useCallback(() => {
    if (!projectId) return;
    evalApi.listRuns(projectId, goldenId || undefined)
      .then(setRuns)
      .catch(() => setRuns([]));
  }, [projectId, goldenId]);

  useEffect(() => {
    if (!projectId) return;
    datasetsApi.listGolden(projectId).then((g) => {
      setGoldens(g);
      setGoldenId(g[0]?.id ?? "");
    }).catch(() => setGoldens([]));
  }, [projectId]);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  const activeGolden = useMemo(() => goldens.find((g) => g.id === goldenId), [goldens, goldenId]);

  // Prefill outputs skeleton from cases
  useEffect(() => {
    if (!activeGolden) { setOutputsText("{}"); return; }
    const skeleton: Record<string, string> = {};
    for (const c of activeGolden.cases ?? []) skeleton[c.id] = "";
    setOutputsText(JSON.stringify(skeleton, null, 2));
  }, [activeGolden]);

  const openRun = useCallback(async (runId: string) => {
    if (!projectId) return;
    setDetailLoading(true); setVerdict(null);
    try {
      const full = await evalApi.getRun(projectId, runId);
      setSelectedRun(full);
      try {
        const v = await evalApi.getRegressionReport(projectId, runId);
        setVerdict(v);
      } catch { /* no baseline yet */ }
    } finally {
      setDetailLoading(false);
    }
  }, [projectId]);

  const markBaseline = async () => {
    if (!projectId || !selectedRun) return;
    await evalApi.setBaselineViaGolden(projectId, selectedRun.golden_dataset_id, selectedRun.id);
    await openRun(selectedRun.id);
  };

  const executeRun = async () => {
    if (!projectId || !goldenId) return;
    setRunning(true); setRunError(null);
    let outputs: Record<string, string> = {};
    try {
      outputs = JSON.parse(outputsText || "{}");
    } catch {
      setRunError("Outputs must be valid JSON mapping case_id → output.");
      setRunning(false);
      return;
    }
    const params: Record<string, any> = {};
    if (strategy === "semantic") params.threshold = parseFloat(threshold) || 0.8;

    try {
      const run = await evalApi.createRun(projectId, {
        golden_dataset_id: goldenId,
        provider: "manual",
        scoring_strategy: strategy,
        scoring_params: params,
        actual_outputs: outputs,
      });
      loadRuns();
      await openRun(run.id);
    } catch (e: any) {
      setRunError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const verdictColor = (v?: string) =>
    v === "PASS" ? "#50FA7B" : v === "WARN" ? "#FFC24B" : v === "FAIL" ? "#FF6B6B" : "var(--color-on-surface-variant)";

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
          Evaluation
        </h1>
        <p className="text-sm max-w-2xl" style={{ color: "var(--color-on-surface-variant)" }}>
          Grade real outputs against golden cases, then track regressions against your chosen baseline.
        </p>
      </div>

      {projectList.length === 0 ? (
        <div className="glass-panel rounded-xl p-10 text-center">
          <Link href="/projects" className="btn-primary text-sm">Create a project first</Link>
        </div>
      ) : (
        <>
          {/* Selectors */}
          <div className="flex flex-wrap gap-3">
            <Select value={projectId ?? ""} onChange={setProjectId}>
              {projectList.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
            </Select>
            <Select value={goldenId} onChange={setGoldenId} disabled={goldens.length === 0}>
              {goldens.length === 0 && <option value="">No golden datasets</option>}
              {goldens.map((g) => (<option key={g.id} value={g.id}>{g.name} ({g.cases?.length ?? 0} cases)</option>))}
            </Select>
          </div>

          {/* Run form */}
          {activeGolden && (
            <div className="glass-panel rounded-xl p-5 space-y-4">
              <h2 className="font-semibold" style={{ color: "var(--color-on-surface)" }}>New evaluation run</h2>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {STRATEGIES.map((s) => (
                  <button key={s.id} onClick={() => setStrategy(s.id)}
                    className="rounded-lg p-3 text-left transition-all"
                    style={{
                      background: strategy === s.id ? "rgba(0,242,254,0.1)" : "rgba(35,43,44,0.5)",
                      border: `1px solid ${strategy === s.id ? "rgba(0,242,254,0.4)" : "rgba(255,255,255,0.07)"}`,
                      cursor: "pointer",
                    }}>
                    <div className="text-sm font-semibold" style={{ color: "var(--color-on-surface)" }}>{s.label}</div>
                    <div className="text-xs mt-0.5" style={{ color: "var(--color-on-surface-variant)" }}>{s.hint}</div>
                  </button>
                ))}
              </div>

              {strategy === "semantic" && (
                <label className="flex items-center gap-2 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
                  Pass threshold
                  <input value={threshold} onChange={(e) => setThreshold(e.target.value)}
                    className="w-20 rounded-lg px-2 py-1 mono"
                    style={{ background: "rgba(35,43,44,0.6)", border: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface)" }} />
                </label>
              )}

              <div>
                <div className="mono text-xs uppercase mb-1.5" style={{ color: "var(--color-on-surface-variant)" }}>
                  Actual outputs — JSON: case_id → output
                </div>
                <textarea value={outputsText} onChange={(e) => setOutputsText(e.target.value)} rows={8}
                  className="w-full rounded-lg px-3 py-2.5 text-xs mono font-mono"
                  style={{ background: "rgba(35,43,44,0.6)", border: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface)" }} />
              </div>

              {runError && (
                <div className="rounded-lg p-3 text-xs" style={{ background: "rgba(255,107,107,0.08)", color: "#FF6B6B" }}>{runError}</div>
              )}

              <button onClick={executeRun} disabled={running} className="btn-primary text-sm">
                {running ? "Scoring…" : "Run evaluation"}
              </button>
            </div>
          )}

          {/* History */}
          <div className="glass-panel rounded-xl overflow-hidden">
            <div className="p-5 flex justify-between items-center" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
              <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>Run history</h2>
              <button onClick={loadRuns} className="btn-ghost text-xs">Refresh</button>
            </div>
            {runs.length === 0 ? (
              <p className="p-6 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>No runs yet.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="mono text-xs uppercase" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
                    <th className="text-left px-5 py-2.5">Status</th>
                    <th className="text-left px-5 py-2.5">Strategy</th>
                    <th className="text-left px-5 py-2.5">Pass rate</th>
                    <th className="text-left px-5 py-2.5">Mean score</th>
                    <th className="text-left px-5 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const agg = r.aggregate_results ?? {};
                    return (
                      <tr key={r.id} style={{
                        borderBottom: "1px solid rgba(255,255,255,0.04)",
                        background: selectedRun?.id === r.id ? "rgba(0,242,254,0.05)" : undefined,
                      }}>
                        <td className="px-5 py-2.5">
                          <span className="mono text-xs capitalize" style={{
                            color: r.status === "completed" ? "#50FA7B" : r.status === "failed" ? "#FF6B6B" : "#FFC24B",
                          }}>{r.status}</span>
                        </td>
                        <td className="px-5 py-2.5 mono text-xs" style={{ color: "var(--color-on-surface)" }}>{r.scoring_strategy ?? "—"}</td>
                        <td className="px-5 py-2.5 mono text-xs" style={{ color: "var(--color-on-surface)" }}>
                          {agg.pass_rate != null ? `${Math.round(agg.pass_rate * 100)}%` : "—"}
                        </td>
                        <td className="px-5 py-2.5 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                          {agg.mean_score != null ? agg.mean_score : "—"}
                        </td>
                        <td className="px-5 py-2.5">
                          <button onClick={() => openRun(r.id)} className="btn-ghost text-xs">
                            {selectedRun?.id === r.id ? "Hide" : "Inspect"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Detail */}
          {detailLoading && <div className="flex justify-center py-8"><div className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} /></div>}

          {selectedRun && !detailLoading && (
            <div className="space-y-4">
              {/* Verdict */}
              <div className="glass-panel rounded-xl p-5">
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>Regression status</h2>
                  <div className="flex items-center gap-2">
                    {verdict && (
                      <span className="mono text-sm px-3 py-1 rounded-full font-bold"
                        style={{ background: `${verdictColor(verdict.verdict)}18`, color: verdictColor(verdict.verdict), border: `1px solid ${verdictColor(verdict.verdict)}44` }}>
                        {verdict.verdict}
                      </span>
                    )}
                    <button onClick={markBaseline} className="btn-ghost text-xs">
                      Mark this run as baseline
                    </button>
                  </div>
                </div>
                <p className="text-sm mt-2" style={{ color: verdict ? verdictColor(verdict.verdict) : "var(--color-on-surface-variant)" }}>
                  {verdict ? verdict.verdict_reason : "No baseline designated yet — mark one to enable regression tracking."}
                </p>
                {verdict && (
                  <>
                    <div className="flex gap-4 mt-3 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                      <span>regressed: <b style={{ color: "#FF6B6B" }}>{verdict.regressed_cases}</b></span>
                      <span>newly passing: <b style={{ color: "#50FA7B" }}>{verdict.newly_passing_cases}</b></span>
                      <span>stable: <b>{verdict.stable_cases}</b></span>
                      {verdict.score_changed_cases > 0 && <span>score changed: <b>{verdict.score_changed_cases}</b></span>}
                    </div>
                    {verdict.flaky_cases.length > 0 && (
                      <div className="mt-3 rounded-lg p-3 text-xs" style={{ background: "rgba(255,194,75,0.07)", color: "#FFC24B" }}>
                        ⚡ {verdict.flaky_cases.length} flaky case(s): inconsistent results across runs — {verdict.flaky_cases[0].note}
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Per-case results */}
              <div className="glass-panel rounded-xl overflow-hidden">
                <div className="p-4 text-xs mono uppercase tracking-wider" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
                  Per-case results ({selectedRun.results.length})
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="mono text-xs uppercase" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", color: "var(--color-on-surface-variant)" }}>
                      <th className="text-left px-5 py-2">Result</th>
                      <th className="text-left px-5 py-2">Score</th>
                      <th className="text-left px-5 py-2">Actual output</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedRun.results.map((r) => (
                      <tr key={r.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                        <td className="px-5 py-2">
                          <span className="material-symbols-outlined text-lg align-middle" style={{ color: r.status === "pass" ? "#50FA7B" : "#FF6B6B" }}>
                            {r.status === "pass" ? "check_circle" : "cancel"}
                          </span>
                        </td>
                        <td className="px-5 py-2 mono text-xs">{r.score.toFixed(2)}</td>
                        <td className="px-5 py-2 mono text-xs truncate max-w-md" style={{ color: "var(--color-on-surface-variant)" }} title={r.actual_output}>
                          {r.actual_output.slice(0, 120)}
                        </td>
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
  );
}
