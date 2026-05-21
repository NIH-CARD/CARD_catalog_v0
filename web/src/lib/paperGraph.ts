import { pmcidFrom } from "./loadPublications";
import type {
  PubDataset,
  Publication,
  SciLiteAnnotation,
} from "../types";

/**
 * Augmented publication row carrying paper-grounded value sets used as both
 * filter-rail facets and KG edge sources.
 *
 * The values stored in these columns are URIs (or dataset identifiers) — not
 * human-readable names. Resolve to names via :func:`AnnotationIndex.conceptMeta`.
 */
export type GraphPublication = Publication & {
  "Diseases (Annotated)": string;
  "Genes / Proteins": string;

  "Chemicals": string;
  "Cited Datasets": string;
};

const SCILITE_TYPE_TO_FIELD: Record<string, keyof GraphPublication> = {
  Diseases: "Diseases (Annotated)",
  Gene_Proteins: "Genes / Proteins",

  Chemicals: "Chemicals",
};

export interface ConceptMeta {
  /** Best human-readable name (most common Tag Name for this URI). */
  name: string;
  /** SciLite annotation type, e.g. "Diseases". */
  type: string;
}

/**
 * Pre-computed indices over the SciLite + datasets corpus. These don't depend
 * on which subset of publications you're looking at, so build once and reuse
 * across multiple :func:`applyToPubs` calls.
 */
export interface AnnotationIndex {
  /** PMC ID -> SciLite annotation type -> Set of Tag URIs. */
  pmcConcepts: Map<string, Map<string, Set<string>>>;
  /** Tag URI -> display metadata (canonical name + type). */
  conceptMeta: Map<string, ConceptMeta>;
  /** PMC ID -> Set of cited dataset identifiers. */
  pmcDatasets: Map<string, Set<string>>;
  /** Dataset identifier -> {repository}. */
  datasetMeta: Map<string, { repository: string }>;
}

/**
 * Build all per-PMC concept/dataset maps + the URI->display-name lookup.
 *
 * Idempotent and corpus-agnostic — call this once for the full corpus.
 */
export function indexAnnotations(
  scilite: SciLiteAnnotation[],
  datasets: PubDataset[],
): AnnotationIndex {
  const pmcConcepts = new Map<string, Map<string, Set<string>>>();
  const conceptMeta = new Map<string, ConceptMeta>();
  const nameCount = new Map<string, Map<string, number>>();

  for (const ann of scilite) {
    const pmc = ann["PMC ID"];
    const uri = ann["Tag URI"];
    const name = ann["Tag Name"];
    const type = ann.Type;
    if (!pmc || !uri || !type) continue;

    let byType = pmcConcepts.get(pmc);
    if (!byType) {
      byType = new Map();
      pmcConcepts.set(pmc, byType);
    }
    let set = byType.get(type);
    if (!set) {
      set = new Set();
      byType.set(type, set);
    }
    set.add(uri);

    let names = nameCount.get(uri);
    if (!names) {
      names = new Map();
      nameCount.set(uri, names);
    }
    names.set(name, (names.get(name) ?? 0) + 1);
    if (!conceptMeta.has(uri)) conceptMeta.set(uri, { name, type });
  }

  for (const [uri, names] of nameCount) {
    let bestName = "";
    let bestN = -1;
    for (const [n, c] of names) {
      if (c > bestN) {
        bestN = c;
        bestName = n;
      }
    }
    const meta = conceptMeta.get(uri);
    if (meta) meta.name = bestName || meta.name;
  }

  const pmcDatasets = new Map<string, Set<string>>();
  const datasetMeta = new Map<string, { repository: string }>();
  for (const d of datasets) {
    const pmc = pmcidFrom(d.source_url);
    if (!pmc) continue;
    const id = d.dataset_identifier;
    if (!id) continue;
    let s = pmcDatasets.get(pmc);
    if (!s) {
      s = new Set();
      pmcDatasets.set(pmc, s);
    }
    s.add(id);
    if (!datasetMeta.has(id)) {
      datasetMeta.set(id, { repository: d.data_repository });
    }
  }

  return { pmcConcepts, conceptMeta, pmcDatasets, datasetMeta };
}

/**
 * Augment a publication list with paper-grounded columns derived from the
 * given index. ``hubThreshold`` (fraction in 0..1) drops URIs that appear in
 * more than that fraction of ``pubs``; pass any value >= 1 to disable.
 */
export function applyToPubs(
  index: AnnotationIndex,
  pubs: Publication[],
  hubThreshold: number = 1.1,
): GraphPublication[] {
  const { pmcConcepts, pmcDatasets } = index;
  const totalPapers = pubs.length || 1;

  const hubExclude = new Set<string>();
  if (hubThreshold < 1) {
    const uriPaperCount = new Map<string, number>();
    for (const p of pubs) {
      const pmc = pmcidFrom(p["PubMed Central Link"]);
      const byType = pmc ? pmcConcepts.get(pmc) : undefined;
      if (!byType) continue;
      const seenForThisPmc = new Set<string>();
      for (const [, uris] of byType) {
        for (const uri of uris) {
          if (seenForThisPmc.has(uri)) continue;
          seenForThisPmc.add(uri);
          uriPaperCount.set(uri, (uriPaperCount.get(uri) ?? 0) + 1);
        }
      }
    }
    for (const [uri, n] of uriPaperCount) {
      if (n / totalPapers > hubThreshold) hubExclude.add(uri);
    }
  }

  return pubs.map((p) => {
    const pmc = pmcidFrom(p["PubMed Central Link"]);
    const byType = pmc ? pmcConcepts.get(pmc) : undefined;

    const getField = (type: string) => {
      if (!byType) return "";
      const uris = byType.get(type);
      if (!uris) return "";
      return Array.from(uris)
        .filter((u) => !hubExclude.has(u))
        .join(";");
    };

    const datasetIds = pmc ? pmcDatasets.get(pmc) : undefined;
    const datasetField = datasetIds ? Array.from(datasetIds).join(";") : "";

    return {
      ...p,
      "Diseases (Annotated)": getField("Diseases"),
      "Genes / Proteins": getField("Gene_Proteins"),

      "Chemicals": getField("Chemicals"),
      "Cited Datasets": datasetField,
    };
  });
}

/**
 * Convenience wrapper: index + apply in one call. Prefer the split form when
 * you'll augment multiple publication subsets (e.g. rail vs. graph).
 */
export function buildGraphData(
  pubs: Publication[],
  scilite: SciLiteAnnotation[],
  datasets: PubDataset[],
  hubThreshold: number = 1.1,
): { rows: GraphPublication[]; conceptMeta: AnnotationIndex["conceptMeta"]; datasetMeta: AnnotationIndex["datasetMeta"] } {
  const index = indexAnnotations(scilite, datasets);
  const rows = applyToPubs(index, pubs, hubThreshold);
  return { rows, conceptMeta: index.conceptMeta, datasetMeta: index.datasetMeta };
}

export const PAPER_GRAPH_FIELD_OPTIONS = [
  { field: "Diseases (Annotated)" as const, label: "Diseases (SciLite)", delimiter: ";" },
  { field: "Genes / Proteins" as const, label: "Genes / Proteins (SciLite)", delimiter: ";" },

  { field: "Chemicals" as const, label: "Chemicals (SciLite)", delimiter: ";" },
  { field: "Cited Datasets" as const, label: "Cited Datasets", delimiter: ";" },
];

export { SCILITE_TYPE_TO_FIELD };
