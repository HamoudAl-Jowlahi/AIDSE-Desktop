/**
 * AIDSE Platform — Sidecar handshake
 *
 * When the app runs inside the Tauri shell, the backend's port and session
 * token are decided at launch and are not knowable any other way: the port is
 * whatever the OS handed out, and the token is 256 random bits held only by
 * the shell and the sidecar it spawned.
 *
 * This runs once before the first API call. Until now the shell exposed a
 * `get_sidecar_config` command that nothing called, so the frontend fell back
 * to a hardcoded port and sent no token at all.
 *
 * Outside Tauri — `next dev`, or the Edge launcher — there is no shell to ask,
 * and the same-origin default in getApiBase() is already correct.
 */
import { setApiBase, setInternalToken } from "./api";

interface SidecarConfig {
  host: string;
  port: number;
  token: string;
}

let handshake: Promise<boolean> | null = null;

function insideTauri(): boolean {
  if (typeof window === "undefined") return false;
  // Tauri v2 marks its windows with __TAURI_INTERNALS__.
  return "__TAURI_INTERNALS__" in window || "__TAURI__" in window;
}

/**
 * Resolve the backend address and token. Safe to call repeatedly — the work
 * happens once. Resolves to true when a Tauri config was applied.
 */
export function connectToSidecar(): Promise<boolean> {
  if (handshake) return handshake;

  handshake = (async () => {
    if (!insideTauri()) return false;

    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const config = await invoke<SidecarConfig>("get_sidecar_config");

      setApiBase(`http://${config.host}:${config.port}/api/v1`);
      if (config.token) setInternalToken(config.token);
      return true;
    } catch (err) {
      // Leave the same-origin default in place rather than blocking the UI on
      // a handshake that cannot happen.
      console.error("Could not reach the AIDSE shell for its sidecar config", err);
      return false;
    }
  })();

  return handshake;
}
