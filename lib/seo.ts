import type { Essay } from "./essays";

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** Trim prose to a clean meta-description length on a word boundary. */
export function excerpt(text: string, max = 130): string {
  const clean = text.replace(/\[\d+\]/g, "").replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max);
  const at = cut.lastIndexOf(" ");
  return `${cut.slice(0, at > 40 ? at : max).trim()}…`;
}

/** "July 2009" -> "2009-07-01" for datePublished. Undated essays return undefined. */
export function isoDate(date: string | null): string | undefined {
  if (!date) return undefined;
  const monthYear = date.match(/^([A-Za-z]+)\s+(\d{4})$/);
  if (monthYear) {
    const month = MONTHS.indexOf(monthYear[1]);
    if (month >= 0) return `${monthYear[2]}-${String(month + 1).padStart(2, "0")}-01`;
  }
  const year = date.match(/\b(19\d{2}|20\d{2})\b/);
  return year ? `${year[1]}-01-01` : undefined;
}

export function essayDescription(essay: Essay): string {
  return `${excerpt(essay.paragraphs[0] ?? "")} — ${essay.title} by Paul Graham, full text.`;
}
