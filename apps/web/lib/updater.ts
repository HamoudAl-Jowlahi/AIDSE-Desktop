/**
 * AIDSE Platform — Application updates
 *
 * Releases are published to GitHub Releases. Each release carries a
 * `latest.json` manifest listing the installer URL and a minisign signature
 * over it; the Rust updater plugin verifies that signature against the public
 * key compiled into the shell before it runs anything. An unsigned or
 * tampered installer is refused, which matters here because the download is
 * an executable that then replaces the app.
 *
 * The check is deliberately quiet. This is an offline-first desktop app: no
 * network is the normal case, not an error worth interrupting anyone over. A
 * failed check leaves the UI exactly as it was.
 */
import { notify } from "./notifications";

export type UpdateStage =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "ready"
  | "error";

export interface UpdateState {
  stage: UpdateStage;
  /** Version offered by the release manifest, once one is found. */
  version?: string;
  /** Release notes from the manifest body. */
  notes?: string;
  /** 0–100 while downloading, undefined when the total size is unknown. */
  progress?: number;
  error?: string;
}

/** Opaque handle to the pending update, held between check and install. */
type PendingUpdate = {
  version: string;
  body?: string;
  downloadAndInstall: (
    onEvent: (e: { event: string; data?: { contentLength?: number; chunkLength?: number } }) => void,
  ) => Promise<void>;
};

const CHANGE_EVENT = "aidse:update-changed";
/** Once a day is plenty for an app a person keeps open for weeks. */
const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
const LAST_CHECK_KEY = "aidse_update_last_check";
/** Versions the user dismissed; do not nag about them again. */
const DISMISSED_KEY = "aidse_update_dismissed";

let state: UpdateState = { stage: "idle" };
let pending: PendingUpdate | null = null;
let inFlight: Promise<void> | null = null;

function setState(next: UpdateState): void {
  state = next;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
  }
}

export function getUpdateState(): UpdateState {
  return state;
}

export function subscribeToUpdates(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

function insideTauri(): boolean {
  if (typeof window === "undefined") return false;
  return "__TAURI_INTERNALS__" in window || "__TAURI__" in window;
}

function readDismissed(): string[] {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Hide the banner for this version. A later version will still surface. */
export function dismissUpdate(): void {
  if (state.version) {
    try {
      localStorage.setItem(
        DISMISSED_KEY,
        JSON.stringify([...readDismissed(), state.version].slice(-20)),
      );
    } catch {
      /* storage unavailable — the banner just returns next launch */
    }
  }
  pending = null;
  setState({ stage: "idle" });
}

/**
 * Ask the release manifest whether a newer version exists.
 *
 * `silent` skips the "you are up to date" feedback and honours the once-a-day
 * throttle — that is the automatic check on launch. The Settings button passes
 * silent: false, because a person who clicked Check for updates deserves an
 * answer either way.
 */
export async function checkForUpdates({ silent = true } = {}): Promise<void> {
  if (!insideTauri()) return;
  if (inFlight) return inFlight;

  if (silent) {
    try {
      const last = Number(localStorage.getItem(LAST_CHECK_KEY) ?? 0);
      if (Date.now() - last < CHECK_INTERVAL_MS) return;
    } catch {
      /* no storage — check anyway */
    }
  }

  inFlight = (async () => {
    setState({ stage: "checking" });
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = (await check()) as PendingUpdate | null;

      try {
        localStorage.setItem(LAST_CHECK_KEY, String(Date.now()));
      } catch {
        /* ignore */
      }

      if (!update) {
        setState({ stage: "idle" });
        if (!silent) {
          notify({
            title: "AIDSE is up to date",
            message: "You are running the latest version.",
            type: "success",
          });
        }
        return;
      }

      if (silent && readDismissed().includes(update.version)) {
        setState({ stage: "idle" });
        return;
      }

      pending = update;
      setState({ stage: "available", version: update.version, notes: update.body });
      notify({
        title: `AIDSE ${update.version} is available`,
        message: "A new version is ready to install. Open the banner to update.",
        type: "info",
      });
    } catch (err) {
      // Offline, no release published yet, or no signing key configured. None
      // of those are the user's problem, so they stay in the console.
      const message = err instanceof Error ? err.message : String(err);
      console.warn("Update check failed:", message);
      setState(silent ? { stage: "idle" } : { stage: "error", error: message });
      if (!silent) {
        notify({
          title: "Could not check for updates",
          message,
          type: "warning",
        });
      }
    } finally {
      inFlight = null;
    }
  })();

  return inFlight;
}

/**
 * Download the update, verify it, install it, and restart into it.
 *
 * The install step hands control to the NSIS installer, so nothing after
 * `relaunch()` is guaranteed to run.
 */
export async function installUpdate(): Promise<void> {
  if (!pending) return;

  const version = pending.version;
  let downloaded = 0;
  let total = 0;

  setState({ stage: "downloading", version, notes: state.notes, progress: 0 });

  try {
    await pending.downloadAndInstall((event) => {
      if (event.event === "Started") {
        total = event.data?.contentLength ?? 0;
      } else if (event.event === "Progress") {
        downloaded += event.data?.chunkLength ?? 0;
        setState({
          stage: "downloading",
          version,
          notes: state.notes,
          progress: total > 0 ? Math.min(100, Math.round((downloaded / total) * 100)) : undefined,
        });
      } else if (event.event === "Finished") {
        setState({ stage: "ready", version, notes: state.notes, progress: 100 });
      }
    });

    notify({
      title: `Updated to AIDSE ${version}`,
      message: "Restarting to finish the installation.",
      type: "success",
    });

    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    setState({ stage: "error", version, error: message });
    notify({
      title: "Update failed",
      message,
      type: "error",
    });
  }
}
