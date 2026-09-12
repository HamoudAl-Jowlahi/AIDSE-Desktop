/**
 * AIDSE Platform — Notification store
 *
 * The notifications page used to hold `useState<NotificationItem[]>([])` and
 * nothing ever wrote to it, so it rendered a permanent empty state no matter
 * what happened in the app. This is the store the rest of the app records real
 * events into.
 *
 * Persisted in localStorage rather than the database on purpose: these are
 * UI-level events for the person at this machine, they are worthless to
 * another install, and writing them server-side would mean a migration and an
 * endpoint for something the backend never reads.
 */

export type NotificationType = "info" | "success" | "warning" | "error";

export interface AppNotification {
  id: string;
  title: string;
  message: string;
  /** ISO timestamp. */
  timestamp: string;
  type: NotificationType;
  read: boolean;
  /** Optional in-app link to whatever the notification is about. */
  href?: string;
}

const STORAGE_KEY = "aidse_notifications";
const CHANGE_EVENT = "aidse:notifications-changed";
/** Keep the log bounded; the oldest fall off. */
const MAX_STORED = 200;

function read(): AppNotification[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as AppNotification[]) : [];
  } catch {
    // Corrupt or unavailable storage must not take the page down.
    return [];
  }
}

function write(items: AppNotification[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_STORED)));
  } catch {
    /* quota or private mode — the in-memory view still updates */
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

export function getNotifications(): AppNotification[] {
  return read();
}

export function getUnreadCount(): number {
  return read().filter((n) => !n.read).length;
}

/**
 * Record an event. Call this where something actually happens — a dataset
 * finished profiling, a training run completed, an evaluation failed — not on
 * page render.
 */
export function notify(input: {
  title: string;
  message: string;
  type?: NotificationType;
  href?: string;
}): void {
  const item: AppNotification = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    title: input.title,
    message: input.message,
    timestamp: new Date().toISOString(),
    type: input.type ?? "info",
    read: false,
    href: input.href,
  };
  write([item, ...read()]);
}

export function markAllRead(): void {
  write(read().map((n) => ({ ...n, read: true })));
}

export function markRead(id: string): void {
  write(read().map((n) => (n.id === id ? { ...n, read: true } : n)));
}

export function removeNotification(id: string): void {
  write(read().filter((n) => n.id !== id));
}

export function clearAll(): void {
  write([]);
}

/**
 * Subscribe to changes. Covers both same-tab writes (custom event) and other
 * windows of the app (storage event).
 */
export function subscribe(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};

  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) listener();
  };
  window.addEventListener(CHANGE_EVENT, listener);
  window.addEventListener("storage", onStorage);

  return () => {
    window.removeEventListener(CHANGE_EVENT, listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** Human-readable age, e.g. "just now", "12m ago", "3d ago". */
export function formatAge(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));

  if (seconds < 45) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${Math.max(1, minutes)}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
