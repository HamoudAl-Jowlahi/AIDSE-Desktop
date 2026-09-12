"use client";
/**
 * AIDSE Platform — Application Lock
 *
 * Gates the workspace behind the master password set in Settings. Until this
 * existed the password was collected, hashed and stored, and then never asked
 * for — /auth/verify-password had no caller anywhere in the app.
 *
 * What this protects, stated plainly so the UI does not overclaim: it keeps
 * someone at your keyboard out of the workspace. It is not encryption. The
 * dataset files sit in your user profile and the local API answers on
 * loopback, so anyone able to run programs as you can still reach the data.
 * Use your operating system account and full-disk encryption for that.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Lock, LoaderCircle } from "lucide-react";

import { auth } from "@/lib/api";

const UNLOCK_KEY = "aidse_session_unlocked";

type LockState = "checking" | "locked" | "unlocked";

export function useAppLock() {
  const [state, setState] = useState<LockState>("checking");

  useEffect(() => {
    let cancelled = false;

    (async () => {
      // sessionStorage, not localStorage: closing the window re-locks. Only a
      // boolean is ever stored — never the password itself.
      let alreadyUnlocked = false;
      try {
        alreadyUnlocked = sessionStorage.getItem(UNLOCK_KEY) === "true";
      } catch {
        /* private mode or blocked storage — treat as locked */
      }

      try {
        const { has_password } = await auth.hasPassword();
        if (cancelled) return;
        if (!has_password) {
          setState("unlocked");
          return;
        }
        setState(alreadyUnlocked ? "unlocked" : "locked");
      } catch {
        // If the check itself fails, do not lock the user out of their own
        // offline app over a transient error.
        if (!cancelled) setState("unlocked");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const unlock = useCallback(() => {
    try {
      sessionStorage.setItem(UNLOCK_KEY, "true");
    } catch {
      /* still unlock for this render even if storage is unavailable */
    }
    setState("unlocked");
  }, []);

  return { state, unlock };
}

export default function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!password || busy) return;

    setBusy(true);
    setError(null);
    try {
      await auth.verifyPassword(password);
      setPassword("");
      onUnlock();
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      setError(
        message.toLowerCase().includes("too many")
          ? "Too many attempts. Wait a minute and try again."
          : "Incorrect password.",
      );
      setPassword("");
      inputRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: "var(--color-background)" }}
    >
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
            <Lock className="w-6 h-6 text-cyan-400" />
          </div>
          <h1 className="text-xl font-semibold text-white">AIDSE is locked</h1>
          <p className="text-sm text-slate-400 mt-1.5">
            Enter your master password to open the workspace.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            ref={inputRef}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Master password"
            autoComplete="current-password"
            aria-label="Master password"
            aria-invalid={error ? true : undefined}
            className="w-full px-4 py-3 rounded-xl bg-slate-900/70 border border-slate-800 text-slate-100 text-sm outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/40 transition-colors"
          />

          {error && (
            <p role="alert" className="text-xs text-red-400 px-1">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={!password || busy}
            className="w-full py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 disabled:cursor-not-allowed text-slate-950 font-semibold text-sm transition-colors flex items-center justify-center gap-2 cursor-pointer"
          >
            {busy && <LoaderCircle className="w-4 h-4 animate-spin" />}
            <span>{busy ? "Checking..." : "Unlock"}</span>
          </button>
        </form>

        <p className="text-[11px] leading-relaxed text-slate-500 mt-6 text-center">
          This lock keeps others out of the AIDSE workspace on this computer. It
          does not encrypt your datasets — rely on your Windows account and disk
          encryption for that.
        </p>
      </div>
    </div>
  );
}
