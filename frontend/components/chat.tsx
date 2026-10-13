"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import CitationPanel from "./citation-panel";
import { SearchIcon } from "./icons";
import {
  addMessage,
  clearMessages,
  persistMessages,
  updateLast,
  useChatMessages,
  type ChatSource,
} from "@/lib/chat-store";

// Keep the request (and the bill) bounded; the server enforces the same cap.
const MAX_HISTORY = 12;
const CITATION = /\[([a-z0-9-]+)#(\d+)-(\d+)\]/gi;

const EXAMPLES = [
  "How do I get my first customers?",
  "How do I know if an idea is good?",
  "Why do founders pick bad ideas?",
];

type Active = { slug: string; start: number; end: number };

function dedupeSources(sources: ChatSource[]): ChatSource[] {
  const seen = new Set<string>();
  return sources.filter((s) => (seen.has(s.slug) ? false : (seen.add(s.slug), true)));
}

/** Answer text with `[slug#a-b]` tokens turned into clickable source markers. */
function renderAnswer(text: string, sources: ChatSource[], onOpen: (source: Active) => void) {
  const order = new Map<string, number>();
  for (const source of sources) {
    if (!order.has(source.slug)) order.set(source.slug, order.size + 1);
  }

  const parts = text.split(CITATION);
  const nodes: ReactNode[] = [];
  for (let i = 0; i < parts.length; i += 4) {
    nodes.push(<span key={`t${i}`}>{parts[i]}</span>);
    const slug = parts[i + 1];
    if (!slug) continue;
    const start = Number(parts[i + 2]);
    const end = Number(parts[i + 3]);
    const source = sources.find((s) => s.slug === slug);
    nodes.push(
      <button
        key={`c${i}`}
        type="button"
        onClick={() => onOpen({ slug, start, end })}
        title={source?.title ?? slug}
        className="mx-0.5 align-super text-[0.7em] font-semibold text-accent hover:underline"
      >
        {order.get(slug) ?? "?"}
      </button>,
    );
  }
  return nodes;
}

export default function Chat() {
  const messages = useChatMessages();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<Active | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const openCitation = useCallback((source: Active) => setActive(source), []);
  const closeCitation = useCallback(() => setActive(null), []);

  async function send(override?: string) {
    const question = (override ?? input).trim();
    if (!question || busy) return;

    const history = messages.slice(-MAX_HISTORY).map((m) => ({ role: m.role, content: m.text }));

    setInput("");
    addMessage({ role: "user", text: question });
    addMessage({ role: "assistant", text: "" });
    setBusy(true);

    try {
      const response = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, history }),
      });
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const event = JSON.parse(line.slice(5).trim());
          if (event.type === "sources") {
            const sources: ChatSource[] = event.sources;
            updateLast((m) => ({ ...m, sources }));
            persistMessages();
          } else if (event.type === "delta") {
            const piece: string = event.text;
            updateLast((m) => ({ ...m, text: m.text + piece }));
          } else if (event.type === "error") {
            const message: string = event.message;
            updateLast((m) => ({ ...m, text: m.text + `\n\n(${message})`, failed: true }));
            persistMessages();
          }
        }
      }
    } catch (error) {
      updateLast((m) => ({ ...m, text: `Something went wrong: ${String(error)}`, failed: true }));
    } finally {
      setBusy(false);
      persistMessages();
    }
  }

  function newChat() {
    clearMessages();
    setActive(null);
    setInput("");
  }

  return (
    <div className="flex w-full items-start gap-6">
      <div className="mx-auto flex min-w-0 max-w-3xl flex-1 flex-col gap-5">
        <div className="max-w-[46ch]">
          <h1 className="font-serif text-3xl font-semibold tracking-tight">Ask the essays</h1>
          <p className="mt-2.5 text-[0.95rem] leading-relaxed text-fg-muted">
            Every answer is grounded in the corpus and cites the passage it came from.
          </p>
        </div>

        {messages.length > 0 && (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={newChat}
              className="rounded-md px-2 py-1 text-xs text-fg-subtle transition-colors hover:bg-fg/[0.06] hover:text-fg-muted"
            >
              New chat
            </button>
          </div>
        )}

        {messages.length === 0 && (
          <div className="flex flex-col gap-3">
            <p className="text-[0.95rem] leading-relaxed text-fg-muted">
              Ask a question and get an answer grounded in the essays. Every claim links to the
              passage it came from.
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => void send(example)}
                  className="rounded-full border border-line px-3 py-1.5 text-sm text-fg-muted transition-colors hover:border-line-firm hover:bg-fg/[0.04] hover:text-fg"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, i) =>
          message.role === "user" ? (
            <p key={i} className="self-end rounded-2xl bg-fg/[0.07] px-3.5 py-2 text-[0.95rem]">
              {message.text}
            </p>
          ) : (
            <div key={i} className="flex flex-col gap-2">
              {message.text ? (
                <div
                  className={`whitespace-pre-wrap font-serif text-[1.02rem] leading-relaxed ${
                    message.failed ? "text-red-700 dark:text-red-400" : ""
                  }`}
                >
                  {renderAnswer(message.text, message.sources ?? [], openCitation)}
                </div>
              ) : (
                <p className="flex items-center gap-2 text-sm text-fg-subtle">
                  {busy && i === messages.length - 1 ? (
                    <>
                      <SearchIcon size={14} /> Searching the essays…
                    </>
                  ) : (
                    ""
                  )}
                </p>
              )}

              {message.sources && message.sources.length > 0 && (
                <div className="flex flex-wrap gap-x-4 gap-y-1 border-l border-line pl-3 text-xs text-fg-subtle">
                  {dedupeSources(message.sources).map((source, n) => (
                    <button
                      key={source.slug}
                      type="button"
                      onClick={() =>
                        openCitation({
                          slug: source.slug,
                          start: source.start_paragraph,
                          end: source.end_paragraph,
                        })
                      }
                      className="text-left hover:text-fg-muted hover:underline"
                    >
                      <span className="font-medium text-fg-subtle">{n + 1}.</span> {source.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ),
        )}
        <div ref={endRef} />

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="sticky bottom-4 flex items-end gap-2 rounded-xl border border-line bg-raised/90 p-1.5 backdrop-blur"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={1}
            placeholder="Ask about startups, ideas, work…"
            aria-label="Ask a question"
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2.5 py-2 text-[0.95rem] outline-none placeholder:text-fg-subtle"
          />
          <button
            type="submit"
            disabled={busy || input.trim().length === 0}
            className="rounded-lg bg-fg px-3 py-2 text-sm font-medium text-surface transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {busy ? "…" : "Ask"}
          </button>
        </form>
      </div>

      {active && (
        <CitationPanel
          key={active.slug}
          slug={active.slug}
          start={active.start}
          end={active.end}
          onClose={closeCitation}
        />
      )}
    </div>
  );
}
