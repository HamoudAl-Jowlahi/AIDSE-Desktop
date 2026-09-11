"use client";
import { useEffect, useState } from "react";
import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import { automl as automlApi, type ExperimentResponse } from "@/lib/api";

export default function AutoMLLeaderboardPage() {
  const params = useParams<{ id: string; experiment_id: string }>();
  const pathname = usePathname();
  const pathParts = pathname.split("/").filter(Boolean);
  const id = params.id === "default" ? pathParts[1] : params.id;
  const experiment_id = params.experiment_id === "default" ? pathParts[4] : params.experiment_id;
  const [experiment, setExperiment] = useState<ExperimentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchExperiment = () => {
    automlApi.getExperiment(id, experiment_id)
      .then(setExperiment)
      .catch((err: any) => setError(err.message || "Failed to load experiment"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!id || !experiment_id) return;
    fetchExperiment();
    
    // Poll every 3 seconds if running
    let interval: NodeJS.Timeout;
    if (experiment?.status === "running" || experiment?.status === "pending" || !experiment) {
      interval = setInterval(fetchExperiment, 3000);
    }
    return () => clearInterval(interval);
  }, [id, experiment_id, experiment?.status]);

  if (loading && !experiment) {
    return (
      <div className="flex justify-center py-20">
        <div
          className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "var(--color-primary-container)" }}
        />
      </div>
    );
  }

  if (error || !experiment) {
    return (
      <div className="glass-panel p-10 text-center">
        <span className="material-symbols-outlined text-4xl mb-3" style={{ color: "var(--color-error)" }}>error</span>
        <p style={{ color: "var(--color-on-surface)" }}>{error ?? "Experiment not found"}</p>
        <Link href={`/projects/${id}/automl`} className="btn-primary mt-4 inline-flex">Back to AutoML</Link>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    switch(status) {
      case 'completed': return <span className="badge-success uppercase">Completed</span>;
      case 'running': return <span className="badge-warning uppercase">Running</span>;
      case 'failed': return <span className="badge-error uppercase">Failed</span>;
      default: return <span className="badge-neutral uppercase">{status}</span>;
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
        <Link href={`/projects/${id}`} className="hover:text-primary-container transition-colors">Project</Link>
        <span className="material-symbols-outlined" style={{ fontSize: "1rem" }}>chevron_right</span>
        <Link href={`/projects/${id}/automl`} className="hover:text-primary-container transition-colors">AutoML</Link>
        <span className="material-symbols-outlined" style={{ fontSize: "1rem" }}>chevron_right</span>
        <span className="mono truncate max-w-[200px]" style={{ color: "var(--color-on-surface)" }}>{experiment.id}</span>
      </div>

      {/* Header */}
      <div className="glass-panel rounded-xl p-6">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--color-on-surface)" }}>
              Target: {experiment.target_column}
            </h1>
            <div className="flex items-center gap-3">
              <span className="mono text-xs text-on-surface-variant bg-surface-variant px-2 py-0.5 rounded-full capitalize">
                {experiment.problem_type}
              </span>
              <span className="mono text-xs font-bold text-secondary bg-secondary/10 border border-secondary/20 px-2 py-0.5 rounded-full">
                Metric: {experiment.primary_metric}
              </span>
            </div>
          </div>
          <div className="text-right">
            {getStatusBadge(experiment.status)}
            {experiment.status === "running" && (
              <div className="text-xs mt-2 flex items-center justify-end gap-2" style={{ color: "var(--color-primary-container)" }}>
                <span className="w-2 h-2 rounded-full bg-primary-container animate-ping" />
                Optimizing models...
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="glass-card p-4 rounded-lg">
            <div className="text-xs mb-1 mono" style={{ color: "var(--color-on-surface-variant)" }}>TRIALS COMPLETED</div>
            <div className="text-2xl font-bold">{experiment.trials?.length || 0}</div>
          </div>
          <div className="glass-card p-4 rounded-lg">
            <div className="text-xs mb-1 mono" style={{ color: "var(--color-on-surface-variant)" }}>BEST SCORE</div>
            <div className="text-2xl font-bold" style={{ color: "var(--color-secondary)" }}>
              {experiment.trials?.length > 0 
                ? experiment.trials[0].primary_metric_score?.toFixed(4) || "—"
                : "—"}
            </div>
          </div>
          <div className="glass-card p-4 rounded-lg">
            <div className="text-xs mb-1 mono" style={{ color: "var(--color-on-surface-variant)" }}>BEST ALGORITHM</div>
            <div className="text-xl font-bold truncate">
              {experiment.trials?.length > 0 ? experiment.trials[0].algorithm_name : "—"}
            </div>
          </div>
          <div className="glass-card p-4 rounded-lg">
            <div className="text-xs mb-1 mono" style={{ color: "var(--color-on-surface-variant)" }}>STARTED AT</div>
            <div className="text-sm font-bold truncate">
              {new Date(experiment.created_at).toLocaleString()}
            </div>
          </div>
        </div>
      </div>

      {/* Leaderboard */}
      <div>
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2" style={{ color: "var(--color-on-surface)" }}>
          <span className="material-symbols-outlined text-yellow-400">emoji_events</span>
          Model Leaderboard
        </h2>
        
        <div className="glass-panel rounded-xl overflow-hidden">
          {experiment.trials?.length === 0 ? (
            <div className="p-10 text-center" style={{ color: "var(--color-on-surface-variant)" }}>
              {experiment.status === "running" ? "Waiting for the first trial to complete..." : "No trials found."}
            </div>
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr style={{ background: "rgba(35,43,44,0.3)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  <th className="p-4 mono text-xs w-16 text-center" style={{ color: "var(--color-on-surface-variant)" }}>RANK</th>
                  <th className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>ALGORITHM</th>
                  <th className="p-4 mono text-xs text-right" style={{ color: "var(--color-secondary)" }}>{experiment.primary_metric.toUpperCase()}</th>
                  <th className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>HYPERPARAMETERS</th>
                  <th className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>MLFLOW RUN</th>
                </tr>
              </thead>
              <tbody>
                {experiment.trials.map((trial, idx) => (
                  <tr
                    key={trial.id}
                    className="transition-colors group"
                    style={{ 
                      borderBottom: "1px solid rgba(255,255,255,0.04)",
                      background: idx === 0 ? "rgba(255,215,0,0.05)" : "transparent"
                    }}
                    onMouseEnter={(e) => { if (idx !== 0) e.currentTarget.style.background = "rgba(255,255,255,0.03)"; }}
                    onMouseLeave={(e) => { if (idx !== 0) e.currentTarget.style.background = "transparent"; }}
                  >
                    <td className="p-4 text-center">
                      {idx === 0 ? (
                        <span className="w-8 h-8 rounded-full bg-yellow-500/20 text-yellow-500 border border-yellow-500/30 flex items-center justify-center font-bold mx-auto">
                          1
                        </span>
                      ) : (
                        <span className="text-lg font-bold" style={{ color: "var(--color-on-surface-variant)" }}>
                          {idx + 1}
                        </span>
                      )}
                    </td>
                    <td className="p-4">
                      <div className="font-bold text-lg" style={{ color: "var(--color-on-surface)" }}>
                        {trial.algorithm_name}
                      </div>
                    </td>
                    <td className="p-4 text-right">
                      <div className="font-mono font-bold text-lg" style={{ color: "var(--color-secondary)" }}>
                        {trial.primary_metric_score?.toFixed(4) || "—"}
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(trial.hyperparameters || {}).map(([k, v]) => (
                          <span key={k} className="mono text-[10px] px-1.5 py-0.5 rounded bg-white/5 border border-white/10" style={{ color: "var(--color-on-surface-variant)" }}>
                            {k}: {typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(4) : String(v)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="p-4">
                      {trial.mlflow_run_id ? (
                        <span className="mono text-[10px] truncate max-w-[120px] block" style={{ color: "var(--color-on-surface-variant)" }}>
                          {trial.mlflow_run_id}
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
// export function generateStaticParams() { return [{ id: 'default', experiment_id: 'default' }]; }
