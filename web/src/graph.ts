// Heart-rate graph segments: only CONSECUTIVE valid readings connect.
// A gap in readings or an invalid reading breaks the line — missing data is
// never interpolated or drawn as zero (docs/PROJECT_SPEC.md honesty rules).

export interface GraphPoint {
  t: number; // seconds from window start
  bpm: number;
  valid: boolean;
  status: string | null;
}

export interface Segment {
  points: GraphPoint[];
}

const MAX_GAP_S = 4; // >3 s carry rule means readings older than that are stale

export function buildSegments(points: GraphPoint[]): Segment[] {
  const sorted = [...points].sort((a, b) => a.t - b.t);
  const segments: Segment[] = [];
  let current: GraphPoint[] = [];
  let lastValidT: number | null = null;

  for (const p of sorted) {
    if (!p.valid) {
      // Invalid reading: end the current line here (visible gap).
      if (current.length > 0) segments.push({ points: current });
      current = [];
      lastValidT = null;
      continue;
    }
    if (lastValidT !== null && p.t - lastValidT > MAX_GAP_S) {
      if (current.length > 0) segments.push({ points: current });
      current = [];
    }
    current.push(p);
    lastValidT = p.t;
  }
  if (current.length > 0) segments.push({ points: current });
  return segments;
}

export function formatDuration(ms: number): string {
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function levelForXp(xp: number): number {
  return 1 + Math.floor(xp / 100);
}
