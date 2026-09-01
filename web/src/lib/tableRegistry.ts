import {
  loadCellularModels,
  loadCodeRepos,
  loadPubDatasets,
  loadPubGrants,
  loadPubModels,
  loadPublications,
  loadPubSoftware,
  loadResources,
  loadSciLite,
  loadSupplementary,
} from "./loaders";

type Row = Record<string, unknown>;

export interface ColumnMeta {
  field: string;
  multivalue: boolean;
  /** Only meaningful when multivalue is true. Defaults to ";" if omitted. */
  delimiter?: string;
}

export interface TableMeta {
  name: string;
  route: string;
  columns: ColumnMeta[];
  /** Lazy loader - only called the first time this table is actually selected. */
  loadRows: () => Promise<Row[]>;
}

const col = (field: string, multivalue = false, delimiter?: string): ColumnMeta => ({
  field,
  multivalue,
  delimiter,
});

/**
 * Table schema + delimiter registry - the single source of truth this app
 * previously duplicated across each page's own facet configuration (FACETS /
 * GRAPH_FIELD_OPTIONS arrays) and the Docs page's schema listing. Explore
 * reads this for free (schema browsing costs no data load) and to know how
 * to split each attribute's value before joining.
 *
 * Multivalue/delimiter facts are drawn from each page's authoritative facet
 * declarations, cross-checked against known pipeline normalization behavior
 * where a field is multivalue but not currently exposed as its own facet on
 * any page (e.g. Publications' Abbreviation, Code Repositories' FAIR Issues).
 * Fields with no positive evidence either way default to single-value -
 * treating an actually-multivalue field as single degrades a join rather than
 * breaking it, which is the safer default.
 */
export const TABLE_REGISTRY: readonly TableMeta[] = [
  {
    name: "Resources",
    route: "/resources",
    loadRows: () => loadResources() as unknown as Promise<Row[]>,
    columns: [
      col("Resource Name"),
      col("Abbreviation"),
      col("Coarse Data Modality", true, ","),
      col("Granular Data Modality", true, ";"),
      col("Diseases Included", true, ";"),
      col("Sample Size"),
      col("Access URL"),
      col("FAIR Compliance Notes"),
      col("Date added to catalog"),
      col("Reviewer"),
      col("Alternative URLs"),
      col("Resource Type", true, ","),
      col("Is Part Of", true, ";"),
      col("Remove"),
      col("Notes"),
      col("new_corpus"),
    ],
  },
  {
    name: "Publications",
    route: "/publications",
    loadRows: () => loadPublications() as unknown as Promise<Row[]>,
    columns: [
      col("PMID"),
      col("DOI"),
      col("Resource Name", true, ";"),
      col("Abbreviation", true, ";"),
      col("PubMed Central Link"),
      col("Authors", true, ";"),
      col("Affiliations", true, ";"),
      col("Title"),
      col("Abstract"),
      col("Keywords", true, ";"),
      col("Publication Date"),
      col("Publication Year"),
      col("Data Completeness"),
    ],
  },
  {
    name: "Code Repositories",
    route: "/code",
    loadRows: () => loadCodeRepos() as unknown as Promise<Row[]>,
    columns: [
      col("Resource Name", true, ";"),
      col("Abbreviation", true, ";"),
      col("Repository Link"),
      col("Source"),
      col("Owner"),
      col("Contributors", true, ";"),
      col("Languages", true, ";"),
      col("Biomedical Relevance"),
      col("Relevance Rationale"),
      col("Code Summary"),
      col("Data Types", true, ";"),
      col("Tooling", true, ";"),
      col("FAIR Score"),
      col("FAIR Issues", true, ";"),
    ],
  },
  {
    name: "Datasets",
    route: "/annotations",
    loadRows: () => loadPubDatasets() as unknown as Promise<Row[]>,
    columns: [
      col("pub_title"),
      col("source_url"),
      col("raw_data_format"),
      col("dataset_identifier"),
      col("data_repository"),
      col("dataset_context_from_paper"),
      col("dataset_keywords", true, ","),
      col("citation_type"),
      col("dataset_webpage"),
      col("access_mode"),
    ],
  },
  {
    name: "Supplementary Files",
    route: "/annotations/supplementary",
    loadRows: () => loadSupplementary() as unknown as Promise<Row[]>,
    columns: [
      col("link"),
      col("source_url"),
      col("download_link"),
      col("title"),
      col("content_type"),
      col("caption"),
      col("description"),
      col("context_description"),
      col("source_section"),
      col("file_extension"),
      col("pub_title"),
      col("raw_data_format"),
    ],
  },
  {
    name: "Grants",
    route: "/annotations/grants",
    loadRows: () => loadPubGrants() as unknown as Promise<Row[]>,
    columns: [
      col("source_url"),
      col("funder_name"),
      col("grant_number"),
      col("funding_context_from_paper"),
      col("recipient"),
    ],
  },
  {
    name: "Software",
    route: "/annotations/software",
    loadRows: () => loadPubSoftware() as unknown as Promise<Row[]>,
    columns: [
      col("source_url"),
      col("software_name"),
      col("version"),
      col("mention_type"),
      col("url"),
      col("context_from_paper"),
    ],
  },
  {
    name: "Models",
    route: "/annotations/models",
    loadRows: () => loadPubModels() as unknown as Promise<Row[]>,
    columns: [
      col("source_url"),
      col("model_name"),
      col("version"),
      col("mention_type"),
      col("url"),
      col("context_from_paper"),
    ],
  },
  {
    name: "SciLite Annotations",
    route: "/annotations/scilite",
    loadRows: () => loadSciLite() as unknown as Promise<Row[]>,
    columns: [
      col("PMC ID"),
      col("Type"),
      col("Exact"),
      col("Prefix"),
      col("Postfix"),
      col("Section"),
      col("Provider"),
      col("Annotation ID"),
      col("Tag Name"),
      col("Tag URI"),
    ],
  },
  {
    name: "Human Cellular Models",
    route: "/cellular-models",
    loadRows: () => loadCellularModels() as unknown as Promise<Row[]>,
    columns: [
      col("Product Code"),
      col("Parental Line"),
      col("Gene"),
      col("Gene Variant"),
      col("Genotype"),
      col("dbSNP"),
      col("Condition"),
      col("Other Names"),
      col("Genome Assembly"),
      col("Protospacer Sequence"),
      col("Genomic Coordinate"),
      col("Genomic Sequence"),
      col("Procurement link"),
      col("About this gene"),
      col("About this variant"),
      col("Linked Publications", true, ";"),
      col("Linked Studies", true, ";"),
    ],
  },
];

export function findTable(name: string): TableMeta | undefined {
  return TABLE_REGISTRY.find((t) => t.name === name);
}

export function findColumn(tableName: string, field: string): ColumnMeta | undefined {
  return findTable(tableName)?.columns.find((c) => c.field === field);
}

/** One known-good attribute pairing between two tables, offered as the
 * auto-suggested default when adding a hop - always overridable, per the PRD.
 * Verified against real data during Explore's design, not guessed:
 * Code Repositories' `Source` is deliberately excluded here even though it
 * can link to Publications, because it only does so for ~55% of rows (the
 * rest is discovery-method text); `Resource Name` is the reliable default.
 *
 * `extract: "pmcid"` marks a pairing where the two fields aren't literally
 * equal strings (a bare "PMC1234567" vs. a full PMC URL) and both sides need
 * a PMC ID pulled out (via loadPublications.ts's pmcidFrom) before comparing.
 */
export interface JoinSuggestion {
  tableA: string;
  fieldA: string;
  tableB: string;
  fieldB: string;
  extract?: "pmcid";
}

const JOIN_SUGGESTIONS: readonly JoinSuggestion[] = [
  { tableA: "Datasets", fieldA: "source_url", tableB: "Publications", fieldB: "PubMed Central Link" },
  { tableA: "Supplementary Files", fieldA: "source_url", tableB: "Publications", fieldB: "PubMed Central Link" },
  { tableA: "Grants", fieldA: "source_url", tableB: "Publications", fieldB: "PubMed Central Link" },
  { tableA: "Software", fieldA: "source_url", tableB: "Publications", fieldB: "PubMed Central Link" },
  { tableA: "Models", fieldA: "source_url", tableB: "Publications", fieldB: "PubMed Central Link" },
  { tableA: "SciLite Annotations", fieldA: "PMC ID", tableB: "Publications", fieldB: "PubMed Central Link", extract: "pmcid" },
  { tableA: "Code Repositories", fieldA: "Resource Name", tableB: "Resources", fieldB: "Resource Name" },
  // Not Gene <-> SciLite's Exact: that match needs raw per-annotation SciLite rows
  // (~270MB, never loaded client-side). Linked Publications is precomputed
  // server-side instead (staging/publication_glue.py::join_cellular_model_publications),
  // resolving the same Gene/dbSNP relationship into a plain PMC ID list.
  { tableA: "Human Cellular Models", fieldA: "Linked Publications", tableB: "Publications", fieldB: "PubMed Central Link", extract: "pmcid" },
];

/** Looks up a known-good pairing between two tables, in either order. */
export function suggestJoin(tableA: string, tableB: string): JoinSuggestion | undefined {
  return JOIN_SUGGESTIONS.find(
    (s) =>
      (s.tableA === tableA && s.tableB === tableB) ||
      (s.tableA === tableB && s.tableB === tableA),
  );
}
