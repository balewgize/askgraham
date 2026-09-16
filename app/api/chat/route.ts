import { NextResponse } from "next/server";

/**
 * Seam for the future chat feature (RAG over the scraped essays).
 *
 * Intended shape when implemented:
 *   POST /api/chat  { messages: [{role, content}] }  -> streaming answer
 *   grounded in data/essays/*.json via lib/essays.ts (getEssay / getIndex).
 *
 * Not implemented yet — returns 501 so clients can detect it.
 */
export async function POST() {
  return NextResponse.json({ error: "Chat is not implemented yet." }, { status: 501 });
}

export async function GET() {
  return NextResponse.json({ status: "not-implemented" }, { status: 501 });
}
