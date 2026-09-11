"use client";
import { useEffect, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  automl as automlApi,
  datasets as datasetsApi,
  type ExperimentResponse,
  type DatasetResponse,
  type ExperimentCreate
} from "@/lib/api";

function CreateExperimentModal({
  projectId,
  datasets,
  onClose,
  onCreated,
}: {
  projectId: string;
  datasets: DatasetResponse[];
  onClose: () => void;
  onCreated: (e: ExperimentResponse) => void;
}) {
  const [datasetId, setDatasetId] = useState(datasets.length > 0 ? datasets[0].id : "");
  const [targetColumn, setTargetColumn] = useState("");
  const [problemType, setProblemType] = useState("classification");
  const [primaryMetric, setPrimaryMetric] = useState("f1_macro");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Reset primary metric choices based on problem type
    if (problemType === "classification") {
      setPrimaryMetric("f1_macro");
    } else {
      setPrimaryMetric("r2");
    }
  }, [problemType]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!datasetId) {
      setError("Please select a dataset.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const payload: ExperimentCreate = {
        target_column: targetColumn,
        problem_type: problemType,
        primary_metric: primaryMetric,
      };
      const exp = await automlApi.createExperiment(projectId, datasetId, payload);
      onCreated(exp);
    } catch (err: unknown) {
      setError(
        (err as { data?: { error?: { message?: string } } })?.data?.error?.message ??
          "Failed to start experiment"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="glass-panel rounded-2xl p-8 w-full max-w-md animate-fade-in">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold" style={{ color: "var(--color-on-surface)" }}>
            New AutoML Experiment
          </h2>
          <button onClick={onClose} style={{ color: "var(--color-on-surface-variant)" }}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {error && (
          <div
            className="mb-4 p-3 rounded-lg text-sm"
            style={{
              background: "rgba(147,0,10,0.2)",
              border: "1px solid rgba(255,180,171,0.3)",
              color: "var(--color-error)",
            }}
          >
            {error}
          </div>
        )}

        {datasets.length === 0 ? (
          <div className="text-sm p-4 rounded-lg text-center" style={{ background: "rgba(255,255,255,0.05)" }}>
            You need to upload a dataset to this project first before running AutoML.
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
                SELECT DATASET
              </label>
              <select
                value={datasetId}
                onChange={(e) => setDatasetId(e.target.value)}
                className="input-field"
                required
              >
                {datasets.map(d => (
                  <option key={d.id} value={d.id}>{d.name} ({d.format})</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
                TARGET COLUMN NAME
              </label>
              <input
                type="text"
                value={targetColumn}
                onChange={(e) => setTargetColumn(e.target.value)}
                placeholder="e.g. price, is_fraud"
                required
                className="input-field"
              />
            </div>

            <div>
              <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
                PROBLEM TYPE
              </label>
              <select
                value={problemType}
                onChange={(e) => setProblemType(e.target.value)}
                className="input-field"
              >
                <option value="classification">Classification</option>
                <option value="regression">Regression</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
                PRIMARY METRIC (TO OPTIMIZE)
              </label>
              <select
                value={primaryMetric}
                onChange={(e) => setPrimaryMetric(e.target.value)}
                className="input-field"
              >
                {problemType === "classification" ? (
                  <>
                    <option value="f1_macro">F1 Score (Macro)</option>
                    <option value="accuracy">Accuracy</option>
                    <option value="precision">Precision</option>
                    <option value="recall">Recall</option>
                  </>
                ) : (
                  <>
                    <option value="r2">R-Squared (R2)</option>
                    <option value="rmse">Root Mean Squared Error (RMSE)</option>
                    <option value="mae">Mean Absolute Error (MAE)</option>
                  </>
                )}
              </select>
            </div>

            <div className="flex gap-3 pt-4">
              <button type="button" onClick={onClose} className="btn-ghost flex-1">
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="btn-primary flex-1"
                style={{ opacity: loading ? 0.7 : 1 }}
              >
                {loading ? "Launching..." : "Launch Experiment"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default function AutoMLDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const [experiments, setExperiments] = useState<ExperimentResponse[]>([]);
  const [datasets, setDatasets] = useState<DatasetResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchExperiments = () => {
    Promise.all([
      automlApi.listExperiments(id).catch(() => []),
      datasetsApi.list(id).catch(() => []),
    ])
      .then(([exps, dsets]) => {
        setExperiments(exps);
        setDatasets(dsets);
      })
      .catch(() => setError("Failed to load AutoML experiments."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!id) return;
    fetchExperiments();
    // Poll every 5 seconds for status updates
    const interval = setInterval(fetchExperiments, 5000);
    return () => clearInterval(interval);
  }, [id]);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div
          className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "var(--color-primary-container)" }}
        />
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
        <span style={{ color: "var(--color-on-surface)" }}>AutoML</span>
      </div>

      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold mb-1" style={{ color: "var(--color-on-surface)" }}>
            AutoML Experiments
          </h1>
          <p className="mt-2 text-sm max-w-xl" style={{ color: "var(--color-on-surface-variant)" }}>
            Launch hyperparameter tuning jobs, compare algorithm performance, and view leaderboards.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="btn-primary"
        >
          <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>
            science
          </span>
          New Experiment
        </button>
      </div>

      {error && (
        <div className="glass-panel p-4 text-sm" style={{ color: "var(--color-error)" }}>
          {error}
        </div>
      )}

      {/* Experiment List */}
      <div className="glass-panel rounded-xl overflow-hidden">
        {experiments.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center gap-4" style={{ color: "var(--color-on-surface-variant)" }}>
            <div className="w-16 h-16 rounded-full flex items-center justify-center" style={{ background: "rgba(0,242,254,0.1)", color: "var(--color-primary-container)" }}>
              <span className="material-symbols-outlined text-3xl">rocket_launch</span>
            </div>
            <div>
              <h3 className="text-lg font-bold mb-1" style={{ color: "var(--color-on-surface)" }}>No experiments yet</h3>
              <p className="text-sm">Kick off an AutoML job to automatically find the best model for your dataset.</p>
            </div>
          </div>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr style={{ background: "rgba(35,43,44,0.3)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                <th className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>TARGET</th>
                <th className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>PROBLEM TYPE</th>
                <th className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>METRIC</th>
                <th className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>STATUS</th>
                <th className="p-4 mono text-xs text-right" style={{ color: "var(--color-on-surface-variant)" }}>STARTED</th>
              </tr>
            </thead>
            <tbody>
              {experiments.map((exp) => (
                <tr
                  key={exp.id}
                  className="transition-colors group"
                  style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.03)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <td className="p-4">
                    <Link href={`/projects/${id}/automl/experiments/${exp.id}`} className="font-semibold text-lg hover:text-primary-container hover:underline block" style={{ color: "var(--color-on-surface)" }}>
                      {exp.target_column}
                    </Link>
                    <div className="mono text-[10px] mt-1 truncate max-w-[200px]" style={{ color: "var(--color-on-surface-variant)" }}>
                      ID: {exp.id}
                    </div>
                  </td>
                  <td className="p-4 text-sm capitalize" style={{ color: "var(--color-on-surface-variant)" }}>
                    {exp.problem_type}
                  </td>
                  <td className="p-4 text-sm mono font-bold" style={{ color: "var(--color-secondary)" }}>
                    {exp.primary_metric}
                  </td>
                  <td className="p-4">
                    {getStatusBadge(exp.status)}
                    {exp.error_message && (
                      <div className="text-xs mt-1 text-red-400 truncate max-w-[200px]">
                        {exp.error_message}
                      </div>
                    )}
                  </td>
                  <td className="p-4 mono text-xs text-right" style={{ color: "var(--color-on-surface-variant)" }}>
                    {new Date(exp.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {typeof document !== "undefined" && createPortal(
        <>
          {showCreate && (
            <CreateExperimentModal
              projectId={id!}
              datasets={datasets}
              onClose={() => setShowCreate(false)}
              onCreated={(exp) => {
                setExperiments((prev) => [exp, ...prev]);
                setShowCreate(false);
              }}
            />
          )}
        </>,
        document.body
      )}
    </div>
  );
}
// export function generateStaticParams() { return [{ id: 'default' }]; }
