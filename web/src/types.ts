export interface Publication {
  PMID: string;
  DOI: string;
  "Resource Name": string;
  Abbreviation: string;
  "PubMed Central Link": string;
  Authors: string;
  Affiliations: string;
  Title: string;
  Abstract: string;
  Keywords: string;
  "Publication Date": string;
  "Publication Year": string;
  "Data Completeness": string;
}

export interface Resource {
  "Resource Name": string;
  Abbreviation: string;
  "Coarse Data Modality": string;
  "Granular Data Modality": string;
  "Diseases Included": string;
  "Sample Size": string;
  "Access URL": string;
  "FAIR Compliance Notes": string;
  "Date added to catalog": string;
  Reviewer: string;
  "Alternative URLs": string;
  "Resource Type": string;
  "Is Part Of"?: string;
  Remove?: string;
  Notes?: string;
  new_corpus?: string;
}

export interface CodeRepo {
  "Resource Name": string;
  Abbreviation: string;
  "Repository Link": string;
  Source: string;
  Owner: string;
  Contributors: string;
  Languages: string;
  "Biomedical Relevance": string;
  "Relevance Rationale": string;
  "Code Summary": string;
  "Data Types": string;
  Tooling: string;
  "FAIR Score": string;
  "FAIR Issues": string;
}

export interface PubDataset {
  pub_title: string;
  source_url: string;
  raw_data_format: string;
  dataset_identifier: string;
  data_repository: string;
  dataset_context_from_paper: string;
  dataset_keywords: string;
  citation_type: string;
  dataset_webpage: string;
  access_mode: string;
}

export interface Supplementary {
  link: string;
  source_url: string;
  download_link: string;
  title: string;
  content_type: string;
  caption: string;
  description: string;
  context_description: string;
  source_section: string;
  file_extension: string;
  pub_title: string;
  raw_data_format: string;
}

export interface PubGrant {
  source_url: string;
  funder_name: string;
  grant_number: string;
  funding_context_from_paper: string;
  recipient: string;
}

export interface PubSoftware {
  source_url: string;
  software_name: string;
  version: string;
  mention_type: string;
  url: string;
  context_from_paper: string;
}

export interface PubModel {
  source_url: string;
  model_name: string;
  version: string;
  mention_type: string;
  url: string;
  context_from_paper: string;
}

export interface SciLiteAnnotation {
  "PMC ID": string;
  Type: string;
  Exact: string;
  Prefix: string;
  Postfix: string;
  Section: string;
  Provider: string;
  "Annotation ID": string;
  "Tag Name": string;
  "Tag URI": string;
}

export interface CellularModel {
  "Product Code": string;
  "Parental Line": string;
  Gene: string;
  "Gene Variant": string;
  Genotype: string;
  dbSNP: string;
  Condition: string;
  "Other Names": string;
  "Genome Assembly": string;
  "Protospacer Sequence": string;
  "Genomic Coordinate": string;
  "Genomic Sequence": string;
  "Procurement link": string;
  "About this gene": string;
  "About this variant": string;
  "Linked Publications": string;
  "Linked Studies": string;
}

export interface SciLitePmcTypeCount {
  "PMC ID": string;
  Type: string;
  "Tag Name": string;
  Exact: string;
  Section: string;
  Provider: string;
  "Tag URI": string;
  Count: string;
}

export interface FairIssue {
  Repository: string;
  Study: string;
  "Issue Type": string;
  Details: string;
  Timestamp: string;
}

export interface AnnotationSummary {
  stages: Record<string, number>;
  scilite_total: number;
  scilite_top_types: { type: string; count: number }[];
}

export interface FacetCount {
  value: string;
  count: number;
}

export interface FacetSpec<T> {
  field: keyof T & string;
  label?: string;
  multivalue?: boolean;
  /** Override the multi-value delimiter. Defaults to ";". */
  delimiter?: string;
  /**
   * Optional: turn each underlying value (e.g. a URI) into a human-readable
   * label. The Facet uses this for display and for search; selections still
   * carry the underlying value.
   */
  displayLabel?: (value: string) => string;
  /**
   * Optional: map a raw value to its canonical/harmonized form (e.g. many
   * spellings of "Whole Genome Sequencing" -> one chip). Unlike displayLabel,
   * this changes what gets counted and what selections carry — synonym
   * variants merge into one chip instead of appearing as separate rows with
   * the same-looking label.
   */
  canonicalize?: (value: string) => string;
}
