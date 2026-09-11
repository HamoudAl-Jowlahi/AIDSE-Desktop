"use client";
/**
 * AIDSE Platform — Datasets Page (V1)
 * Project-scoped dataset browser built on existing backend endpoints:
 * GET /projects then GET /projects/{id}/datasets.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { datasets as datasetsApi, projects as projectsApi, type DatasetResponse, type ProjectOut } from "@/lib/api";

function formatBytes(n: number | undefined): string {
  if (!n) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function DatasetsPage() {
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [datasetRows, setDatasetRows] = useState<DatasetResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingDatasets, setLoadingDatasets] = useState(false);

  useEffect(() => {
    projectsApi
      .list(1, 50)
      .then((d) => {
        setProjectList(d.items);
        if (d.items.length > 0) setSelectedProject(d.items[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const loadDatasets = useCallback((projectId: string) => {
    setLoadingDatasets(true);
    datasetsApi
      .list(projectId)
      .then(setDatasetRows)
      .catch(() => setDatasetRows([]))
      .finally(() => setLoadingDatasets(false));
  }, []);

  useEffect(() => {
    if (selectedProject) loadDatasets(selectedProject);
  }, [selectedProject, loadDatasets]);

  const selected = projectList.find((p) => p.id === selectedProject);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
            Datasets
          </h1>
          <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            Upload CSV/XLSX files and manage versions. Every upload is profiled automatically.
          </p>
        </div>
        {selected && (
          <Link href={`/projects/${selected.id}`} className="btn-ghost text-sm">
            Open project
          </Link>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
        </div>
      ) : projectList.length === 0 ? (
        <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
          <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)" }}>folder_off</span>
          <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>No projects yet</div>
          <p className="text-sm max-w-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            Create a project first — datasets live inside projects.
          </p>
          <Link href="/projects" className="btn-primary mt-2 text-sm">Go to Projects</Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Project selector */}
          <div className="lg:col-span-1">
            <div className="glass-panel rounded-xl overflow-hidden">
              <div className="p-4 text-xs mono uppercase tracking-wider" style={{ borderBottom: "1px solid rgba(255,255,255,0.1)", color: "var(--color-on-surface-variant)" }}>
                Projects ({projectList.length})
              </div>
              <ul>
                {projectList.map((p) => (
                  <li key={p.id}>
                    <button
                      onClick={() => setSelectedProject(p.id)}
                      className="w-full text-left px-4 py-3 text-sm transition-all duration-200"
                      style={
                        p.id === selectedProject
                          ? { background: "rgba(0,242,254,0.08)", color: "var(--color-primary)", borderLeft: "3px solid var(--color-primary-container)" }
                          : { color: "var(--color-on-surface-variant)", borderLeft: "3px solid transparent" }
                      }
                      onMouseEnter={(e) => {
                        if (p.id !== selectedProject) e.currentTarget.style.background = "rgba(255,255,255,0.05)";
                      }}
                      onMouseLeave={(e) => {
                        if (p.id !== selectedProject) e.currentTarget.style.background = "transparent";
                      }}
                    >
                      <span className="block truncate font-medium">{p.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Dataset list */}
          <div className="lg:col-span-3">
            <div className="glass-panel rounded-xl overflow-hidden min-h-[300px]">
              <div className="p-5 flex justify-between items-center" style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
                <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>
                  {selected?.name ?? "Datasets"}
                </h2>
                <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                  {datasetRows.length} {datasetRows.length === 1 ? "dataset" : "datasets"}
                </span>
              </div>

              {loadingDatasets ? (
                <div className="flex justify-center py-16">
                  <div className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
                </div>
              ) : datasetRows.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
                  <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)", fontSize: "2.5rem" }}>
                    database
                  </span>
                  <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>No datasets in this project</div>
                  <p className="text-sm max-w-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                    Upload a CSV or XLSX file to get an automatic quality profile.
                  </p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="mono text-xs uppercase" style={{ color: "var(--color-on-surface-variant)", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                      <th className="text-left px-5 py-3 font-medium">Name</th>
                      <th className="text-left px-5 py-3 font-medium">Format</th>
                      <th className="text-left px-5 py-3 font-medium">Versions</th>
                      <th className="text-left px-5 py-3 font-medium">Latest profile</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datasetRows.map((d) => {
                      const latest = d.versions?.[d.versions.length - 1];
                      const profiled = Boolean(latest?.profile_data);
                      return (
                        <tr key={d.id} className="transition-colors" style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                          <td className="px-5 py-3">
                            <Link
                              href={`/projects/${d.project_id}/datasets/${d.id}`}
                              className="font-medium transition-colors"
                              style={{ color: "var(--color-on-surface)" }}
                              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--color-primary)")}
                              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--color-on-surface)")}
                            >
                              {d.name}
                            </Link>
                          </td>
                          <td className="px-5 py-3 mono text-xs uppercase" style={{ color: "var(--color-on-surface-variant)" }}>{d.format}</td>
                          <td className="px-5 py-3 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>{d.versions?.length ?? 0}</td>
                          <td className="px-5 py-3">
                            {profiled ? (
                              <span className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--color-primary)" }}>
                                <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>check_circle</span>
                                Ready
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                                <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>pending</span>
                                Not profiled
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            {/* Storage note */}
            <p className="mt-3 flex items-center gap-1.5 text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
              <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>info</span>
              Supported formats: CSV, XLSX. Original uploads are never mutated — transformations create new versions.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
