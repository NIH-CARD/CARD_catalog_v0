import { loadTsv } from "./loadPublications";
import type {
  AnnotationSummary,
  CellularModel,
  CodeRepo,
  FairIssue,
  PubDataset,
  PubGrant,
  PubModel,
  PubSoftware,
  Publication,
  Resource,
  SciLiteAnnotation,
  SciLitePmcTypeCount,
  Supplementary,
} from "../types";

export const loadPublications = () =>
  loadTsv<Publication>("/data/publications.tsv");
export const loadResources = () => loadTsv<Resource>("/data/resources.tsv");
export const loadCodeRepos = () => loadTsv<CodeRepo>("/data/code_repos.tsv");
export const loadFairCompliance = () =>
  loadTsv<FairIssue>("/data/fair_compliance.tsv").catch(() => [] as FairIssue[]);
export const loadPubDatasets = () =>
  loadTsv<PubDataset>("/data/pub_datasets.tsv");
export const loadSupplementary = () =>
  loadTsv<Supplementary>("/data/pub_supplementary.tsv");
export const loadPubGrants = () =>
  loadTsv<PubGrant>("/data/pub_grants.tsv");
export const loadPubSoftware = () =>
  loadTsv<PubSoftware>("/data/pub_software.tsv");
export const loadPubModels = () =>
  loadTsv<PubModel>("/data/pub_models.tsv");
export const loadSciLite = () =>
  loadTsv<SciLiteAnnotation>("/data/scilite_annotations.tsv");
export const loadCellularModels = () =>
  loadTsv<CellularModel>("/data/cellular_models.tsv");
export const loadAnnotationSummary = (): Promise<AnnotationSummary> =>
  fetch("/data/annotation_summary.json").then((r) => r.json());
export const loadSciLitePmcTypeCounts = () =>
  loadTsv<SciLitePmcTypeCount>("/data/scilite_pmc_type_counts.tsv");
// Precomputed (scripts/build-connections-stats.mjs), not always present -
// missing gracefully degrades to no baseline section rather than a page error.
export const loadConnectionsStats = (): Promise<import("./connectionsGraph").ConnectionsStats | null> =>
  fetch("/data/connections_stats.json")
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
