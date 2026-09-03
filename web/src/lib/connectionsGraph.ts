import { pmcidFrom, splitMulti } from "./loadPublications";
import { TABLE_REGISTRY, type ColumnMeta } from "./tableRegistry";

type Row = Record<string, unknown>;
export type Domain = "publication" | "resource" | "concept";

const DOI_RE = /10\.\d{4,9}\/[^\s"'<>]+/;

function doiFrom(value: string): string {
  const m = value.match(DOI_RE);
  return m ? m[0].toLowerCase().replace(/[.,;)\]]+$/, "") : "";
}

/** A publication is identified by whichever of PMC ID / DOI it actually has -
 * ~3.3% of Publications rows are DOI-only (no PMC deposit yet), and a few
 * pub-metadata source_urls are DOI links rather than PMC links, so matching
 * on PMC ID alone would silently drop both. Returns "" (no join) rather than
 * a raw-string fallback when neither identifier is found in the value -
 * an un-normalized generic URL isn't a safe thing to match rows on. */
function publicationKey(value: string): string {
  return pmcidFrom(value) || doiFrom(value);
}

interface FieldSource {
  field: string;
  extract?: (v: string) => string;
}

/** Tables that carry a Publication (PMC ID or DOI) lineage, and the real
 * column(s) to read it from - Publications itself has two (PubMed Central
 * Link, DOI), since either identifies the same row. */
const PUBLICATION_FIELDS: Record<string, FieldSource[]> = {
  Publications: [
    { field: "PubMed Central Link", extract: publicationKey },
    { field: "DOI", extract: publicationKey },
  ],
  Datasets: [{ field: "source_url", extract: publicationKey }],
  "Supplementary Files": [{ field: "source_url", extract: publicationKey }],
  Grants: [{ field: "source_url", extract: publicationKey }],
  Software: [{ field: "source_url", extract: publicationKey }],
  Models: [{ field: "source_url", extract: publicationKey }],
  // Europe PMC's SciLite API is PMC-ID-keyed only - no DOI path exists here.
  "SciLite Annotations": [{ field: "PMC ID", extract: publicationKey }],
  // Precomputed server-side (join_cellular_model_publications, via SciLite's
  // RefSNP annotations) - PMC-ID-only for the same reason as SciLite above.
  "Human Cellular Models": [{ field: "Linked Publications", extract: publicationKey }],
};

/** Tables that carry a Resource Name lineage. Human Cellular Models' Linked
 * Studies (precomputed server-side alongside Linked Publications, see
 * join_cellular_model_publications) is a semicolon list of Resource Name
 * values - a real Resource-domain field, not just a Publication one. */
const RESOURCE_FIELDS: Record<string, FieldSource[]> = {
  Resources: [{ field: "Resource Name" }],
  "Code Repositories": [{ field: "Resource Name" }],
  Publications: [{ field: "Resource Name" }],
  "Human Cellular Models": [{ field: "Linked Studies" }],
};

/** Tables that carry a gene/bioentity concept lineage - verified against real
 * data as Human Cellular Models' Gene against SciLite's Exact (the literal
 * mention text): 89% coverage (99/111 distinct genes), vs. only 53% via
 * SciLite's normalized Tag Name (59/111) - Tag Name often resolves to a full
 * protein name rather than the plain symbol papers actually write. Also NOT
 * routed through Publication (Human Cellular Models' Linked Publications is
 * dbSNP/RefSNP-matched, only ~18% coverage) - Gene<->Exact is its own, more
 * reliable, verified pairing and needs its own domain. */
const CONCEPT_FIELDS: Record<string, FieldSource[]> = {
  "Human Cellular Models": [{ field: "Gene" }],
  "SciLite Annotations": [{ field: "Exact" }],
};

function sourcesFor(domain: Domain): Record<string, FieldSource[]> {
  return domain === "publication" ? PUBLICATION_FIELDS : domain === "resource" ? RESOURCE_FIELDS : CONCEPT_FIELDS;
}

/** Which tables can participate in a given join domain. */
export function tablesInDomain(domain: Domain): string[] {
  return Object.keys(sourcesFor(domain));
}

/** Which domains both tables share - the only join keys valid for merging
 * `table` into `base` (used to populate the DAG's "join key" choices). */
export function validDomainsFor(base: string, table: string): Domain[] {
  return (["publication", "resource", "concept"] as const).filter(
    (d) => tablesInDomain(d).includes(base) && tablesInDomain(d).includes(table),
  );
}

function columnMeta(table: string, field: string): ColumnMeta | undefined {
  return connectionsColumns(table).find((c) => c.field === field);
}

/** A Publication row's own resolved identity key (PMC ID, falling back to
 * DOI - see publicationKey()'s docstring for why not PMID: PMID is blank for
 * DOI-only publications, and Title isn't a safe/unique join key). Exposed
 * for use as a graph "edge field" meaning "same publication" - e.g.
 * connecting two Author nodes because they co-authored one paper - which
 * needs a key that's actually populated for every row, not a specific
 * identifier column that happens to be blank for some.
 *
 * Deliberately NOT domainValue("Publications", row, "publication") - that
 * helper concatenates every identity field it finds (PMC ID *and* DOI, both
 * valid alternate keys for cross-table *joining*), but an edge/identity key
 * needs exactly one value per row: a row with both would otherwise surface
 * as two distinct "shared" values for what is really the same single paper,
 * inflating shared-publication counts. */
export function publicationIdFor(row: Row): string {
  const pmcRaw = row["PubMed Central Link"];
  const pmc = typeof pmcRaw === "string" ? pmcidFrom(pmcRaw) : "";
  if (pmc) return pmc;
  const doiRaw = row["DOI"];
  return typeof doiRaw === "string" ? doiFrom(doiRaw) : "";
}

function domainValue(table: string, row: Row, domain: Domain): string {
  const specs = sourcesFor(domain)[table];
  if (!specs) return "";
  const out: string[] = [];
  for (const spec of specs) {
    const raw = row[spec.field];
    if (typeof raw !== "string" || !raw.trim()) continue;
    const meta = columnMeta(table, spec.field);
    const parts = meta?.multivalue ? splitMulti(raw, meta.delimiter) : [raw];
    const values = spec.extract ? parts.map(spec.extract) : parts;
    out.push(...values.filter(Boolean));
  }
  return out.join(";");
}

/**
 * Overrides tableRegistry.ts's column list for a table whose Connections row
 * source isn't the real table - today, only SciLite Annotations, which loads
 * a small aggregate (loaders.ts's loadSciLitePmcTypeCounts) instead of the
 * ~270MB real table. Prefix/Postfix (per-mention free-text context) and
 * Annotation ID (a unique-by-construction per-mention URL) are excluded -
 * keeping them would balloon the aggregate back toward the raw table's size
 * for no filtering benefit, since they're near-unique per row either way.
 */
const CONNECTIONS_COLUMNS_OVERRIDE: Record<string, ColumnMeta[]> = {
  "SciLite Annotations": [
    { field: "PMC ID", multivalue: false },
    { field: "Type", multivalue: false },
    { field: "Tag Name", multivalue: false },
    { field: "Exact", multivalue: false },
    { field: "Section", multivalue: false },
    { field: "Provider", multivalue: false },
    { field: "Tag URI", multivalue: false },
    { field: "Count", multivalue: false },
  ],
};

/** The columns Connections actually has data for, for a given table - see
 * CONNECTIONS_COLUMNS_OVERRIDE. */
export function connectionsColumns(table: string): ColumnMeta[] {
  return CONNECTIONS_COLUMNS_OVERRIDE[table] ?? TABLE_REGISTRY.find((t) => t.name === table)?.columns ?? [];
}

/**
 * The exact facet fields each table's own dedicated page already filters by
 * (PublicationsPage's FACETS, AnnotationsPage's DS_FACETS/etc.) - narrows a
 * merge-source table's rows before they're joined in, using the same filter
 * vocabulary that table's own page already uses.
 */
const FACET_COLUMNS: Record<string, string[]> = {
  Resources: ["Resource Type", "Diseases Included", "Coarse Data Modality", "Granular Data Modality", "Is Part Of"],
  Publications: ["Resource Name", "Keywords", "Authors", "Publication Year"],
  "Code Repositories": ["Resource Name", "Languages", "Data Types", "Tooling", "Biomedical Relevance"],
  Datasets: ["data_repository", "citation_type", "dataset_keywords"],
  "Supplementary Files": ["file_extension", "content_type", "source_section"],
  Grants: ["funder_name", "grant_number", "recipient"],
  Software: ["software_name", "version", "mention_type"],
  Models: ["model_name", "version", "mention_type"],
  "SciLite Annotations": ["Type", "Section", "Tag Name"],
  "Human Cellular Models": ["Gene", "Condition", "Parental Line", "Genotype"],
};

/** A table's sidebar facet columns in Connections - see FACET_COLUMNS. */
export function facetColumnsFor(table: string): ColumnMeta[] {
  const allowed = FACET_COLUMNS[table];
  if (!allowed) return [];
  const cols = connectionsColumns(table);
  return allowed
    .map((field) => cols.find((c) => c.field === field))
    .filter((c): c is ColumnMeta => c !== undefined);
}

/**
 * Explicit, curated list of a table's own columns worth pulling into the
 * merged wide table (or offering as a same-table graph edge) - deliberately
 * NOT "is it multivalue" (excludes genuinely good single-value connectors
 * like Gene, funder_name, data_repository; would include bad multivalue ones
 * like Notes if any existed). Curated from the CARD Catalog data dictionary
 * (2026-08-31 pietro):
 *
 * - Excludes only identifiers unique BY CONSTRUCTION - internal to this
 *   catalog and never legitimately repeated (PMID, Annotation ID, Product
 *   Code, Protospacer/Genomic Coordinate/Sequence). An identifier of an
 *   *external* resource (a specific dataset, tool, model, or git repo) is
 *   kept even though most rows are unique - two publications citing the same
 *   dataset_identifier/url/Repository Link is a real, valuable connection.
 * - Excludes free text (Title, Abstract, rationale/summary fields,
 *   *_context_from_paper, caption, description, dataset_webpage).
 * - Excludes administrative/QC fields, not catalog content (Sample Size,
 *   Date added to catalog, Reviewer, Remove, Notes, Data Completeness,
 *   Biomedical Relevance, raw_data_format, Genome Assembly, Other Names,
 *   mention_type, software/model version). FAIR Score is the one exception -
 *   still a QC metric, but a numeric one worth actually merging in and
 *   filtering/grouping by, not just seeing in the AI-prompt baseline.
 * - Excludes each table's own Resource Name/Abbreviation - already covered
 *   by the universal Resource domain.
 *
 * Domain fields (PubMed Central Link, DOI, source_url, PMC ID, Linked
 * Publications, Linked Studies, Gene, Exact) are never listed here.
 */
const CONNECTABLE_COLUMNS: Record<string, string[]> = {
  Resources: ["Coarse Data Modality", "Granular Data Modality", "Diseases Included", "Resource Type", "Is Part Of"],
  Publications: ["Authors", "Affiliations", "Keywords", "Publication Year"],
  "Code Repositories": ["Repository Link", "Owner", "Contributors", "Languages", "Data Types", "Tooling", "FAIR Issues", "FAIR Score"],
  Datasets: ["dataset_identifier", "data_repository", "dataset_keywords", "citation_type", "access_mode"],
  "Supplementary Files": ["content_type", "source_section", "file_extension"],
  Grants: ["funder_name", "grant_number", "recipient"],
  Software: ["software_name", "url"],
  Models: ["model_name", "url"],
  "SciLite Annotations": ["Type", "Tag Name", "Exact", "Section", "Provider", "Tag URI"],
  "Human Cellular Models": ["Parental Line", "Gene Variant", "Genotype", "dbSNP", "Condition"],
};

/** A table's own curated shareable columns (CONNECTABLE_COLUMNS), resolved
 * against connectionsColumns() for accurate delimiter/multivalue info. */
export function nativeColumnsFor(table: string): ColumnMeta[] {
  const allowed = CONNECTABLE_COLUMNS[table];
  if (!allowed) return [];
  const cols = connectionsColumns(table);
  return allowed
    .map((field) => cols.find((c) => c.field === field))
    .filter((c): c is ColumnMeta => c !== undefined);
}

/** Namespaced wide-table column key for a merged-in table's column, e.g.
 * "Datasets: dataset_identifier" - namespaced so two merged tables can't
 * collide on a same-named column, and so it's obvious in the Table/Graph
 * view where a column came from. */
export function mergedFieldKey(table: string, field: string): string {
  return `${table}: ${field}`;
}

/** Build a domain-key -> field-values lookup from a table's raw rows - the
 * LEFT JOIN's right-hand side, keyed by the join column so buildWideRows can
 * look up matches for each Publication row in O(1). */
export function buildJoinIndex(table: string, field: string, domain: Domain, rows: readonly Row[]): Map<string, string[]> {
  const meta = columnMeta(table, field);
  const index = new Map<string, string[]>();
  for (const row of rows) {
    const keys = splitMulti(domainValue(table, row, domain), ";");
    if (keys.length === 0) continue;
    const raw = row[field];
    if (typeof raw !== "string" || !raw.trim()) continue;
    const values = meta?.multivalue ? splitMulti(raw, meta.delimiter) : [raw];
    for (const key of keys) {
      const bucket = index.get(key) ?? [];
      for (const v of values) if (!bucket.includes(v)) bucket.push(v);
      index.set(key, bucket);
    }
  }
  return index;
}

/** Look up every value a Publication row's own domain value(s) resolve to in
 * a join index - a value can itself be a semicolon list (e.g. Human Cellular
 * Models' Linked Publications), so every key in it is tried. Values from
 * repeated lookups are deduplicated and joined with "; " (STRING_AGG). */
export function joinedValue(baseDomainValue: string, index: Map<string, string[]>): string {
  const out: string[] = [];
  for (const key of splitMulti(baseDomainValue, ";")) {
    for (const v of index.get(key) ?? []) if (!out.includes(v)) out.push(v);
  }
  return out.join("; ");
}

/** One "merge this table into Publications" step - the DAG's edge. */
export interface DagEdge {
  table: string;
  domain: Domain;
  /** Which of the table's own columns to pull in - each becomes one wide-table column. */
  columns: string[];
}

/**
 * Merge each DagEdge's table into Publications' rows as a *chain*, not
 * independent joins that get unioned - edge 2 operates on the survivors of
 * edge 1, not on the original Publications set, exactly like a sequence of
 * SQL INNER JOINs each narrowing the accumulated result. A Publication with
 * no match on an edge is dropped at that step, before it ever reaches the
 * next one - so with two edges, a row needs a hit on *both* to survive, not
 * either.
 *
 * The join key for every edge is still resolved from Publications' own
 * identity fields (PMC ID/DOI, Resource Name, Gene) via domainValue() - those
 * don't change as rows get merged in, so "chained" here means the row *set*
 * narrows at each step, not that later edges join against an earlier edge's
 * merged-in columns.
 *
 * @param pubRows Publications' own (already facet-filtered) rows.
 * @param edges The DAG's edges, in order - order matters, since each one
 *   narrows what the next one sees.
 * @param rawByTable Each edge table's own (already facet-filtered) raw rows.
 */
export function buildWideRows(
  pubRows: readonly Row[],
  edges: readonly DagEdge[],
  rawByTable: Record<string, Row[] | undefined>,
): Row[] {
  let current: Row[] = pubRows.map((r) => ({ ...r }));

  for (const edge of edges) {
    const rows = rawByTable[edge.table] ?? [];
    const indices = edge.columns.map((field) => ({
      key: mergedFieldKey(edge.table, field),
      index: buildJoinIndex(edge.table, field, edge.domain, rows),
    }));

    const next: Row[] = [];
    for (const row of current) {
      const base = domainValue("Publications", row, edge.domain);
      let anyHit = false;
      for (const { key, index } of indices) {
        const value = joinedValue(base, index);
        row[key] = value;
        if (value) anyHit = true;
      }
      if (anyHit) next.push(row);
    }
    current = next;
  }

  return current;
}

const DOMAIN_SQL_JOIN_KEY: Record<Domain, string> = {
  publication: "pmcid_or_doi(...)",
  resource: "Resource Name",
  concept: "Gene / Exact (gene symbol)",
};

/** One sidebar facet's selected values, in the shape generateSql needs -
 * see toFacetFilters() for converting the UI's Record<field, Set<value>>
 * selections into this. */
export interface FacetFilter {
  field: string;
  values: readonly string[];
}

/** Convert a table's sidebar facet selections (as ConnectionsPage's
 * Record<field, Set<value>> state holds them) into FacetFilter[] - drops
 * any facet with nothing selected. */
export function toFacetFilters(selections: Record<string, Set<string>> | undefined): FacetFilter[] {
  if (!selections) return [];
  return Object.entries(selections)
    .filter(([, values]) => values.size > 0)
    .map(([field, values]) => ({ field, values: Array.from(values) }));
}

function sqlEscape(v: string): string {
  return v.replace(/'/g, "''");
}

function sqlWhereClause(alias: string, filters: readonly FacetFilter[]): string {
  return filters
    .filter((f) => f.values.length > 0)
    .map((f) => `${alias}."${f.field}" IN (${f.values.map((v) => `'${sqlEscape(v)}'`).join(", ")})`)
    .join(" AND ");
}

/**
 * Render the DAG (plus any active sidebar filters) as a readable,
 * illustrative SQL query - not executed anywhere, just a live, honest
 * translation of what buildWideRows/the sidebar filters actually compute:
 * one INNER JOIN + STRING_AGG per edge, chained in order (each edge narrows
 * what the next one sees, mirroring how a sequence of SQL JOINs on the same
 * FROM naturally narrows the result - no separate HAVING needed for that),
 * each pre-filtered by that table's own facet selections via a subquery,
 * plus a WHERE on Publications' own filters.
 *
 * A merge-source table's filter is rendered as a subquery (`(SELECT * FROM
 * ... WHERE ...) alias`) rather than a WHERE after the JOIN - functionally
 * equivalent for an INNER JOIN, but keeps each edge's own filter visually
 * scoped to that edge instead of piling into one shared WHERE clause.
 */
export function generateSql(
  edges: readonly DagEdge[],
  pubFilters: readonly FacetFilter[] = [],
  edgeFilters: Record<string, readonly FacetFilter[]> = {},
): string {
  const lines: string[] = [];
  lines.push("SELECT");
  lines.push("  p.*" + (edges.length > 0 ? "," : ""));
  edges.forEach((edge, i) => {
    const alias = `t${i + 1}`;
    const cols = edge.columns.map(
      (c) => `  STRING_AGG(DISTINCT ${alias}."${c}", '; ') AS "${mergedFieldKey(edge.table, c)}"`,
    );
    lines.push(cols.join(",\n") + (i < edges.length - 1 ? "," : ""));
  });
  lines.push("FROM Publications p");
  edges.forEach((edge, i) => {
    const alias = `t${i + 1}`;
    const where = sqlWhereClause(alias, edgeFilters[edge.table] ?? []);
    const source = where ? `(\n  SELECT * FROM "${edge.table}" WHERE ${where}\n)` : `"${edge.table}"`;
    // INNER JOIN, chained - each one narrows the accumulated result so far,
    // not an independent join against Publications that gets unioned back in.
    lines.push(`INNER JOIN ${source} ${alias}`);
    lines.push(`  ON ${DOMAIN_SQL_JOIN_KEY[edge.domain]} matches (p, ${alias})  -- ${edge.domain} domain`);
  });
  const pubWhere = sqlWhereClause("p", pubFilters);
  if (pubWhere) lines.push(`WHERE ${pubWhere}`);
  if (edges.length > 0) lines.push("GROUP BY p.PMID");
  return lines.join("\n");
}

/** One synthetic node row built by buildValueNodes - a distinct value of the
 * chosen node field, standing in for every real row that contained it. */
export interface ValueNodeRow {
  value: string;
  count: number;
  [key: string]: unknown;
}

/**
 * Aggregate rows into one synthetic row per distinct value of `nodeField`,
 * for feeding into KnowledgeGraph unchanged - each synthetic row's edge-field
 * columns are the union of that field's values across every real row
 * containing this node value, so KnowledgeGraph's existing shared-value-
 * overlap edge logic connects two node-values whenever they co-occur with a
 * shared edge value (e.g. two Authors connected because they've each
 * published under the same Resource Name, or via PMID for "same paper"),
 * without any change to that component's own algorithm.
 *
 * This is the same grouping/counting a plain value-counts report on
 * `nodeField` would do (split on its real delimiter, count occurrences) -
 * the per-group edge-field union is the one addition beyond a bare value
 * count, needed to compute edges afterward.
 *
 * Sorted by frequency descending - feeding this into KnowledgeGraph's
 * existing `maxNodes` (a plain first-N slice) then means "top-N most
 * frequent node values," not an arbitrary first-N cut.
 *
 * `countKeyField` (typically "__publicationKey", the PMC-ID/DOI-fallback
 * identity from publicationIdFor) dedupes what "frequency" counts: `rows`
 * here is a wide, already-joined table, so the same publication can appear
 * as more than one row (e.g. once per dataset it lists) - without dedup, an
 * author who wrote one paper listing five datasets would count as five,
 * inflating both node size and the "N publication(s)" hover count. A row
 * with no value in that field (identity unknown) still counts on its own,
 * since there's nothing to dedupe it against.
 */
export function buildValueNodes(
  rows: readonly Row[],
  nodeField: string,
  nodeDelimiter: string | undefined,
  edgeFields: readonly { field: string; delimiter?: string }[],
  countKeyField?: string,
): ValueNodeRow[] {
  const byValue = new Map<
    string,
    { pubKeys: Set<string>; unkeyedRows: number; edgeSets: Map<string, Set<string>> }
  >();
  for (const row of rows) {
    const raw = row[nodeField];
    if (typeof raw !== "string" || !raw.trim()) continue;
    const keyRaw = countKeyField ? row[countKeyField] : undefined;
    const pubKey = typeof keyRaw === "string" && keyRaw.trim() ? keyRaw : undefined;
    for (const v of splitMulti(raw, nodeDelimiter)) {
      if (!byValue.has(v)) {
        byValue.set(v, {
          pubKeys: new Set(),
          unkeyedRows: 0,
          edgeSets: new Map(edgeFields.map((f) => [f.field, new Set<string>()])),
        });
      }
      const rec = byValue.get(v)!;
      if (pubKey) rec.pubKeys.add(pubKey);
      else rec.unkeyedRows++;
      for (const ef of edgeFields) {
        const efRaw = row[ef.field];
        if (typeof efRaw !== "string" || !efRaw.trim()) continue;
        for (const ev of splitMulti(efRaw, ef.delimiter)) rec.edgeSets.get(ef.field)!.add(ev);
      }
    }
  }

  const out: ValueNodeRow[] = [];
  for (const [value, rec] of byValue) {
    const synthetic: ValueNodeRow = { value, count: rec.pubKeys.size + rec.unkeyedRows };
    for (const ef of edgeFields) synthetic[ef.field] = Array.from(rec.edgeSets.get(ef.field) ?? []).join(";");
    out.push(synthetic);
  }
  out.sort((a, b) => b.count - a.count);
  return out;
}

/**
 * Drop hub values - ones appearing in more than `threshold` of rows - from
 * one or more semicolon-delimited fields before edges are drawn. A common
 * value (e.g. the gene APOE, mentioned across a huge fraction of ADRD
 * papers) would otherwise connect nearly everything to everything, producing
 * a dense, low-signal hairball instead of a useful graph.
 *
 * `threshold >= 1` or an empty field list is a no-op (returns rows as-is).
 */
export function dropHubValues<T extends Record<string, unknown>>(
  rows: readonly T[],
  threshold: number,
  fields: readonly string[],
): T[] {
  if (threshold >= 1 || fields.length === 0) return rows.slice();
  const total = rows.length || 1;
  const valueCount = new Map<string, number>();
  for (const row of rows) {
    const seen = new Set<string>();
    for (const field of fields) {
      const raw = row[field];
      if (typeof raw !== "string") continue;
      for (const v of splitMulti(raw, ";")) {
        if (seen.has(v)) continue;
        seen.add(v);
        valueCount.set(v, (valueCount.get(v) ?? 0) + 1);
      }
    }
  }
  const hubExclude = new Set<string>();
  for (const [v, n] of valueCount) if (n / total > threshold) hubExclude.add(v);
  if (hubExclude.size === 0) return rows.slice();

  return rows.map((row) => {
    const next = { ...row };
    for (const field of fields) {
      const raw = row[field];
      if (typeof raw !== "string") continue;
      (next as Record<string, unknown>)[field] = splitMulti(raw, ";")
        .filter((v) => !hubExclude.has(v))
        .join(";");
    }
    return next;
  });
}

export interface ValueCountsColumn {
  field: string;
  delimiter?: string;
  /** Skip counting a free-text column (Title, Abstract) - every value is
   * near-unique, so a value-counts breakdown would just be noise. */
  skip?: boolean;
  /** A quantity (e.g. Code Repositories' FAIR Score), not a category - report
   * mean/variance instead of a top-values breakdown. A field like a 0-10 QC
   * score has no natural "top value"; a percentage-of-rows framing for it is
   * actively misleading (and, once merged from a table with more than one
   * matching row per Publication, values aren't mutually exclusive per row
   * either - percentages can overlap past 100%). See ConnectionsStats' own
   * "numeric" classification (the same one build-connections-stats.mjs uses),
   * which callers look up per field to set this flag consistently. */
  numeric?: boolean;
}

/** Every numeric value across `rows[field]` (multivalue-split first, so a
 * merged column with more than one matching source row per Publication -
 * "6; 7" - still contributes each of its individual numbers). */
function numericValues(rows: readonly Row[], field: string, delimiter: string | undefined): number[] {
  const nums: number[] = [];
  for (const row of rows) {
    const raw = row[field];
    if (typeof raw !== "string" || !raw.trim()) continue;
    for (const v of splitMulti(raw, delimiter)) {
      const n = Number(v);
      if (!Number.isNaN(n)) nums.push(n);
    }
  }
  return nums;
}

/**
 * A per-column value-counts breakdown of a (frozen) wide table, as markdown -
 * the "freeze table" report. Doubles as both a standalone document (download/
 * view) and the literal prompt content sent to AI Analysis (see
 * ConnectionsPage) - one report, two uses, so what gets analyzed is always
 * exactly what's shown.
 */
export function buildValueCountsReport(
  rows: readonly Row[],
  columns: readonly ValueCountsColumn[],
  mergedTables: readonly string[],
  topN = 15,
): string {
  const lines: string[] = [];
  lines.push("# Cross-Table Report");
  lines.push("");
  lines.push(
    `**${rows.length.toLocaleString()} Publications** merged with: ${mergedTables.length ? mergedTables.join(", ") : "(none)"}`,
  );
  lines.push("");
  for (const col of columns) {
    if (col.skip) continue;
    lines.push(`## ${col.field}`);
    if (col.numeric) {
      const nums = numericValues(rows, col.field, col.delimiter);
      if (nums.length === 0) {
        lines.push("(no values)");
      } else {
        const mean = nums.reduce((s, n) => s + n, 0) / nums.length;
        const variance = nums.reduce((s, n) => s + (n - mean) ** 2, 0) / nums.length;
        lines.push(`- mean: ${mean.toFixed(2)}`);
        lines.push(`- variance: ${variance.toFixed(2)}`);
        lines.push(`- n: ${nums.length}`);
      }
      lines.push("");
      continue;
    }
    const counts = new Map<string, number>();
    for (const row of rows) {
      const raw = row[col.field];
      if (typeof raw !== "string" || !raw.trim()) continue;
      for (const v of splitMulti(raw, col.delimiter)) {
        counts.set(v, (counts.get(v) ?? 0) + 1);
      }
    }
    const sorted = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
    if (sorted.length === 0) {
      lines.push("(no values)");
    } else {
      for (const [value, count] of sorted.slice(0, topN)) {
        lines.push(`- ${value}: ${count}`);
      }
      if (sorted.length > topN) lines.push(`- ...and ${sorted.length - topN} more distinct value(s)`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

/**
 * A sample of full Title + Abstract text, for genuine comparative reading -
 * value counts alone can't support a claim like "ROSMAP focuses more on
 * microglial profiling than the spatial-transcriptomics cohort," which
 * requires actually reading what the papers say. Capped at `maxRows` (not
 * all of them) since full abstract text is expensive - mirrors the same
 * per-row sampling cap AnalysisPanel already uses for the other analysis
 * types, layered on top of buildValueCountsReport's full-set aggregation
 * rather than replacing it.
 */
export function buildAbstractSample(rows: readonly Row[], maxRows = 30): string {
  const candidateRows = rows.slice(0, maxRows);
  const sample = candidateRows.filter(
    (r) => typeof r["Abstract"] === "string" && (r["Abstract"] as string).trim(),
  );
  if (sample.length === 0) return "";

  const lines = ["## Publication Abstracts (sample)", ""];
  if (rows.length > maxRows) {
    lines.push(
      `_Showing the first ${maxRows} of ${rows.length} rows (not all of them) - value counts above cover the full set, but abstract text is capped for size._`,
    );
    lines.push("");
  }
  for (const row of sample) {
    lines.push(`### ${(row["Title"] as string) || "(untitled)"}`);
    if (row["Resource Name"]) lines.push(`Resource: ${row["Resource Name"]}`);
    lines.push((row["Abstract"] as string).trim());
    lines.push("");
  }
  return lines.join("\n");
}

/** One column's precomputed full-catalog summary - see
 * scripts/build-connections-stats.mjs, which produces this shape. */
export interface ColumnStat {
  kind: "numeric" | "categorical" | "skipped";
  /** numeric only: non-empty, numeric-parseable value count. */
  count?: number;
  mean?: number;
  variance?: number;
  /** categorical only: distinct value count (post multivalue-split). */
  distinct?: number;
  /** categorical only: [value, count] pairs, most frequent first - stored
   * wider than any single prompt needs so callers can slice to their own top-k. */
  top?: [string, number][];
  reason?: string;
}
export interface TableStats {
  rowCount: number;
  columns: Record<string, ColumnStat>;
}
/** Table name -> its precomputed stats - see loaders.ts's loadConnectionsStats. */
export type ConnectionsStats = Record<string, TableStats>;

/** One (table, field) pair to pull a baseline for - see buildBaselineSummary. */
export interface BaselineColumn {
  table: string;
  field: string;
}

/**
 * The full-catalog (unfiltered) baseline for exactly the columns a DAG
 * actually selects, from the precomputed static stats - meant to sit
 * alongside buildMacroSummary's *subset* summary so the AI prompt can make a
 * genuine contrastive read ("the merged subset skews toward X vs. the full
 * catalog's Y"), not just describe the subset in isolation.
 *
 * Deliberately scoped to `columns` (the same table+field pairs the query's
 * SELECT/JOIN actually touches - i.e. the same set macroColumns builds from
 * dagEdges) rather than every column of every merged table: dumping a whole
 * table's schema regardless of what the query asked for reads as random
 * noise the model has to sift through, and doesn't line up 1:1 with what the
 * subset summary reports for a real side-by-side comparison. A column like
 * Code Repositories' FAIR Score is never selectable as a DAG merge column,
 * so it only appears here once a query actually merges it in - by design,
 * not a gap: it's still real catalog content the moment it's relevant.
 *
 * `topN` caps how many of each column's stored top values are rendered here
 * - the stats file itself stores more (see TOP_K_STORED in the build
 * script) so different callers can pick their own render-time budget.
 */
export function buildBaselineSummary(
  stats: ConnectionsStats | null | undefined,
  columns: readonly BaselineColumn[],
  topN = 10,
): string {
  if (!stats) return "";
  const byTable = new Map<string, string[]>();
  for (const { table, field } of columns) {
    if (!byTable.has(table)) byTable.set(table, []);
    byTable.get(table)!.push(field);
  }

  const lines: string[] = ["## Full-Catalog Baseline (unfiltered, for contrast)", ""];
  let any = false;
  for (const [table, fields] of byTable) {
    const t = stats[table];
    if (!t) continue;
    const fieldLines: string[] = [];
    for (const field of fields) {
      const col = t.columns[field];
      if (!col) continue;
      if (col.kind === "numeric" && col.mean !== undefined && col.variance !== undefined) {
        fieldLines.push(`- **${field}**: mean ${col.mean.toFixed(2)}, variance ${col.variance.toFixed(2)} (n=${col.count})`);
      } else if (col.kind === "categorical" && col.top?.length) {
        const total = t.rowCount || 1;
        const top = col.top
          .slice(0, topN)
          .map(([v, n]) => `${v} (${Math.round((n / total) * 100)}%)`)
          .join(", ");
        fieldLines.push(`- **${field}**: ${col.distinct} distinct. Top: ${top}`);
      }
    }
    if (fieldLines.length === 0) continue;
    any = true;
    lines.push(`### ${table} (${t.rowCount.toLocaleString()} rows, full catalog)`, ...fieldLines, "");
  }
  return any ? lines.join("\n") : "";
}

export interface MacroSummaryColumn {
  field: string;
  delimiter?: string;
  /** A quantity, not a category - see ValueCountsColumn.numeric. */
  numeric?: boolean;
}

/**
 * A compact "landscape at a glance" summary for a small set of macro
 * variables - top values as a share of the total plus a one-line long-tail
 * note, NOT an exhaustive per-value histogram. Meant to sit at the top of
 * the AI prompt so a contrastive read ("A is 3x more common than B") is
 * cheap, without spending thousands of tokens on raw counts the way a full
 * per-column breakdown (buildValueCountsReport) would for every column.
 */
export function buildMacroSummary(
  rows: readonly Row[],
  columns: readonly MacroSummaryColumn[],
  topN = 10,
): string {
  const total = rows.length || 1;
  const lines: string[] = ["## At a Glance", ""];
  for (const col of columns) {
    if (col.numeric) {
      const nums = numericValues(rows, col.field, col.delimiter);
      if (nums.length === 0) {
        lines.push(`- **${col.field}**: no values.`);
      } else {
        const mean = nums.reduce((s, n) => s + n, 0) / nums.length;
        const variance = nums.reduce((s, n) => s + (n - mean) ** 2, 0) / nums.length;
        lines.push(`- **${col.field}**: mean ${mean.toFixed(2)}, variance ${variance.toFixed(2)} (n=${nums.length}).`);
      }
      continue;
    }
    const counts = new Map<string, number>();
    for (const row of rows) {
      const raw = row[col.field];
      if (typeof raw !== "string" || !raw.trim()) continue;
      for (const v of splitMulti(raw, col.delimiter)) counts.set(v, (counts.get(v) ?? 0) + 1);
    }
    const sorted = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
    if (sorted.length === 0) {
      lines.push(`- **${col.field}**: no values.`);
      continue;
    }
    const top = sorted.slice(0, topN);
    const topStr = top.map(([v, n]) => `${v} (${n}, ${Math.round((n / total) * 100)}%)`).join(", ");
    const restCount = sorted.length - top.length;
    // A "remaining X%" complement only makes sense for single-valued fields -
    // a multivalue field's per-value shares don't partition the row set (one
    // row can count toward several values at once), so top-N can already sum
    // past 100% and "100% - topShare" would go negative.
    const topShare = top.reduce((s, [, n]) => s + n, 0) / total;
    const rest =
      restCount > 0
        ? col.delimiter
          ? ` ${restCount} more distinct value(s) also appear.`
          : ` ${restCount} more distinct value(s) cover the remaining ${Math.round((1 - topShare) * 100)}%.`
        : "";
    lines.push(`- **${col.field}**: ${sorted.length} distinct value(s). Top: ${topStr}.${rest}`);
  }
  return lines.join("\n");
}
