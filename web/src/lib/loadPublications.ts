import Papa from "papaparse";

export async function loadTsv<T extends object>(path: string): Promise<T[]> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
  const text = await res.text();
  return new Promise((resolve, reject) => {
    Papa.parse<T>(text, {
      header: true,
      delimiter: "\t",
      skipEmptyLines: true,
      complete: (result) => resolve(result.data),
      error: (err: Error) => reject(err),
    });
  });
}

/** Split a delimited multivalue field into trimmed parts. Default delimiter is ";". */
export function splitMulti(value: string | undefined, delimiter: string = ";"): string[] {
  if (!value) return [];
  return value
    .split(delimiter)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Extract the first PMC\d+ ID from a URL or arbitrary string. */
export function pmcidFrom(s: string | undefined): string {
  if (!s) return "";
  const m = String(s).match(/PMC\d+/);
  return m ? m[0] : "";
}

/** Derive a publication year from "Publication Date" - not a real column, format varies
 * ("2026", "2025 Dec", "2025-05-05", "2026 Jan 21", and older "Mon YYYY" rows), so pull
 * out a real 4-digit year token instead of assuming a fixed position. */
export function publicationYearFrom(date: string | undefined): string {
  return date?.match(/\b(19|20)\d{2}\b/)?.[0] ?? "";
}
