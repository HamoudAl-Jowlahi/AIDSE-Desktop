"use client";
/**
 * AIDSE Platform — Golden Datasets Page (V1)
 * Lists golden datasets across the user's projects using existing endpoints:
 * GET /projects then GET /projects/{id}/datasets/golden-datasets.
 * Create/manage flows live inside each project (backend CRUD already exists).
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  datasets as datasetsApi,
  projects as projectsApi,
  type GoldenDatasetResponse,
  type ProjectOut,
} from "@/lib/api";

interface Row {
  project: ProjectOut;
  golden: GoldenDatasetResponse;
}

export default function GoldenDatasetsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { items } = await projectsApi.list(1, 50);
        const results = await Promise.all(
          items.map(async (project) => {
            try {
              const goldens = await datasetsApi.listGolden(project.id);
              return goldens.map((golden) => ({ project, golden }));
            } catch {
              return [] as Row[];
            }
          })
        );
        if (!cancelled) setRows(results.flat());
      } catch {
        if (!cancelled) setRows([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
            Golden Datasets
          </h1>
          <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            Curated test cases with expected outputs. Baselines for AI evaluation runs and regression detection.
          </p>
        </div>
        <Link href="/projects" className="btn-primary text-sm">New Golden Dataset</Link>
      </div>

      <div className="glass-panel rounded-xl overflow-hidden min-h-[300px]">
        {loading ? (
          <div className="flex justify-center py-20">
            <div
              className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: "var(--color-primary-container)" }}
            />
          </div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <span
              className="material-symbols-outlined text-4xl"
              style={{ color: "var(--color-outline)", fontSize: "2.5rem" }}
            >
              workspace_premium
            </span>
            <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>
              No golden datasets yet
            </div>
            <p className="text-sm max-w-md" style={{ color: "var(--color-on-surface-variant)" }}>
              A golden dataset holds input cases with expected outputs. Run evaluations against it, mark a run as baseline, and catch regressions before they ship.
            </p>
            <Link href="/projects" className="btn-primary mt-2 text-sm">
              Open a project to create one
            </Link>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr
                className="mono text-xs uppercase"
                style={{ color: "var(--color-on-surface-variant)", borderBottom: "1px solid rgba(255,255,255,0.08)" }}
              >
                <th className="text-left px-5 py-3 font-medium">Name</th>
                <th className="text-left px-5 py-3 font-medium">Project</th>
                <th className="text-left px-5 py-3 font-medium">Version</th>
                <th className="text-left px-5 py-3 font-medium">Cases</th>
                <th className="text-left px-5 py-3 font-medium">Baseline</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ project, golden }) => (
                <tr key={golden.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <td className="px-5 py-3 font-medium" style={{ color: "var(--color-on-surface)" }}>
                    <span className="inline-flex items-center gap-2">
                      <span className="material-symbols-outlined text-lg" style={{ color: "var(--color-tertiary-container)" }}>
                        workspace_premium
                      </span>
                      {golden.name}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <Link
                      href={`/projects/${project.id}`}
                      className="transition-colors"
                      style={{ color: "var(--color-on-surface-variant)" }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = "var(--color-primary)")}
                      onMouseLeave={(e) => (e.currentTarget.style.color = "var(--color-on-surface-variant)")}
                    >
                      {project.name}
                    </Link>
                  </td>
                  <td className="px-5 py-3 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                    v{golden.version}
                  </td>
                  <td className="px-5 py-3 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                    {golden.cases?.length ?? 0}
                  </td>
                  <td className="px-5 py-3">
                    {golden.baseline_run_id ? (
                      <span className="mono text-xs" style={{ color: "var(--color-primary)" }}>
                        {golden.baseline_run_id.slice(0, 8)}…
                      </span>
                    ) : (
                      <span className="text-xs" style={{ color: "var(--color-on-surface-variant)" }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
