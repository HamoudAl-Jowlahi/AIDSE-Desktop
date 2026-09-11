"use client";
/**
 * AIDSE Platform — Dataset Workspace Tabs (Phase 16)
 *
 * The seven-section workspace around one dataset. Overview stays on the
 * dataset page; the other six route to their dedicated workspaces carrying
 * ?project= &dataset= so selection follows the user.
 */
import { useRouter } from "next/navigation";

export type WorkspaceTab =
  | "overview" | "quality" | "prepare" | "ml"
  | "explain" | "chat" | "evaluation";

const TABS: { id: WorkspaceTab; label: string; icon: string; href?: string }[] = [
  { id: "overview", label: "Overview", icon: "article" },
  { id: "quality", label: "Quality", icon: "fact_check", href: "/quality" },
  { id: "prepare", label: "Prepare", icon: "tune", href: "/prepare" },
  { id: "ml", label: "ML Lab", icon: "model_training", href: "/ml-lab" },
  { id: "explain", label: "Explain", icon: "insights", href: "/ml-lab" },
  { id: "chat", label: "Chat", icon: "psychology", href: "/analyst" },
  { id: "evaluation", label: "Evaluation", icon: "assignment_turned_in", href: "/evaluations" },
];

export default function WorkspaceTabs({
  active, projectId, datasetId,
}: {
  active: WorkspaceTab;
  projectId: string;
  datasetId: string;
}) {
  const router = useRouter();
  const qs = `?project=${projectId}&dataset=${datasetId}`;

  return (
    <div className="glass-panel rounded-xl p-1 flex flex-wrap gap-1">
      {TABS.map((t) => {
        const isActive = t.id === active;
        const target = t.href ? `${t.href}${qs}` : undefined;
        return (
          <button
            key={t.id}
            onClick={() => {
              if (!target) return; // overview handled locally by host page
              router.push(target);
            }}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm transition-all"
            style={isActive
              ? { background: "rgba(0,242,254,0.12)", color: "var(--color-primary)", fontWeight: 600 }
              : { color: "var(--color-on-surface-variant)" }}
          >
            <span className="material-symbols-outlined text-base">{t.icon}</span>
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
