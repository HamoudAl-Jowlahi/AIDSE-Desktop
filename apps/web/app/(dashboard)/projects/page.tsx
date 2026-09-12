"use client";
/**
 * AIDSE Platform — Projects List Page
 * Displays the user's projects as glass cards.
 * "New Project" button opens an inline modal.
 */
import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { projects as projectsApi, type ProjectOut } from "@/lib/api";

function ProjectCard({ project, onDelete }: { project: ProjectOut; onDelete?: (id: string) => void }) {
  const typeIcon: Record<string, string> = {
    evaluation: "analytics",
    automl: "model_training",
    general: "folder_shared",
  };

  return (
    <Link href={`/projects/${project.id}`}>
      <div
        className="glass-card rounded-xl p-5 group cursor-pointer transition-all duration-200 hover:scale-[1.01] relative"
        style={{
          border: "1px solid rgba(255,255,255,0.07)",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.border = "1px solid rgba(0,242,254,0.2)";
          (e.currentTarget as HTMLElement).style.boxShadow = "0 0 20px rgba(0,242,254,0.05)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.border = "1px solid rgba(255,255,255,0.07)";
          (e.currentTarget as HTMLElement).style.boxShadow = "";
        }}
      >
        <div className="flex justify-between items-start mb-4">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{
              background: "rgba(0,242,254,0.1)",
              border: "1px solid rgba(0,242,254,0.2)",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ color: "var(--color-primary-container)", fontSize: "1.25rem" }}
            >
              {typeIcon[project.project_type] ?? "folder"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="mono text-xs px-2 py-0.5 rounded-full"
              style={{
                background: "rgba(35,43,44,0.6)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "var(--color-on-surface-variant)",
              }}
            >
              {project.project_type}
            </span>
            {onDelete && (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onDelete(project.id);
                }}
                className="p-1 rounded text-white/30 hover:text-red-400 hover:bg-white/10 transition-all"
                title="Delete project"
              >
                <span className="material-symbols-outlined text-base">delete</span>
              </button>
            )}
          </div>
        </div>

        <h3
          className="text-base font-semibold mb-1 group-hover:text-primary transition-colors"
          style={{ color: "var(--color-on-surface)" }}
        >
          {project.name}
        </h3>
        {project.description && (
          <p
            className="text-xs mb-3 line-clamp-2"
            style={{ color: "var(--color-on-surface-variant)" }}
          >
            {project.description}
          </p>
        )}

        <div
          className="flex items-center justify-between mt-3 pt-3"
          style={{ borderTop: "1px solid rgba(255,255,255,0.07)" }}
        >
          <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
            {project.project_type}
          </span>
          <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
            {new Date(project.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>
    </Link>
  );
}

function NewProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (p: ProjectOut) => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState("general");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const project = await projectsApi.create({ name, type, description: description || undefined });
      onCreated(project);
    } catch (err: unknown) {
      setError(
        (err as { data?: { error?: { message?: string } } })?.data?.error?.message ?? "Failed to create project"
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
            New Project
          </h2>
          <button
            onClick={onClose}
            style={{ color: "var(--color-on-surface-variant)" }}
          >
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

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
              PROJECT NAME
            </label>
            <input
              id="project-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Voice Assistant Evaluation"
              required
              className="input-field"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
              PROJECT TYPE
            </label>
            <select
              id="project-type"
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="input-field"
              style={{ cursor: "pointer" }}
            >
              <option value="general">General</option>
              <option value="evaluation">Evaluation</option>
              <option value="automl">AutoML</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
              DESCRIPTION (optional)
            </label>
            <textarea
              id="project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of the project..."
              rows={3}
              className="input-field resize-none"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="btn-ghost flex-1"
            >
              Cancel
            </button>
            <button
              id="create-project-submit"
              type="submit"
              disabled={loading}
              className="btn-primary flex-1"
              style={{ opacity: loading ? 0.7 : 1 }}
            >
              {loading ? "Creating..." : "Create Project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [totalCount, setTotalCount] = useState(0);

  async function loadProjects() {
    setLoading(true);
    try {
      const data = await projectsApi.list(1, 50);
      setProjectList(data.items);
      setTotalCount(data.total);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadProjects(); }, []);

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold" style={{ color: "var(--color-on-surface)" }}>
            Projects
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--color-on-surface-variant)" }}>
            {totalCount} {totalCount === 1 ? "project" : "projects"}
          </p>
        </div>
        <button
          id="new-project-btn"
          onClick={() => setShowModal(true)}
          className="btn-primary"
        >
          <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>
            add
          </span>
          New Project
        </button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex justify-center py-20">
          <div
            className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: "var(--color-primary-container)" }}
          />
        </div>
      ) : projectList.length === 0 ? (
        <div className="glass-panel rounded-xl py-20 flex flex-col items-center gap-4 text-center">
          <span className="material-symbols-outlined text-5xl" style={{ color: "var(--color-outline)" }}>
            folder_open
          </span>
          <div>
            <div className="text-lg font-semibold mb-1" style={{ color: "var(--color-on-surface)" }}>
              No projects yet
            </div>
            <p className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
              Create your first project to start organizing your AI evaluation work.
            </p>
          </div>
          <button onClick={() => setShowModal(true)} className="btn-primary mt-2">
            Create your first project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projectList.map((p, i) => (
            <div key={p.id} className={`animate-fade-in delay-${(i % 4) + 1}`}>
              <ProjectCard
                project={p}
                onDelete={async (id) => {
                  if (window.confirm(`Are you sure you want to delete project "${p.name}"?`)) {
                    try {
                      await projectsApi.delete(id);
                      setProjectList((prev) => prev.filter((item) => item.id !== id));
                      setTotalCount((t) => Math.max(0, t - 1));
                    } catch {
                      alert("Failed to delete project.");
                    }
                  }
                }}
              />
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <NewProjectModal
          onClose={() => setShowModal(false)}
          onCreated={(p) => {
            setProjectList((prev) => [p, ...prev]);
            setTotalCount((t) => t + 1);
            setShowModal(false);
          }}
        />
      )}
    </div>
  );
}
