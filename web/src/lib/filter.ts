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
  // selected holds canonical values when spec.canonicalize is set (see
  // FacetPanel) — canonicalize each row value the same way before matching,
  // or a selected chip would only match its own exact raw spelling.
  for (const v of values) {
    if (selected.has(spec.canonicalize?.(v) ?? v)) return true;
  }
  return false;
}

// The query is compiled as a case-insensitive regex, not matched literally -
// an ordinary word (no metacharacters) behaves exactly like today's substring
// search, but a query like "rna.*seq" or "rna[-_ ]?seq" now genuinely means
// what it looks like it means. This is deliberately not auto-normalized
// (stripping dashes/underscores/spaces) - that would silently rewrite what
// the user typed; regex syntax lets them express exactly the match they
// want, including cases separator-stripping can't (optional characters,
// alternation, anchors).
//
// A single-entry cache: every row in one filter pass shares the same query,
// so this avoids recompiling the RegExp per row - re-checked by reference
// equality against the exact query string across calls.
let compiledCache: { source: string; re: RegExp | null } | null = null;

function compileQuery(q: string): RegExp | null {
  if (compiledCache?.source === q) return compiledCache.re;
  let re: RegExp | null;
  try {
    re = new RegExp(q, "i");
  } catch {
    // Invalid regex (e.g. an unbalanced "(" mid-typing) - no matches rather
    // than throwing or silently falling back to a different match strategy.
    re = null;
  }
  compiledCache = { source: q, re };
  return re;
}

export function matchesQuery<T>(row: T, fields: (keyof T & string)[], q: string): boolean {
  if (!q) return true;
  const re = compileQuery(q);
  if (!re) return false;
  for (const f of fields) {
    const v = row[f];
    if (v && re.test(String(v))) return true;
  }
  return false;
}
