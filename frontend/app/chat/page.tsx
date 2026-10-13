import type { Metadata } from "next";
import Chat from "@/components/chat";

export const metadata: Metadata = {
  title: "Ask the essays",
  description:
    "Ask questions about Paul Graham's essays and get answers grounded in the text, with citations back to the passage.",
  alternates: { canonical: "/chat" },
};

export default function ChatPage() {
  return (
    <div className="flex flex-col gap-5">
      <div className="max-w-[46ch]">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Ask the essays</h1>
        <p className="mt-2.5 text-[0.95rem] leading-relaxed text-fg-muted">
          Every answer is grounded in the corpus and cites the passage it came from.
        </p>
      </div>
      <Chat />
    </div>
  );
}
