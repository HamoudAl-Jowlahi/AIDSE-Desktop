"use client";
/**
 * AIDSE Platform — Reports (Phase 15)
 *
 * One coherent view per project: datasets + quality totals, ML results,
 * AI evaluation status. Export formats are a V2 roadmap item.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  projects as projectsApi,
  reports as reportsApi,
  type ProjectOut,
  type ProjectReport,
} from "@/lib/api";

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

function sevColor(n: number): string {
  return n > 0 ? "#FF6B6B" : "var(--color-on-surface-variant)";
}

export default function ReportsPage() {
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [report, setReport] = useState<ProjectReport | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    projectsApi.list(1, 50).then((d) => {
      setProjectList(d.items);
      if (d.items.length > 0) setProjectId(d.items[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    setReport(null);
    reportsApi.getProjectReport(projectId)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [projectId]);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex justify-between items-end flex-wrap gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
            Reports
          </h1>
          <p className="text-sm max-w-2xl" style={{ color: "var(--color-on-surface-variant)" }}>
            The full story of this project: what the data looked like, which models won, and where evaluations stand.
          </p>
        </div>
        {projectList.length > 0 && (
          <Select value={projectId} onChange={setProjectId}>
            {projectList.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </Select>
        )}
      </div>

      {projectList.length === 0 ? (
        <div className="glass-panel rounded-xl p-10 text-center">
          <Link href="/projects" className="btn-primary text-sm">Create a project first</Link>
        </div>
      ) : loading ? (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: "var(--color-primary-container)" }} />
        </div>
      ) : !report ? (
        <div className="glass-panel rounded-xl p-10 text-center text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
          Report unavailable.
        </div>
      ) : (
        <div className="space-y-6">
          {/* Summary strip */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <SummaryCard label="Datasets" value={String(report.summary.datasets)} />
            <SummaryCard label="Experiments" value={String(report.summary.experiments)} />
            <SummaryCard label="Golden sets" value={String(report.summary.golden_datasets)} />
            <SummaryCard label="Eval runs" value={String(report.summary.evaluation_runs)} />
            <SummaryCard
              label="Quality C/W/I"
              value={`${report.summary.data_quality_totals.critical}/${report.summary.data_quality_totals.warning}/${report.summary.data_quality_totals.info}`}
              color={sevColor(report.summary.data_quality_totals.critical)}
            />
          </div>

          {/* Datasets */}
          <Section title={`Datasets (${report.datasets.length})`}>
            {report.datasets.length === 0 ? (
              <Empty text="No datasets uploaded." />
            ) : (
              report.datasets.map((d) => (
                <div key={d.dataset_id}
                  className="flex items-center justify-between flex-wrap gap-2 px-4 py-3"
                  style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <div>
                    <div className="text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>{d.name}</div>
                    <div className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                      {d.format.toUpperCase()} · {d.latest_version ?? d.profile_status ?? "?"}
                    </div>
                  </div>
                  <div className="flex items-center gap-4 mono text-xs">
                    <span style={{ color: "var(--color-on-surface)" }}>
                      {d.num_rows != null ? `${d.num_rows.toLocaleString()} × ${d.num_columns}` : "—"}
                    </span>
                    {(d.duplicate_rows ?? 0) > 0 && (
                      <span style={{ color: "#FF6B6B" }}>{d.duplicate_rows} dupes</span>
                    )}
                    {d.quality ? (
                      <span style={{ color: sevColor(d.quality.critical) }}>
                        {d.quality.critical}/{d.quality.warning}/{d.quality.info}
                      </span>
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </Section>

          {/* ML results */}
          <Section title={`ML results (${report.ml_results.length})`}>
            {report.ml_results.length === 0 ? (
              <Empty text="No models trained yet — visit the ML Lab." />
            ) : (
              report.ml_results.map((m) => (
                <div key={m.experiment_id}
                  className="flex items-center justify-between flex-wrap gap-2 px-4 py-3"
                  style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <div>
                    <span className="mono text-sm" style={{ color: "var(--color-on-surface)" }}>{m.target_column}</span>
                    <span className="capitalize text-xs ml-2" style={{ color: "var(--color-on-surface-variant)" }}>
                      {m.problem_type} · {m.trials_completed} trials
                    </span>
                  </div>
                  <div className="mono text-xs">
                    {m.best_model ? (
                      <>
                        <span className="capitalize mr-2" style={{ color: "var(--color-primary)" }}>
                          {m.best_model.algorithm.replace(/_/g, " ")}
                        </span>
                        <span style={{ color: "var(--color-on-surface)" }}>
                          {m.best_model.score != null ? Number(m.best_model.score).toFixed(4) : "—"} {m.primary_metric}
                        </span>
                      </>
                    ) : (
                      <span style={{ color: "var(--color-on-surface-variant)" }}>{m.status}</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </Section>

          {/* AI evaluation */}
          <Section title={`AI evaluation (${report.ai_evaluation.length})`}>
            {report.ai_evaluation.length === 0 ? (
              <Empty text="No golden datasets yet." />
            ) : (
              report.ai_evaluation.map((e) => {
                const pr = e.latest_run?.pass_rate;
                return (
                  <div key={e.golden_dataset_id}
                    className="flex items-center justify-between flex-wrap gap-2 px-4 py-3"
                    style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <div>
                      <span className="text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>{e.name}</span>
                      <span className="mono text-xs ml-2" style={{ color: "var(--color-on-surface-variant)" }}>
                        v{e.version} · {e.case_count} cases · {e.total_runs} runs
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mono text-xs">
                      <span style={{ color: e.baseline_designated ? "#50FA7B" : "var(--color-on-surface-variant)" }}>
                        baseline {e.baseline_designated ? "✓" : "—"}
                      </span>
                      <span style={{
                        color: pr == null ? "var(--color-on-surface-variant)"
                          : pr >= 0.9 ? "#50FA7B" : pr >= 0.7 ? "#FFC24B" : "#FF6B6B",
                      }}>
                        {pr != null ? `${Math.round(pr * 100)}% pass` : "no runs"}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </Section>

          <p className="mono text-xs flex items-center gap-1.5" style={{ color: "var(--color-on-surface-variant)" }}>
            <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>schedule</span>
            Generated {new Date(report.generated_at).toLocaleString()} · PDF/XLSX export planned for V2
          </p>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="glass-card rounded-xl p-4" style={{ cursor: "default" }}>
      <div className="text-2xl font-bold mono" style={{ color: color ?? "var(--color-on-surface)" }}>{value}</div>
      <div className="mono text-xs uppercase mt-1" style={{ color: "var(--color-on-surface-variant)" }}>{label}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass-panel rounded-xl overflow-hidden">
      <div className="p-4 text-xs mono uppercase tracking-wider"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--color-on-surface-variant)" }}>
        {title}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="p-4 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>{text}</p>;
}
