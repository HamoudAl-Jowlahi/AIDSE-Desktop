"use client";

import { useEffect, useState, FormEvent } from "react";
import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import { automl as automlApi, type ExperimentResponse } from "@/lib/api";

export default function AutoMLPage() {
  const params = useParams<{ id: string; datasetId: string }>();
  const pathname = usePathname();
  const pathParts = pathname.split("/").filter(Boolean);
  const id = params.id === "default" ? pathParts[1] : params.id;
  const datasetId = params.datasetId === "default" ? pathParts[3] : params.datasetId;
  const [experiment, setExperiment] = useState<ExperimentResponse | null>(null);
  
  const [targetColumn, setTargetColumn] = useState("");
  const [problemType, setProblemType] = useState("classification");
  const [primaryMetric, setPrimaryMetric] = useState("accuracy");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Poll for experiment updates if running
  useEffect(() => {
    if (!experiment || (experiment.status !== "pending" && experiment.status !== "running")) return;
    
    const interval = setInterval(async () => {
      try {
        const data = await automlApi.getExperiment(id!, experiment.id);
        setExperiment(data);
      } catch (err) {
        console.error("Polling error", err);
      }
    }, 3000);
    
    return () => clearInterval(interval);
  }, [experiment?.id, experiment?.status, id]);

  const handleStart = async (e: FormEvent) => {
    e.preventDefault();
    if (!targetColumn) return;
    setLoading(true);
    setError(null);
    try {
      const newExp = await automlApi.createExperiment(id!, datasetId!, {
        target_column: targetColumn,
        problem_type: problemType,
        primary_metric: primaryMetric,
      });
      setExperiment(newExp);
    } catch (err: any) {
      setError(err.message || "Failed to start AutoML");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-2 text-sm text-on-surface-variant mb-6">
        <Link href={`/projects/${id}`} className="hover:text-primary-container transition-colors">Project View</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <Link href={`/projects/${id}/datasets/${datasetId}`} className="hover:text-primary-container transition-colors">Dataset</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <span className="text-on-surface">AutoML Training</span>
      </div>

      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold mb-1 text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-3xl">model_training</span>
            AutoML Engine
          </h1>
          <p className="text-sm text-on-surface-variant max-w-xl mt-2">
            Automatically train and tune multiple machine learning algorithms (Random Forest, XGBoost, LightGBM, CatBoost) to find the best model for your dataset.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
        {/* Left Side: Configuration Form */}
        <div className="glass-panel p-6 rounded-xl md:col-span-1 h-fit">
          <h2 className="text-lg font-semibold text-on-surface mb-4 flex items-center gap-2">
             <span className="material-symbols-outlined">settings</span> Configuration
          </h2>
          {error && <div className="mb-4 p-3 rounded-lg text-sm bg-red-900/20 border border-red-500/30 text-red-400">{error}</div>}
          
          <form onSubmit={handleStart} className="space-y-5">
            <div>
              <label className="block text-xs font-medium mb-1.5 mono text-on-surface-variant">TARGET COLUMN</label>
              <input 
                type="text" 
                value={targetColumn} 
                onChange={(e) => setTargetColumn(e.target.value)} 
                placeholder="e.g., Target, Price, Class" 
                required 
                className="input-field w-full"
                disabled={experiment?.status === "running" || experiment?.status === "pending"}
              />
            </div>
            
            <div>
              <label className="block text-xs font-medium mb-1.5 mono text-on-surface-variant">PROBLEM TYPE</label>
              <select 
                value={problemType} 
                onChange={(e) => {
                  setProblemType(e.target.value);
                  setPrimaryMetric(e.target.value === "classification" ? "accuracy" : "rmse");
                }} 
                className="input-field w-full cursor-pointer"
                disabled={experiment?.status === "running" || experiment?.status === "pending"}
              >
                <option value="classification">Classification (Predict Categories)</option>
                <option value="regression">Regression (Predict Numbers)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium mb-1.5 mono text-on-surface-variant">PRIMARY OPTIMIZATION METRIC</label>
              <select 
                value={primaryMetric} 
                onChange={(e) => setPrimaryMetric(e.target.value)} 
                className="input-field w-full cursor-pointer"
                disabled={experiment?.status === "running" || experiment?.status === "pending"}
              >
                {problemType === "classification" ? (
                  <>
                    <option value="accuracy">Accuracy</option>
                    <option value="f1_macro">F1-Score (Macro)</option>
                    <option value="precision">Precision</option>
                    <option value="recall">Recall</option>
                  </>
                ) : (
                  <>
                    <option value="rmse">RMSE (Root Mean Squared Error)</option>
                    <option value="mae">MAE (Mean Absolute Error)</option>
                    <option value="r2">R² Score</option>
                  </>
                )}
              </select>
            </div>

            <button 
              type="submit" 
              disabled={loading || experiment?.status === "running" || experiment?.status === "pending"} 
              className="btn-primary w-full mt-4 flex justify-center items-center gap-2"
            >
              {(experiment?.status === "running" || experiment?.status === "pending") ? (
                <>
                  <div className="w-4 h-4 rounded-full border-2 border-t-transparent border-white animate-spin"></div>
                  Training...
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined">play_arrow</span>
                  Start AutoML Run
                </>
              )}
            </button>
          </form>
        </div>

        {/* Right Side: Leaderboard */}
        <div className="glass-panel p-0 rounded-xl md:col-span-2 overflow-hidden flex flex-col min-h-[400px]">
          <div className="p-5 border-b border-white/10 flex justify-between items-center bg-surface/30">
            <h2 className="text-lg font-semibold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-secondary">emoji_events</span>
              Model Leaderboard
            </h2>
            {experiment && (
              <span className={`px-2.5 py-1 rounded-md text-xs font-bold uppercase ${
                experiment.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                experiment.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                'bg-yellow-500/20 text-yellow-400 animate-pulse'
              }`}>
                {experiment.status}
              </span>
            )}
          </div>
          
          <div className="flex-1 overflow-auto">
            {!experiment ? (
              <div className="flex flex-col items-center justify-center h-full p-12 text-on-surface-variant opacity-60">
                <span className="material-symbols-outlined text-5xl mb-3">query_stats</span>
                <p>Configure and start an AutoML run to see the leaderboard.</p>
              </div>
            ) : experiment.trials.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full p-12 text-on-surface-variant">
                {experiment.status === "failed" ? (
                  <div className="text-red-400 text-center">
                    <span className="material-symbols-outlined text-4xl mb-2">error</span>
                    <p>Experiment failed: {experiment.error_message}</p>
                  </div>
                ) : (
                  <div className="text-center animate-pulse">
                     <span className="material-symbols-outlined text-4xl mb-2 text-primary">hourglass_empty</span>
                     <p>Training models... this may take a few minutes.</p>
                  </div>
                )}
              </div>
            ) : (
              <table className="w-full text-left">
                <thead className="bg-surface/50 border-b border-white/10">
                  <tr>
                    <th className="p-3 pl-5 mono text-xs font-medium text-on-surface-variant">RANK</th>
                    <th className="p-3 mono text-xs font-medium text-on-surface-variant">ALGORITHM</th>
                    <th className="p-3 mono text-xs font-medium text-on-surface-variant">PRIMARY METRIC ({experiment.primary_metric.toUpperCase()})</th>
                    <th className="p-3 pr-5 mono text-xs font-medium text-on-surface-variant text-right">ALL METRICS</th>
                  </tr>
                </thead>
                <tbody>
                  {experiment.trials.map((trial, idx) => (
                    <tr key={trial.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="p-3 pl-5 font-bold">
                        {idx === 0 ? (
                          <span className="flex items-center justify-center w-6 h-6 rounded-full bg-yellow-500/20 text-yellow-500 text-xs shadow-[0_0_10px_rgba(234,179,8,0.2)]">1</span>
                        ) : (
                          <span className="text-on-surface-variant pl-2">{idx + 1}</span>
                        )}
                      </td>
                      <td className="p-3">
                        <span className="font-mono text-sm text-primary-container">{trial.algorithm_name}</span>
                        {trial.is_best && <span className="ml-2 badge-primary text-[10px] px-1 py-0 border-primary">BEST</span>}
                      </td>
                      <td className="p-3 font-mono text-sm text-on-surface font-semibold">
                        {trial.primary_metric_score?.toFixed(4) || "N/A"}
                      </td>
                      <td className="p-3 pr-5 text-right flex items-center justify-end gap-3">
                        <div className="flex flex-wrap gap-1 justify-end">
                           {Object.entries(trial.metrics).map(([key, val]) => (
                             key !== experiment.primary_metric && (
                               <span key={key} className="text-[10px] px-1.5 py-0.5 rounded bg-surface/80 border border-white/5 text-on-surface-variant whitespace-nowrap">
                                 {key.toUpperCase()}: {val.toFixed(3)}
                               </span>
                             )
                           ))}
                        </div>
                        <Link href={`/projects/${id}/datasets/${datasetId}/automl/trials/${trial.id}/explain`} className="btn-ghost text-xs px-2 py-1 flex items-center gap-1 text-primary hover:bg-primary/10">
                           <span className="material-symbols-outlined text-[16px]">visibility</span>
                           Explain
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
// export function generateStaticParams() { return [{ id: 'default', datasetId: 'default' }]; }
