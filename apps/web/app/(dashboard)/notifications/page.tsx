"use client";
/**
 * AIDSE Platform — Notifications Page
 * Displays user notifications or an empty state when no notifications exist.
 */
import Link from "next/link";
import { useState } from "react";

interface NotificationItem {
  id: string;
  title: string;
  message: string;
  timestamp: string;
  type: "info" | "success" | "warning" | "error";
  read: boolean;
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1
            className="text-4xl font-bold tracking-tight mb-2"
            style={{ color: "var(--color-on-surface)" }}
          >
            Notifications
          </h1>
          <p
            className="text-sm max-w-xl"
            style={{ color: "var(--color-on-surface-variant)" }}
          >
            Platform alerts and updates regarding training tasks, evaluations, and dataset profiling.
          </p>
        </div>
        {notifications.length > 0 && (
          <button
            onClick={() => setNotifications([])}
            className="btn-ghost text-xs"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Main Content */}
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
              style={{
                fontSize: "2.25rem",
                color: "var(--color-on-surface-variant)",
              }}
            >
              notifications_off
            </span>
          </div>

          <h2
            className="text-xl font-bold"
            style={{ color: "var(--color-on-surface)" }}
          >
            No notifications right now
          </h2>

          <p
            className="text-sm max-w-md leading-relaxed"
            style={{ color: "var(--color-on-surface-variant)" }}
          >
            Notifications for dataset recommendations, model training completion, and evaluation reports will appear here when available.
          </p>

          <Link href="/projects" className="btn-primary text-xs mt-2">
            Go to Projects
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {notifications.map((item) => (
            <div
              key={item.id}
              className="glass-card rounded-xl p-4 flex items-start justify-between gap-4"
            >
              <div className="flex items-start gap-3">
                <span
                  className="material-symbols-outlined mt-0.5"
                  style={{ color: "var(--color-primary)" }}
                >
                  info
                </span>
                <div>
                  <h3
                    className="text-sm font-semibold mb-1"
                    style={{ color: "var(--color-on-surface)" }}
                  >
                    {item.title}
                  </h3>
                  <p
                    className="text-xs"
                    style={{ color: "var(--color-on-surface-variant)" }}
                  >
                    {item.message}
                  </p>
                </div>
              </div>
              <span
                className="mono text-xs"
                style={{ color: "var(--color-on-surface-variant)" }}
              >
                {item.timestamp}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
