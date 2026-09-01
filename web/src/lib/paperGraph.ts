import { splitMulti } from "./loadPublications";
import type { Publication } from "../types";

export type GraphPublication = Publication;

/**
 * Apply hub filter: drop values that appear in more than hubThreshold fraction
 * of pubs, across whichever fields are currently selected as graph edges (not
 * a fixed field list - it needs to generalize to whatever's actually selected,
 * since Publications no longer carries dedicated SciLite/dataset-derived
 * columns to hardcode against).
 *
 * This is the only transformation that stays in React because it is driven by
 * a user-controlled slider in the Knowledge Graph view.
 */
export function applyToPubs(
  pubs: Publication[],
  hubThreshold: number,
  fields: readonly (keyof Publication & string)[],
): GraphPublication[] {
  if (hubThreshold >= 1 || fields.length === 0) return pubs;

  const totalPapers = pubs.length || 1;
  const valueCount = new Map<string, number>();

  for (const p of pubs) {
    const seen = new Set<string>();
    for (const field of fields) {
      for (const v of splitMulti(p[field])) {
        if (!seen.has(v)) {
          seen.add(v);
          valueCount.set(v, (valueCount.get(v) ?? 0) + 1);
        }
      }
    }
  }

  const hubExclude = new Set<string>();
  for (const [v, n] of valueCount) {
    if (n / totalPapers > hubThreshold) hubExclude.add(v);
  }

  return pubs.map((p) => {
    const next = { ...p };
    for (const field of fields) {
      next[field] = splitMulti(p[field])
        .filter((v) => !hubExclude.has(v))
        .join(";");
    }
    return next;
  });
}

export const PAPER_GRAPH_FIELD_OPTIONS = [
  { field: "Authors" as const, label: "Authors", delimiter: ";" },
  { field: "Resource Name" as const, label: "Study", delimiter: ";" },
];
