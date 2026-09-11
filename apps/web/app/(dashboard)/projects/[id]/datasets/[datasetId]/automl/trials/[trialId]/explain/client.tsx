"use client";

import { useEffect, useState, FormEvent } from "react";
import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import { explainability as explainApi, type ShapGlobalResponse, type ShapLocalResponse } from "@/lib/api";

export default function ExplainabilityPage() {
  const params = useParams<{ id: string; datasetId: string; trialId: string }>();
  const pathname = usePathname();
  const pathParts = pathname.split("/").filter(Boolean);
  const id = params.id === "default" ? pathParts[1] : params.id;
  const datasetId = params.datasetId === "default" ? pathParts[3] : params.datasetId;
  const trialId = params.trialId === "default" ? pathParts[6] : params.trialId;
  
  const [globalData, setGlobalData] = useState<ShapGlobalResponse | null>(null);
  const [globalLoading, setGlobalLoading] = useState(true);
  const [globalError, setGlobalError] = useState<string | null>(null);
  
  const [localData, setLocalData] = useState<ShapLocalResponse | null>(null);
  const [localLoading, setLocalLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [rowIndex, setRowIndex] = useState(0);

  useEffect(() => {
    explainApi.getGlobalExplanation(id!, trialId!)
      .then(setGlobalData)
      .catch((e) => setGlobalError(e.message))
      .finally(() => setGlobalLoading(false));
  }, [id, trialId]);

  const handleFetchLocal = async (e: FormEvent) => {
    e.preventDefault();
    setLocalLoading(true);
    setLocalError(null);
    try {
      const data = await explainApi.getLocalExplanation(id!, trialId!, rowIndex);
      setLocalData(data);
    } catch (err: any) {
      setLocalError(err.message || "Failed to fetch local explanation");
    } finally {
      setLocalLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in pb-20">
      <div className="flex items-center gap-2 text-sm text-on-surface-variant mb-6">
        <Link href={`/projects/${id}`} className="hover:text-primary-container transition-colors">Project</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <Link href={`/projects/${id}/datasets/${datasetId}`} className="hover:text-primary-container transition-colors">Dataset</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <Link href={`/projects/${id}/datasets/${datasetId}/automl`} className="hover:text-primary-container transition-colors">AutoML</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <span className="text-on-surface">Explain Model</span>
      </div>

      <div>
        <h1 className="text-3xl font-bold mb-1 text-on-surface flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-3xl">psychology</span>
          Model Interpretability (SHAP)
        </h1>
        <p className="text-sm text-on-surface-variant max-w-xl mt-2">
          Understand how your machine learning model makes decisions globally across all data, and locally for individual predictions.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
        
        {/* Global Explanation */}
        <div className="glass-panel p-6 rounded-xl flex flex-col">
          <h2 className="text-xl font-bold text-on-surface mb-2 flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary">public</span>
            Global Feature Importance
          </h2>
          <p className="text-sm text-on-surface-variant mb-6">
            Shows the overall impact of each feature on the model&apos;s predictions.
          </p>

          {globalLoading ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 opacity-50">
               <div className="w-8 h-8 rounded-full border-2 border-t-transparent border-primary animate-spin mb-4"></div>
               <p>Computing Shapley values across the dataset... this may take a moment.</p>
            </div>
          ) : globalError ? (
            <div className="p-4 bg-red-900/20 border border-red-500/30 text-red-400 rounded-lg">
              {globalError}
            </div>
          ) : globalData ? (
            <div className="space-y-6">
              <div className="bg-surface/50 rounded-xl p-4 flex justify-center items-center overflow-hidden border border-white/5">
                <img 
                  src={`data:image/png;base64,${globalData.summary_plot_base64}`} 
                  alt="SHAP Summary Plot" 
                  className="max-w-full h-auto rounded-lg"
                  style={{ filter: "invert(0.9) hue-rotate(180deg)" }}
                />
              </div>
              
              <div className="p-4 bg-primary/10 border border-primary/20 rounded-xl relative overflow-hidden">
                 <div className="absolute top-0 right-0 p-2 opacity-20">
                   <span className="material-symbols-outlined text-6xl">smart_toy</span>
                 </div>
                 <h3 className="text-sm font-bold text-primary mb-2">AI Insight</h3>
                 <p className="text-sm text-on-surface-variant leading-relaxed relative z-10">
                   {globalData.insight}
                 </p>
              </div>
            </div>
          ) : null}
        </div>

        {/* Local Explanation */}
        <div className="glass-panel p-6 rounded-xl flex flex-col">
          <h2 className="text-xl font-bold text-on-surface mb-2 flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary">person_search</span>
            Local Prediction Explanation
          </h2>
          <p className="text-sm text-on-surface-variant mb-6">
            Explain why the model made a specific prediction for a single row of data.
          </p>

          <form onSubmit={handleFetchLocal} className="flex gap-3 mb-6 items-end">
            <div className="flex-1">
              <label className="block text-xs font-medium mb-1.5 mono text-on-surface-variant">ROW INDEX (0 to N)</label>
              <input 
                type="number" 
                min={0}
                value={rowIndex} 
                onChange={(e) => setRowIndex(parseInt(e.target.value))} 
                className="input-field w-full"
                required
              />
            </div>
            <button type="submit" disabled={localLoading} className="btn-primary shrink-0">
              {localLoading ? "Computing..." : "Explain Row"}
            </button>
          </form>

          {localError && (
             <div className="mb-6 p-4 bg-red-900/20 border border-red-500/30 text-red-400 rounded-lg">
               {localError}
             </div>
          )}

          {!localData && !localLoading && !localError && (
            <div className="flex-1 flex flex-col items-center justify-center p-12 opacity-50 border border-dashed border-white/20 rounded-xl">
               <span className="material-symbols-outlined text-5xl mb-3">manage_search</span>
               <p className="text-center">Select a row index above to view the forces pushing the prediction higher or lower.</p>
            </div>
          )}

          {localLoading && (
            <div className="flex-1 flex flex-col items-center justify-center p-12 opacity-50 border border-dashed border-white/20 rounded-xl">
               <div className="w-8 h-8 rounded-full border-2 border-t-transparent border-primary animate-spin mb-4"></div>
               <p>Computing local Shapley values...</p>
            </div>
          )}

          {localData && !localLoading && (
            <div className="space-y-6 animate-fade-in">
              <div className="flex items-center gap-4 p-4 bg-surface rounded-xl border border-white/5">
                 <div className="flex-1">
                   <div className="text-xs text-on-surface-variant uppercase tracking-wider mb-1">Model Prediction</div>
                   <div className="text-2xl font-mono text-primary font-bold">{localData.prediction.toFixed(4)}</div>
                 </div>
                 <div className="w-px h-10 bg-white/10"></div>
                 <div className="flex-1">
                   <div className="text-xs text-on-surface-variant uppercase tracking-wider mb-1">Base Expected Value</div>
                   <div className="text-xl font-mono text-on-surface-variant">{localData.base_value.toFixed(4)}</div>
                 </div>
              </div>

              <div className="bg-surface/50 rounded-xl p-4 flex justify-center items-center overflow-hidden border border-white/5">
                <img 
                  src={`data:image/png;base64,${localData.force_plot_base64}`} 
                  alt="SHAP Local Waterfall Plot" 
                  className="max-w-full h-auto rounded-lg"
                  style={{ filter: "invert(0.9) hue-rotate(180deg)" }}
                />
              </div>

              <div className="p-4 bg-surface rounded-xl border border-white/5 overflow-x-auto">
                 <h3 className="text-xs font-bold text-on-surface-variant uppercase tracking-wider mb-3">Raw Input Values</h3>
                 <table className="w-full text-left text-sm">
                   <tbody>
                     {Object.entries(localData.row_values).map(([col, val]) => (
                       <tr key={col} className="border-b border-white/5 last:border-0 hover:bg-white/5">
                         <td className="py-2 px-3 text-on-surface-variant font-medium">{col}</td>
                         <td className="py-2 px-3 font-mono text-primary-container">{val}</td>
                       </tr>
                     ))}
                   </tbody>
                 </table>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
// export function generateStaticParams() { return [{ id: 'default', datasetId: 'default', trialId: 'default' }]; }
