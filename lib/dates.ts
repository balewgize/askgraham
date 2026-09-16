/** Display helper: "September 2026" -> "Sep 2026". Data is never mutated. */
export function formatDateShort(date: string | null): string {
  if (!date) return "undated";
  return date.replace(
    /^(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b/,
    (m) => m.slice(0, 3),
  );
}
