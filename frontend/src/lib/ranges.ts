/** Merge overlapping/adjacent intervals into a canonical list. */
export function mergeIntervals(
  intervals: { start: number; end: number }[]
): { start: number; end: number }[] {
  if (intervals.length === 0) return [];
  const sorted = [...intervals].sort((a, b) => a.start - b.start);
  const out: { start: number; end: number }[] = [{ ...sorted[0] }];
  for (let i = 1; i < sorted.length; i++) {
    const cur = sorted[i];
    const last = out[out.length - 1];
    if (cur.start <= last.end) {
      last.end = Math.max(last.end, cur.end);
    } else {
      out.push({ ...cur });
    }
  }
  return out;
}

/** Return [start,end] intervals in `domain` that are NOT covered by any input
 *  interval. Used to render dim overlays in spotlight-filter mode. */
export function complementWithin(
  domain: [number, number],
  intervals: { start: number; end: number }[]
): { start: number; end: number }[] {
  const merged = mergeIntervals(
    intervals.map((i) => ({
      start: Math.max(i.start, domain[0]),
      end: Math.min(i.end, domain[1]),
    })).filter((i) => i.end > i.start)
  );
  if (merged.length === 0) return [{ start: domain[0], end: domain[1] }];

  const out: { start: number; end: number }[] = [];
  let cursor = domain[0];
  for (const m of merged) {
    if (m.start > cursor) out.push({ start: cursor, end: m.start });
    cursor = Math.max(cursor, m.end);
  }
  if (cursor < domain[1]) out.push({ start: cursor, end: domain[1] });
  return out;
}
