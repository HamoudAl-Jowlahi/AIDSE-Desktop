"use client";
/**
 * AIDSE Platform — Top Bar
 * Sticky glass top bar with global search, notifications, and navigation.
 */
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUnreadCount } from "@/lib/use-notifications";
import { GlobalSearchModal } from "./GlobalSearchModal";

const TOP_TABS = [
  { href: "/projects", label: "Projects" },
];

export default function TopBar() {
  const pathname = usePathname();
  const unreadCount = useUnreadCount();
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

        {/* Right: Actions
         *
         * No account avatar here. This is a single-user desktop app with no
         * sign-in, so an avatar and a "log out" action described a multi-user
         * platform that no longer exists. The icon actions are grouped and set
         * apart from the primary button so they stop competing with it.
         */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <Link
              href="/notifications"
              className="relative p-1.5 rounded-lg transition-colors hover:bg-white/5 flex items-center justify-center"
              style={{ color: "var(--color-on-surface-variant)" }}
              title="Notifications"
              aria-label={
                unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"
              }
            >
              <span className="material-symbols-outlined">notifications</span>
              {unreadCount > 0 && (
                <span
                  className="absolute top-0.5 right-0.5 min-w-[1rem] h-4 px-1 rounded-full text-[10px] font-bold leading-4 text-center"
                  style={{
                    background: "var(--color-error)",
                    color: "var(--color-on-error, #fff)",
                  }}
                >
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </Link>

            <Link
              href="/settings"
              className="p-1.5 rounded-lg transition-colors hover:bg-white/5 flex items-center justify-center"
              style={{ color: "var(--color-on-surface-variant)" }}
              title="Settings"
              aria-label="Settings"
            >
              <span className="material-symbols-outlined">settings</span>
            </Link>
          </div>

          <Link href="/projects" className="btn-primary text-xs" style={{ padding: "0.375rem 0.875rem" }}>
            Create New
          </Link>
        </div>
      </header>

      {/* Global Search Modal Overlay */}
      <GlobalSearchModal isOpen={isSearchOpen} onClose={() => setIsSearchOpen(false)} />
    </>
  );
}
