"use client";
/**
 * AIDSE Platform — Data Preparation Workbench (Phases 4-5)
 *
 * Tabs:
 *  - Transform : build a step queue, preview before/after, apply → new version
 *  - Outliers  : multi-method outlier intelligence with recommendations
 *  - History   : step lineage, undo via revert, before/after compare
 *
 * Original uploads are never mutated; every apply creates a new version.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  datasets as datasetsApi,
  outliers as outliersApi,
  preparation as prepApi,
  projects as projectsApi,
  recommendations as recsApi,
  type DatasetResponse,
  type DatasetVersionResponse,
  type OutlierScanResponse,
  type PlanStep,
  type PreviewResponse,
  type ProjectOut,
  type QualityRecommendation,
  type RecommendationResponse,
  type TransformStepInput,
  type VersionHistoryEntry,
} from "@/lib/api";
import { urlSelection } from "@/lib/selection";

// ── Transformation catalog ─────────────────────────────────────────────────
interface CatalogAction {
  action: string;
  label: string;
  category: string;
  needsColumn: boolean;
  columnTypes?: ("numeric" | "categorical" | "any")[];
  params?: { key: string; label: string; kind: "number" | "text" | "select"; options?: string[]; default?: any }[];
}

const CATALOG: CatalogAction[] = [
  // Missing values
  { action: "fillna_mean", label: "Mean imputation", category: "Missing Values", needsColumn: true, columnTypes: ["numeric"] },
  { action: "fillna_median", label: "Median imputation", category: "Missing Values", needsColumn: true, columnTypes: ["numeric"] },
  { action: "fillna_mode", label: "Mode imputation", category: "Missing Values", needsColumn: true, columnTypes: ["categorical", "any"] },
  {
    action: "fillna_constant", label: "Fill constant…", category: "Missing Values", needsColumn: true,
    params: [{ key: "value", label: "Value", kind: "text" }],
  },
  // Duplicates
  { action: "drop_duplicates", label: "Remove duplicate rows", category: "Duplicates", needsColumn: false },
  { action: "drop_na", label: "Drop rows with NaN", category: "Missing Values", needsColumn: true },
  // Encoding
  { action: "one_hot_encode", label: "One-hot encode", category: "Encoding", needsColumn: true, columnTypes: ["categorical"] },
  { action: "label_encode", label: "Label encode", category: "Encoding", needsColumn: true, columnTypes: ["categorical", "any"] },
  { action: "frequency_encode", label: "Frequency encode", category: "Encoding", needsColumn: true, columnTypes: ["categorical"] },
  // Scaling
  { action: "standard_scale", label: "StandardScaler", category: "Scaling", needsColumn: true, columnTypes: ["numeric"] },
  { action: "minmax_scale", label: "MinMaxScaler", category: "Scaling", needsColumn: true, columnTypes: ["numeric"] },
  { action: "robust_scale", label: "RobustScaler", category: "Scaling", needsColumn: true, columnTypes: ["numeric"] },
  // Outliers
  { action: "cap_outliers", label: "Cap outliers (IQR)", category: "Outliers", needsColumn: true, columnTypes: ["numeric"] },
  {
    action: "winsorize", label: "Winsorize…", category: "Outliers", needsColumn: true, columnTypes: ["numeric"],
    params: [
      { key: "lower_pct", label: "Lower pct", kind: "number", default: 0.01 },
      { key: "upper_pct", label: "Upper pct", kind: "number", default: 0.99 },
    ],
  },
  { action: "drop_outliers", label: "Drop outlier rows (IQR)", category: "Outliers", needsColumn: true, columnTypes: ["numeric"] },
  { action: "log_transform", label: "Log transform", category: "Outliers", needsColumn: true, columnTypes: ["numeric"] },
  // Structure
  { action: "drop_column", label: "Drop column", category: "Structure", needsColumn: true },
  {
    action: "convert_type", label: "Convert type…", category: "Structure", needsColumn: true,
    params: [{ key: "to", label: "To", kind: "select", options: ["numeric", "string", "boolean", "datetime"], default: "numeric" }],
  },
];

const CATEGORY_ORDER = ["Missing Values", "Duplicates", "Encoding", "Scaling", "Outliers", "Structure"];

// ── Small building blocks ──────────────────────────────────────────────────
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

function RecommendationBox({ rec }: { rec: QualityRecommendation }) {
  return (
    <div className="rounded-lg p-3" style={{ background: "rgba(0,242,254,0.05)", border: "1px solid rgba(0,242,254,0.12)" }}>
      <div className="text-xs mono uppercase tracking-wider mb-1" style={{ color: "var(--color-primary)" }}>
        Recommended
      </div>
      <div className="text-sm font-semibold mb-1" style={{ color: "var(--color-on-surface)" }}>{rec.technique}</div>
      <p className="text-xs leading-relaxed mb-1" style={{ color: "var(--color-on-surface-variant)" }}>{rec.reason}</p>
      <p className="text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
        <span style={{ color: "var(--color-on-surface)" }}>Trade-off: </span>{rec.risk}
      </p>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function PreparePage() {
  const [tab, setTab] = useState<"transform" | "outliers" | "history">("transform");

  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [datasetRows, setDatasetRows] = useState<DatasetResponse[]>([]);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [versions, setVersions] = useState<DatasetVersionResponse[]>([]);
  const [versionId, setVersionId] = useState<string | null>(null);

  const activeDataset = datasetRows.find((d) => d.id === datasetId) ?? null;
  const activeVersion = versions.find((v) => v.id === versionId) ?? null;
  const profileColumns = useMemo(
    () => Object.keys(activeVersion?.profile_data?.columns ?? {}),
    [activeVersion]
  );

  // Load projects
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
      .then((rows) => {
        setDatasetRows(rows);
        const dsSel = urlSelection().dataset;
        const preferredDs = dsSel && rows.some((r) => r.id === dsSel) ? dsSel : null;
        if (rows.length > 0) setDatasetId(preferredDs ?? rows[0].id);
      })
      .catch(() => {});
  }, [projectId]);

  useEffect(() => {
    const ds = datasetRows.find((d) => d.id === datasetId);
    const vs = ds?.versions ?? [];
    setVersions(vs);
    setVersionId(vs.length > 0 ? vs[vs.length - 1].id : null);
  }, [datasetRows, datasetId]);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-end flex-wrap gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
            Data Preparation
          </h1>
          <p className="text-sm max-w-2xl" style={{ color: "var(--color-on-surface-variant)" }}>
            Apply transformations safely: preview first, apply to a new version, undo anytime.
            Original uploads are never modified.
          </p>
        </div>
      </div>

      {projectList.length === 0 ? (
        <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
          <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)" }}>folder_off</span>
          <Link href="/projects" className="btn-primary mt-2 text-sm">Create a project first</Link>
        </div>
      ) : (
        <>
          {/* Selectors + tabs */}
          <div className="flex flex-wrap gap-3 items-center">
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

            <div className="ml-auto flex gap-1 glass-card rounded-lg p-1">
              {(["transform", "outliers", "history"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className="px-4 py-1.5 rounded-md text-sm capitalize transition-all"
                  style={
                    tab === t
                      ? { background: "rgba(0,242,254,0.12)", color: "var(--color-primary)", fontWeight: 600 }
                      : { color: "var(--color-on-surface-variant)" }
                  }
                >
                  {t === "transform" ? "Transform" : t === "outliers" ? "Outlier Intelligence" : "History & Compare"}
                </button>
              ))}
            </div>
          </div>

          {!versionId ? (
            <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
              <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)" }}>database</span>
              <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>No dataset version selected</div>
              <Link href="/datasets" className="btn-primary mt-2 text-sm">Upload a dataset</Link>
            </div>
          ) : tab === "transform" ? (
            <TransformTab
              projectId={projectId!} datasetId={datasetId!} versionId={versionId}
              profileColumns={profileColumns}
              onApplied={(newTag, newId) => {
                setVersions((vs) => {
                  const ds = [...vs];
                  const src = ds.find((v) => v.id === versionId);
                  if (src) {
                    ds.push({
                      ...src, id: newId, version_tag: newTag,
                      parent_version_id: src.id,
                    });
                  }
                  return ds;
                });
                setVersionId(newId);
              }}
            />
          ) : tab === "outliers" ? (
            <OutliersTab projectId={projectId!} datasetId={datasetId!} versionId={versionId} />
          ) : (
            <HistoryTab projectId={projectId!} datasetId={datasetId!} versionId={versionId} versions={versions} onReverted={(newId, newTag) => {
              setVersions((vs) => {
                const src = vs.find((v) => v.id === versionId);
                const parent = src?.parent_version_id ? vs.find((v) => v.id === src.parent_version_id) : null;
                const base = parent ?? src;
                if (base && !vs.some((v) => v.id === newId)) {
                  return [...vs, { ...base, id: newId, version_tag: newTag, parent_version_id: base.id }];
                }
                return vs;
              });
              setVersionId(newId);
            }} />
          )}
        </>
      )}
    </div>
  );
}

// ── Transform Tab ──────────────────────────────────────────────────────────
function TransformTab({
  projectId, datasetId, versionId, profileColumns, onApplied,
}: {
  projectId: string; datasetId: string; versionId: string; profileColumns: string[];
  onApplied: (tag: string, id: string) => void;
}) {
  const [steps, setSteps] = useState<(TransformStepInput & { _id: number })[]>([]);
  const [openAction, setOpenAction] = useState<CatalogAction | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [busy, setBusy] = useState<"preview" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [appliedMsg, setAppliedMsg] = useState<string | null>(null);

  const addStep = (actionDef: CatalogAction, column: string, params: Record<string, any>) => {
    setSteps((s) => [...s, { _id: Date.now() + Math.random(), action: actionDef.action, column, params }]);
    setOpenAction(null);
    setPreview(null);
    setAppliedMsg(null);
  };

  const runPreview = async () => {
    if (steps.length === 0) return;
    setBusy("preview"); setError(null); setPreview(null);
    try {
      const result = await prepApi.preview(
        projectId, datasetId, versionId,
        steps.map(({ action, column, params }) => ({ action, column, params }))
      );
      setPreview(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    if (steps.length === 0) return;
    setBusy("apply"); setError(null);
    try {
      const newVersion = await datasetsApi.transform(
        projectId, datasetId, versionId,
        { steps: steps.map(({ action, column, params }) => ({ action, column, params })) }
      );
      setSteps([]);
      setPreview(null);
      setAppliedMsg(`Applied successfully → new version ${newVersion.version_tag}`);
      onApplied(newVersion.version_tag, newVersion.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      {/* Catalog + AI plan */}
      <div className="lg:col-span-2 space-y-4">
        <AISuggestionsPanel
          projectId={projectId} datasetId={datasetId} versionId={versionId}
          onAddSteps={(planSteps) => {
            setSteps((existing) => {
              const next = [...existing];
              for (const ps of planSteps) {
                const dup = existing.some(
                  (e) => e.action === ps.action && e.column === (ps.column ?? "") &&
                         JSON.stringify(e.params ?? {}) === JSON.stringify(ps.params ?? {})
                );
                if (!dup) {
                  next.push({ _id: Date.now() + Math.random(), action: ps.action, column: ps.column ?? "", params: ps.params });
                }
              }
              return next;
            });
            setPreview(null);
            setAppliedMsg(null);
          }}
        />

        <div className="glass-panel rounded-xl overflow-hidden">
          <div className="p-4 text-xs mono uppercase tracking-wider" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
            Transformations — click to queue
          </div>
          <div className="max-h-[480px] overflow-y-auto p-3 space-y-3">
            {CATEGORY_ORDER.map((cat) => (
              <div key={cat}>
                <div className="mono text-xs mb-1.5" style={{ color: "var(--color-on-surface-variant)" }}>{cat}</div>
                <div className="flex flex-wrap gap-1.5">
                  {CATALOG.filter((a) => a.category === cat).map((a) => (
                    <button
                      key={a.action}
                      onClick={() => setOpenAction(a)}
                      className="text-xs px-2.5 py-1.5 rounded-md transition-all"
                      style={{
                        background: "rgba(35,43,44,0.6)",
                        border: "1px solid rgba(255,255,255,0.07)",
                        color: openAction?.action === a.action ? "var(--color-primary)" : "var(--color-on-surface)",
                      }}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Step configurator */}
        {openAction && (
          <StepConfigurator
            actionDef={openAction}
            columns={profileColumns}
            onCancel={() => setOpenAction(null)}
            onAdd={addStep}
          />
        )}
      </div>

      {/* Queue + preview */}
      <div className="lg:col-span-3 space-y-4">
        <div className="glass-panel rounded-xl overflow-hidden">
          <div className="p-4 flex justify-between items-center" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
            <h2 className="font-semibold" style={{ color: "var(--color-on-surface)" }}>
              Pending steps {steps.length > 0 && `(${steps.length})`}
            </h2>
            <div className="flex gap-2">
              {steps.length > 0 && (
                <>
                  <button onClick={() => { setSteps([]); setPreview(null); }} className="btn-ghost text-xs">Clear</button>
                  <button onClick={runPreview} disabled={busy !== null} className="btn-ghost text-xs">
                    {busy === "preview" ? "Previewing…" : "Preview"}
                  </button>
                  <button onClick={apply} disabled={busy !== null || preview === null || !preview.ok} className="btn-primary text-xs">
                    {busy === "apply" ? "Applying…" : "Apply → New Version"}
                  </button>
                </>
              )}
            </div>
          </div>

          {steps.length === 0 ? (
            <div className="p-8 text-center text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
              Queue is empty. Pick transformations from the left, preview the result, then apply.
            </div>
          ) : (
            <ol className="p-3 space-y-2">
              {steps.map((s, i) => {
                const def = CATALOG.find((a) => a.action === s.action)!;
                return (
                  <li key={s._id} className="flex items-center justify-between px-3 py-2.5 rounded-lg" style={{ background: "rgba(35,43,44,0.4)", border: "1px solid rgba(255,255,255,0.06)" }}>
                    <div className="flex items-center gap-3">
                      <span className="mono text-xs w-6 h-6 rounded-full flex items-center justify-center" style={{ background: "rgba(0,242,254,0.1)", color: "var(--color-primary)" }}>
                        {i + 1}
                      </span>
                      <span className="text-sm" style={{ color: "var(--color-on-surface)" }}>
                        {def.label}{s.column ? <span className="mono" style={{ color: "var(--color-on-surface-variant)" }}> · {s.column}</span> : null}
                        {s.params && Object.keys(s.params).length > 0 && (
                          <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                            {" "}({Object.entries(s.params).map(([k, v]) => `${k}=${v}`).join(", ")})
                          </span>
                        )}
                      </span>
                    </div>
                    <button
                      onClick={() => { setSteps(steps.filter((x) => x._id !== s._id)); setPreview(null); }}
                      className="material-symbols-outlined text-lg"
                      style={{ color: "var(--color-error)" }}
                      title="Remove step"
                    >
                      close
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </div>

        {error && (
          <div className="rounded-xl p-4 text-sm" style={{ background: "rgba(255,107,107,0.08)", border: "1px solid rgba(255,107,107,0.25)", color: "#FF6B6B" }}>
            <span className="material-symbols-outlined text-base align-middle mr-1">error</span>{error}
          </div>
        )}
        {appliedMsg && (
          <div className="rounded-xl p-4 text-sm" style={{ background: "rgba(80,250,123,0.07)", border: "1px solid rgba(80,250,123,0.25)", color: "#50FA7B" }}>
            <span className="material-symbols-outlined text-base align-middle mr-1">check_circle</span>{appliedMsg}
          </div>
        )}

        {/* Preview result */}
        {preview && (
          <div className="glass-panel rounded-xl overflow-hidden">
            <div className="p-4 text-xs mono uppercase tracking-wider" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
              Dry-run result — rows {preview.rows_before} → {preview.rows_after} · columns {preview.columns_before} → {preview.columns_after}
              {preview.truncated_for_preview && " · truncated sample"}
            </div>
            {preview.changed_columns.length > 0 && (
              <div className="p-3 flex flex-wrap gap-2" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                {preview.changed_columns.map((c, i) => (
                  <span key={i} className="mono text-xs px-2 py-1 rounded-md" style={{ background: "rgba(35,43,44,0.6)", color: "var(--color-on-surface)" }}>
                    {c.column}: <span style={{ color: "var(--color-primary)" }}>{c.change}</span>
                    {c.before !== undefined && c.after !== undefined && ` (${String(c.before)} → ${String(c.after)})`}
                  </span>
                ))}
              </div>
            )}
            <SampleTable title="Before" rows={preview.sample_before} />
            <SampleTable title="After" rows={preview.sample_after} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── AI Suggestions Panel (Phase 6) ─────────────────────────────────────────
const CONFIDENCE_META: Record<string, { color: string; label: string }> = {
  high: { color: "#50FA7B", label: "High confidence" },
  medium: { color: "#FFC24B", label: "Medium" },
  low: { color: "#4FC3F7", label: "Low — review" },
};

function AISuggestionsPanel({
  projectId, datasetId, versionId, onAddSteps,
}: {
  projectId: string; datasetId: string; versionId: string;
  onAddSteps: (steps: PlanStep[]) => void;
}) {
  const [plan, setPlan] = useState<RecommendationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [expandedStep, setExpandedStep] = useState<number | null>(null);

  const generate = useCallback(() => {
    setLoading(true);
    setPlan(null);
    setAdded(new Set());
    recsApi.getPlan(projectId, datasetId, versionId)
      .then(setPlan)
      .catch(() => setPlan(null))
      .finally(() => setLoading(false));
  }, [projectId, datasetId, versionId]);

  useEffect(() => {
    setPlan(null); setAdded(new Set()); setLoading(false);
  }, [versionId]);

  const addAll = () => {
    if (!plan) return;
    onAddSteps(plan.steps.filter((s) => !added.has(`${s.order}`)));
    setAdded(new Set(plan.steps.map((s) => `${s.order}`)));
  };

  return (
    <div
      className="glass-panel rounded-xl overflow-hidden"
      style={{ border: "1px solid rgba(0,242,254,0.18)" }}
    >
      <div className="p-4 flex justify-between items-center gap-2" style={{ borderBottom: plan ? "1px solid rgba(255,255,255,0.08)" : "none" }}>
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-lg" style={{ color: "var(--color-primary)" }}>auto_awesome</span>
          <h2 className="font-semibold text-sm" style={{ color: "var(--color-on-surface)" }}>AI Preprocessing Plan</h2>
        </div>
        {plan ? (
          <div className="flex gap-2">
            <button onClick={generate} className="btn-ghost text-xs">Regenerate</button>
            <button onClick={addAll} className="btn-primary text-xs">Approve all → Queue</button>
          </div>
        ) : (
          <button onClick={generate} disabled={loading} className="btn-primary text-xs">
            {loading ? "Analyzing…" : "Generate"}
          </button>
        )}
      </div>

      {!plan && !loading && (
        <p className="p-4 text-xs leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>
          The rule engine inspects the profile and proposes an ordered cleaning plan.
          An LLM only narrates the reasoning — it never computes statistics. You approve every step.
        </p>
      )}

      {loading && (
        <div className="flex justify-center items-center gap-3 p-6">
          <div className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
          <span className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>Inspecting dataset profile…</span>
        </div>
      )}

      {plan && (
        <div className="p-4 space-y-3">
          {/* Narrative */}
          <div className="rounded-lg p-3" style={{ background: "rgba(0,242,254,0.05)", border: "1px solid rgba(0,242,254,0.12)" }}>
            <div className="flex items-center justify-between mb-1">
              <span className="mono text-xs uppercase tracking-wider" style={{ color: "var(--color-primary)" }}>
                Why this plan
              </span>
              <span
                className="text-xs mono px-2 py-0.5 rounded-full"
                style={{
                  background: plan.generated_by === "rules+llm" ? "rgba(80,250,123,0.1)" : "rgba(35,43,44,0.6)",
                  color: plan.generated_by === "rules+llm" ? "#50FA7B" : "var(--color-on-surface-variant)",
                }}
              >
                {plan.generated_by === "rules+llm" ? "rules + LLM narration" : "rule engine"}
              </span>
            </div>
            <p className="text-xs leading-relaxed" style={{ color: "var(--color-on-surface)" }}>{plan.narrative}</p>
          </div>

          {/* Steps */}
          {plan.steps.length === 0 ? (
            <div className="flex items-center gap-2 p-3 rounded-lg" style={{ background: "rgba(80,250,123,0.07)" }}>
              <span className="material-symbols-outlined text-lg" style={{ color: "#50FA7B" }}>verified</span>
              <span className="text-sm" style={{ color: "var(--color-on-surface)" }}>No preprocessing needed.</span>
            </div>
          ) : (
            <ol className="space-y-2">
              {plan.steps.map((s) => {
                const meta = CONFIDENCE_META[s.confidence] ?? CONFIDENCE_META.medium;
                const isAdded = added.has(`${s.order}`);
                const isOpen = expandedStep === s.order;
                return (
                  <li
                    key={s.order}
                    className="rounded-lg p-3"
                    style={{ background: "rgba(35,43,44,0.45)", border: "1px solid rgba(255,255,255,0.06)" }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <button onClick={() => setExpandedStep(isOpen ? null : s.order)} className="text-left flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="mono text-xs w-5 h-5 rounded-full inline-flex items-center justify-center" style={{ background: "rgba(0,242,254,0.12)", color: "var(--color-primary)" }}>
                            {s.order}
                          </span>
                          <span className="text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>
                            {ACTION_LABELS[s.action] ?? s.action}
                          </span>
                          {s.column && (
                            <span className="mono text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(35,43,44,0.7)", color: "var(--color-on-surface-variant)" }}>
                              {s.column}
                            </span>
                          )}
                          <span className="mono text-xs" style={{ color: meta.color }}>{meta.label}</span>
                        </div>
                        <div className="text-xs mt-1" style={{ color: "var(--color-on-surface-variant)" }}>{s.problem}</div>
                      </button>
                      <button
                        onClick={() => { onAddSteps([s]); setAdded((a) => new Set(a).add(`${s.order}`)); }}
                        disabled={isAdded}
                        className="btn-ghost text-xs whitespace-nowrap"
                        style={isAdded ? { opacity: 0.45 } : undefined}
                        title="Queue this step"
                      >
                        {isAdded ? "✓ Queued" : "+ Queue"}
                      </button>
                    </div>

                    {isOpen && (
                      <div className="mt-2 pl-7 space-y-1.5 text-xs leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>
                        <p><span style={{ color: "var(--color-on-surface)" }}>Why: </span>{s.rationale}</p>
                        <p><span style={{ color: "var(--color-on-surface)" }}>Effect: </span>{s.expected_effect}</p>
                        {s.alternatives.length > 0 && (
                          <p><span style={{ color: "var(--color-on-surface)" }}>Alternatives: </span>{s.alternatives.join(" · ")}</p>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          )}

          {/* Notes */}
          {plan.notes.length > 0 && (
            <ul className="space-y-1">
              {plan.notes.map((n, i) => (
                <li key={i} className="text-xs flex items-start gap-1" style={{ color: "var(--color-on-surface-variant)" }}>
                  <span className="material-symbols-outlined" style={{ fontSize: "0.875rem", marginTop: "1px" }}>info</span>
                  {n}
                </li>
              ))}
            </ul>
          )}

          <p className="text-xs flex items-center gap-1" style={{ color: "var(--color-on-surface-variant)" }}>
            <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>lock</span>
            Nothing runs without your approval — queued steps appear in the list to the right for preview and apply.
          </p>
        </div>
      )}
    </div>
  );
}

const ACTION_LABELS: Record<string, string> = {
  convert_type: "Convert type",
  fillna_mean: "Mean imputation",
  fillna_median: "Median imputation",
  fillna_mode: "Mode imputation",
  drop_column: "Drop column",
  log_transform: "Log transform",
  winsorize: "Winsorize (p1/p99)",
  one_hot_encode: "One-hot encode",
  frequency_encode: "Frequency encode",
  robust_scale: "Robust scaling",
};

function StepConfigurator({
  actionDef, columns, onCancel, onAdd,
}: {
  actionDef: CatalogAction; columns: string[];
  onCancel: () => void;
  onAdd: (def: CatalogAction, col: string, params: Record<string, any>) => void;
}) {
  const usableColumns = useMemo(() => {
    if (!actionDef.columnTypes || actionDef.columnTypes.includes("any")) return columns;
    return columns.filter((c) => {
      // Column semantic type lives in profile; here we only have names, so allow all
      // but sort numeric-looking hints first when requested.
      return true;
    });
  }, [actionDef, columns]);

  const [column, setColumn] = useState(usableColumns[0] ?? "");
  const [params, setParams] = useState<Record<string, any>>(
    Object.fromEntries((actionDef.params ?? []).map((p) => [p.key, p.default ?? ""]))
  );

  return (
    <div className="glass-panel rounded-xl p-4 space-y-3" style={{ borderColor: "rgba(0,242,254,0.2)" }}>
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-semibold" style={{ color: "var(--color-primary)" }}>Configure: {actionDef.label}</h3>
        <button onClick={onCancel} className="material-symbols-outlined text-lg" style={{ color: "var(--color-on-surface-variant)" }}>close</button>
      </div>

      {actionDef.needsColumn && (
        <label className="block">
          <span className="mono text-xs uppercase" style={{ color: "var(--color-on-surface-variant)" }}>Column</span>
          <select
            value={column}
            onChange={(e) => setColumn(e.target.value)}
            className="w-full mt-1 rounded-lg px-3 py-2 text-sm mono"
            style={{ background: "rgba(35,43,44,0.6)", border: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface)" }}
          >
            {usableColumns.map((c) => (<option key={c} value={c}>{c}</option>))}
          </select>
        </label>
      )}

      {(actionDef.params ?? []).map((p) => (
        <label key={p.key} className="block">
          <span className="mono text-xs uppercase" style={{ color: "var(--color-on-surface-variant)" }}>{p.label}</span>
          {p.kind === "select" ? (
            <select
              value={params[p.key]}
              onChange={(e) => setParams({ ...params, [p.key]: e.target.value })}
              className="w-full mt-1 rounded-lg px-3 py-2 text-sm mono"
              style={{ background: "rgba(35,43,44,0.6)", border: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface)" }}
            >
              {p.options!.map((o) => (<option key={o} value={o}>{o}</option>))}
            </select>
          ) : (
            <input
              type={p.kind === "number" ? "number" : "text"}
              step={p.kind === "number" ? "0.01" : undefined}
              value={params[p.key]}
              onChange={(e) => setParams({ ...params, [p.key]: e.target.value })}
              className="w-full mt-1 rounded-lg px-3 py-2 text-sm mono"
              style={{ background: "rgba(35,43,44,0.6)", border: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface)" }}
            />
          )}
        </label>
      ))}

      <button
        onClick={() => onAdd(actionDef, column, params)}
        disabled={actionDef.needsColumn && !column}
        className="btn-primary w-full text-sm"
      >
        Add to queue
      </button>
    </div>
  );
}

function SampleTable({ title, rows }: { title: string; rows: Record<string, any>[] }) {
  if (rows.length === 0) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div>
      <div className="px-4 pt-3 pb-1 text-xs mono uppercase" style={{ color: "var(--color-on-surface-variant)" }}>{title}</div>
      <div className="overflow-x-auto max-h-56">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
              {cols.map((c) => (
                <th key={c} className="text-left px-4 py-1.5 mono font-medium whitespace-nowrap" style={{ color: "var(--color-on-surface-variant)" }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 10).map((row, i) => (
              <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                {cols.map((c) => (
                  <td key={c} className="px-4 py-1.5 whitespace-nowrap mono" style={{ color: "var(--color-on-surface)" }}>
                    {row[c] === null ? <span style={{ color: "var(--color-error)" }}>null</span> : String(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Outliers Tab ───────────────────────────────────────────────────────────
function OutliersTab({ projectId, datasetId, versionId }: {
  projectId: string; datasetId: string; versionId: string;
}) {
  const [scan, setScan] = useState<OutlierScanResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    outliersApi.scan(projectId, datasetId, versionId)
      .then(setScan)
      .catch(() => setScan(null))
      .finally(() => setLoading(false));
  }, [projectId, datasetId, versionId]);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
      </div>
    );
  }

  if (!scan || scan.items.length === 0) {
    return (
      <div className="glass-panel rounded-xl p-10 text-center">
        <span className="material-symbols-outlined text-4xl mb-2" style={{ color: "var(--color-outline)" }}>scan_search</span>
        <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>No numeric columns to scan</div>
      </div>
    );
  }

  const flagged = scan.items.filter((i) => i.count > 0);

  return (
    <div className="space-y-4">
      <p className="text-xs flex items-center gap-1.5" style={{ color: "var(--color-on-surface-variant)" }}>
        <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>policy</span>
        Detection is advisory only — nothing is removed automatically. Treatments are applied in the Transform tab.
      </p>

      {flagged.length === 0 ? (
        <div className="glass-panel rounded-xl p-10 text-center">
          <span className="material-symbols-outlined text-4xl mb-2" style={{ color: "var(--color-primary)", fontSize: "3rem" }}>verified</span>
          <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>No IQR outliers detected</div>
          <p className="text-sm mt-1" style={{ color: "var(--color-on-surface-variant)" }}>
            Run a per-column deep-dive below for density-based methods (Isolation Forest / LOF).
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {flagged.map((item) => (
            <OutlierColumnCard
              key={item.column}
              projectId={projectId} datasetId={datasetId} versionId={versionId}
              item={item}
            />
          ))}
        </div>
      )}

      {/* Clean columns summary */}
      {scan.items.some((i) => i.count === 0) && (
        <div className="glass-panel rounded-xl p-4">
          <div className="mono text-xs uppercase mb-2" style={{ color: "var(--color-on-surface-variant)" }}>Clean columns</div>
          <div className="flex flex-wrap gap-1.5">
            {scan.items.filter((i) => i.count === 0).map((i) => (
              <span key={i.column} className="mono text-xs px-2 py-1 rounded-md" style={{ background: "rgba(35,43,44,0.6)", color: "var(--color-on-surface-variant)" }}>
                {i.column}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function OutlierColumnCard({
  projectId, datasetId, versionId, item,
}: {
  projectId: string; datasetId: string; versionId: string;
  item: { column: string; count: number; share_pct: number; recommendation: QualityRecommendation };
}) {
  const [detail, setDetail] = useState<any>(null);
  const [method, setMethod] = useState("all");
  const [expanded, setExpanded] = useState(false);

  const loadDetail = useCallback((m: string) => {
    outliersApi.detail(projectId, datasetId, versionId, item.column, m)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [projectId, datasetId, versionId, item.column]);

  useEffect(() => {
    if (expanded) loadDetail(method);
  }, [expanded, method, loadDetail]);

  return (
    <div className="glass-card rounded-xl p-5" style={{ cursor: "default" }}>
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>
            <span className="mono">{item.column}</span>
          </div>
          <div className="text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
            {item.count} flagged ({item.share_pct}%)
          </div>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="btn-ghost text-xs"
        >
          {expanded ? "Hide methods" : "Compare methods"}
        </button>
      </div>

      <RecommendationBox rec={item.recommendation} />

      {expanded && (
        <div className="mt-4 space-y-3">
          <div className="flex gap-1.5">
            {["all", "iqr", "zscore", "isolation_forest", "lof"].map((m) => (
              <button
                key={m}
                onClick={() => setMethod(m)}
                className="text-xs px-2 py-1 rounded-md transition-all"
                style={{
                  background: method === m ? "rgba(0,242,254,0.12)" : "rgba(35,43,44,0.6)",
                  color: method === m ? "var(--color-primary)" : "var(--color-on-surface)",
                  border: "1px solid rgba(255,255,255,0.07)",
                }}
              >
                {m === "all" ? "All" : m.replace("_", " ")}
              </button>
            ))}
          </div>

          {detail && (
            <>
              {/* Method counts */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {detail.methods.map((m: any) => (
                  <div key={m.method} className="rounded-lg p-2.5 text-center" style={{ background: "rgba(35,43,44,0.5)", border: "1px solid rgba(255,255,255,0.06)" }}>
                    <div className="text-lg font-bold" style={{ color: "var(--color-on-surface)" }}>{m.count}</div>
                    <div className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>{m.method.replace("_", " ")}</div>
                  </div>
                ))}
              </div>

              {/* Histogram */}
              {detail.histogram && (
                <Histogram data={detail.histogram} fences={detail.fences} />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Histogram({ data, fences }: {
  data: { bin_edges: number[]; counts: number[] };
  fences: Record<string, any> | null;
}) {
  const maxCount = Math.max(...data.counts, 1);
  return (
    <div className="rounded-lg p-3" style={{ background: "rgba(35,43,44,0.5)", border: "1px solid rgba(255,255,255,0.06)" }}>
      <div className="flex items-end gap-[2px] h-20">
        {data.counts.map((count, i) => (
          <div
            key={i}
            className="flex-1 rounded-t transition-all group relative"
            style={{
              height: `${(count / maxCount) * 100}%`,
              minHeight: count > 0 ? "2px" : "0",
              background: count === maxCount ? "var(--color-primary-container)" : "rgba(0,242,254,0.35)",
            }}
            title={`${count} rows in [${Number(data.bin_edges[i]).toFixed(1)}, ${Number(data.bin_edges[i + 1]).toFixed(1)}]`}
          />
        ))}
      </div>
      <div className="flex justify-between mt-1 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
        <span>{Number(data.bin_edges[0]).toFixed(1)}</span>
        {fences?.lower_fence != null && (
          <span style={{ color: "var(--color-error)" }}>
            fences: [{Number(fences.lower_fence).toFixed(1)}, {Number(fences.upper_fence).toFixed(1)}]
          </span>
        )}
        <span>{Number(data.bin_edges[data.bin_edges.length - 1]).toFixed(1)}</span>
      </div>
    </div>
  );
}

// ── History & Compare Tab ──────────────────────────────────────────────────
function HistoryTab({
  projectId, datasetId, versionId, versions, onReverted,
}: {
  projectId: string; datasetId: string; versionId: string;
  versions: DatasetVersionResponse[];
  onReverted: (newId: string, tag: string) => void;
}) {
  const [chain, setChain] = useState<VersionHistoryEntry[] | null>(null);
  const [compare, setCompare] = useState<Record<string, any> | null>(null);
  const [compareTo, setCompareTo] = useState<string>("");
  const [revertError, setRevertError] = useState<string | null>(null);

  const loadChain = useCallback(() => {
    prepApi.history(projectId, datasetId, versionId).then(setChain).catch(() => setChain(null));
  }, [projectId, datasetId, versionId]);

  useEffect(() => {
    loadChain();
    setCompare(null);
    setCompareTo("");
  }, [loadChain]);

  const revert = async () => {
    setRevertError(null);
    try {
      const nv = await prepApi.revert(projectId, datasetId, versionId);
      onReverted(nv.id, nv.version_tag);
    } catch (e: any) {
      setRevertError(e.message);
    }
  };

  const runCompare = async () => {
    if (!compareTo) return;
    try {
      const result = await prepApi.compare(projectId, datasetId, compareTo, versionId);
      setCompare(result);
    } catch {
      setCompare(null);
    }
  };

  const otherVersions = versions.filter((v) => v.id !== versionId);
  const canRevert = chain ? chain.length > 1 : false;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Lineage */}
      <div className="glass-panel rounded-xl overflow-hidden">
        <div className="p-4 flex justify-between items-center" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
          <h2 className="font-semibold" style={{ color: "var(--color-on-surface)" }}>Transformation history</h2>
          <div className="flex gap-2">
            {canRevert && (
              <button onClick={revert} className="btn-ghost text-xs">
                <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>undo</span>
                Undo last apply
              </button>
            )}
            <button onClick={loadChain} className="btn-ghost text-xs">Refresh</button>
          </div>
        </div>

        {revertError && (
          <div className="m-3 p-3 rounded-lg text-xs" style={{ background: "rgba(255,107,107,0.08)", color: "#FF6B6B" }}>{revertError}</div>
        )}

        {!chain ? (
          <div className="p-6 text-sm text-center" style={{ color: "var(--color-on-surface-variant)" }}>Loading lineage…</div>
        ) : (
          <div className="p-4 space-y-4">
            {[...chain].reverse().map((entry, idx) => (
              <div key={entry.version_id}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span
                    className="mono text-xs px-2 py-1 rounded-md font-bold"
                    style={{
                      background: entry.version_id === versionId ? "rgba(0,242,254,0.12)" : "rgba(35,43,44,0.6)",
                      color: entry.version_id === versionId ? "var(--color-primary)" : "var(--color-on-surface)",
                    }}
                  >
                    {entry.version_tag}
                  </span>
                  {idx === 0 && <span className="text-xs" style={{ color: "var(--color-on-surface-variant)" }}>original upload</span>}
                </div>
                {entry.steps.length === 0 ? (
                  <div className="text-xs pl-2" style={{ color: "var(--color-on-surface-variant)" }}>No transformations</div>
                ) : (
                  <ol className="pl-2 space-y-1">
                    {entry.steps.map((s) => (
                      <li key={`${s.step_no}-${s.action}`} className="text-xs" style={{ color: "var(--color-on-surface)" }}>
                        <span className="mono" style={{ color: "var(--color-on-surface-variant)" }}>Step {s.step_no}</span>{" "}
                        {s.action}{s.column ? ` · ${s.column}` : ""}
                        {s.note ? <span style={{ color: "var(--color-on-surface-variant)" }}> — {s.note}</span> : null}
                      </li>
                    ))}
                  </ol>
                )}
                {idx < chain.length - 1 && (
                  <div className="pl-2 mt-2 material-symbols-outlined text-base" style={{ color: "var(--color-outline)" }}>arrow_downward</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Compare */}
      <div className="glass-panel rounded-xl overflow-hidden">
        <div className="p-4 text-xs mono uppercase tracking-wider" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
          Compare before / after
        </div>
        <div className="p-4 space-y-3">
          <div className="flex gap-2 items-center">
            <Select value={compareTo} onChange={setCompareTo} disabled={otherVersions.length === 0}>
              <option value="">Pick “before” version…</option>
              {otherVersions.map((v) => (<option key={v.id} value={v.id}>{v.version_tag}</option>))}
            </Select>
            <button onClick={runCompare} disabled={!compareTo} className="btn-ghost text-sm">Compare</button>
          </div>

          {!compare ? (
            <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
              Select an older version to diff against the currently selected one.
            </p>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "Rows", b: compare.rows_before, a: compare.rows_after },
                  { label: "Duplicate rows", b: compare.duplicate_rows_before, a: compare.duplicate_rows_after },
                  { label: "Missing cells", b: compare.missing_cells_before, a: compare.missing_cells_after },
                ].map((row) => (
                  <div key={row.label} className="rounded-lg p-3" style={{ background: "rgba(35,43,44,0.5)", border: "1px solid rgba(255,255,255,0.06)" }}>
                    <div className="mono text-xs uppercase mb-1" style={{ color: "var(--color-on-surface-variant)" }}>{row.label}</div>
                    <div className="text-sm font-semibold" style={{ color: "var(--color-on-surface)" }}>
                      {row.b.toLocaleString()} <span className="material-symbols-outlined text-sm" style={{ verticalAlign: "-3px" }}>arrow_forward</span> {row.a.toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>

              {compare.columns_added?.length > 0 && (
                <DiffLine label="Added" items={compare.columns_added} color="#50FA7B" />
              )}
              {compare.columns_removed?.length > 0 && (
                <DiffLine label="Removed" items={compare.columns_removed} color="#FF6B6B" />
              )}
              {compare.columns_changed?.length > 0 && (
                <div>
                  <div className="mono text-xs uppercase mb-1" style={{ color: "var(--color-on-surface-variant)" }}>Changed columns</div>
                  <ul className="space-y-1">
                    {compare.columns_changed.map((c: any, i: number) => (
                      <li key={i} className="mono text-xs" style={{ color: "var(--color-on-surface)" }}>
                        {c.column} <span style={{ color: "var(--color-primary)" }}>({c.change})</span>
                        {c.before !== undefined && c.after !== undefined && ` ${String(c.before)} → ${String(c.after)}`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DiffLine({ label, items, color }: { label: string; items: string[]; color: string }) {
  return (
    <div>
      <div className="mono text-xs uppercase mb-1" style={{ color: "var(--color-on-surface-variant)" }}>{label} columns</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((c) => (
          <span key={c} className="mono text-xs px-2 py-1 rounded-md" style={{ background: "rgba(35,43,44,0.6)", color, border: `1px solid ${color}33` }}>
            {c}
          </span>
        ))}
      </div>
    </div>
  );
}
