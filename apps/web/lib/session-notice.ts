/**
 * AIDSE Platform — Session notices
 * Survives hard redirects (window.location.href) via sessionStorage so the
 * login page can explain WHY the user landed there.
 */
export type SessionNoticeKind = "expired" | "logged_out";

const KEY = "aidse_session_notice";

export function setSessionNotice(kind: SessionNoticeKind): void {
  try {
    sessionStorage.setItem(KEY, kind);
  } catch {
    /* storage unavailable (private mode) — banner silently skipped */
  }
}

export function takeSessionNotice(): SessionNoticeKind | null {
  try {
    const v = sessionStorage.getItem(KEY);
    if (v === "expired" || v === "logged_out") {
      sessionStorage.removeItem(KEY);
      return v;
    }
    return null;
  } catch {
    return null;
  }
}
