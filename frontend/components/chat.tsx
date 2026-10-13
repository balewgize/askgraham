"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

type SourceMeta = {
  slug: string;
  title: string;
  start_paragraph: number;
  end_paragraph: number;
};

type Message = {
  role: "user" | "assistant";
  text: string;
  sources?: SourceMeta[];
  failed?: boolean;
};

// Keep the request (and the bill) bounded; the server enforces the same cap.
const MAX_HISTORY = 12;
const CITATION = /\[([a-z0-9-]+)#(\d+)-(\d+)\]/gi;

function dedupeSources(sources: SourceMeta[]): SourceMeta[] {
  const seen = new Set<string>();
  return sources.filter((s) => (seen.has(s.slug) ? false : (seen.add(s.slug), true)));
}

function renderAnswer(text: string, sources: SourceMeta[]): ReactNode {
  // Number sources by first appearance so inline markers map to the list below.
  const order = new Map<string, number>();
  for (const source of sources) {
    if (!order.has(source.slug)) order.set(source.slug, order.size + 1);
  }

  const parts = text.split(CITATION);
  const nodes: ReactNode[] = [];
  // split() with a capture group interleaves text and the captured groups.
  for (let i = 0; i < parts.length; i += 4) {
    nodes.push(<Fragment key={`t${i}`}>{parts[i]}</Fragment>);
    const slug = parts[i + 1];
    if (!slug) continue;
    const n = order.get(slug);
    nodes.push(
      <Link
        key={`c${i}`}
        href={`/essays/${slug}`}
        title={sources.find((s) => s.slug === slug)?.title ?? slug}
        className="mx-0.5 align-super text-[0.7em] font-medium text-accent hover:underline"
      >
        {n ?? "?"}
      </Link>,
    );
  }
  return nodes;
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const updateLast = (update: (message: Message) => Message) => {
    setMessages((prev) => prev.map((m, i) => (i === prev.length - 1 ? update(m) : m)));
  };

  async function send() {
    const question = input.trim();
    if (!question || busy) return;

    const history = messages
      .slice(-MAX_HISTORY)
      .map((m) => ({ role: m.role, content: m.text }));

    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", text: "" },
    ]);
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
      let sources: SourceMeta[] = [];

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
            sources = event.sources;
            updateLast((m) => ({ ...m, sources }));
          } else if (event.type === "delta") {
            const piece: string = event.text;
            updateLast((m) => ({ ...m, text: m.text + piece }));
          } else if (event.type === "error") {
            updateLast((m) => ({ ...m, text: m.text + `\n\n(${event.message})`, failed: true }));
          }
        }
      }
    } catch (error) {
      updateLast((m) => ({ ...m, text: `Something went wrong: ${String(error)}`, failed: true }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {messages.length === 0 && (
        <p className="text-[0.95rem] leading-relaxed text-fg-muted">
          Ask a question and get an answer grounded in the essays, with a citation back to the
          passage it came from. Try{" "}
          <button
            type="button"
            className="underline underline-offset-2 hover:text-fg"
            onClick={() => setInput("How do I get my first customers?")}
          >
            How do I get my first customers?
          </button>
        </p>
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
                {renderAnswer(message.text, message.sources ?? [])}
              </div>
            ) : (
              <p className="text-sm text-fg-subtle">
                {busy && i === messages.length - 1 ? "Searching the essays…" : ""}
              </p>
            )}

            {message.sources && message.sources.length > 0 && (
              <ol className="flex flex-col gap-1 border-l border-line pl-3 text-xs text-fg-subtle">
                {dedupeSources(message.sources).map((source) => (
                  <li key={source.slug}>
                    <Link
                      href={`/essays/${source.slug}`}
                      className="hover:text-fg-muted hover:underline"
                    >
                      {source.title}
                    </Link>{" "}
                    ¶{source.start_paragraph}–{source.end_paragraph}
                  </li>
                ))}
              </ol>
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
  );
}
