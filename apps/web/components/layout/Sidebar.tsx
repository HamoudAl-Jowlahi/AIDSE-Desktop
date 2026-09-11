"use client";
/**
 * AIDSE Platform — Sidebar Navigation
 * Glass panel, 288px wide, fixed left.
 *
 * V1 information architecture (refocused):
 * Dashboard, Datasets, Data Quality, Data Preparation, ML Lab,
 * Evaluation, Golden Datasets, AI Data Analyst, Reports (+ Settings).
 * Deferred features (deployment, monitoring, infrastructure) intentionally absent.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "dashboard" },
  { href: "/datasets", label: "Datasets", icon: "database" },
  { href: "/quality", label: "Data Quality", icon: "fact_check" },
  { href: "/prepare", label: "Data Preparation", icon: "tune" },
  { href: "/ml-lab", label: "ML Lab", icon: "model_training" },
  { href: "/evaluations", label: "Evaluation", icon: "assignment_turned_in" },
  { href: "/golden-datasets", label: "Golden Datasets", icon: "workspace_premium" },
  { href: "/analyst", label: "AI Data Analyst", icon: "psychology" },
  { href: "/reports", label: "Reports", icon: "summarize" },
];

const BOTTOM_ITEMS = [
  { href: "/settings", label: "Settings", icon: "settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <nav
      className="fixed left-0 top-0 h-screen z-50 w-72 flex flex-col glass-panel shadow-2xl"
      style={{ borderRight: "1px solid rgba(255,255,255,0.1)" }}
    >
      {/* Brand */}
      <div className="p-6">
        <div
          className="text-2xl font-bold tracking-tight mb-1"
          style={{ color: "var(--color-primary)" }}
        >
          AIDSE
        </div>
        <div className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>
          AI Data Science Workspace
        </div>
      </div>

      {/* New Evaluation CTA */}
      <div className="px-4 mb-4">
        <Link href="/evaluations" className="btn-primary w-full" style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "0.375rem" }}>
          <span className="material-symbols-outlined text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>
            add
          </span>
          <span>New Evaluation</span>
        </Link>
      </div>

      {/* Primary nav */}
      <div className="flex-1 overflow-y-auto py-2 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={
              isActive(item.href)
                ? "nav-link-active"
                : "nav-link"
            }
            style={
              isActive(item.href)
                ? {
                    background: "rgba(0,242,254,0.08)",
                    borderLeft: "4px solid var(--color-primary-container)",
                    color: "var(--color-primary)",
                  }
                : {
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    padding: "0.75rem 1rem",
                    color: "var(--color-on-surface-variant)",
                    transition: "all 0.2s",
                    borderLeft: "4px solid transparent",
                  }
            }
            onMouseEnter={(e) => {
              if (!isActive(item.href)) {
                e.currentTarget.style.background = "rgba(255,255,255,0.05)";
                e.currentTarget.style.color = "var(--color-on-surface)";
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive(item.href)) {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--color-on-surface-variant)";
              }
            }}
          >
            <span className="material-symbols-outlined text-xl">{item.icon}</span>
            <span className="text-sm font-medium">{item.label}</span>
          </Link>
        ))}
      </div>

      {/* Bottom nav */}
      <div className="pb-4" style={{ borderTop: "1px solid rgba(255,255,255,0.1)" }}>
        {BOTTOM_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="flex items-center gap-3 px-4 py-2.5 mx-2 mt-1 rounded-md text-sm transition-all duration-200"
            style={{ color: "var(--color-on-surface-variant)" }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(255,255,255,0.05)";
              e.currentTarget.style.color = "var(--color-on-surface)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "var(--color-on-surface-variant)";
            }}
          >
            <span className="material-symbols-outlined text-lg">{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        ))}

        {/* User pill */}
        {user && (
          <div
            className="mx-4 mt-3 p-3 rounded-lg flex items-center gap-3"
            style={{
              background: "rgba(35,43,44,0.4)",
              border: "1px solid rgba(255,255,255,0.07)",
            }}
          >
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
              style={{
                background: "var(--color-secondary-container)",
                color: "var(--color-secondary)",
              }}
            >
              {user.name.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate" style={{ color: "var(--color-on-surface)" }}>
                {user.name}
              </div>
              <div className="text-xs truncate" style={{ color: "var(--color-on-surface-variant)" }}>
                {user.role}
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
