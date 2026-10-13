import type { Metadata } from "next";
import Chat from "@/components/chat";

export const metadata: Metadata = {
  title: "Ask the essays",
  description:
    "Ask questions about Paul Graham's essays and get answers grounded in the text, with citations back to the passage.",
  alternates: { canonical: "/chat" },
};

export default function ChatPage() {
  // Pin the whole chat below the sticky header so the composer stays at the
  // bottom of the viewport and only the message list scrolls. `--header-h` is
  // measured by HeaderHeight; the fixed layer sits below the header (z-40).
  return (
    <div className="fixed inset-x-0 bottom-0 top-[var(--header-h)] z-10">
      <Chat />
    </div>
  );
}
