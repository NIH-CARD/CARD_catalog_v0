/**
 * Deterministic force-directed layout (Fruchterman-Reingold with a weak pull to
 * the center), the in-browser counterpart of the legacy Streamlit graph's
 * networkx spring_layout(seed=42): connected nodes cluster, unrelated ones spread.
 * A fixed seed keeps the picture stable across renders and reloads.
 */

export interface LayoutEdge {
  i: number;
  j: number;
}

/** Small seeded PRNG (mulberry32) - Math.random would reshuffle the layout every render. */
function seededRandom(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Node positions in px, centered on (0, 0). Iterations shrink as n grows so large graphs stay responsive.
 * Attraction on each endpoint is divided by its degree, so a dense group (e.g. every resource sharing
 * "Alzheimer's Disease") spreads into a readable cluster instead of collapsing onto one point; a final
 * pass pushes apart dots that still overlap, given their radii.
 */
function layoutComponent(
  n: number,
  edges: readonly LayoutEdge[],
  radii: readonly number[],
  seed: number,
): { x: number; y: number }[] {
  if (n === 0) return [];
  if (n === 1) return [{ x: 0, y: 0 }];

  const rand = seededRandom(seed);
  const side = Math.max(400, Math.sqrt(n) * 90);
  const k = side / Math.sqrt(n); // ideal edge length
  const iterations = n <= 150 ? 300 : n <= 400 ? 200 : 100;
  const gravity = 0.05;

  const x = Float64Array.from({ length: n }, () => (rand() - 0.5) * side);
  const y = Float64Array.from({ length: n }, () => (rand() - 0.5) * side);
  const dx = new Float64Array(n);
  const dy = new Float64Array(n);
  const degree = new Float64Array(n);
  for (const { i, j } of edges) {
    degree[i]++;
    degree[j]++;
  }

  for (let it = 0; it < iterations; it++) {
    dx.fill(0);
    dy.fill(0);
    // Repulsion between every pair
    for (let a = 0; a < n; a++) {
      for (let b = a + 1; b < n; b++) {
        const ddx = x[a] - x[b];
        const ddy = y[a] - y[b];
        const d2 = Math.max(ddx * ddx + ddy * ddy, 0.01);
        const f = (k * k) / d2; // (k^2 / d) / d - normalizes the direction vector
        dx[a] += ddx * f;
        dy[a] += ddy * f;
        dx[b] -= ddx * f;
        dy[b] -= ddy * f;
      }
    }
    // Attraction along edges
    for (const { i, j } of edges) {
      const ddx = x[i] - x[j];
      const ddy = y[i] - y[j];
      const d = Math.max(Math.sqrt(ddx * ddx + ddy * ddy), 0.01);
      const f = d / k; // (d^2 / k) / d
      dx[i] -= (ddx * f) / degree[i];
      dy[i] -= (ddy * f) / degree[i];
      dx[j] += (ddx * f) / degree[j];
      dy[j] += (ddy * f) / degree[j];
    }
    // Move, capped by a cooling temperature; gravity keeps disconnected nodes in frame
    const temperature = (side / 10) * (1 - it / iterations) + 1;
    for (let a = 0; a < n; a++) {
      dx[a] -= x[a] * gravity;
      dy[a] -= y[a] * gravity;
      const len = Math.max(Math.sqrt(dx[a] * dx[a] + dy[a] * dy[a]), 0.01);
      const step = Math.min(len, temperature);
      x[a] += (dx[a] / len) * step;
      y[a] += (dy[a] / len) * step;
    }
  }
  // Overlap removal: push apart any two dots closer than their radii plus a small gap
  const gap = 3;
  for (let pass = 0; pass < 40; pass++) {
    let moved = false;
    for (let a = 0; a < n; a++) {
      for (let b = a + 1; b < n; b++) {
        const minD = (radii[a] ?? 5) + (radii[b] ?? 5) + gap;
        const ddx = x[a] - x[b];
        const ddy = y[a] - y[b];
        const d = Math.sqrt(ddx * ddx + ddy * ddy);
        if (d >= minD) continue;
        moved = true;
        const ux = d > 0.01 ? ddx / d : rand() - 0.5;
        const uy = d > 0.01 ? ddy / d : rand() - 0.5;
        const push = (minD - d) / 2;
        x[a] += ux * push;
        y[a] += uy * push;
        x[b] -= ux * push;
        y[b] -= uy * push;
      }
    }
    if (!moved) break;
  }
  return Array.from({ length: n }, (_, a) => ({ x: x[a], y: y[a] }));
}

/**
 * Node positions in px. Each connected component is laid out on its own and the
 * components are then packed side by side, largest first - laying out disconnected
 * groups together lets them repel each other far apart and shrinks everything to
 * specks once the view is fit. Isolated nodes fill a compact grid after them.
 */
export function forceLayout(
  n: number,
  edges: readonly LayoutEdge[],
  radii: readonly number[] = [],
  seed = 42,
): { x: number; y: number }[] {
  const parent = Array.from({ length: n }, (_, i) => i);
  const find = (a: number): number => (parent[a] === a ? a : (parent[a] = find(parent[a])));
  for (const { i, j } of edges) parent[find(i)] = find(j);
  const groups = new Map<number, number[]>();
  for (let a = 0; a < n; a++) {
    const root = find(a);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root)!.push(a);
  }
  const components = [...groups.values()].sort((a, b) => b.length - a.length);

  // Lay out each component and record its bounding box (radii included)
  const placed = components.map((members) => {
    const local = new Map(members.map((g, l) => [g, l]));
    const localEdges = edges
      .filter(({ i }) => local.has(i))
      .map(({ i, j }) => ({ i: local.get(i)!, j: local.get(j)! }));
    const localRadii = members.map((g) => radii[g] ?? 5);
    const pos = layoutComponent(members.length, localEdges, localRadii, seed);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    pos.forEach(({ x, y }, l) => {
      minX = Math.min(minX, x - localRadii[l]);
      minY = Math.min(minY, y - localRadii[l]);
      maxX = Math.max(maxX, x + localRadii[l]);
      maxY = Math.max(maxY, y + localRadii[l]);
    });
    return { members, pos, minX, minY, w: maxX - minX, h: maxY - minY };
  });

  // Shelf packing: fill rows up to a width that keeps the overall shape roughly square
  const margin = 40;
  const totalArea = placed.reduce((sum, c) => sum + (c.w + margin) * (c.h + margin), 0);
  const rowWidth = Math.max(Math.sqrt(totalArea) * 1.3, ...placed.map((c) => c.w + margin));
  const out = new Array<{ x: number; y: number }>(n);
  let cx = 0, cy = 0, rowH = 0;
  for (const c of placed) {
    if (cx > 0 && cx + c.w > rowWidth) {
      cx = 0;
      cy += rowH + margin;
      rowH = 0;
    }
    c.members.forEach((g, l) => {
      out[g] = { x: cx + (c.pos[l].x - c.minX), y: cy + (c.pos[l].y - c.minY) };
    });
    cx += c.w + margin;
    rowH = Math.max(rowH, c.h);
  }
  return out;
}
