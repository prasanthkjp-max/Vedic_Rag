/** Small helpers shared by the panels. The engine sends labels like
 *  "Mesha (Aries)" / "Mesha (Mars)"; these pull the parts out safely. */

/** Today as YYYY-MM-DD in the viewer's LOCAL timezone. (`toISOString()` is UTC,
 *  which is the previous day in India between 00:00 and 05:30.) */
export function todayISO(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** True when today falls in [start, end). ISO date strings compare correctly. */
export function isCurrentPeriod(start?: string, end?: string): boolean {
  if (!start || !end) return false;
  const today = todayISO();
  return start <= today && today < end;
}

/** "Mesha (Aries)" -> "Mesha" */
export function firstWord(s?: string | null): string {
  return (s || '').trim().split(' ')[0] || '';
}

/** "Mesha (Mars)" -> "Mars"; "" when there are no parentheses. */
export function parenPart(s?: string | null): string {
  const m = /\(([^)]*)\)/.exec(s || '');
  return m ? m[1] : '';
}

/** "Atmakaraka (Soul & King of Chart)" -> "Atmakaraka" */
export function beforeParen(s?: string | null): string {
  return (s || '').split('(')[0].trim();
}

/** Always an array, whatever the API sent (string, array, null). */
export function asList(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String);
  if (v === null || v === undefined || v === '') return [];
  return [String(v)];
}

/** Fractional years elapsed since an ISO start date (0 if unparsable/future). */
export function yearsSince(startISO?: string): number {
  const t = startISO ? Date.parse(startISO) : NaN;
  if (isNaN(t)) return 0;
  return Math.max(0, (Date.now() - t) / (365.25 * 24 * 3600 * 1000));
}
