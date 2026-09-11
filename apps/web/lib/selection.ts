/**
 * AIDSE Platform — cross-page selection via URL params (Phase 16 tabs).
 * Read once on mount; avoids useSearchParams/Suspense requirements.
 */
export function urlSelection(): { project: string | null; dataset: string | null } {
  if (typeof window === "undefined") return { project: null, dataset: null };
  const q = new URLSearchParams(window.location.search);
  return { project: q.get("project"), dataset: q.get("dataset") };
}
