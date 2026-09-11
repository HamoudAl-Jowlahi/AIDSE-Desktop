"use client";
/**
 * AIDSE Platform — AI Data Analyst (Phase 11)
 *
 * Chat scoped to a dataset. Every numeric answer is produced by a real
 * analysis tool — the badge under each answer shows which tools ran.
 * When the analyst can't answer from data, it says so instead of guessing.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  chat as chatApi,
  datasets as datasetsApi,
  projects as projectsApi,
  type ChatMessage,
  type ProjectOut,
} from "@/lib/api";
import { urlSelection } from "@/lib/selection";

const SUGGESTIONS = [
  "Summarize this dataset",
  "How many missing values are there?",
  "Which features correlate most?",
  "What quality issues exist?",
  "Which preprocessing do you recommend?",
];

interface Bubble {
  id: string;
  role: "user" | "assistant" | "pending";
  content: string;
  toolsUsed?: { tool: string; args: Record<string, any> }[];
  generatedBy?: string;
}

function Select({ value, onChange, children, disabled }: {
  value: string; onChange: (v: string) => void; children: React.ReactNode; disabled?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="rounded-lg px-3 py-2 text-sm mono"
      style={{
        background: "rgba(35,43,44,0.5)",
        border: "1px solid rgba(255,255,255,0.07)",
        color: "var(--color-on-surface)",
      }}
    >
      {children}
    </select>
  );
}

export default function AnalystPage() {
  const [projectList, setProjectList] = useState<ProjectOut[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [datasetRows, setDatasetRows] = useState<{ id: string; name: string }[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");

  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    projectsApi.list(1, 50)
      .then((d) => {
        setProjectList(d.items);
        const sel = urlSelection();
        const preferred = sel.project && d.items.some((p) => p.id === sel.project) ? sel.project : null;
        if (d.items.length > 0) setProjectId(preferred ?? d.items[0].id);
      })
      .catch(() => {});
  }, []);

  // Load datasets of project
  useEffect(() => {
    if (!projectId) return;
    setDatasetRows([]); setDatasetId("");
    datasetsApi.list(projectId)
      .then((rows) => {
        setDatasetRows(rows.map((d) => ({ id: d.id, name: d.name })));
        const dsSel = urlSelection().dataset;
        const preferredDs = dsSel && rows.some((r) => r.id === dsSel) ? dsSel : null;
        if (rows.length > 0) setDatasetId(preferredDs ?? rows[0].id);
      })
      .catch(() => {});
  }, [projectId]);

  const loadHistory = useCallback(() => {
    if (!projectId) return;
    chatApi.history(projectId, datasetId || undefined)
      .then((h) => {
        setBubbles(h.messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          toolsUsed: m.tools_used ?? undefined,
          generatedBy: m.generated_by ?? undefined,
        })));
      })
      .catch(() => {});
  }, [projectId, datasetId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles]);

  const send = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || sending || !projectId) return;
    setInput("");
    setSending(true);
    setBubbles((b) => [...b, { id: `u-${Date.now()}`, role: "user", content: message }]);
    try {
      const resp = await chatApi.send(projectId, message, datasetId || undefined);
      setBubbles((b) => [...b, {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: resp.answer,
        toolsUsed: resp.tools_used,
        generatedBy: resp.generated_by,
      }]);
    } catch (e: any) {
      setBubbles((b) => [...b, { id: `e-${Date.now()}`, role: "assistant", content: `Error: ${e.message}` }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-bold tracking-tight mb-2" style={{ color: "var(--color-on-surface)" }}>
          AI Data Analyst
        </h1>
        <p className="text-sm max-w-2xl" style={{ color: "var(--color-on-surface-variant)" }}>
          Chat with your dataset. Numbers come only from real analysis tools — when something can&apos;t be answered from the data, the analyst says so.
        </p>
      </div>

      {projectList.length === 0 ? (
        <div className="glass-panel rounded-xl p-10 flex flex-col items-center gap-3 text-center">
          <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)" }}>folder_off</span>
          <Link href="/projects" className="btn-primary mt-2 text-sm">Create a project first</Link>
        </div>
      ) : (
        <div className="glass-panel rounded-xl flex flex-col" style={{ height: "calc(100vh - 220px)", minHeight: 480 }}>
          {/* Context bar */}
          <div className="p-4 flex items-center gap-3 flex-wrap" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
            <span className="material-symbols-outlined text-xl" style={{ color: "var(--color-primary)" }}>psychology</span>
            <Select value={projectId ?? ""} onChange={setProjectId}>
              {projectList.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
            </Select>
            <Select value={datasetId} onChange={setDatasetId} disabled={datasetRows.length === 0}>
              <option value="">No dataset context</option>
              {datasetRows.map((d) => (<option key={d.id} value={d.id}>{d.name}</option>))}
            </Select>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {bubbles.length === 0 && !sending && (
              <div className="h-full flex flex-col items-center justify-center gap-4 text-center">
                <span className="material-symbols-outlined text-4xl" style={{ color: "var(--color-outline)", fontSize: "3rem" }}>forum</span>
                <div className="font-semibold" style={{ color: "var(--color-on-surface)" }}>
                  Ask about {datasetId ? "the selected dataset" : "your trained models"}
                </div>
                {!datasetId && (
                  <p className="text-sm max-w-md" style={{ color: "var(--color-on-surface-variant)" }}>
                    Tip: pick a dataset above for data questions — model questions work without one.
                  </p>
                )}
              </div>
            )}

            {bubbles.map((b) => (
              <div key={b.id} className={`flex ${b.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className="max-w-[80%] rounded-xl px-4 py-3"
                  style={
                    b.role === "user"
                      ? { background: "rgba(0,242,254,0.12)", border: "1px solid rgba(0,242,254,0.25)" }
                      : { background: "rgba(35,43,44,0.55)", border: "1px solid rgba(255,255,255,0.07)" }
                  }
                >
                  <p className="text-sm whitespace-pre-wrap leading-relaxed" style={{ color: "var(--color-on-surface)" }}>
                    {b.content}
                  </p>

                  {/* Tool audit trail */}
                  {b.toolsUsed && b.toolsUsed.length > 0 && (
                    <div className="mt-2 pt-2 flex flex-wrap items-center gap-1.5" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                      <span className="mono text-xs" style={{ color: "var(--color-on-surface-variant)" }}>tools:</span>
                      {b.toolsUsed.map((t, i) => (
                        <span key={i} className="mono text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(0,242,254,0.08)", color: "var(--color-primary)" }}>
                          {t.tool}
                          {Object.keys(t.args ?? {}).length > 0 && Object.entries(t.args).length > 0 && (
                            `(${Object.values(t.args)[0]})`
                          )}
                        </span>
                      ))}
                    </div>
                  )}

                  {b.role === "assistant" && b.generatedBy && (
                    <div className="mono text-xs mt-1" style={{ color: "var(--color-on-surface-variant)" }}>
                      {b.generatedBy === "rules+llm" ? "✦ LLM narration over tool results" : "rule engine — computed locally"}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex justify-start">
                <div className="rounded-xl px-4 py-3 flex items-center gap-2" style={{ background: "rgba(35,43,44,0.55)", border: "1px solid rgba(255,255,255,0.07)" }}>
                  <div className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--color-primary-container)" }} />
                  <span className="text-sm" style={{ color: "var(--color-on-surface-variant)" }}>Running analysis tools…</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Suggestions */}
          <div className="px-5 pb-2 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                disabled={sending || !datasetId}
                className="text-xs px-2.5 py-1.5 rounded-full transition-all disabled:opacity-40"
                style={{
                  background: "rgba(35,43,44,0.6)",
                  border: "1px solid rgba(255,255,255,0.07)",
                  color: "var(--color-on-surface-variant)",
                }}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="p-4 flex gap-2" style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder={datasetId ? "Ask anything about this dataset…" : "Pick a dataset for data questions…"}
              className="flex-1 rounded-lg px-4 py-2.5 text-sm"
              style={{
                background: "rgba(35,43,44,0.6)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "var(--color-on-surface)",
              }}
            />
            <button onClick={() => send()} disabled={sending || !input.trim()} className="btn-primary text-sm">
              <span className="material-symbols-outlined text-base">send</span>
              Ask
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
