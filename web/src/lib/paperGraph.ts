import { splitMulti } from "./loadPublications";
import type { Publication } from "../types";

/**
 * GraphPublication is now identical to Publication — the annotation columns
 * (Diseases (Annotated), Genes / Proteins, Chemicals, Cited Datasets) are
 * pre-computed by the Python pipeline (staging/join_annotations.py) and baked into
 * the publications TSV. This alias is kept so call sites don't need updating.
 */
export type GraphPublication = Publication;

/**
 * Apply hub filter: drop values that appear in more than hubThreshold fraction
 * of pubs from the four annotation columns. Pass hubThreshold >= 1 to disable.
 *
 * This is the only transformation that stays in React because it is driven by
 * a user-controlled slider in the Knowledge Graph view.
 */
export function applyToPubs(
  _index: unknown,
  pubs: Publication[],
  hubThreshold: number = 1.1,
): GraphPublication[] {
  if (hubThreshold >= 1) return pubs;

  const annotationFields = [
    "Diseases (Annotated)",
    "Genes / Proteins",
    "Chemicals",
    "Cited Datasets",
  ] as const;

  const totalPapers = pubs.length || 1;
  const valueCount = new Map<string, number>();

  for (const p of pubs) {
    const seen = new Set<string>();
    for (const field of annotationFields) {
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
    const filter = (field: typeof annotationFields[number]) =>
      splitMulti(p[field])
        .filter((v) => !hubExclude.has(v))
        .join(";");

    return {
      ...p,
      "Diseases (Annotated)": filter("Diseases (Annotated)"),
      "Genes / Proteins": filter("Genes / Proteins"),
      "Chemicals": filter("Chemicals"),
      "Cited Datasets": filter("Cited Datasets"),
    };
  });
}

/**
 * Stub: index is no longer needed since annotation columns are pre-computed.
 * Kept for backwards compatibility with PublicationsPage call sites.
 */
export function indexAnnotations(): unknown {
  return {};
}

export const PAPER_GRAPH_FIELD_OPTIONS = [
  { field: "Diseases (Annotated)" as const, label: "Diseases (SciLite)", delimiter: ";" },
  { field: "Genes / Proteins" as const, label: "Genes / Proteins (SciLite)", delimiter: ";" },
  { field: "Chemicals" as const, label: "Chemicals (SciLite)", delimiter: ";" },
  { field: "Cited Datasets" as const, label: "Cited Datasets", delimiter: ";" },
  { field: "Authors" as const, label: "Authors", delimiter: ";" },
  { field: "Resource Name" as const, label: "Study", delimiter: ";" },
];
