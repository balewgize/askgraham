import type { Metadata } from "next";
import Chat from "@/components/chat";

export const metadata: Metadata = {
  title: "Ask the essays",
  description:
    "Ask questions about Paul Graham's essays and get answers grounded in the text, with citations back to the passage.",
  alternates: { canonical: "/chat" },
};

export default function ChatPage() {
  // Break out of the reader's narrow column so chat and the citation panel can
  // sit side by side on large screens. `overflow-x-clip` on the body keeps the
  // wider child from producing a horizontal scrollbar.
  return (
    <div className="relative left-1/2 w-[min(100dvw-2rem,84rem)] -translate-x-1/2">
      <Chat />
    </div>
  );
}
