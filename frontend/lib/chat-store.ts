"use client";

import { useSyncExternalStore } from "react";

export type ChatSource = {
  slug: string;
  title: string;
  start_paragraph: number;
  end_paragraph: number;
};

export type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  sources?: ChatSource[];
  failed?: boolean;
};

const KEY = "askgraham:chat:v1";
const MAX_MESSAGES = 60;
const EMPTY: ChatMessage[] = [];

let messages: ChatMessage[] = EMPTY;
let hydrated = false;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function isMessage(value: unknown): value is ChatMessage {
  if (typeof value !== "object" || value === null) return false;
  const m = value as Record<string, unknown>;
  return (m.role === "user" || m.role === "assistant") && typeof m.text === "string";
}

function hydrate() {
  if (hydrated) return;
  hydrated = true;
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    if (Array.isArray(parsed)) {
      const valid = parsed.filter(isMessage).slice(-MAX_MESSAGES);
      // A trailing empty answer means the page was reloaded mid-stream.
      const last = valid[valid.length - 1];
      messages = last?.role === "assistant" && last.text === "" ? valid.slice(0, -1) : valid;
    }
  } catch {
    messages = EMPTY;
  }
}

/** Server snapshot is empty; the client reads localStorage after hydration. */
export function getSnapshot(): ChatMessage[] {
  hydrate();
  return messages;
}

export function getServerSnapshot(): ChatMessage[] {
  return EMPTY;
}

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(messages.slice(-MAX_MESSAGES)));
  } catch {
    /* quota or private mode — the in-memory conversation still works */
  }
}

export function useChatMessages(): ChatMessage[] {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function addMessage(message: ChatMessage): void {
  messages = [...messages, message];
  emit();
  persist();
}

/** Streaming updates many times a second; persistence waits for `persistMessages`. */
export function updateLast(update: (message: ChatMessage) => ChatMessage): void {
  if (messages.length === 0) return;
  messages = [...messages.slice(0, -1), update(messages[messages.length - 1])];
  emit();
}

export function persistMessages(): void {
  persist();
}

export function clearMessages(): void {
  messages = EMPTY;
  emit();
  persist();
}
