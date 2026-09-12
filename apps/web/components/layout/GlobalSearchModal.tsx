"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { projects as projectsApi, datasets as datasetsApi, type ProjectOut, type DatasetResponse } from "@/lib/api";

const STATIC_PAGES = [
  { label: "Dashboard", path: "/", icon: "dashboard" },
  { label: "Projects", path: "/projects", icon: "folder" },
  { label: "Datasets", path: "/datasets", icon: "database" },
  { label: "ML Lab", path: "/ml-lab", icon: "science" },
  { label: "Quality Intelligence", path: "/quality", icon: "fact_check" },
  { label: "Data Preparation", path: "/prepare", icon: "tune" },
  { label: "Evaluations", path: "/evaluations", icon: "assignment_turned_in" },
  { label: "Golden Datasets", path: "/golden-datasets", icon: "workspace_premium" },
  { label: "Reports", path: "/reports", icon: "description" },
  { label: "Notifications", path: "/notifications", icon: "notifications" },
  { label: "Settings", path: "/settings", icon: "settings" },
];

export function GlobalSearchModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [datasetList, setDatasetList] = useState<DatasetResponse[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setLoading(true);
      setTimeout(() => inputRef.current?.focus(), 50);

      projectsApi
        .list(1, 50)
        .then(async (res) => {
          setProjectList(res.items);
          if (res.items.length > 0) {
            try {
              // Every project, not the first five. The cap silently made
              // datasets in the sixth project onward unsearchable, with no
              // hint that results were incomplete.
              const allDs = await Promise.all(
                res.items.map((p) => datasetsApi.list(p.id).catch(() => []))
              );
              setDatasetList(allDs.flat());
            } catch {
              setDatasetList([]);
            }
          }
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const q = query.trim().toLowerCase();

  const matchedPages = STATIC_PAGES.filter(
    (p) => !q || p.label.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)
  );

  const matchedProjects = projectList.filter(
    (p) => !q || p.name.toLowerCase().includes(q) || (p.description && p.description.toLowerCase().includes(q))
  );

  const matchedDatasets = datasetList.filter(
    (d) => !q || d.name.toLowerCase().includes(q) || d.format.toLowerCase().includes(q)
  );

  const handleSelect = (path: string) => {
    onClose();
    router.push(path);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div
        className="w-full max-w-2xl glass-panel rounded-2xl shadow-2xl border overflow-hidden flex flex-col max-h-[80vh]"
        style={{
          background: "#161C1D",
          borderColor: "rgba(255,255,255,0.12)",
        }}
      >
        {/* Search Header Input */}
        <div className="p-4 border-b flex items-center gap-3" style={{ borderColor: "rgba(255,255,255,0.08)" }}>
          <span className="material-symbols-outlined text-xl" style={{ color: "var(--color-primary)" }}>
            search
          </span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search projects, datasets, pages..."
            className="w-full bg-transparent text-base outline-none"
            style={{ color: "var(--color-on-surface)" }}
          />
          {query && (
            <button onClick={() => setQuery("")} className="text-xs text-white/50 hover:text-white">
              Clear
            </button>
          )}
          <button
            onClick={onClose}
            className="text-xs px-2 py-1 rounded bg-white/10 text-white/70 hover:bg-white/20"
          >
            ESC
          </button>
        </div>

        {/* Results List */}
        <div className="p-4 overflow-y-auto space-y-5">
          {loading && (
            <div className="flex justify-center py-6">
              <div
                className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin"
                style={{ borderColor: "var(--color-primary-container)" }}
              />
            </div>
          )}

          {!loading && matchedProjects.length === 0 && matchedDatasets.length === 0 && matchedPages.length === 0 && (
            <div className="text-center py-8 text-sm text-white/50">
              No matching results found for &quot;{query}&quot;
            </div>
          )}

          {/* Projects Section */}
          {matchedProjects.length > 0 && (
            <div>
              <div className="text-xs mono uppercase tracking-wider mb-2" style={{ color: "var(--color-on-surface-variant)" }}>
                Projects ({matchedProjects.length})
              </div>
              <div className="space-y-1">
                {matchedProjects.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handleSelect(`/projects/${p.id}`)}
                    className="w-full text-left p-3 rounded-xl flex items-center justify-between transition-colors hover:bg-white/5"
                  >
                    <div className="flex items-center gap-3">
                      <span className="material-symbols-outlined text-lg" style={{ color: "var(--color-primary)" }}>
                        folder
                      </span>
                      <div>
                        <div className="text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>
                          {p.name}
                        </div>
                        {p.description && (
                          <div className="text-xs text-white/50 line-clamp-1">{p.description}</div>
                        )}
                      </div>
                    </div>
                    <span className="text-xs mono text-white/40">View</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Datasets Section */}
          {matchedDatasets.length > 0 && (
            <div>
              <div className="text-xs mono uppercase tracking-wider mb-2" style={{ color: "var(--color-on-surface-variant)" }}>
                Datasets ({matchedDatasets.length})
              </div>
              <div className="space-y-1">
                {matchedDatasets.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => handleSelect(`/projects/${d.project_id}/datasets/${d.id}`)}
                    className="w-full text-left p-3 rounded-xl flex items-center justify-between transition-colors hover:bg-white/5"
                  >
                    <div className="flex items-center gap-3">
                      <span className="material-symbols-outlined text-lg" style={{ color: "#4FC3F7" }}>
                        database
                      </span>
                      <div>
                        <div className="text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>
                          {d.name}
                        </div>
                        <div className="text-xs mono text-white/40">{d.format.toUpperCase()} dataset</div>
                      </div>
                    </div>
                    <span className="text-xs mono text-white/40">Open</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Pages Navigation Section */}
          {matchedPages.length > 0 && (
            <div>
              <div className="text-xs mono uppercase tracking-wider mb-2" style={{ color: "var(--color-on-surface-variant)" }}>
                Pages
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
                {matchedPages.map((page) => (
                  <button
                    key={page.path}
                    onClick={() => handleSelect(page.path)}
                    className="text-left p-2.5 rounded-xl flex items-center gap-3 transition-colors hover:bg-white/5"
                  >
                    <span className="material-symbols-outlined text-base" style={{ color: "var(--color-on-surface-variant)" }}>
                      {page.icon}
                    </span>
                    <span className="text-sm font-medium" style={{ color: "var(--color-on-surface)" }}>
                      {page.label}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
