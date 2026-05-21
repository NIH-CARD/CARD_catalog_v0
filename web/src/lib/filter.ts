import type { FacetSpec } from "../types";
import { splitMulti } from "./loadPublications";

export function matchesFacet<T>(
  row: T,
  spec: FacetSpec<T>,
  selected: Set<string>,
): boolean {
  if (selected.size === 0) return true;
  const raw = (row[spec.field] ?? "") as unknown as string;
  const values = spec.multivalue
    ? splitMulti(raw, spec.delimiter)
    : raw
      ? [String(raw).trim()]
      : [];
  for (const v of values) if (selected.has(v)) return true;
  return false;
}

export function matchesQuery<T>(row: T, fields: (keyof T & string)[], q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  for (const f of fields) {
    const v = row[f];
    if (v && String(v).toLowerCase().includes(needle)) return true;
  }
  return false;
}
