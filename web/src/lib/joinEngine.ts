import { splitMulti } from "./loadPublications";

/** An attribute to join on: the field name, plus its multi-value delimiter
 * (";" for almost every column in the catalog; "," for Coarse Data Modality).
 * Omit delimiter for a scalar (single-value) field. */
export interface JoinAttribute<T> {
  field: keyof T & string;
  delimiter?: string;
}

/** One matched pair of rows, plus the actual value(s) that connected them -
 * a left/right pair sharing several values (e.g. two overlapping diseases)
 * produces one match with multiple sharedValues, not one match per value. */
export interface JoinMatch<A, B> {
  left: A;
  right: B;
  sharedValues: string[];
}

export interface JoinResult<A, B> {
  matches: JoinMatch<A, B>[];
  /** Total matches found, independent of any downstream rendering cap -
   * this is what the "showing 60 of 3,412" honest-count UI reads from. */
  matchCount: number;
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function valuesOf<T>(row: T, attr: JoinAttribute<T>): string[] {
  const raw = row[attr.field];
  return typeof raw === "string" ? splitMulti(raw, attr.delimiter) : [];
}

/**
 * Join two row collections on a chosen attribute pair, connecting any left/right
 * row whose attribute value sets intersect (case-insensitive, whitespace-trimmed).
 * Multi-value fields are split by their delimiter before comparing, so a single
 * exact-match field (e.g. PubMed Central Link) and a genuinely multi-value field
 * (e.g. Diseases Included) both work through the same mechanism - an exact-match
 * join is just the one-value-per-side special case.
 *
 * Pure, React-free, and index-based (not pairwise O(n*m)) so it stays usable
 * against the catalog's larger tables.
 */
export function joinRows<A extends object, B extends object>(
  leftRows: readonly A[],
  leftAttr: JoinAttribute<A>,
  rightRows: readonly B[],
  rightAttr: JoinAttribute<B>,
): JoinResult<A, B> {
  const rightIndex = new Map<string, { row: B; original: string }[]>();
  for (const row of rightRows) {
    for (const value of valuesOf(row, rightAttr)) {
      const key = normalize(value);
      if (!key) continue;
      const bucket = rightIndex.get(key);
      if (bucket) bucket.push({ row, original: value });
      else rightIndex.set(key, [{ row, original: value }]);
    }
  }

  const matches: JoinMatch<A, B>[] = [];
  for (const leftRow of leftRows) {
    const perRight = new Map<B, string[]>();
    for (const leftValue of valuesOf(leftRow, leftAttr)) {
      const key = normalize(leftValue);
      if (!key) continue;
      const bucket = rightIndex.get(key);
      if (!bucket) continue;
      for (const { row: rightRow, original } of bucket) {
        const shared = perRight.get(rightRow);
        if (shared) {
          if (!shared.includes(original)) shared.push(original);
        } else {
          perRight.set(rightRow, [original]);
        }
      }
    }
    for (const [rightRow, sharedValues] of perRight) {
      matches.push({ left: leftRow, right: rightRow, sharedValues });
    }
  }

  return { matches, matchCount: matches.length };
}
