"use client";
/**
 * AIDSE Platform — ML Lab (Phases 7-9)
 *
 * Flow: pick dataset version → choose target → task detection (with honest
 * ambiguity confirmation) → review metric advice in plain language →
 * select focused models → train (queued experiment) → leaderboard.
 *
 * Metrics are never shown as bare numbers: every column carries its
 * plain-language meaning, per the product spec.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  automl as automlApi,
  datasets as datasetsApi,
  evaluation as evaluationApi,
  projects as projectsApi,
  taskDetection,
  type DatasetResponse,
  type DatasetVersionResponse,
  type EvaluationResponse,
  type ExperimentResponse,
  type ProjectOut,
  type SuggestedTarget,
  type TaskDetectionResponse,
} from "@/lib/api";
import { urlSelection } from "@/lib/selection";

const METRIC_LABELS: Record<string, string> = {
  f1_macro: "F1 (macro)",
  accuracy: "Accuracy",
  roc_auc: "ROC-AUC",
  precision: "Precision",
  recall: "Recall",
  r2: "R²",
  rmse: "RMSE",
  mae: "MAE",
};

function Select({ value, onChange, children, disabled }: {
  value: string; onChange: (v: string) => void; children: React.ReactNode; disabled?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="rounded-lg px-3 py-2 text-sm mono"
      style={{
        background: "rgba(35,43,44,0.5)",
        border: "1px solid rgba(255,255,255,0.07)",
        color: "var(--color-on-surface)",
      }}
    >
      {children}
    </select>
  );
}

export default function MlLabPage() {
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [datasetRows, setDatasetRows] = useState<DatasetResponse[]>([]);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [versions, setVersions] = useState<DatasetVersionResponse[]>([]);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [targetColumn, setTargetColumn] = useState("");
  const [confirmedTask, setConfirmedTask] = useState<string | null>(null);

  const columns = useMemo(
    () => Object.keys(versions.find((v) => v.id === versionId)?.profile_data?.columns ?? {}),
    [versions, versionId]
  );

  useEffect(() => {
    projectsApi.list(1, 50)
      .then((d) => {
        setProjectList(d.items);
        const sel = urlSelection();
        const preferred = sel.project && d.items.some((p) => p.id === sel.project) ? sel.project : null;
        if (d.items.length > 0) setProjectId(preferred ?? d.items[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setDatasetRows([]); setDatasetId(null); setVersions([]); setVersionId(null);
    datasetsApi.list(projectId)
      .then((rows) => { setDatasetRows(rows); const dsSel = urlSelection().dataset;
        const preferredDs = dsSel && rows.some((r) => r.id === dsSel) ? dsSel : null;
        if (rows.length > 0) setDatasetId(preferredDs ?? rows[0].id); })
      .catch(() => {});
  }, [projectId]);

  useEffect(() => {
    const ds = datasetRows.find((d) => d.id === datasetId);
    const vs = ds?.versions ?? [];
    setVersions(vs);
    setVersionId(vs.length > 0 ? vs[vs.length - 1].id : null);
  }, [datasetRows, datasetId]);

  useEffect(() => {
    setTargetColumn(""); setConfirmedTask(null);
  }, [versionId]);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
          ML Lab
        </h1>
        <p className="text-sm max-w-2xl" style={{ color: "var(--color-on-surface-variant)" }}>
          Pick a target, get honest task detection, train a focused model set, and compare results — with every metric explained in plain language.
        </p>
      </div>

      {projectList.length === 0 ? (
        <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
          <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)" }}>folder_off</span>
          <Link href="/projects" className="btn-primary mt-2 text-sm">Create a project first</Link>
        </div>
      ) : (
        <>
          {/* Selectors */}
          <div className="flex flex-wrap gap-3">
            <Select value={projectId ?? ""} onChange={setProjectId}>
              {projectList.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
            </Select>
            <Select value={datasetId ?? ""} onChange={setDatasetId} disabled={datasetRows.length === 0}>
              {datasetRows.length === 0 && <option value="">No datasets</option>}
              {datasetRows.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
            </Select>
            <Select value={versionId ?? ""} onChange={setVersionId} disabled={versions.length === 0}>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.version_tag}{v.profile_status === "pending" ? " (profiling…)" : ""}
                </option>
              ))}
            </Select>
            <Select value={targetColumn} onChange={(v) => setTargetColumn(v)} disabled={!versionId || columns.length === 0}>
              <option value="">Target column…</option>
              {columns.map((c) => (<option key={c} value={c}>{c}</option>))}
            </Select>
          </div>

          {!versionId ? (
            <EmptyState icon="database" title="No dataset version selected" cta="Upload a dataset" href="/datasets" />
          ) : !targetColumn ? (
            <TargetSuggestions projectId={projectId!} datasetId={datasetId!} versionId={versionId}
              onPick={(col) => setTargetColumn(col)} />
          ) : (
            <TrainingFlow projectId={projectId!} datasetId={datasetId!} versionId={versionId}
              targetColumn={targetColumn} confirmedTask={confirmedTask} onConfirmTask={setConfirmedTask} />
          )}
        </>
      )}
    </div>
  );
}

// ── Target suggestions (user-requested feature) ────────────────────────────
const SUGGESTION_ICON: Record<string, string> = {
  high: "verified",
  medium: "thumb_up",
  low: "lightbulb",
};

function TargetSuggestions({ projectId, datasetId, versionId, onPick }: {
  projectId: string; datasetId: string; versionId: string;
  onPick: (column: string) => void;
}) {
  const [detection, setDetection] = useState<TaskDetectionResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    taskDetection.detect(projectId, datasetId, versionId)
      .then(setDetection)
      .catch(() => setDetection(null))
      .finally(() => setLoading(false));
  }, [projectId, datasetId, versionId]);

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <div className="w-7 h-7 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "var(--color-primary-container)" }} />
      </div>
    );
  }

  const suggestions = detection?.suggested_targets ?? [];

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-xl p-5">
        <h2 className="text-lg font-semibold mb-1 flex items-center gap-2" style={{ color: "var(--color-on-surface)" }}>
          <span className="material-symbols-outlined" style={{ color: "var(--color-primary)" }}>ads_click</span>
          Choose the column you want to predict
        </h2>
        {suggestions.length > 0 ? (
          <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            Based on this dataset&apos;s profile, these columns look like targets — click one to confirm:
          </p>
        ) : (
          <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            Pick any column from the dropdown above. The system will detect the task type and ask when unsure.
          </p>
        )}
      </div>

      {suggestions.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {suggestions.map((s) => (
            <button key={s.column} onClick={() => onPick(s.column)}
              className="glass-card rounded-xl p-4 text-left transition-all hover:opacity-90"
              style={{ borderColor: s.rank === 1 ? "rgba(0,242,254,0.35)" : undefined, cursor: "pointer" }}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="mono text-sm font-bold" style={{ color: "var(--color-on-surface)" }}>{s.column}</span>
                <span className="material-symbols-outlined text-lg" style={{
                  color: s.confidence === "high" ? "#50FA7B" : s.confidence === "medium" ? "#FFC24B" : "#4FC3F7",
                }}>
                  {SUGGESTION_ICON[s.confidence] ?? "lightbulb"}
                </span>
              </div>
              <span className="inline-block mono text-xs px-2 py-0.5 rounded-full mb-2 capitalize"
                style={{
                  background: s.task_type === "regression" ? "rgba(79,195,247,0.12)" : "rgba(80,250,123,0.1)",
                  color: s.task_type === "regression" ? "#4FC3F7" : "#50FA7B",
                }}>
                {s.task_type}
              </span>
              <p className="text-xs leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>{s.reason}</p>
            </button>
          ))}
        </div>
      )}

      {/* Manual pick fallback */}
      <p className="text-xs flex items-center gap-1.5" style={{ color: "var(--color-on-surface-variant)" }}>
        <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>info</span>
        Not what you need? Pick any column from the dropdown above — suggestions are advisory only.
      </p>
    </div>
  );
}

// ── Training flow ──────────────────────────────────────────────────────────
function TrainingFlow({
  projectId, datasetId, versionId, targetColumn, confirmedTask, onConfirmTask,
}: {
  projectId: string; datasetId: string; versionId: string; targetColumn: string;
  confirmedTask: string | null; onConfirmTask: (t: string | null) => void;
}) {
  const [detection, setDetection] = useState<TaskDetectionResponse | null>(null);
  const [loadingDetection, setLoadingDetection] = useState(true);
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [primaryMetric, setPrimaryMetric] = useState<string>("");
  const [experiment, setExperiment] = useState<ExperimentResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Detect on target change; reset confirmations
  useEffect(() => {
    setLoadingDetection(true); setError(null);
    taskDetection.detect(projectId, datasetId, versionId, targetColumn)
      .then((d) => {
        setDetection(d);
        onConfirmTask(d.needs_confirmation ? null : d.task_type);
        const prim = d.recommended_metrics.find((m) => m.primary);
        setPrimaryMetric(prim?.metric ?? "");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingDetection(false));
  }, [projectId, datasetId, versionId, targetColumn]);

  // Poll running experiment
  useEffect(() => {
    if (!experiment || experiment.status === "completed" || experiment.status === "failed") return;
    const t = setInterval(async () => {
      try {
        const fresh = await automlApi.getExperiment(projectId, experiment.id);
        setExperiment(fresh);
        if (fresh.status === "completed" || fresh.status === "failed") clearInterval(t);
      } catch { /* transient */ }
    }, 3000);
    return () => clearInterval(t);
  }, [experiment, projectId]);

  const toggleModel = (id: string) => {
    setSelectedModels((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const train = async () => {
    setSubmitting(true); setError(null);
    try {
      const exp = await automlApi.createExperiment(projectId, datasetId, {
        target_column: targetColumn,
        problem_type: confirmedTask ?? detection?.task_type ?? "classification",
        primary_metric: primaryMetric,
        algorithms: selectedModels.size > 0 ? [...selectedModels] : undefined,
      });
      setExperiment(exp);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingDetection) {
    return (
      <div className="flex justify-center py-16">
        <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
      </div>
    );
  }

  if (!detection) {
    return <div className="glass-panel rounded-xl p-6 text-sm" style={{ color: "var(--color-error)" }}>{error ?? "Detection failed."}</div>;
  }

  const effectiveTask = confirmedTask ?? detection.task_type;

  return (
    <div className="space-y-6">
      {/* Detection card */}
      <div className="glass-panel rounded-xl p-5">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>
            Target: <span className="mono">{targetColumn}</span>
          </h2>
          {effectiveTask && (
            <span
              className="text-xs mono px-2.5 py-1 rounded-full capitalize"
              style={{
                background: effectiveTask === "regression" ? "rgba(79,195,247,0.12)" : "rgba(80,250,123,0.1)",
                color: effectiveTask === "regression" ? "#4FC3F7" : "#50FA7B",
                border: `1px solid ${effectiveTask === "regression" ? "rgba(79,195,247,0.3)" : "rgba(80,250,123,0.3)"}`,
              }}
            >
              {effectiveTask}
            </span>
          )}
          {detection.confidence && !detection.needs_confirmation && (
            <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
              confidence: {detection.confidence}
            </span>
          )}
        </div>

        {/* Honest ambiguity question */}
        {detection.needs_confirmation && !confirmedTask && (
          <div className="rounded-lg p-4 mb-3" style={{ background: "rgba(255,194,75,0.08)", border: "1px solid rgba(255,194,75,0.3)" }}>
            <div className="flex items-start gap-2">
              <span className="material-symbols-outlined" style={{ color: "#FFC24B" }}>help</span>
              <div className="flex-1">
                <p className="text-sm mb-3" style={{ color: "var(--color-on-surface)" }}>{detection.question}</p>
                <div className="flex gap-2">
                  <button onClick={() => onConfirmTask("classification")} className="btn-primary text-xs">Classification</button>
                  {detection.alternative_task && (
                    <button onClick={() => onConfirmTask("regression")} className="btn-ghost text-xs">Regression</button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Notes */}
        {detection.notes.length > 0 && (
          <ul className="space-y-1 mb-3">
            {detection.notes.map((n, i) => (
              <li key={i} className="text-xs flex items-start gap-1.5" style={{ color: "var(--color-on-surface-variant)" }}>
                <span className="material-symbols-outlined" style={{ fontSize: "0.875rem", marginTop: "1px" }}>info</span>{n}
              </li>
            ))}
          </ul>
        )}

        {/* Metric recommendations */}
        {detection.recommended_metrics.length > 0 && (
          <div>
            <div className="mono text-xs uppercase tracking-wider mb-2" style={{ color: "var(--color-on-surface-variant)" }}>
              Recommended metrics
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {detection.recommended_metrics.map((m) => (
                <button
                  key={m.metric}
                  onClick={() => setPrimaryMetric(m.metric)}
                  className="rounded-lg p-3 text-left transition-all"
                  style={{
                    background: primaryMetric === m.metric ? "rgba(0,242,254,0.1)" : "rgba(35,43,44,0.5)",
                    border: `1px solid ${primaryMetric === m.metric ? "rgba(0,242,254,0.4)" : "rgba(255,255,255,0.07)"}`,
                    cursor: "pointer",
                  }}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-semibold mono" style={{ color: "var(--color-on-surface)" }}>
                      {METRIC_LABELS[m.metric] ?? m.metric}
                    </span>
                    {m.primary && (
                      <span className="mono text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(0,242,254,0.15)", color: "var(--color-primary)" }}>
                        suggested
                      </span>
                    )}
                  </div>
                  <p className="text-xs mt-1 leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>{m.explanation}</p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Model picker + train */}
      {(detection.recommended_models.length > 0 || confirmedTask) && (
        <div className="glass-panel rounded-xl p-5">
          <div className="mono text-xs uppercase tracking-wider mb-3" style={{ color: "var(--color-on-surface-variant)" }}>
            Focused model set — all are trained and compared
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 mb-4">
            {detection.recommended_models.map((m) => {
              const active = selectedModels.size === 0 || selectedModels.has(m.id);
              return (
                <button
                  key={m.id}
                  onClick={() => toggleModel(m.id)}
                  className="rounded-lg p-3 text-left transition-all"
                  style={{
                    background: active ? "rgba(0,242,254,0.08)" : "rgba(35,43,44,0.5)",
                    border: `1px solid ${active ? "rgba(0,242,254,0.35)" : "rgba(255,255,255,0.07)"}`,
                    opacity: active ? 1 : 0.55,
                    cursor: "pointer",
                  }}
                >
                  <div className="text-sm font-semibold mb-1" style={{ color: "var(--color-on-surface)" }}>{m.name}</div>
                  <p className="text-xs leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>{m.why}</p>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={train}
              disabled={submitting || !primaryMetric}
              className="btn-primary text-sm"
            >
              <span className="material-symbols-outlined text-base" style={{ fontVariationSettings: "'FILL' 1" }}>play_arrow</span>
              {submitting ? "Queuing…" : `Train (${selectedModels.size > 0 ? selectedModels.size : detection.recommended_models.length} models)`}
            </button>
            <span className="text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
              Primary metric: <span className="mono" style={{ color: "var(--color-on-surface)" }}>{METRIC_LABELS[primaryMetric] ?? (primaryMetric || "—")}</span>
              · 20% hold-out · best of trials wins the leaderboard
            </span>
          </div>

          {error && (
            <div className="mt-3 rounded-lg p-3 text-sm" style={{ background: "rgba(255,107,107,0.08)", border: "1px solid rgba(255,107,107,0.25)", color: "#FF6B6B" }}>
              {error}
            </div>
          )}
        </div>
      )}

      {/* Experiment status / Leaderboard */}
      {experiment && (
        <Leaderboard experiment={experiment} projectId={projectId} />
      )}

      {/* Explained evaluation (Phase 9) */}
      {experiment?.status === "completed" && (
        <EvaluationPanel projectId={projectId} experimentId={experiment.id} />
      )}
    </div>
  );
}

// ── Evaluation Panel ───────────────────────────────────────────────────────
function EvaluationPanel({ projectId, experimentId }: {
  projectId: string; experimentId: string;
}) {
  const [data, setData] = useState<EvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    evaluationApi.getExperimentEvaluation(projectId, experimentId)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [projectId, experimentId]);

  if (error) return null;
  if (!data) {
    return (
      <div className="flex justify-center py-10">
        <div className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
      </div>
    );
  }

  const primary = data.metrics.find((m) => m.is_primary);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: "var(--color-on-surface)" }}>
        <span className="material-symbols-outlined">fact_check</span>
        Evaluation explained — best model
        {primary && (
          <span className="mono text-sm font-normal" style={{ color: "var(--color-on-surface-variant)" }}>
            ({METRIC_LABELS[primary.metric] ?? primary.metric})
          </span>
        )}
      </h2>

      {/* Metric cards with interpretations */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {data.metrics.map((m) => (
          <div
            key={m.metric}
            className="glass-card rounded-xl p-4"
            style={{
              cursor: "default",
              borderColor: m.is_primary ? "rgba(0,242,254,0.35)" : undefined,
            }}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="mono text-xs uppercase tracking-wider" style={{ color: "var(--color-on-surface-variant)" }}>
                {METRIC_LABELS[m.metric] ?? m.metric}
              </span>
              <span
                className="mono text-xs px-1.5 py-0.5 rounded"
                style={{
                  background: m.higher_is_better
                    ? (m.value >= 0.7 ? "rgba(80,250,123,0.12)" : "rgba(255,194,75,0.1)")
                    : (m.value <= 0.3 ? "rgba(80,250,123,0.12)" : "rgba(255,194,75,0.1)"),
                  color: m.higher_is_better
                    ? (m.value >= 0.7 ? "#50FA7B" : "#FFC24B")
                    : (m.value <= 0.3 ? "#50FA7B" : "#FFC24B"),
                }}
              >
                {m.higher_is_better ? "higher is better" : "lower is better"}
              </span>
            </div>
            <div className="text-3xl font-bold mono mb-1.5" style={{ color: "var(--color-on-surface)" }}>
              {m.value.toFixed(4).replace(/\.?0+$/, "") || "0"}
            </div>
            <p className="text-xs leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>
              {m.explanation}
            </p>
            <p className="text-xs leading-relaxed mt-1.5 pl-2" style={{ color: "var(--color-primary)", borderLeft: "2px solid rgba(0,242,254,0.35)" }}>
              {m.interpretation}
            </p>
          </div>
        ))}
      </div>

      {/* Confusion matrix + per-class */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {data.confusion_matrix && (
          <ConfusionMatrixCard cm={data.confusion_matrix} guide={data.confusion_matrix_reading_guide} />
        )}
        {data.per_class && data.per_class.length > 0 && (
          <div className="glass-panel rounded-xl overflow-hidden">
            <div className="p-4 text-xs mono uppercase tracking-wider" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
              Per-class performance
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="mono text-xs uppercase" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
                  <th className="text-left px-4 py-2.5 font-medium">Class</th>
                  <th className="text-left px-4 py-2.5 font-medium">Precision</th>
                  <th className="text-left px-4 py-2.5 font-medium">Recall</th>
                  <th className="text-left px-4 py-2.5 font-medium">F1</th>
                  <th className="text-left px-4 py-2.5 font-medium">Cases</th>
                </tr>
              </thead>
              <tbody>
                {data.per_class.map((c) => (
                  <tr key={c.class_name} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <td className="px-4 py-2.5 mono font-medium" style={{ color: "var(--color-on-surface)" }}>{c.class_name}</td>
                    <td className="px-4 py-2.5 mono" style={{ color: c.precision < 0.5 ? "#FFC24B" : "var(--color-on-surface)" }}>{c.precision.toFixed(2)}</td>
                    <td className="px-4 py-2.5 mono" style={{ color: c.recall < 0.5 ? "#FFC24B" : "var(--color-on-surface)" }}>{c.recall.toFixed(2)}</td>
                    <td className="px-4 py-2.5 mono" style={{ color: "var(--color-on-surface)" }}>{c.f1_score.toFixed(2)}</td>
                    <td className="px-4 py-2.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>{c.support}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="p-3 text-xs" style={{ color: "var(--color-on-surface-variant)", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
              Low recall for a class means the model misses most of its cases — the yellow cells above flag values under 0.50.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function ConfusionMatrixCard({ cm, guide }: { cm: { labels: string[]; matrix: number[][] }; guide?: string | null }) {
  const total = cm.matrix.flat().reduce((a, b) => a + b, 0);
  const correct = cm.matrix.reduce((acc, row, i) => acc + row[i], 0);

  return (
    <div className="glass-panel rounded-xl overflow-hidden">
      <div className="p-4 text-xs mono uppercase tracking-wider" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
        Confusion matrix
      </div>
      <div className="p-5">
        <div className="inline-block">
          {/* Column headers = predicted */}
          <div className="flex items-end gap-1 mb-1 ml-14">
            {cm.labels.map((l) => (
              <div key={`pred-${l}`} className="w-16 text-center mono text-xs truncate" style={{ color: "var(--color-on-surface-variant)" }} title={`predicted ${l}`}>
                pred {l}
              </div>
            ))}
          </div>
          {cm.matrix.map((row, i) => (
            <div key={`row-${i}`} className="flex items-center gap-1 mb-1">
              <div className="w-13 text-right pr-1 mono text-xs whitespace-nowrap" style={{ width: "3.25rem", color: "var(--color-on-surface-variant)" }} title={`actual ${cm.labels[i]}`}>
                act {cm.labels[i]}
              </div>
              {row.map((count, j) => {
                const diagonal = i === j;
                const intensity = total > 0 ? count / Math.max(...cm.matrix.flat()) : 0;
                return (
                  <div
                    key={`${i}-${j}`}
                    className="w-16 h-16 rounded-lg flex flex-col items-center justify-center"
                    style={{
                      background: diagonal ? `rgba(80,250,123,${0.1 + intensity * 0.25})` : `rgba(255,107,107,${0.06 + intensity * 0.3})`,
                      border: `1px solid ${diagonal ? "rgba(80,250,123,0.3)" : "rgba(255,107,107,0.3)"}`,
                    }}
                    title={`Actual ${cm.labels[i]}, predicted ${cm.labels[j]}: ${count} cases`}
                  >
                    <span className="text-lg font-bold" style={{ color: "var(--color-on-surface)" }}>{count}</span>
                    <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                      {total > 0 ? `${Math.round((count / total) * 100)}%` : "0%"}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        <p className="mt-4 text-xs leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>
          <span className="mono" style={{ color: "#50FA7B" }}>Green = correct</span> ({correct.toLocaleString()} cases) ·{" "}
          <span className="mono" style={{ color: "#FF6B6B" }}>red = mistakes</span> ({(total - correct).toLocaleString()} cases)
        </p>
        {guide && <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>{guide}</p>}
      </div>
    </div>
  );
}

// ── Leaderboard ────────────────────────────────────────────────────────────
function Leaderboard({ experiment, projectId }: { experiment: ExperimentResponse; projectId: string }) {
  const trials = [...(experiment.trials ?? [])];
  const lowerBetter = ["rmse", "mae"].includes(experiment.primary_metric);
  trials.sort((a, b) =>
    lowerBetter
      ? (a.primary_metric_score ?? Infinity) - (b.primary_metric_score ?? Infinity)
      : (b.primary_metric_score ?? -Infinity) - (a.primary_metric_score ?? -Infinity)
  );

  const metricKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const t of trials) Object.keys(t.metrics ?? {}).forEach((k) => keys.add(k));
    return [...keys];
  }, [trials]);

  return (
    <div className="glass-panel rounded-xl overflow-hidden">
      <div className="p-5 flex justify-between items-center" style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
        <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>Leaderboard</h2>
        <StatusBadge status={experiment.status} error={experiment.error_message} />
      </div>

      {experiment.status === "running" || experiment.status === "pending" ? (
        <div className="p-8 flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
          <span className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            Training models — the leaderboard fills in as trials complete…
          </span>
        </div>
      ) : experiment.status === "failed" ? (
        <div className="p-6 text-sm" style={{ color: "var(--color-error)" }}>
          Training failed: {experiment.error_message}
        </div>
      ) : trials.length === 0 ? (
        <div className="p-6 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>No completed trials.</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="mono text-xs uppercase" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
                  <th className="text-left px-5 py-3 font-medium">#</th>
                  <th className="text-left px-5 py-3 font-medium">Model</th>
                  <th className="text-left px-5 py-3 font-medium">{METRIC_LABELS[experiment.primary_metric] ?? experiment.primary_metric} ★</th>
                  {metricKeys.filter((k) => k !== experiment.primary_metric).map((k) => (
                    <th key={k} className="text-left px-5 py-3 font-medium">{METRIC_LABELS[k] ?? k}</th>
                  ))}
                  <th className="text-left px-5 py-3 font-medium">Explain</th>
                </tr>
              </thead>
              <tbody>
                {trials.map((t, i) => (
                  <tr key={t.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <td className="px-5 py-3 mono" style={{ color: i === 0 ? "var(--color-primary)" : "var(--color-on-surface-variant)" }}>
                      {i === 0 ? "🏆 1" : i + 1}
                    </td>
                    <td className="px-5 py-3 font-medium" style={{ color: "var(--color-on-surface)" }}>
                      {t.algorithm_name.replace(/_/g, " ")}
                    </td>
                    <td className="px-5 py-3 mono font-bold" style={{ color: "var(--color-primary)" }}>
                      {fmt(t.primary_metric_score)}
                    </td>
                    {metricKeys.filter((k) => k !== experiment.primary_metric).map((k) => (
                      <td key={k} className="px-5 py-3 mono" style={{ color: "var(--color-on-surface)" }}>
                        {t.metrics?.[k] != null ? fmt(t.metrics[k]) : "—"}
                      </td>
                    ))}
                    <td className="px-5 py-3">
                      <Link href={`/projects/${projectId}/datasets/${experiment.dataset_id}/automl/trials/${t.id}/explain`} className="btn-ghost text-xs">
                        SHAP
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Plain-language metric glossary */}
          <div className="p-5" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
            <div className="mono text-xs uppercase tracking-wider mb-2" style={{ color: "var(--color-on-surface-variant)" }}>
              What these numbers mean
            </div>
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
              {metricKeys.map((k) => (
                <li key={k} className="text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                  <span className="mono" style={{ color: "var(--color-on-surface)" }}>{METRIC_LABELS[k] ?? k}: </span>
                  {metricGlossary(k)}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

function StatusBadge({ status, error }: { status: string; error?: string | null }) {
  const map: Record<string, { color: string }> = {
    completed: { color: "#50FA7B" },
    running: { color: "#FFC24B" },
    pending: { color: "#FFC24B" },
    failed: { color: "#FF6B6B" },
  };
  const meta = map[status] ?? { color: "var(--color-on-surface-variant)" };
  return (
    <span className="text-xs mono px-2.5 py-1 rounded-full capitalize" style={{ background: `${meta.color}14`, color: meta.color }} title={error ?? undefined}>
      {status}
    </span>
  );
}

function EmptyState({ icon, title, description, cta, href }: {
  icon: string; title: string; description?: string; cta?: string; href?: string;
}) {
  return (
    <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
      <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)", fontSize: "2.5rem" }}>{icon}</span>
      <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>{title}</div>
      {description && (
        <p className="text-sm max-w-md" style={{ color: "var(--color-on-surface-variant)" }}>{description}</p>
      )}
      {cta && href && <Link href={href} className="btn-primary mt-2 text-sm">{cta}</Link>}
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  if (v == null) return "—";
  return Math.abs(v) >= 1000 ? v.toExponential(2) : v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function metricGlossary(metric: string): string {
  const g: Record<string, string> = {
    accuracy: "share of all predictions that were correct",
    f1_macro: "balance of precision & recall averaged over classes — fair when class sizes differ",
    roc_auc: "how well the model ranks positives above negatives (0.5 = coin flip)",
    precision: "when it predicts positive, how often it is right",
    recall: "of actual positives, the % it caught",
    r2: "% of target variance explained (closer to 1 is better)",
    rmse: "typical error size in target units — big misses hurt most",
    mae: "average absolute error in target units",
  };
  return g[metric] ?? "model quality score for this trial";
}
