"use client";
/**
 * AIDSE Platform — Page Stub
 * Clean placeholder for V1 modules under active development.
 * Describes exactly what the section will contain. Never shows fake data
 * and never surfaces deferred (V2/V3/Enterprise) features as UI.
 */
import Link from "next/link";

export interface StubSection {
  title: string;
  description: string;
}

export default function PageStub({
  icon,
  title,
  description,
  sections,
  primaryAction,
  primaryActionHref,
}: {
  icon: string;
  title: string;
  description: string;
  sections?: StubSection[];
  primaryAction?: string;
  primaryActionHref?: string;
}) {
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1
          className="text-4xl font-bold tracking-tight mb-2"
          style={{ color: "var(--color-on-surface)" }}
        >
          {title}
        </h1>
        <p className="text-sm max-w-2xl" style={{ color: "var(--color-on-surface-variant)" }}>
          {description}
        </p>
      </div>

      <div className="glass-panel rounded-xl p-8">
        {/* Centered icon + optional action */}
        <div className="flex flex-col items-center text-center gap-3 py-8">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center"
            style={{
              background: "rgba(0,242,254,0.08)",
              border: "1px solid rgba(0,242,254,0.15)",
            }}
          >
            <span
              className="material-symbols-outlined text-3xl"
              style={{ color: "var(--color-primary)" }}
            >
              {icon}
            </span>
          </div>
          {primaryAction && primaryActionHref && (
            <Link href={primaryActionHref} className="btn-primary mt-2 text-sm">
              {primaryAction}
            </Link>
          )}
        </div>

        {/* Planned capability cards */}
        {sections && sections.length > 0 && (
          <div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-6"
            style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}
          >
            {sections.map((s) => (
              <div key={s.title} className="glass-card rounded-lg p-4" style={{ cursor: "default" }}>
                <div
                  className="text-sm font-semibold mb-1"
                  style={{ color: "var(--color-on-surface)" }}
                >
                  {s.title}
                </div>
                <p className="text-xs leading-relaxed" style={{ color: "var(--color-on-surface-variant)" }}>
                  {s.description}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
