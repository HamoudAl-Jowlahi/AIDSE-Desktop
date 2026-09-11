"use client";
/**
 * AIDSE Platform — Top Bar
 * Sticky glass top bar with global search, notifications, and navigation.
 */
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { GlobalSearchModal } from "./GlobalSearchModal";

const TOP_TABS = [
  { href: "/projects", label: "Projects" },
];

export default function TopBar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  return (
    <>
      <header
        className="sticky top-0 right-0 w-full h-16 flex items-center justify-between px-8 z-40 glass-panel"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}
      >
        {/* Left: Search + Nav tabs */}
        <div className="flex items-center gap-8">
          {/* Interactive Search pill */}
          <button
            onClick={() => setIsSearchOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-all hover:border-white/20"
            style={{
              background: "rgba(35,43,44,0.5)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "var(--color-on-surface-variant)",
              cursor: "pointer",
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "1rem", color: "var(--color-primary)" }}>
              search
            </span>
            <span className="text-xs">Search projects, datasets...</span>
          </button>

          {/* Top navigation tabs */}
          <nav className="hidden md:flex gap-6">
            {TOP_TABS.map((tab) => {
              const active = pathname.startsWith(tab.href);
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  className="text-xs mono pb-1 transition-colors"
                  style={
                    active
                      ? {
                          color: "var(--color-primary)",
                          fontWeight: 700,
                          borderBottom: "2px solid var(--color-primary-container)",
                        }
                      : { color: "var(--color-on-surface-variant)" }
                  }
                >
                  {tab.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-3">
          {/* Notifications button */}
          <Link
            href="/notifications"
            className="p-1.5 rounded-lg transition-colors hover:bg-white/5 flex items-center justify-center"
            style={{ color: "var(--color-on-surface-variant)" }}
            title="Notifications"
          >
            <span className="material-symbols-outlined">notifications</span>
          </Link>

          {/* Settings */}
          <Link
            href="/settings"
            className="p-1.5 rounded-lg transition-colors hover:bg-white/5 flex items-center justify-center"
            style={{ color: "var(--color-on-surface-variant)" }}
            title="Settings"
          >
            <span className="material-symbols-outlined">settings</span>
          </Link>

          {/* Create New button */}
          <Link href="/projects" className="btn-primary text-xs" style={{ padding: "0.375rem 0.875rem" }}>
            Create New
          </Link>

          {/* User avatar */}
          {user && (
            <button
              onClick={logout}
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 transition-all"
              style={{
                background: "var(--color-secondary-container)",
                color: "var(--color-secondary)",
                border: "1px solid rgba(255,255,255,0.2)",
              }}
              title={`${user.name} — Click to logout`}
            >
              {user.name.charAt(0).toUpperCase()}
            </button>
          )}
        </div>
      </header>

      {/* Global Search Modal Overlay */}
      <GlobalSearchModal isOpen={isSearchOpen} onClose={() => setIsSearchOpen(false)} />
    </>
  );
}
