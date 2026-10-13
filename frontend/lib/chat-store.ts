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

/** A saved conversation. `at` orders the sidebar. */
export type Conversation = {
  id: string;
  title: string;
  at: number;
  messages: ChatMessage[];
};

const KEY = "askgraham:chats:v1";
const MAX_CONVERSATIONS = 30;
const MAX_MESSAGES = 60;
const EMPTY: ChatMessage[] = [];
const EMPTY_LIST: Conversation[] = [];

let conversations: Conversation[] = EMPTY_LIST;
let currentId: string | null = null; // null = an unsaved, brand-new chat
let hydrated = false;
const listeners = new Set<() => void>();

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

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

function isConversation(value: unknown): value is Conversation {
  if (typeof value !== "object" || value === null) return false;
  const c = value as Record<string, unknown>;
  return typeof c.id === "string" && typeof c.title === "string" && Array.isArray(c.messages);
}

/** Restores past chats from localStorage. The page always opens on a fresh chat. */
function hydrate() {
  if (hydrated) return;
  hydrated = true;
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    if (Array.isArray(parsed)) {
      conversations = parsed
        .filter(isConversation)
        .map((c) => ({ ...c, messages: c.messages.filter(isMessage).slice(-MAX_MESSAGES) }))
        .filter((c) => c.messages.length > 0)
        .slice(0, MAX_CONVERSATIONS);
    }
  } catch {
    conversations = EMPTY_LIST;
  }
  currentId = null;
}

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(conversations.slice(0, MAX_CONVERSATIONS)));
  } catch {
    /* quota or private mode — the session still works in memory */
  }
}

function current(): Conversation | undefined {
  return currentId ? conversations.find((c) => c.id === currentId) : undefined;
}

function titleFrom(message: ChatMessage): string {
  const text = message.text.trim().replace(/\s+/g, " ");
  return text.length > 48 ? `${text.slice(0, 48)}…` : text || "New chat";
}

// --- snapshots (referentially stable between real changes) ---

export function getSnapshot(): ChatMessage[] {
  hydrate();
  return current()?.messages ?? EMPTY;
}

function getServerSnapshot(): ChatMessage[] {
  return EMPTY;
}

export function getListSnapshot(): Conversation[] {
  hydrate();
  return conversations;
}

function getServerListSnapshot(): Conversation[] {
  return EMPTY_LIST;
}

function getCurrentIdSnapshot(): string | null {
  hydrate();
  return currentId;
}

// --- mutations ---

export function addMessage(message: ChatMessage): void {
  let conversation = current();
  if (!conversation) {
    conversation = { id: uid(), title: "", at: Date.now(), messages: [] };
    conversations = [conversation, ...conversations].slice(0, MAX_CONVERSATIONS);
    currentId = conversation.id;
  }
  conversation.messages = [...conversation.messages, message].slice(-MAX_MESSAGES);
  if (message.role === "user" && !conversation.title) conversation.title = titleFrom(message);
  emit();
  persist();
}

/** Streaming updates many times a second; persistence waits for `persistMessages`. */
export function updateLast(update: (message: ChatMessage) => ChatMessage): void {
  const conversation = current();
  if (!conversation || conversation.messages.length === 0) return;
  const last = conversation.messages[conversation.messages.length - 1];
  conversation.messages = [...conversation.messages.slice(0, -1), update(last)];
  emit();
}

export function persistMessages(): void {
  persist();
}

/** Clears the view to a fresh chat. The previous one stays in the sidebar. */
export function newChat(): void {
  currentId = null;
  emit();
}

export function openConversation(id: string): void {
  currentId = id;
  emit();
}

/** Removes a saved chat. Deleting the open one drops back to a fresh chat. */
export function deleteConversation(id: string): void {
  conversations = conversations.filter((c) => c.id !== id);
  if (currentId === id) currentId = null;
  emit();
  persist();
}

// --- React bindings ---

export function useChatMessages(): ChatMessage[] {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function useConversations(): Conversation[] {
  return useSyncExternalStore(subscribe, getListSnapshot, getServerListSnapshot);
}

export function useCurrentId(): string | null {
  return useSyncExternalStore(subscribe, getCurrentIdSnapshot, () => null);
}
