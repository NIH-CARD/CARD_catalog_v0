import { loadTsv } from "./loadPublications";
import type {
  CellularModel,
  CodeRepo,
  FairIssue,
  PubDataset,
  PubGrant,
  PubSoftware,
  Publication,
  Resource,
  SciLiteAnnotation,
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
export const loadSciLite = () =>
  loadTsv<SciLiteAnnotation>("/data/scilite_annotations.tsv");
export const loadCellularModels = () =>
  loadTsv<CellularModel>("/data/cellular_models.tsv");
