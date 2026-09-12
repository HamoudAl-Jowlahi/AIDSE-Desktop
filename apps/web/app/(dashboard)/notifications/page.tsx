"use client";
/**
 * AIDSE Platform — Notifications
 *
 * Reads the real notification store. The previous version kept an empty array
 * in component state that nothing ever wrote to, so the page showed "no
 * notifications" permanently no matter what the app did.
 */
import Link from "next/link";
import { useEffect } from "react";

import {
  clearAll,
  formatAge,
  markAllRead,
  markRead,
  removeNotification,
  type NotificationType,
} from "@/lib/notifications";
import { useNotifications } from "@/lib/use-notifications";

const STYLE: Record<NotificationType, { icon: string; color: string; tint: string }> = {
  success: { icon: "check_circle", color: "#6fb98c", tint: "rgba(111,185,140,0.12)" },
  error: { icon: "error", color: "#e0707a", tint: "rgba(224,112,122,0.12)" },
  warning: { icon: "warning", color: "#d79c4a", tint: "rgba(215,156,74,0.12)" },
  info: { icon: "info", color: "#86aac8", tint: "rgba(134,170,200,0.12)" },
};

export default function NotificationsPage() {
  const notifications = useNotifications();
  const unread = notifications.filter((n) => !n.read).length;

  // Opening the page is what "seeing" them means; mark them read on the way
  // out so the list does not reshuffle under the cursor while reading.
  useEffect(() => {
    return () => {
      markAllRead();
    };
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex justify-between items-start gap-4">
        <div>
          <h1
            className="text-4xl font-bold tracking-tight mb-2"
            style={{ color: "var(--color-on-surface)" }}
          >
            Notifications
          </h1>
          <p className="text-sm max-w-xl" style={{ color: "var(--color-on-surface-variant)" }}>
            Events from this machine: dataset profiling, training runs, and evaluations.
          </p>
        </div>

        {notifications.length > 0 && (
          <div className="flex items-center gap-2 shrink-0">
            {unread > 0 && (
              <button onClick={markAllRead} className="btn-ghost text-xs">
                Mark all read
              </button>
            )}
            <button onClick={clearAll} className="btn-ghost text-xs">
              Clear all
            </button>
          </div>
        )}
      </div>

      {notifications.length === 0 ? (
        <div className="glass-panel rounded-xl p-16 flex flex-col items-center justify-center text-center gap-4">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center mb-1"
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
          >
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "2rem", color: "var(--color-on-surface-variant)" }}
            >
              notifications_off
            </span>
          </div>
          <h2 className="text-lg font-semibold" style={{ color: "var(--color-on-surface)" }}>
            Nothing yet
          </h2>
          <p className="text-sm max-w-sm" style={{ color: "var(--color-on-surface-variant)" }}>
            Upload a dataset or start a training run and the results will show up here.
          </p>
          <Link href="/datasets" className="btn-primary text-xs mt-2">
            Go to datasets
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {notifications.map((n) => {
            const s = STYLE[n.type];
            const body = (
              <>
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: s.tint }}
                >
                  <span
                    className="material-symbols-outlined"
                    style={{ fontSize: "1.15rem", color: s.color }}
                  >
                    {s.icon}
                  </span>
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span
                      className="text-sm font-medium"
                      style={{ color: "var(--color-on-surface)" }}
                    >
                      {n.title}
                    </span>
                    {!n.read && (
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: "var(--color-primary-container)" }}
                        aria-label="unread"
                      />
                    )}
                    <span
                      className="text-[11px] mono ml-auto shrink-0"
                      style={{ color: "var(--color-on-surface-variant)" }}
                    >
                      {formatAge(n.timestamp)}
                    </span>
                  </div>
                  <p
                    className="text-xs mt-0.5 break-words"
                    style={{ color: "var(--color-on-surface-variant)" }}
                  >
                    {n.message}
                  </p>
                </div>
              </>
            );

            return (
              <li
                key={n.id}
                className="glass-panel rounded-xl p-4 flex items-start gap-3 group"
                style={n.read ? { opacity: 0.72 } : undefined}
              >
                {n.href ? (
                  <Link
                    href={n.href}
                    onClick={() => markRead(n.id)}
                    className="flex items-start gap-3 flex-1 min-w-0"
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="flex items-start gap-3 flex-1 min-w-0">{body}</div>
                )}

                <button
                  onClick={() => removeNotification(n.id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded shrink-0"
                  style={{ color: "var(--color-on-surface-variant)" }}
                  title="Dismiss"
                  aria-label={`Dismiss: ${n.title}`}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "1rem" }}>
                    close
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
