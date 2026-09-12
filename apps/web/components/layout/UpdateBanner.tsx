"use client";
/**
 * AIDSE Platform — Update notice
 *
 * A corner toast rather than a modal, on the same reasoning VS Code uses: an
 * update is worth telling someone about, never worth interrupting them over.
 * It stays out of the way until dismissed or acted on, and dismissing silences
 * that version for good.
 *
 * All the actual work — verifying the signature, downloading, installing,
 * relaunching — lives in lib/updater.ts. This is the surface.
 */
import { useEffect, useSyncExternalStore } from "react";
import { Download, RefreshCw, X, AlertTriangle, CheckCircle2 } from "lucide-react";

import {
  checkForUpdates,
  dismissUpdate,
  getUpdateState,
  installUpdate,
  subscribeToUpdates,
  type UpdateState,
} from "@/lib/updater";

const SERVER_SNAPSHOT: UpdateState = { stage: "idle" };

export function useUpdateState(): UpdateState {
  return useSyncExternalStore(subscribeToUpdates, getUpdateState, () => SERVER_SNAPSHOT);
}

export default function UpdateBanner() {
  const update = useUpdateState();

  useEffect(() => {
    // A short delay so the first paint and the sidecar handshake are not
    // competing with a network call nobody is waiting on.
    const timer = setTimeout(() => void checkForUpdates({ silent: true }), 8000);
    return () => clearTimeout(timer);
  }, []);

  // "checking" is silent by design; only the outcomes are worth a banner.
  if (update.stage === "idle" || update.stage === "checking") return null;

  const busy = update.stage === "downloading" || update.stage === "ready";
  const failed = update.stage === "error";

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 right-6 z-50 w-[22rem] rounded-xl border shadow-lg animate-fade-in"
      style={{
        background: "var(--color-surface-container-high)",
        borderColor: "var(--color-outline-variant)",
        color: "var(--color-on-surface)",
      }}
    >
      <div className="flex items-start gap-3 p-4">
        <div
          className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
          style={{
            // The container/on-container pair, not primary on primary-container:
            // in dark mode that would put near-white #e0fdff on cyan #00f2fe.
            background: failed
              ? "var(--color-error-container)"
              : "var(--color-primary-container)",
            color: failed
              ? "var(--color-on-error-container)"
              : "var(--color-on-primary-container)",
          }}
        >
          {failed ? (
            <AlertTriangle className="h-4 w-4" />
          ) : update.stage === "ready" ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : (
            <Download className="h-4 w-4" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">
            {failed
              ? "Update failed"
              : update.stage === "ready"
                ? "Restarting to finish"
                : update.stage === "downloading"
                  ? `Downloading ${update.version ?? ""}`
                  : `AIDSE ${update.version} is available`}
          </p>

          <p
            className="mt-1 text-xs leading-relaxed break-words"
            style={{ color: "var(--color-on-surface-variant)" }}
          >
            {failed
              ? update.error
              : update.stage === "downloading" || update.stage === "ready"
                ? "AIDSE will restart on its own once the installer finishes."
                : (update.notes?.trim() ||
                  "A newer version is ready to install.")}
          </p>

          {update.stage === "downloading" && (
            <div
              className="mt-3 h-1.5 w-full overflow-hidden rounded-full"
              style={{ background: "var(--color-surface-container-highest)" }}
            >
              <div
                className="h-full rounded-full transition-[width] duration-200"
                style={{
                  background: "var(--color-primary)",
                  // No content-length in the manifest means no percentage to
                  // show; a full bar would be a lie, so it pulses instead.
                  width: update.progress === undefined ? "100%" : `${update.progress}%`,
                  opacity: update.progress === undefined ? 0.5 : 1,
                }}
              />
            </div>
          )}

          {(update.stage === "available" || failed) && (
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                onClick={() =>
                  failed
                    ? void checkForUpdates({ silent: false })
                    : void installUpdate()
                }
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-opacity hover:opacity-90"
                style={{
                  background: "var(--color-primary)",
                  color: "var(--color-on-primary)",
                }}
              >
                {failed ? (
                  <>
                    <RefreshCw className="h-3 w-3" /> Try again
                  </>
                ) : (
                  <>
                    <Download className="h-3 w-3" /> Install and restart
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={dismissUpdate}
                className="rounded-lg px-3 py-1.5 text-xs transition-colors hover:opacity-80"
                style={{ color: "var(--color-on-surface-variant)" }}
              >
                Later
              </button>
            </div>
          )}
        </div>

        {!busy && (
          <button
            type="button"
            onClick={dismissUpdate}
            aria-label="Dismiss update notice"
            className="shrink-0 rounded-md p-1 transition-opacity hover:opacity-70"
            style={{ color: "var(--color-on-surface-variant)" }}
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
