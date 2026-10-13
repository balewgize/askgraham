"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import CitationPanel from "./citation-panel";
import { ArrowUpIcon, MenuIcon, SearchIcon, TrashIcon } from "./icons";
import {
  addMessage,
  deleteConversation,
  newChat,
  openConversation,
  persistMessages,
  updateLast,
  useChatMessages,
  useConversations,
  useCurrentId,
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
  const conversations = useConversations();
  const currentId = useCurrentId();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<Active | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Follow the conversation, but only when the reader is already at the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 120) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // Opening another conversation always starts at the latest message.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [currentId]);

  const openCitation = useCallback((source: Active) => setActive(source), []);
  const closeCitation = useCallback(() => setActive(null), []);

  const startNew = useCallback(() => {
    newChat();
    setActive(null);
    setInput("");
    setNavOpen(false);
  }, []);

  const openChat = useCallback((id: string) => {
    openConversation(id);
    setActive(null);
    setNavOpen(false);
  }, []);

  const removeChat = useCallback((id: string) => {
    deleteConversation(id);
    setActive(null);
  }, []);

  // Starters drop the question into the composer; the reader decides to send.
  const fillInput = useCallback((example: string) => {
    setInput(example);
    inputRef.current?.focus();
  }, []);

  async function send() {
    const question = input.trim();
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

  return (
    <div className="flex h-full w-full">
      {navOpen && (
        <button
          type="button"
          aria-label="Close chat history"
          onClick={() => setNavOpen(false)}
          className="absolute inset-0 z-20 bg-black/40 lg:hidden"
        />
      )}

      <aside
        aria-label="Chat history"
        className={`absolute inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-line bg-surface transition-transform duration-200 lg:static lg:z-auto lg:w-56 lg:translate-x-0 xl:w-60 ${
          navOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between gap-2 px-3 py-2.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">Chats</span>
          <button
            type="button"
            onClick={startNew}
            className="rounded-md px-2 py-1 text-xs text-fg-muted transition-colors hover:bg-fg/[0.06] hover:text-fg"
          >
            New chat
          </button>
        </div>
        <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {conversations.length === 0 ? (
            <p className="px-2 py-2 text-xs text-fg-subtle">Your past chats show up here.</p>
          ) : (
            conversations.map((conversation) => {
              const activeChat = conversation.id === currentId;
              return (
                <div
                  key={conversation.id}
                  className={`group/item flex items-center rounded-md transition-colors ${
                    activeChat ? "bg-fg/[0.07]" : "hover:bg-fg/[0.05]"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => openChat(conversation.id)}
                    className={`min-w-0 flex-1 truncate px-2.5 py-2 text-left text-sm transition-colors ${
                      activeChat ? "font-medium text-fg" : "text-fg-muted group-hover/item:text-fg"
                    }`}
                  >
                    {conversation.title}
                  </button>
                  <button
                    type="button"
                    onClick={() => removeChat(conversation.id)}
                    aria-label={`Delete chat: ${conversation.title}`}
                    className="mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-fg-subtle transition-opacity hover:bg-fg/[0.08] hover:text-fg focus-visible:opacity-100 lg:opacity-0 lg:group-hover/item:opacity-100"
                  >
                    <TrashIcon size={15} />
                  </button>
                </div>
              );
            })
          )}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6">
            <div className="max-w-[46ch]">
              <h1 className="font-serif text-3xl font-semibold tracking-tight">Ask the essays</h1>
              <p className="mt-2.5 text-[0.95rem] leading-relaxed text-fg-muted">
                Every answer is grounded in the corpus and cites the passage it came from.
              </p>
            </div>

            {messages.length === 0 && (
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => fillInput(example)}
                    className="rounded-full border border-line px-3 py-1.5 text-sm text-fg-muted transition-colors hover:border-line-firm hover:bg-fg/[0.04] hover:text-fg"
                  >
                    {example}
                  </button>
                ))}
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
                    busy &&
                    i === messages.length - 1 && (
                      <p className="flex items-center gap-2 text-sm text-fg-subtle">
                        <SearchIcon size={14} /> Searching the essays…
                      </p>
                    )
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
          </div>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="border-t border-line bg-surface/95 px-4 py-3 backdrop-blur"
        >
          <div className="mx-auto flex w-full max-w-3xl items-end gap-2">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="Chat history"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-line text-fg-muted transition-colors hover:bg-fg/[0.05] hover:text-fg lg:hidden"
            >
              <MenuIcon size={18} />
            </button>
            <div className="flex min-w-0 flex-1 items-end gap-1.5 rounded-2xl border border-line bg-raised p-1.5 transition-colors focus-within:border-line-firm">
              <textarea
                ref={inputRef}
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
                className="max-h-40 min-h-8 flex-1 resize-none bg-transparent px-2 py-1.5 text-[0.95rem] outline-none placeholder:text-fg-subtle focus-visible:outline-hidden!"
              />
              <button
                type="submit"
                disabled={busy || input.trim().length === 0}
                aria-label="Send question"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fg text-surface transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                <ArrowUpIcon size={18} />
              </button>
            </div>
          </div>
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
