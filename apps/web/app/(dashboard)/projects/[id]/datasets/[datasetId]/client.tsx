"use client";
import { useEffect, useState, FormEvent } from "react";
import { createPortal } from "react-dom";
import { useParams, usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { datasets as datasetsApi, type DatasetResponse, type DatasetVersionResponse } from "@/lib/api";
import WorkspaceTabs from "@/components/layout/WorkspaceTabs";

// --- Upload Modal ---
function UploadFileModal({
  projectId,
  datasetId,
  onClose,
  onUploaded,
}: {
  projectId: string;
  datasetId: string;
  onClose: () => void;
  onUploaded: (v: DatasetVersionResponse) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setLoading(true);
    try {
      const version = await datasetsApi.uploadFile(projectId, datasetId, file);
      onUploaded(version);
    } catch (err: any) {
      setError(err.message || "Failed to upload file");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] p-4 bg-black/60 backdrop-blur-sm overflow-y-auto" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="glass-panel rounded-2xl p-8 w-full max-w-md mx-auto mt-10 mb-10 animate-fade-in relative">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold">Upload Dataset</h2>
          <button onClick={onClose} className="text-on-surface-variant hover:text-white"><span className="material-symbols-outlined">close</span></button>
        </div>
        {error && <div className="mb-4 p-3 rounded-lg text-sm bg-red-900/20 border border-red-500/30 text-red-400">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5 mono text-on-surface-variant">SELECT CSV OR EXCEL FILE</label>
            <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] || null)} required className="w-full text-sm file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 cursor-pointer" />
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={loading || !file} className="btn-primary flex-1 opacity-90 hover:opacity-100 disabled:opacity-50">
              {loading ? "Uploading..." : "Upload File"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Profile Modal ---
function ProfileViewModal({
  profile,
  onClose,
}: {
  profile: Record<string, any>;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[100] p-4 bg-black/60 backdrop-blur-sm overflow-y-auto" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="glass-panel rounded-2xl p-8 w-full max-w-4xl mx-auto mt-10 mb-10 animate-fade-in relative">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-on-surface">Data Intelligence Report</h2>
          <button onClick={onClose} className="text-on-surface-variant hover:text-white"><span className="material-symbols-outlined">close</span></button>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="glass-card p-4 rounded-xl text-center">
            <div className="text-3xl font-bold text-primary mb-1">{profile.num_rows?.toLocaleString() ?? 0}</div>
            <div className="text-xs uppercase mono text-on-surface-variant">Total Rows</div>
          </div>
          <div className="glass-card p-4 rounded-xl text-center">
            <div className="text-3xl font-bold text-secondary mb-1">{profile.num_columns?.toLocaleString() ?? 0}</div>
            <div className="text-xs uppercase mono text-on-surface-variant">Total Columns</div>
          </div>
          <div className="glass-card p-4 rounded-xl text-center">
            <div className="text-3xl font-bold text-error mb-1">{profile.duplicate_rows?.toLocaleString() ?? 0}</div>
            <div className="text-xs uppercase mono text-on-surface-variant">Duplicate Rows</div>
          </div>
        </div>

        {profile.target_leakage?.length > 0 && (
          <div className="mb-6 p-4 rounded-xl bg-red-900/20 border border-red-500/30">
            <h3 className="font-bold text-red-400 flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined">warning</span> Target Leakage Detected
            </h3>
            <ul className="list-disc pl-5 text-sm text-red-300 space-y-1">
              {profile.target_leakage.map((l: any, i: number) => (
                <li key={i}>Column <b>{l.column}</b> has a {l.correlation} correlation with the target.</li>
              ))}
            </ul>
          </div>
        )}

        {profile.imbalance?.warning && (
          <div className="mb-6 p-4 rounded-xl bg-yellow-900/20 border border-yellow-500/30">
             <h3 className="font-bold text-yellow-400 flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined">balance</span> Class Imbalance Detected
            </h3>
            <p className="text-sm text-yellow-300">{profile.imbalance.warning}</p>
          </div>
        )}

        <h3 className="text-lg font-semibold mb-3 border-b border-white/10 pb-2">Schema & Column Stats</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-surface/30 text-on-surface-variant mono text-xs">
                <th className="p-3 font-medium">COLUMN</th>
                <th className="p-3 font-medium">TYPE</th>
                <th className="p-3 font-medium">MISSING</th>
                <th className="p-3 font-medium">MIN/MAX/MEAN</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(profile.columns || {}).map(([col, stats]: [string, any]) => (
                <tr key={col} className="border-b border-white/5 hover:bg-white/5">
                  <td className="p-3 font-medium text-primary-container">{col}</td>
                  <td className="p-3 font-mono text-xs text-on-surface-variant">{stats.type}</td>
                  <td className="p-3">
                    <span className={stats.null_count > 0 ? "text-yellow-400" : "text-green-400"}>
                      {stats.null_pct}% ({stats.null_count})
                    </span>
                  </td>
                  <td className="p-3 text-xs text-on-surface-variant">
                    {stats.min !== undefined ? (
                      <div className="space-y-1">
                        <div>
                          <span className="opacity-50">Min:</span> {Number(stats.min).toFixed(2)} 
                          <span className="mx-2">|</span> <span className="opacity-50">Median:</span> {stats.median !== undefined ? Number(stats.median).toFixed(2) : '-'}
                          <span className="mx-2">|</span> <span className="opacity-50">Mean:</span> {Number(stats.mean).toFixed(2)}
                          <span className="mx-2">|</span> <span className="opacity-50">Max:</span> {Number(stats.max).toFixed(2)}
                        </div>
                        {stats.outliers_count > 0 && (
                          <div className="text-error font-medium">
                            <span className="material-symbols-outlined text-[12px] mr-1 align-middle">warning</span>
                            {stats.outliers_count.toLocaleString()} outliers detected
                          </div>
                        )}
                      </div>
                    ) : (
                      <span>{stats.unique_count} unique values</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// --- Transform Modal ---
function TransformModal({
  projectId,
  datasetId,
  versionId,
  profile,
  onClose,
  onTransformed,
}: {
  projectId: string;
  datasetId: string;
  versionId: string;
  profile: any;
  onClose: () => void;
  onTransformed: (v: DatasetVersionResponse) => void;
}) {
  const [action, setAction] = useState("drop_column");
  const [column, setColumn] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Generate recommendations
  type RecOption = { label: string; desc: string; action: string; col: string; isRecommended?: boolean };
  const recommendations: { problem: string; type: "warning" | "error"; col: string; options: RecOption[] }[] = [];
  
  if (profile) {
    if (profile.duplicate_rows && profile.duplicate_rows > 0) {
      recommendations.push({
        problem: `Found ${profile.duplicate_rows} duplicate rows across the dataset.`,
        type: "error",
        col: "",
        options: [
          {
            label: "Drop Duplicates",
            desc: "Best and standard method to ensure data points are unique. Recommended.",
            action: "drop_duplicates",
            col: "",
            isRecommended: true
          }
        ]
      });
    }
    if (profile.columns) {
      for (const [colName, stats] of Object.entries<any>(profile.columns)) {
        if (stats.null_count && stats.null_count > 0) {
          const isHighMissing = stats.null_pct > 50;
          const hasOutliers = stats.outliers_count > 0;
          
          recommendations.push({
            problem: `Column '${colName}' has ${stats.null_pct}% missing values (${stats.null_count} rows).`,
            type: isHighMissing ? "error" : "warning",
            col: colName,
            options: [
              ...(isHighMissing ? [{
                label: "Drop Column",
                desc: "Recommended because more than 50% data is missing. Imputing could bias the model.",
                action: "drop_column",
                col: colName,
                isRecommended: true
              }] : []),
              {
                label: "Fill with Median",
                desc: hasOutliers ? "Recommended because the column contains outliers, making the Mean skewed." : "Safe to use, but Mean is typically better when there are no outliers.",
                action: "fillna_median",
                col: colName,
                isRecommended: !isHighMissing && hasOutliers
              },
              {
                label: "Fill with Mean",
                desc: hasOutliers ? "Not recommended due to outliers skewing the average." : "Recommended for normal distributions without outliers.",
                action: "fillna_mean",
                col: colName,
                isRecommended: !isHighMissing && !hasOutliers
              },
              {
                label: "Drop Rows with Missing",
                desc: "Good if the dataset is massive and dropping a few rows won't impact training size.",
                action: "drop_na",
                col: colName
              }
            ]
          });
        }
        
        if (stats.outliers_count && stats.outliers_count > 0) {
          recommendations.push({
            problem: `Column '${colName}' has ${stats.outliers_count} extreme outliers.`,
            type: "warning",
            col: colName,
            options: [
              {
                label: "Cap Outliers (IQR)",
                desc: "Recommended. Limits extreme values without deleting data rows, preserving dataset size.",
                action: "cap_outliers",
                col: colName,
                isRecommended: true
              },
              {
                label: "Drop Outlier Rows",
                desc: "Removes extreme data completely. Useful if you believe the outliers are measurement errors.",
                action: "drop_outliers",
                col: colName
              }
            ]
          });
        }
      }
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!column && action !== "drop_duplicates") return;
    setError(null);
    setLoading(true);
    try {
      const version = await datasetsApi.transform(projectId, datasetId, versionId, {
        steps: [{ action, column }]
      });
      onTransformed(version);
    } catch (err: any) {
      setError(err.message || "Failed to apply transformation");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] p-4 bg-black/60 backdrop-blur-sm overflow-y-auto" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="glass-panel rounded-2xl p-8 w-full max-w-2xl mx-auto mt-10 mb-10 animate-fade-in relative flex flex-col md:flex-row gap-8">
        
        {/* Left: Form */}
        <div className="flex-1">
          <div className="flex justify-between items-center mb-6 md:hidden">
            <h2 className="text-xl font-bold">Apply Transformation</h2>
            <button onClick={onClose} className="text-on-surface-variant hover:text-white"><span className="material-symbols-outlined">close</span></button>
          </div>
          <h2 className="text-xl font-bold mb-4 hidden md:block">Apply Transformation</h2>
          <p className="text-sm text-on-surface-variant mb-4">
            This will apply a cleaning operation and generate a completely new dataset version automatically.
          </p>
          {error && <div className="mb-4 p-3 rounded-lg text-sm bg-red-900/20 border border-red-500/30 text-red-400">{error}</div>}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium mb-1.5 mono text-on-surface-variant">ACTION</label>
              <select value={action} onChange={(e) => setAction(e.target.value)} className="input-field cursor-pointer">
                <option value="drop_column">Drop Column</option>
                <option value="fillna_mean">Fill Missing (Mean)</option>
                <option value="fillna_median">Fill Missing (Median)</option>
                <option value="fillna_mode">Fill Missing (Mode)</option>
                <option value="drop_na">Drop Rows with Missing</option>
                <option value="cap_outliers">Cap Outliers (IQR Method)</option>
                <option value="drop_outliers">Drop Outlier Rows (IQR)</option>
                <option value="drop_duplicates">Drop Duplicate Rows</option>
              </select>
            </div>
            {action !== "drop_duplicates" && (
              <div>
                <label className="block text-xs font-medium mb-1.5 mono text-on-surface-variant">COLUMN NAME</label>
                <input type="text" value={column} onChange={(e) => setColumn(e.target.value)} placeholder="e.g., age" required={action !== "drop_duplicates"} className="input-field" />
              </div>
            )}
            <div className="flex gap-3 pt-4">
              <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
              <button type="submit" disabled={loading || (!column && action !== "drop_duplicates")} className="btn-primary flex-1">
                {loading ? "Applying..." : "Apply & Create"}
              </button>
            </div>
          </form>
        </div>

        {/* Right: Smart Recommendations */}
        <div className="flex-1 border-t md:border-t-0 md:border-l border-white/10 pt-6 md:pt-0 md:pl-6 max-h-[60vh] overflow-y-auto pr-2">
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-primary">auto_awesome</span>
            <h3 className="font-bold">Smart Recommendations</h3>
          </div>
          
          {recommendations.filter(r => !column || r.col.toLowerCase() === column.toLowerCase() || r.col === "").length === 0 ? (
            <div className="text-sm text-on-surface-variant italic p-4 bg-white/5 rounded-lg border border-white/10">
              {column ? `No specific issues detected for column '${column}'.` : "Your dataset looks clean! No immediate issues detected."}
            </div>
          ) : (
            <div className="space-y-4">
              {recommendations
                .filter(r => !column || r.col.toLowerCase() === column.toLowerCase() || r.col === "")
                .map((rec, i) => (
                <div key={i} className={`p-4 rounded-xl border flex flex-col gap-3 ${rec.type === 'error' ? 'bg-red-500/5 border-red-500/20' : 'bg-yellow-500/5 border-yellow-500/20'}`}>
                  <h4 className="font-semibold text-on-surface flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px]">{rec.type === 'error' ? 'error' : 'warning'}</span>
                    {rec.problem}
                  </h4>
                  <div className="space-y-2 mt-1">
                    {rec.options.map((opt, j) => (
                      <div key={j} className={`p-3 rounded-lg border flex flex-col gap-2 ${opt.isRecommended ? 'bg-primary/10 border-primary/30' : 'bg-surface border-white/5'}`}>
                        <div className="flex justify-between items-start gap-2">
                          <div>
                            <div className="font-medium text-sm flex items-center gap-2 text-on-surface">
                              {opt.label}
                              {opt.isRecommended && <span className="badge-primary text-[10px] px-1.5 py-0.5" style={{ color: "var(--color-primary)" }}>Recommended</span>}
                            </div>
                            <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">{opt.desc}</p>
                          </div>
                          <button 
                            type="button" 
                            className="text-xs shrink-0 px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded font-medium transition-colors"
                            onClick={() => { setAction(opt.action); setColumn(opt.col); }}
                          >
                            Select
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Desktop Close button */}
        <button onClick={onClose} className="absolute top-4 right-4 text-on-surface-variant hover:text-white hidden md:block">
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>
    </div>
  );
}

// --- Main Page ---
export default function DatasetDetailPage() {
  const params = useParams<{ id: string; datasetId: string }>();
  const pathname = usePathname();
  const pathParts = pathname.split("/").filter(Boolean);
  const id = params.id === "default" ? pathParts[1] : params.id;
  const datasetId = params.datasetId === "default" ? pathParts[3] : params.datasetId;
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);

  async function handleDeleteDataset() {
    if (!id || !datasetId || deleting) return;
    if (!confirm(`Delete "${dataset?.name ?? "this dataset"}" and ALL its versions? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await datasetsApi.delete(id, datasetId);
      router.push(`/projects/${id}`);
    } catch (e: any) {
      alert(e.message ?? "Delete failed");
      setDeleting(false);
    }
  }
  const [dataset, setDataset] = useState<DatasetResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [showUpload, setShowUpload] = useState(false);
  const [profileData, setProfileData] = useState<Record<string, any> | null>(null);
  const [transformVersionId, setTransformVersionId] = useState<string | null>(null);

  useEffect(() => {
    if (!id || !datasetId) return;
    datasetsApi.get(id, datasetId)
      .then(setDataset)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, datasetId]);

  if (loading) return <div className="flex justify-center py-20"><div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin border-primary-container" /></div>;
  if (error || !dataset) return <div className="glass-panel p-10 text-center"><p className="text-error">{error ?? "Dataset not found"}</p><Link href={`/projects/${id}`} className="btn-primary mt-4 inline-flex">Back to Project</Link></div>;

  const sortedVersions = [...dataset.versions].reverse(); // Show newest first

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-2 text-sm text-on-surface-variant">
        <Link href="/projects" className="hover:text-primary-container transition-colors">Projects</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <Link href={`/projects/${id}`} className="hover:text-primary-container transition-colors">Project View</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <span className="text-on-surface">{dataset.name}</span>
      </div>

      <WorkspaceTabs active="overview" projectId={id} datasetId={datasetId} />

      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold mb-1 text-on-surface">{dataset.name}</h1>
          <div className="flex items-center gap-3">
            <span className="badge-neutral uppercase text-xs">{dataset.format}</span>
            <span className="text-sm text-on-surface-variant">{dataset.versions.length} versions</span>
          </div>
          {dataset.description && <p className="mt-2 text-sm text-on-surface-variant max-w-xl">{dataset.description}</p>}
        </div>
        <button onClick={() => setShowUpload(true)} className="btn-primary">
          <span className="material-symbols-outlined">upload_file</span>
          Upload File
        </button>
        <button
          onClick={handleDeleteDataset}
          disabled={deleting}
          className="btn-ghost text-xs"
          style={{ color: "var(--color-error)", borderColor: "rgba(255,107,107,0.35)" }}
          title="Delete this dataset and all versions"
        >
          <span className="material-symbols-outlined text-[18px]">delete_forever</span>
          {deleting ? "Deleting…" : "Delete"}
        </button>
      </div>

      <div className="glass-panel rounded-xl overflow-hidden mt-8">
        <div className="p-5 border-b border-white/10 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-on-surface">Versions & Files</h2>
        </div>
        
        {sortedVersions.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center gap-3 text-on-surface-variant">
            <div className="w-16 h-16 rounded-full bg-surface flex items-center justify-center">
               <span className="material-symbols-outlined text-3xl">upload</span>
            </div>
            <p>No files uploaded yet. Click Upload File to add your CSV data.</p>
          </div>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="bg-surface/30 border-b border-white/5">
                <th className="p-4 mono text-xs text-on-surface-variant">VERSION TAG</th>
                <th className="p-4 mono text-xs text-on-surface-variant">STATUS / PROFILE</th>
                <th className="p-4 mono text-xs text-on-surface-variant text-right">ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {sortedVersions.map(v => (
                <tr key={v.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                  <td className="p-4 font-medium font-mono text-primary-container">{v.version_tag}</td>
                  <td className="p-4">
                    {v.profile_data ? (
                      <button onClick={() => setProfileData(v.profile_data)} className="flex items-center gap-2 text-sm text-secondary hover:text-white transition-colors bg-secondary/10 px-3 py-1.5 rounded-full border border-secondary/20 hover:border-secondary/50">
                        <span className="material-symbols-outlined text-[18px]">bar_chart</span>
                        View Intelligence Report
                      </button>
                    ) : (
                      <span className="text-sm text-on-surface-variant italic">No profile data</span>
                    )}
                  </td>
                  <td className="p-4 flex justify-end gap-2">
                    <button onClick={() => datasetsApi.downloadVersion(id!, datasetId!, v.id, `${dataset.name}_${v.version_tag}.csv`).catch(err => alert(err.message))} className="btn-ghost text-xs px-3 py-1" title="Download Dataset">
                      <span className="material-symbols-outlined text-[18px]">download</span>
                      Download
                    </button>
                    <button onClick={() => setTransformVersionId(v.id)} className="btn-ghost text-xs px-3 py-1" title="Clean Dataset">
                      <span className="material-symbols-outlined text-[18px]">auto_fix</span>
                      Clean
                    </button>
                    <Link href={`/projects/${id}/datasets/${datasetId}/automl`} className="btn-primary text-xs px-3 py-1" title="Train Model">
                      <span className="material-symbols-outlined text-[18px]">model_training</span>
                      Train Model
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {typeof document !== "undefined" && createPortal(
        <>
          {showUpload && <UploadFileModal projectId={id!} datasetId={datasetId!} onClose={() => setShowUpload(false)} onUploaded={(v) => { setDataset(prev => prev ? {...prev, versions: [...prev.versions, v]} : prev); setShowUpload(false); }} />}
          {profileData && <ProfileViewModal profile={profileData} onClose={() => setProfileData(null)} />}
          {transformVersionId && <TransformModal projectId={id!} datasetId={datasetId!} versionId={transformVersionId} profile={dataset?.versions.find(v => v.id === transformVersionId)?.profile_data} onClose={() => setTransformVersionId(null)} onTransformed={(v) => { setDataset(prev => prev ? {...prev, versions: [...prev.versions, v]} : prev); setTransformVersionId(null); }} />}
        </>,
        document.body
      )}
    </div>
  );
}
// export function generateStaticParams() { return [{ id: 'default', datasetId: 'default' }]; }
