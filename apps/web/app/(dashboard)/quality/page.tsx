"use client";
/**
 * AIDSE Platform — Data Quality Center (Phase 3)
 *
 * Select project → dataset → version, then inspect detected issues grouped
 * by severity (CRITICAL / WARNING / INFO). Every issue shows the affected
 * columns, how it was detected, why it matters and a rule-based
 * recommendation with reasoning and trade-offs.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  datasets as datasetsApi,
  projects as projectsApi,
  quality as qualityApi,
  type DatasetResponse,
  type DatasetVersionResponse,
  type ProjectOut,
  type QualityIssue,
  type QualityReport,
} from "@/lib/api";
import { urlSelection } from "@/lib/selection";

const SEVERITY_META: Record<
  string,
  { label: string; icon: string; color: string; bg: string; border: string }
> = {
  critical: {
    label: "Critical",
    icon: "error",
    color: "#FF6B6B",
    bg: "rgba(255,107,107,0.08)",
    border: "rgba(255,107,107,0.25)",
  },
  warning: {
    label: "Warning",
    icon: "warning",
    color: "#FFC24B",
    bg: "rgba(255,194,75,0.08)",
    border: "rgba(255,194,75,0.25)",
  },
  info: {
    label: "Info",
    icon: "info",
    color: "#4FC3F7",
    bg: "rgba(79,195,247,0.08)",
    border: "rgba(79,195,247,0.25)",
  },
};

// ── Issue Card ─────────────────────────────────────────────────────────────
function IssueCard({ issue }: { issue: QualityIssue }) {
  const meta = SEVERITY_META[issue.severity] ?? SEVERITY_META.info;
  return (
    <div
      className="glass-card rounded-xl p-5"
      style={{ borderLeft: `3px solid ${meta.color}`, cursor: "default" }}
    >
      {/* Title row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-start gap-2">
          <span className="material-symbols-outlined text-xl" style={{ color: meta.color }}>
            {meta.icon}
          </span>
          <div>
            <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>
              {issue.title}
            </div>
            <div className="mono text-xs mt-0.5" style={{ color: "var(--color-on-surface-variant)" }}>
              Detected via {issue.detection_method}
            </div>
          </div>
        </div>
        <span
          className="text-xs mono px-2 py-1 rounded-full whitespace-nowrap"
          style={{ background: meta.bg, color: meta.color, border: `1px solid ${meta.border}` }}
        >
          {meta.label.toUpperCase()}
        </span>
      </div>

      {/* Affected stats */}
      {(issue.columns.length > 0 || issue.affected_count !== null) && (
        <div className="flex flex-wrap gap-2 mb-3">
          {issue.columns.map((c) => (
            <span
              key={c}
              className="mono text-xs px-2 py-1 rounded-md"
              style={{
                background: "rgba(35,43,44,0.5)",
                border: "1px solid rgba(255,255,255,0.07)",
                color: "var(--color-on-surface)",
              }}
            >
              {c}
            </span>
          ))}
          {issue.affected_count !== null && issue.affected_count > 0 && (
            <span className="text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
              {issue.affected_count.toLocaleString()} rows affected
              {issue.affected_pct !== null ? ` (${issue.affected_pct}%)` : ""}
            </span>
          )}
        </div>
      )}

      {/* Why it matters */}
      <p className="text-sm mb-4 leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>
        {issue.why_it_matters}
      </p>

      {/* Recommendation */}
      <div
        className="rounded-lg p-4"
        style={{ background: "rgba(0,242,254,0.05)", border: "1px solid rgba(0,242,254,0.12)" }}
      >
        <div className="flex items-center gap-1.5 mb-2">
          <span className="material-symbols-outlined text-base" style={{ color: "var(--color-primary)" }}>
            auto_awesome
          </span>
          <span className="text-xs mono uppercase tracking-wider" style={{ color: "var(--color-primary)" }}>
            Recommended
          </span>
        </div>
        <div className="text-sm font-semibold mb-1.5" style={{ color: "var(--color-on-surface)" }}>
          {issue.recommendation.technique}
        </div>
        <p className="text-xs leading-relaxed mb-2" style={{ color: "var(--color-on-surface-variant)" }}>
          {issue.recommendation.reason}
        </p>
        {issue.recommendation.alternatives.length > 0 && (
          <p className="text-xs mb-2" style={{ color: "var(--color-on-surface-variant)" }}>
            <span style={{ color: "var(--color-on-surface)" }}>Alternatives: </span>
            {issue.recommendation.alternatives.join(" · ")}
          </p>
        )}
        <p className="text-xs flex items-start gap-1" style={{ color: "var(--color-on-surface-variant)" }}>
          <span className="material-symbols-outlined" style={{ fontSize: "0.875rem", marginTop: "1px" }}>
            balance
          </span>
          <span>{issue.recommendation.risk}</span>
        </p>
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function QualityPage() {
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [datasetRows, setDatasetRows] = useState<DatasetResponse[]>([]);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [versions, setVersions] = useState<DatasetVersionResponse[]>([]);
  const [versionId, setVersionId] = useState<string | null>(null);

  const [report, setReport] = useState<QualityReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  // Load projects once
  useEffect(() => {
    projectsApi
      .list(1, 50)
      .then((d) => {
        setProjectList(d.items);
        const sel = urlSelection();
        const preferred = sel.project && d.items.some((p) => p.id === sel.project) ? sel.project : null;
        if (d.items.length > 0) setProjectId(preferred ?? d.items[0].id);
      })
      .catch(() => {});
  }, []);

  // Load datasets for project
  useEffect(() => {
    if (!projectId) return;
    setDatasetRows([]);
    setDatasetId(null);
    datasetsApi
      .list(projectId)
      .then((rows) => {
        setDatasetRows(rows);
        const dsSel = urlSelection().dataset;
        const preferredDs = dsSel && rows.some((r) => r.id === dsSel) ? dsSel : null;
        if (rows.length > 0) setDatasetId(preferredDs ?? rows[0].id);
      })
      .catch(() => {});
  }, [projectId]);

  // Pick latest version when dataset changes
  useEffect(() => {
    const ds = datasetRows.find((d) => d.id === datasetId);
    const vs = ds?.versions ?? [];
    setVersions(vs);
    if (vs.length > 0) {
      setVersionId(vs[vs.length - 1].id); // versions arrive oldest-first
    } else {
      setVersionId(null);
    }
  }, [datasetRows, datasetId]);

  // Fetch quality report
  const loadReport = useCallback(() => {
    if (!projectId || !datasetId || !versionId) return;
    setLoadingReport(true);
    qualityApi
      .getVersionReport(projectId, datasetId, versionId)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoadingReport(false));
  }, [projectId, datasetId, versionId]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const grouped = useMemo(() => {
    const g: Record<string, QualityIssue[]> = { critical: [], warning: [], info: [] };
    for (const issue of report?.issues ?? []) {
      (g[issue.severity] ?? g.info).push(issue);
    }
    return g;
  }, [report]);

  const selectStyle = {
    background: "rgba(35,43,44,0.5)",
    border: "1px solid rgba(255,255,255,0.07)",
    color: "var(--color-on-surface)",
  } as const;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
          Data Quality
        </h1>
        <p className="text-sm max-w-2xl" style={{ color: "var(--color-on-surface-variant)" }}>
          Problems are grouped by severity. Every issue explains why it matters and what to do about it — nothing is changed without your approval.
        </p>
      </div>

      {/* Selectors */}
      {projectList.length === 0 ? (
        <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
          <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)" }}>folder_off</span>
          <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>No projects yet</div>
          <Link href="/projects" className="btn-primary mt-2 text-sm">Create a project first</Link>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-3">
            <select
              value={projectId ?? ""}
              onChange={(e) => setProjectId(e.target.value)}
              className="rounded-lg px-3 py-2 text-sm mono"
              style={selectStyle}
            >
              {projectList.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>

            <select
              value={datasetId ?? ""}
              onChange={(e) => setDatasetId(e.target.value)}
              disabled={datasetRows.length === 0}
              className="rounded-lg px-3 py-2 text-sm mono"
              style={selectStyle}
            >
              {datasetRows.length === 0 && <option>No datasets</option>}
              {datasetRows.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>

            <select
              value={versionId ?? ""}
              onChange={(e) => setVersionId(e.target.value)}
              disabled={versions.length === 0}
              className="rounded-lg px-3 py-2 text-sm mono"
              style={selectStyle}
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.version_tag}{v.profile_status === "pending" ? " (profiling...)" : ""}
                </option>
              ))}
            </select>

            <button onClick={loadReport} className="btn-ghost text-sm ml-auto">
              <span className="material-symbols-outlined" style={{ fontSize: "1rem" }}>refresh</span>
              Refresh
            </button>
          </div>

          {/* Summary strip */}
          {report?.summary.available && (
            <div className="grid grid-cols-3 gap-4">
              {(["critical", "warning", "info"] as const).map((sev) => {
                const meta = SEVERITY_META[sev];
                return (
                  <div key={sev} className="glass-card rounded-xl p-4 flex items-center gap-3" style={{ cursor: "default", borderColor: meta.border }}>
                    <span className="material-symbols-outlined text-2xl" style={{ color: meta.color }}>{meta.icon}</span>
                    <div>
                      <div className="text-2xl font-bold" style={{ color: "var(--color-on-surface)" }}>
                        {report.summary[sev]}
                      </div>
                      <div className="mono text-xs uppercase" style={{ color: "var(--color-on-surface-variant)" }}>
                        {meta.label}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Report body */}
          {loadingReport ? (
            <div className="flex justify-center py-20">
              <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
            </div>
          ) : !report ? (
            <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
              <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)" }}>database</span>
              <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>No version selected</div>
              <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>Upload a dataset to see its quality report.</p>
            </div>
          ) : report.summary.pending_profiling ? (
            <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
              <div className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
              <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>Profiling in progress…</div>
              <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>Large file — the report appears when profiling completes.</p>
            </div>
          ) : report.issues.length === 0 ? (
            <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
              <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-primary)", fontSize: "3rem" }}>verified</span>
              <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>No quality issues detected</div>
              <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>This version looks clean. Proceed to ML training whenever you are ready.</p>
              <Link href="/ml-lab" className="btn-primary mt-2 text-sm">Open ML Lab</Link>
            </div>
          ) : (
            /* Issues by severity */
            <div className="space-y-8">
              {(["critical", "warning", "info"] as const).map((sev) =>
                grouped[sev].length > 0 ? (
                  <section key={sev}>
                    <h2 className="flex items-center gap-2 text-lg font-semibold mb-3" style={{ color: SEVERITY_META[sev].color }}>
                      <span className="material-symbols-outlined">{SEVERITY_META[sev].icon}</span>
                      {SEVERITY_META[sev].label}
                      <span className="mono text-xs px-2 py-0.5 rounded-full" style={{ background: SEVERITY_META[sev].bg }}>
                        {grouped[sev].length}
                      </span>
                    </h2>
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      {grouped[sev].map((issue) => (
                        <IssueCard key={issue.id} issue={issue} />
                      ))}
                    </div>
                  </section>
                ) : null
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
