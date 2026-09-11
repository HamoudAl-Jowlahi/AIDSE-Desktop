"use client";
/**
 * AIDSE Platform — Dashboard Page
 * Glass design matching the Stitch "Project Overview Dashboard".
 *
 * V1 summary scope: datasets, data-quality issues, model runs,
 * evaluation runs and regression status.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import {
  datasets as datasetsApi,
  projects as projectsApi,
  type DatasetResponse,
  type ProjectOut,
} from "@/lib/api";

// ── KPI Card ──────────────────────────────────────────────────────────────
function KpiCard({
  label,
  value,
  delta,
  deltaPositive,
  icon,
  iconColor,
  index,
}: {
  label: string;
  value: string | number;
  delta?: string;
  deltaPositive?: boolean;
  icon: string;
  iconColor: string;
  index: number;
}) {
  return (
    <div
      className={`glass-card rounded-xl p-5 relative overflow-hidden group animate-fade-in delay-${index + 1}`}
      style={{ cursor: "default" }}
    >
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{
          background: `linear-gradient(135deg, ${iconColor}08 0%, transparent 100%)`,
        }}
      />
      <div className="flex justify-between items-start mb-4">
        <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
          {label}
        </span>
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center"
          style={{
            background: `${iconColor}1a`,
            border: `1px solid ${iconColor}33`,
          }}
        >
          <span className="material-symbols-outlined" style={{ color: iconColor, fontSize: "1rem" }}>
            {icon}
          </span>
        </div>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-bold" style={{ color: "var(--color-on-surface)" }}>
          {value}
        </span>
        {delta && (
          <span
            className="mono text-xs flex items-center gap-0.5"
            style={{ color: deltaPositive ? "var(--color-primary)" : "var(--color-error)" }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>
              {deltaPositive ? "arrow_upward" : "arrow_downward"}
            </span>
            {delta}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Empty State ───────────────────────────────────────────────────────────
function EmptyState({
  icon,
  title,
  description,
  action,
  actionHref,
}: {
  icon: string;
  title: string;
  description: string;
  action?: string;
  actionHref?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3 text-center">
      <span
        className="material-symbols-outlined text-4xl"
        style={{ color: "var(--color-outline)", fontSize: "2.5rem" }}
      >
        {icon}
      </span>
      <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>
        {title}
      </div>
      <p className="text-sm max-w-xs" style={{ color: "var(--color-on-surface-variant)" }}>
        {description}
      </p>
      {action && actionHref && (
        <Link href={actionHref} className="btn-primary mt-2 text-sm">
          {action}
        </Link>
      )}
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { user } = useAuth();
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [activeProject, setActiveProject] = useState<ProjectOut | null>(null);
  const [projectDatasets, setProjectDatasets] = useState<DatasetResponse[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);

  useEffect(() => {
    projectsApi
      .list(1, 50)
      .then((d) => {
        setProjectList(d.items);
        if (d.items.length > 0) setActiveProject(d.items[0]);
      })
      .catch(() => {})
      .finally(() => setLoadingProjects(false));
  }, []);

  // Load datasets of the active project for the summary KPI + recent analyses
  useEffect(() => {
    if (!activeProject) return;
    setProjectDatasets([]);
    datasetsApi
      .list(activeProject.id)
      .then(setProjectDatasets)
      .catch(() => {});
  }, [activeProject]);

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  };

  const datasetCount = projectDatasets.length;
  const profiledCount = projectDatasets.filter((d) => d.versions?.[d.versions.length - 1]?.profile_data).length;

  const kpis = [
    {
      label: "Datasets",
      value: loadingProjects || !activeProject ? "—" : datasetCount,
      icon: "database",
      iconColor: "var(--color-primary-container)",
    },
    {
      label: "Quality issues",
      value: loadingProjects || !activeProject ? "—" : profiledCount > 0 ? "0 issues" : "—",
      icon: "fact_check",
      iconColor: "var(--color-error)",
    },
    {
      label: "Model runs",
      value: "—",
      icon: "model_training",
      iconColor: "var(--color-tertiary-container)",
    },
    {
      label: "Evaluation runs",
      value: "—",
      icon: "assignment_turned_in",
      iconColor: "var(--color-secondary)",
    },
  ];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Page Header */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
            {greeting()}, {user?.name?.split(" ")[0] ?? "there"}
          </h1>
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            <span className="material-symbols-outlined" style={{ fontSize: "1rem", color: "var(--color-primary)" }}>
              folder_open
            </span>
            {projectList.length > 0 ? (
              <select
                value={activeProject?.id ?? ""}
                onChange={(e) => {
                  const found = projectList.find((p) => p.id === e.target.value);
                  if (found) setActiveProject(found);
                }}
                className="bg-transparent font-medium text-sm outline-none cursor-pointer py-1 px-2.5 rounded-lg hover:bg-white/5 border border-white/10 transition-colors"
                style={{ color: "var(--color-on-surface)" }}
              >
                {projectList.map((p) => (
                  <option key={p.id} value={p.id} style={{ background: "#161C1D", color: "var(--color-on-surface)" }}>
                    {p.name}
                  </option>
                ))}
              </select>
            ) : (
              <span>No project selected</span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost">
            <span className="material-symbols-outlined" style={{ fontSize: "1rem" }}>filter_list</span>
            Filter
          </button>
          <button className="btn-ghost">
            <span className="material-symbols-outlined" style={{ fontSize: "1rem" }}>calendar_today</span>
            Last 7 Days
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi, i) => (
          <KpiCard key={kpi.label} {...kpi} index={i} />
        ))}
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column — 2/3 */}
        <div className="lg:col-span-2 space-y-6">
          {/* Recent Evaluation Runs */}
          <div className="glass-panel rounded-xl overflow-hidden animate-fade-in delay-2">
            <div
              className="p-5 flex justify-between items-center"
              style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}
            >
              <h2 className="text-xl font-semibold" style={{ color: "var(--color-on-surface)" }}>
                Recent evaluation runs
              </h2>
              <button style={{ color: "var(--color-on-surface-variant)" }}>
                <span className="material-symbols-outlined">more_horiz</span>
              </button>
            </div>
            <EmptyState
              icon="science"
              title="No evaluation runs yet"
              description="Run your first evaluation to see results here. Completed runs will show pass rate, model, and dataset."
              action="Start Evaluation"
              actionHref="/evaluations"
            />
          </div>

          {/* Recent Datasets / Analyses */}
          <div className="glass-panel rounded-xl overflow-hidden animate-fade-in delay-3">
            <div
              className="p-5 flex justify-between items-center"
              style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}
            >
              <h2 className="text-xl font-semibold" style={{ color: "var(--color-on-surface)" }}>
                Recent datasets
              </h2>
              <Link
                href="/datasets"
                className="mono text-xs transition-colors"
                style={{ color: "var(--color-primary-container)" }}
              >
                View all
              </Link>
            </div>
            {loadingProjects || !activeProject ? (
              <EmptyState
                icon="timeline"
                title={loadingProjects ? "Loading..." : "No project selected"}
                description={
                  loadingProjects
                    ? "Fetching your workspace."
                    : "Create a project, then upload a dataset to see recent analyses here."
                }
                action={loadingProjects ? undefined : "Go to Projects"}
                actionHref="/projects"
              />
            ) : projectDatasets.length === 0 ? (
              <EmptyState
                icon="database"
                title="No datasets yet"
                description="Upload a CSV or XLSX file — profiling runs automatically and quality issues appear here."
                action="Browse Datasets"
                actionHref="/datasets"
              />
            ) : (
              <ul>
                {projectDatasets.slice(0, 4).map((d) => {
                  const latest = d.versions?.[d.versions.length - 1];
                  const profiled = Boolean(latest?.profile_data);
                  return (
                    <li key={d.id}>
                      <Link
                        href={`/projects/${d.project_id}/datasets/${d.id}`}
                        className="flex items-center justify-between p-3 transition-all duration-200 group"
                        style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", color: "var(--color-on-surface)" }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)";
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLElement).style.background = "transparent";
                        }}
                      >
                        <div className="flex items-center gap-3">
                          <span className="material-symbols-outlined text-lg" style={{ color: "var(--color-on-surface-variant)" }}>
                            database
                          </span>
                          <div>
                            <div className="text-sm font-medium">{d.name}</div>
                            <div className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                              {d.format.toUpperCase()} · v{latest?.version_tag ?? "?"}
                            </div>
                          </div>
                        </div>
                        <span className="inline-flex items-center gap-1 text-xs" style={{ color: profiled ? "var(--color-primary)" : "var(--color-on-surface-variant)" }}>
                          <span className="material-symbols-outlined" style={{ fontSize: "0.875rem" }}>
                            {profiled ? "check_circle" : "pending"}
                          </span>
                          {profiled ? "Profiled" : "Not profiled"}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        {/* Right Column — 1/3 */}
        <div className="space-y-6">
          {/* Needs Attention */}
          <div
            className="glass-panel rounded-xl p-5 animate-fade-in delay-2"
            style={{
              border: "1px solid rgba(255,180,171,0.15)",
              boxShadow: "0 0 20px rgba(147,0,10,0.08)",
            }}
          >
            <div className="flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined" style={{ color: "var(--color-error)" }}>
                notification_important
              </span>
              <h2 className="text-xl font-semibold" style={{ color: "var(--color-on-surface)" }}>
                Needs attention
              </h2>
            </div>
            <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
              Regression status appears here once you mark an evaluation run as baseline — newly failing cases, newly passing cases, and flaky results.
            </p>
          </div>

          {/* Golden Datasets */}
          <div className="glass-panel rounded-xl p-5 animate-fade-in delay-3">
            <div className="flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined" style={{ color: "var(--color-tertiary-container)" }}>
                workspace_premium
              </span>
              <h2 className="text-xl font-semibold" style={{ color: "var(--color-on-surface)" }}>
                Golden datasets
              </h2>
            </div>
            <EmptyState
              icon="dataset"
              title="No golden datasets"
              description="Create curated golden datasets to use as baselines for your evaluation runs."
              action="Open Golden Datasets"
              actionHref="/golden-datasets"
            />
          </div>

          {/* Projects panel */}
          <div className="glass-panel rounded-xl p-5 animate-fade-in delay-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold" style={{ color: "var(--color-on-surface)" }}>
                Projects
              </h2>
              <Link
                href="/projects"
                className="mono text-xs transition-colors"
                style={{ color: "var(--color-primary-container)" }}
              >
                View all
              </Link>
            </div>
            {loadingProjects ? (
              <div className="flex justify-center py-6">
                <div
                  className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin"
                  style={{ borderColor: "var(--color-primary-container)" }}
                />
              </div>
            ) : projectList.length === 0 ? (
              <EmptyState
                icon="folder"
                title="No projects yet"
                description="Create your first project to get started."
                action="Create Project"
                actionHref="/projects"
              />
            ) : (
              <ul className="space-y-2">
                {projectList.map((p) => (
                  <li key={p.id}>
                    <Link
                      href={`/projects/${p.id}`}
                      className="flex items-center justify-between p-2 rounded-lg transition-all duration-200 group"
                      style={{ color: "var(--color-on-surface)" }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)";
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.background = "transparent";
                      }}
                    >
                      <div className="flex items-center gap-3">
                        <span
                          className="material-symbols-outlined text-lg"
                          style={{ color: "var(--color-on-surface-variant)" }}
                        >
                          folder_shared
                        </span>
                        <span className="text-sm font-medium">{p.name}</span>
                      </div>
                      <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                        {p.member_count} {p.member_count === 1 ? "member" : "members"}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
