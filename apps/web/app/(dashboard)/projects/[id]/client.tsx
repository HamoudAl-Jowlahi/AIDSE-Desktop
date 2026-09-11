"use client";
/**
 * AIDSE Platform — Project Detail Page
 * Shows project info, members table, and invite member modal.
 */
import { useEffect, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import {
  projects as projectsApi,
  type ProjectOut,
  type MemberOut,
  type AuditLogOut,
  type DatasetResponse,
  datasets as datasetsApi,
} from "@/lib/api";

function InviteMemberModal({
  projectId,
  onClose,
  onInvited,
}: {
  projectId: string;
  onClose: () => void;
  onInvited: (m: MemberOut) => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"viewer" | "editor" | "admin">("viewer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const member = await projectsApi.inviteMember(projectId, { email, role });
      onInvited(member);
    } catch (err: unknown) {
      setError(
        (err as { data?: { error?: { message?: string } } })?.data?.error?.message ??
          "Failed to invite member"
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
            Invite Member
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

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
              EMAIL ADDRESS
            </label>
            <input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@example.com"
              required
              className="input-field"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
              ROLE
            </label>
            <select
              id="invite-role"
              value={role}
              onChange={(e) => setRole(e.target.value as "viewer" | "editor" | "admin")}
              className="input-field"
              style={{ cursor: "pointer" }}
            >
              <option value="viewer">Viewer — can view results</option>
              <option value="editor">Editor — can create and edit</option>
              <option value="admin">Admin — can manage members</option>
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">
              Cancel
            </button>
            <button
              id="invite-submit"
              type="submit"
              disabled={loading}
              className="btn-primary flex-1"
              style={{ opacity: loading ? 0.7 : 1 }}
            >
              {loading ? "Inviting..." : "Send Invite"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CreateDatasetModal({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: (d: DatasetResponse) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [format, setFormat] = useState("csv");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const dataset = await datasetsApi.create(projectId, { name, description, format });
      onCreated(dataset);
    } catch (err: unknown) {
      setError(
        (err as { data?: { error?: { message?: string } } })?.data?.error?.message ??
          "Failed to create dataset"
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
            Create Dataset
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

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
              DATASET NAME
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Training Data v1"
              required
              className="input-field"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
              DESCRIPTION
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              className="input-field"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5 mono" style={{ color: "var(--color-on-surface-variant)" }}>
              FORMAT
            </label>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              className="input-field"
              style={{ cursor: "pointer" }}
            >
              <option value="csv">CSV</option>
              <option value="xlsx">Excel XLSX</option>
              <option value="xls">Excel XLS</option>
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="btn-primary flex-1"
              style={{ opacity: loading ? 0.7 : 1 }}
            >
              {loading ? "Creating..." : "Create Dataset"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const ROLE_BADGE: Record<string, string> = {
  owner: "badge-warning",
  admin: "badge-success",
  editor: "badge-neutral",
  viewer: "badge-neutral",
};

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  const routeId = params.id === "default" ? pathname.split("/").filter(Boolean)[1] : params.id;
  const [project, setProject] = useState<ProjectOut | null>(null);
  const [members, setMembers] = useState<MemberOut[]>([]);
  const [logs, setLogs] = useState<AuditLogOut[]>([]);
  const [datasetsList, setDatasetsList] = useState<DatasetResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"overview" | "members" | "datasets" | "audit">("overview");
  const [showInvite, setShowInvite] = useState(false);
  const [showCreateDataset, setShowCreateDataset] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!routeId) return;
    Promise.all([
      projectsApi.get(routeId),
      projectsApi.auditLogs(routeId).catch(() => []),
      datasetsApi.list(routeId).catch(() => []), // Optional catch for uninitialized phase 1 DBs
    ])
      .then(([proj, auditLogs, dsets]) => {
        setProject(proj);
        setLogs(auditLogs);
        setDatasetsList(dsets);
      })
      .catch(() => setError("Project not found or access denied."))
      .finally(() => setLoading(false));
  }, [routeId]);

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

  if (error || !project) {
    return (
      <div className="glass-panel rounded-xl p-10 text-center">
        <span className="material-symbols-outlined text-4xl mb-3" style={{ color: "var(--color-error)" }}>error</span>
        <p style={{ color: "var(--color-on-surface)" }}>{error ?? "Project not found"}</p>
        <Link href="/projects" className="btn-primary mt-4 inline-flex">Back to Projects</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
        <Link href="/projects" className="hover:text-primary-container transition-colors">Projects</Link>
        <span className="material-symbols-outlined" style={{ fontSize: "1rem" }}>chevron_right</span>
        <span style={{ color: "var(--color-on-surface)" }}>{project.name}</span>
      </div>

      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold mb-1" style={{ color: "var(--color-on-surface)" }}>
            {project.name}
          </h1>
          <div className="flex items-center gap-3">
            <span
              className="mono text-xs px-2 py-0.5 rounded-full"
              style={{
                background: "rgba(0,242,254,0.1)",
                border: "1px solid rgba(0,242,254,0.2)",
                color: "var(--color-primary-container)",
              }}
            >
              {project.project_type}
            </span>
            <span className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
              {project.member_count} {project.member_count === 1 ? "member" : "members"}
            </span>
          </div>
          {project.description && (
            <p className="mt-2 text-sm max-w-xl" style={{ color: "var(--color-on-surface-variant)" }}>
              {project.description}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            id="delete-project-btn"
            onClick={async () => {
              if (window.confirm(`Are you sure you want to delete project "${project.name}"? All associated datasets and runs will be deleted.`)) {
                try {
                  await projectsApi.delete(project.id);
                  window.location.href = "/projects";
                } catch {
                  alert("Failed to delete project.");
                }
              }
            }}
            className="btn-ghost text-xs text-red-400 hover:text-red-300"
            style={{ color: "#FF6B6B", border: "1px solid rgba(255,107,107,0.3)" }}
          >
            <span className="material-symbols-outlined text-base">delete</span>
            Delete Project
          </button>
          <button
            id="invite-member-btn"
            onClick={() => setShowInvite(true)}
            className="btn-primary text-xs"
          >
            <span className="material-symbols-outlined text-base" style={{ fontVariationSettings: "'FILL' 1" }}>
              person_add
            </span>
            Invite Member
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div
        className="flex gap-1 p-1 rounded-lg"
        style={{
          background: "rgba(21,29,30,0.5)",
          border: "1px solid rgba(255,255,255,0.07)",
          width: "fit-content",
        }}
      >
        {(["overview", "members", "datasets", "audit"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="px-4 py-1.5 rounded-md text-sm font-medium capitalize transition-all duration-200"
            style={
              tab === t
                ? {
                    background: "rgba(0,242,254,0.15)",
                    color: "var(--color-primary)",
                    border: "1px solid rgba(0,242,254,0.2)",
                  }
                : {
                    color: "var(--color-on-surface-variant)",
                    border: "1px solid transparent",
                  }
            }
          >
            {t === "audit" ? "Audit Log" : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "overview" && (
        <div className="glass-panel rounded-xl p-6 space-y-4">
          <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>
            Project Overview
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { label: "Type", value: project.project_type },
              { label: "Members", value: project.member_count.toString() },
              { label: "Created", value: new Date(project.created_at).toLocaleDateString() },
            ].map((item) => (
              <div
                key={item.label}
                className="glass-card rounded-lg p-4"
              >
                <div className="mono text-xs mb-1" style={{ color: "var(--color-on-surface-variant)" }}>
                  {item.label.toUpperCase()}
                </div>
                <div className="text-base font-semibold" style={{ color: "var(--color-on-surface)" }}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>
          <div
            className="rounded-lg p-4 mt-4 text-sm"
            style={{
              background: "rgba(0,242,254,0.05)",
              border: "1px solid rgba(0,242,254,0.1)",
              color: "var(--color-on-surface-variant)",
            }}
          >
            <span className="material-symbols-outlined mr-2" style={{ fontSize: "1rem", color: "var(--color-primary-container)" }}>
              info
            </span>
            Evaluation runs, datasets, and models will appear here in Phase 1.
          </div>
        </div>
      )}

      {tab === "members" && (
        <div className="glass-panel rounded-xl overflow-hidden">
          <div
            className="p-5 flex justify-between items-center"
            style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}
          >
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>
              Members
            </h2>
            <button onClick={() => setShowInvite(true)} className="btn-ghost text-xs">
              <span className="material-symbols-outlined" style={{ fontSize: "1rem" }}>person_add</span>
              Invite
            </button>
          </div>
          {members.length === 0 ? (
            <div className="p-8 text-center text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
              Load members by refreshing — member list requires a /members endpoint (Phase 1).
            </div>
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr style={{ background: "rgba(35,43,44,0.3)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  {["Name", "Email", "Role", "Joined"].map((h) => (
                    <th key={h} className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                      {h.toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr
                    key={m.id}
                    className="transition-colors"
                    style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.03)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <td className="p-4 text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>
                      {m.user_name ?? "—"}
                    </td>
                    <td className="p-4 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
                      {m.user_email ?? "—"}
                    </td>
                    <td className="p-4">
                      <span className={ROLE_BADGE[m.role] ?? "badge-neutral"}>{m.role}</span>
                    </td>
                    <td className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                      {new Date(m.invited_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "datasets" && (
        <div className="glass-panel rounded-xl overflow-hidden">
          <div
            className="p-5 flex justify-between items-center"
            style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}
          >
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>
              Datasets
            </h2>
            <button onClick={() => setShowCreateDataset(true)} className="btn-primary text-xs">
              <span className="material-symbols-outlined" style={{ fontSize: "1rem", fontVariationSettings: "'FILL' 1" }}>add</span>
              Create Dataset
            </button>
          </div>
          {datasetsList.length === 0 ? (
            <div className="p-8 text-center text-sm flex flex-col items-center gap-2" style={{ color: "var(--color-on-surface-variant)" }}>
              <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)" }}>dataset</span>
              No datasets found. Create your first dataset to start evaluating.
            </div>
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr style={{ background: "rgba(35,43,44,0.3)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                  {["Name", "Format", "Versions", "Created"].map((h) => (
                    <th key={h} className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                      {h.toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {datasetsList.map((d) => (
                  <tr
                    key={d.id}
                    className="transition-colors"
                    style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.03)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <td className="p-4 text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>
                      <Link href={`/projects/${routeId}/datasets/${d.id}`} className="hover:text-primary-container hover:underline transition-colors block">
                        {d.name}
                        {d.description && (
                          <div className="text-xs mt-0.5" style={{ color: "var(--color-on-surface-variant)" }}>
                            {d.description}
                          </div>
                        )}
                      </Link>
                    </td>
                    <td className="p-4 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
                      <span className="badge-neutral uppercase text-xs">{d.format}</span>
                    </td>
                    <td className="p-4 text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
                      {d.versions?.length ?? 0}
                    </td>
                    <td className="p-4 mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>
                      —
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "audit" && (
        <div className="glass-panel rounded-xl overflow-hidden">
          <div className="p-5" style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>
              Audit Log
            </h2>
            <p className="text-xs mt-1" style={{ color: "var(--color-on-surface-variant)" }}>
              Append-only record of all state-changing actions in this project.
            </p>
          </div>
          {logs.length === 0 ? (
            <div className="p-8 text-center text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
              No audit events yet.
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: "rgba(255,255,255,0.05)" }}>
              {logs.map((log) => (
                <div key={log.id} className="p-4 flex items-start gap-4">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
                    style={{
                      background: "rgba(0,242,254,0.1)",
                      border: "1px solid rgba(0,242,254,0.15)",
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ color: "var(--color-primary-container)", fontSize: "0.875rem" }}>
                      history
                    </span>
                  </div>
                  <div>
                    <div className="text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>
                      <span className="mono" style={{ color: "var(--color-primary-container)" }}>{log.action}</span>
                      {" on "}<span style={{ color: "var(--color-secondary)" }}>{log.target_type}</span>
                    </div>
                    <div className="mono text-xs mt-0.5" style={{ color: "var(--color-on-surface-variant)" }}>
                      {new Date(log.occurred_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {typeof document !== "undefined" && createPortal(
        <>
          {showInvite && (
            <InviteMemberModal
              projectId={routeId!}
              onClose={() => setShowInvite(false)}
              onInvited={(m) => {
                setMembers((prev) => [...prev, m]);
                setShowInvite(false);
                if (tab !== "members") setTab("members");
              }}
            />
          )}

          {showCreateDataset && (
            <CreateDatasetModal
              projectId={routeId!}
              onClose={() => setShowCreateDataset(false)}
              onCreated={(d) => {
                setDatasetsList((prev) => [...prev, d]);
                setShowCreateDataset(false);
                if (tab !== "datasets") setTab("datasets");
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
