# CARD Catalog — Data Schema

> A reference for the tables behind the CARD Catalog app — a React app (`web/`, deployed on Netlify at alzheimersdatahub.org) as of this writing; the Streamlit app this doc originally referenced is the legacy v0 predecessor, kept for reference but no longer deployed — aimed at readers new to the project.
> Cardinalities and value examples are taken from the export snapshot dated **2026-03-16**, except the `pub_grants`/`pub_software` sections which reflect real exports from July 2026 (see each section for specifics).

---

## What this catalog is

The CARD Catalog is a structured inventory of biomedical **resources, publications, code, and datasets** relevant to neurological disease research (Alzheimer's, Parkinson's, ALS, FTD, and related dementias). It exists to make the landscape of available data and tooling discoverable in one place.

The catalog is built from two complementary sources:

1. **Manual curation** — analysts maintain a hand-vetted "source of truth" list of resources.
2. **Automated enrichment** — a pipeline of scrapers and LLM-assisted annotators expands each curated resource with publications it has produced, code repos that use it, datasets cited in those publications, and supplementary files attached to those publications. The pipeline also surfaces *new* resources discovered along the way as candidates for human review.

Each pipeline run writes timestamped snapshot files (the `*` in filenames like `pubmed_central_*.tsv` is a date stamp), so the catalog has a history rather than only a current state.

---

## Schema versions

The workbook documents two schema generations:

| Version | Tables | Notes |
|---|---|---|
| **v0** (`db`) | 4 tables | Original schema. Publications and code were single flat tables. |
| **v1** (`v1.db`) | 9 tables | Splits publication enrichment into dedicated tables (`pub_datasets`, `pub_supplementary`, `pub_grants`, `pub_software`, `new_corpus`) and formalizes typed row models (`PublicationRow`, `CodeRepoRow`, etc.). `pub_grants` and `pub_software` were added most recently — see their sections below. |

The rest of this document describes **v1**, which is current.

---

## Table map

```
                         ┌─────────────────────────┐
                         │   resources-inventory   │  ← manually curated
                         │       (~236 rows)       │
                         └─────────────────────────┘
                                      │
                  ┌───────────────────┴───────────────────┐
                  ▼                   ▼                   ▼
         ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
         │  publications  │  │      code      │  │   new_corpus   │
         │  (~1.6k rows)  │  │  (~700 repos)  │  │  (discovered)  │
         └────────────────┘  └────────────────┘  └────────────────┘
                  │  source_url (≈ PMC link)
          ┌───────┴───────────┴───────────────────┴───────────────────┐
          ▼                   ▼                   ▼                   ▼
┌──────────────────┐┌──────────────────┐┌──────────────────┐┌──────────────────┐
│   pub_datasets   ││pub_supplementary ││    pub_grants    ││   pub_software   │
└──────────────────┘└──────────────────┘└──────────────────┘└──────────────────┘

                                                                      │
                                                                      └─▶ GitHub-hosted mentions are routed through github_search/
                                                                          repo_analysis and end up in `code` above too.

      ┌──────────────────┐
      │  iNDI_inventory  │  ← standalone (~626 cell lines)
      └──────────────────┘
```

`pub_datasets`/`pub_supplementary`/`pub_grants`/`pub_software` all join back
to `publications` via `source_url` (the PMC link), not `PMID` — see the
Conventions section at the bottom.

---

## Tables

### `resources-inventory`

**File pattern:** `resources-inventory-*.tab` (export filename: `resources_export.tsv`)
**Snapshot size:** 236 rows × 13 columns
**Role:** The hand-curated master list. Every other table (except `iNDI_inventory`) ultimately points back here via `Resource Name` / `Abbreviation`.

| Field | Notes |
|---|---|
| `Resource Name` | Full name. 100% populated. Primary human-readable key. |
| `Abbreviation` | Short identifier (e.g., `DIAN`, `ADNI`, `PPMI`). 92% populated. |
| `Coarse Data Modality` | **Comma-delimited** controlled vocabulary. Top values: `clinical` (183), `genetics` (86), `transcriptomics` (86), `longitudinal` (75), `imaging` (50), `proteomics` (50), `metabolomics` (23), `epigenomics` (21). |
| `Granular Data Modality` | **Semicolon-delimited** free-text descriptors (e.g., `MRI; PET; CSF biomarkers; Genomics`). |
| `Diseases Included` | Semicolon-delimited (e.g., `Familial Alzheimer's Disease;Normal Controls`). |
| `Sample Size` | Free text — usually `N participants`, sometimes with cohort breakdown (`766 participants (664 cases, 102 controls)`) or `Not applicable`. **Not numeric.** |
| `Access URL` | Primary URL. |
| `FAIR Compliance Notes` | One- to two-sentence reviewer comment on FAIR adherence. |
| `Date added to catalog` | ISO datetime (`2025-12-01 00:00:00`). |
| `Reviewer` | Curator initials/name. In current snapshot: `Mette/Pietro` (127), `Mette` (107), `Pietro` (2). Slash denotes joint review. |
| `Alternative URLs` | **Python list-literal string** (e.g., `['https://...', 'https://...']`) — needs `ast.literal_eval` to parse. |
| `Resource Type` | Comma-delimited enum. Values seen: `Study` (192), `Data Repository` (24), `Biorepository` (4), `Data Catalog` (1), and combinations. **Order is not normalized** — both `"Data Repository, Biorepository"` and `"Biorepository, Data Repository"` appear. |
| `new_corpus` | **Not a flag — a JSON-like discovery breadcrumb** populated only when the page-navigation crawler found something. Shape: `{seed_url: {visited_url: [discovered_DOIs]}}`. Populated for 25/236 (11%) of resources. |

> **Workbook-vs-export drift:** The schema sheet documents `Notes` and `Remove` columns, but neither appears in the current export. They may be internal-only fields stripped before export.

---

### `iNDI_inventory`

**File pattern:** `iNDI_inventory_*.tsv` (export filename: `indi_cell_lines_export.csv`)
**Snapshot size:** 626 rows × 15 columns
**Role:** Mirror of the **iNDI** (iPSC Neurodegenerative Disease Initiative) cell-line catalog. Standalone — not produced by the pipeline and not joined to the other tables.

| Field | Notes |
|---|---|
| `Product Code` | iNDI line identifier (e.g., `JIPSC001002`). |
| `Parental Line` | **Constant in current data: `KOLF2.1J`** (all 626 lines). |
| `Gene` | Target gene symbol (e.g., `FUS`). |
| `Gene Variant` | HGVS-like protein change (e.g., `R495X`). 99.8% populated. |
| `Genotype` | Coded as `ALLELE1/ALLELE2`. Allele codes: `WT` (wild-type), `SNV` (single-nucleotide variant), `DEL` (deletion), `REV` (revertant of a prior edit), `HALO` (HaloTag knock-in), `KI` (knock-in), `PTC` (premature termination codon), `Y` (Y chromosome / hemizygous), `INDEL`. Most common combos: `SNV/WT` (154), `SNV/SNV` (145), `REV/WT` (113), `DEL/DEL` (71), `HALO/WT` (65). |
| `dbSNP` | rsID. 70% populated — missing where no canonical rsID exists for the engineered variant. |
| `Condition` | Disease/phenotype. **`0` = no associated condition** (266 lines, mostly engineered controls). Real conditions: `Parkinson's disease` (60), `Alzheimer's disease` (55), `Frontotemporal dementia` (21). |
| `Other Names` | Alternative variant names. 42% populated. |
| `Genome Assembly` | **Constant: `GRCh38`** (all populated rows). |
| `Protospacer Sequence` | CRISPR guide. Prefixed with guide index: `1_ACGT...` (current data has only guide `1_`). |
| `Genomic Coordinate` | `chr:position (strand)` (e.g., `chr16:31191052 (+)`). |
| `Genomic Sequence` | Reference flank with IUPAC bracket notation marking the variant: `...GACCGTGGAGGCTTC[C/T]GAGGGGGCCGGGGT...`. |
| `Procurement link` | **Constant: `https://www.jax.org/jax-mice-and-services/ipsc/cells-collection`** (all lines distributed via JAX). |
| `About this gene` | LLM-generated gene description. |
| `About this variant` | LLM-generated variant description. 70% populated (tracks `dbSNP` fill rate). |

---

### `publications` (`PublicationRow`)

**File pattern:** `pubmed_central_*.tsv`
**Snapshot size:** 1,578 rows × 12 columns, covering 69 distinct resources
**Role:** PubMed Central scraper output. One row per publication tied to a curated resource.

| Field | Notes |
|---|---|
| `PMID` | PubMed identifier. **Join key** for `pub_datasets` and `pub_supplementary`. |
| `Resource Name` | The study/resource this pub belongs to. Top hitters in current snapshot: ADNI (150), NACC (150), PPMI (149), MAP (122), ROS (89). The 150-pub ceiling on the top resources suggests a per-resource cap in the scraper. |
| `Abbreviation` | |
| `Diseases Included` | **Mixed delimiters** — primarily semicolon, but commas appear inside multi-word terms (e.g., `Alzheimer's Disease; Dementia; Normal Aging, Vascular dementia`). Splitting needs care. |
| `Coarse Data Modality` | **Comma-delimited** (matches `resources-inventory` convention). |
| `Granular Data Modality` | Semicolon-delimited. |
| `PubMed Central Link` | Full PMC URL. **84% populated** — open-access subset only. |
| `Authors` | Semicolon-delimited, normalized to `Last First-initial` form. |
| `Affiliations` | 97% populated. |
| `Title` | |
| `Abstract` | 98% populated (a few PMIDs lack indexed abstracts). |
| `Keywords` | Semicolon-delimited. **75% populated** — pre-2010 papers often lack indexed MeSH-style keywords. |

---

### `code` (`CodeRepoRow`)

**File pattern:** `gits_to_reannotate_completed_*.tsv` (export filename: `repositories_export.tsv`)
**Snapshot size:** 699 rows × 13 columns
**Role:** GitHub repo scraper output, with LLM-generated annotations and a FAIR-compliance score.

| Field | Notes |
|---|---|
| `Resource Name` | |
| `Abbreviation` | |
| `Diseases Included` | Semicolon-delimited. |
| `Repository Link` | GitHub URL. |
| `Owner` | GitHub username/org. |
| `Contributors` | Semicolon-delimited; includes bot accounts (e.g., `dependabot[bot]`). 97% populated. |
| `Languages` | Semicolon-delimited *in principle*, but **single-language in current data** (0/618 rows actually have multiple). 88% populated. |
| `Biomedical Relevance` | LLM verdict. Format: `<VERDICT> - <reasoning>`. Current distribution: `YES` (566), `NO` (133). The schema documents `UNCLEAR` as a possible verdict but it does not appear in this snapshot. |
| `Code Summary` | LLM-generated free-text summary of what the repo does. |
| `Data Types` | LLM-generated free-text on data the repo handles. **Not strictly delimited** despite schema implication. |
| `Tooling` | LLM-generated free-text on libraries/frameworks used. **Not strictly delimited.** |
| `FAIR Issues` | **(Not in original schema sheet)** Semicolon-delimited tags flagging FAIR shortcomings. Tags seen, by frequency: `No Version Info` (689), `No Environment Spec` (680), `No Container` (670), `No Dependencies` (530), `No README` (13). |
| `FAIR Score` | **(Not in original schema sheet)** Integer 0–9. Distribution: 0 (6), 2 (36), 4 (6), 5 (3), 6 (472), 7 (144), 8 (29), 9 (3). Median 6, max observed 9. |

---

### `pub_datasets` (`PubDatasetRow`) — *v1 only*

**File pattern:** `pub_datasets_*.tsv`
**Role:** Datasets cited *inside* publications. Joins back via `source_url` (the PMC link).

> **Schema drift:** the fields below are from the schema sheet / `PubDatasetRow`'s
> aspirational `COLUMNS`, but the live pipeline output uses different, lowercase
> `snake_case` columns straight from `data_gatherer`: `pub_title, source_url,
> raw_data_format, dataset_identifier, data_repository,
> dataset_context_from_paper, dataset_keywords, citation_type`. The
> `_normalize_pub_datasets` normalizer is currently a no-op (passes these
> through unchanged) rather than renaming to the schema-sheet names below.

| Field (schema sheet) | Notes |
|---|---|
| `Source PMID` | Links back to `publications`. |
| `Source Resource Name` | |
| `Dataset Identifier` | Accession number or DOI. |
| `Data Repository` | e.g., dbGaP, Zenodo, GEO. |
| `Dataset Webpage` | |
| `Citation Type` | How the dataset is referenced in the paper. |
| `Usage Description` | What the paper did with the dataset. |
| `Dataset Scope` | |
| `Results Relationship` | How the dataset relates to the paper's results. |
| `Decision Rationale` | LLM-generated explanation for inclusion. |

---

### `pub_supplementary` (`SupplementaryRow`) — *v1 only*

**File pattern:** `pub_supplementary_*.tsv`
**Role:** Supplementary files attached to publications. Joins back via `source_url` (the PMC link).

> **Schema drift** (same situation as `pub_datasets` above): live output columns
> are `link, source_url, download_link, title, content_type, caption,
> description, context_description, source_section, file_extension, pub_title,
> raw_data_format`, passed through unchanged by a no-op normalizer.

| Field (schema sheet) | Notes |
|---|---|
| `Source PMID` | Links back to `publications`. |
| `Source Resource Name` | |
| `File URL` | |
| `File Name` | |
| `File Extension` | |
| `File Format` | |
| `Keywords` | |
| `Data Repository` | |
| `Number Of Files` | |
| `File License` | |

---

### `pub_grants` (`PubGrantRow`) — *v1 only, added most recently*

**File pattern:** `pub_grants_*.tsv`
**Role:** Grant/funding mentions extracted from the funding/acknowledgments
section of each publication (`data_gatherer`'s `CLAUDE_FDR_FewShot_grant`
prompt + `grant_response_schema_gpt`, rule-based `FUND`-flagged retrieval —
see `pipelines.pub_grants` in [`api_reference.md`](api_reference.md)). Joins
back via `source_url` (the PMC link).

**Live output columns** (lowercase `snake_case`, straight from `data_gatherer`
— no schema-sheet equivalent exists yet since this table is new):

| Field | Notes |
|---|---|
| `pub_title` | Publication title. |
| `source_url` | PMC link — join key back to `publications`. |
| `raw_data_format` | Format the source article was fetched as (`XML`/`HTML`). |
| `funder_name` | Funding organization, **canonicalized** by `staging.normalizer._normalize_funder_name()` — a set of regex patterns collapsing known variant clusters (e.g. `National Institute on Aging`, `NIA`, `National Institute of Aging` [typo], `NIA/NIH`, `National Institute on Aging (NIA)/National Institutes of Health (NIH)` → one canonical `National Institute on Aging (NIA)`). Not exhaustive — only the high-frequency clusters found in real data are covered; the long tail of ~1500 one-off funder names passes through unchanged. |
| `grant_number` | One row per grant number — `data_gatherer`'s `process_grants_response()` explodes a `grant_numbers` array into one row each, so a paper with 3 grant numbers from the same funder produces 3 rows. |
| `funding_context_from_paper` | The text passage from the paper mentioning this funder/grant. |
| `recipient` | The author/institution that received the grant, if stated (`"n/a"` otherwise). |

---

### `pub_software` (`PubSoftwareRow`) — *v1 only, added most recently*

**File pattern:** `pub_software_*.tsv`
**Role:** Software/tool mentions extracted from each publication — rule-based
retrieval of the code-availability + references sections plus regex-matched
code-hosting URLs, combined with an LLM pass for unlinked mentions
(`CLAUDE_RTR_FewShot_software` prompt + `software_mention_response_schema_gpt`
— see `pipelines.pub_software` in [`api_reference.md`](api_reference.md)).
Joins back via `source_url` (the PMC link).

**Live output columns:**

| Field | Notes |
|---|---|
| `pub_title` | Publication title. |
| `source_url` | PMC link — join key back to `publications`. |
| `raw_data_format` | Format the source article was fetched as. |
| `software_name` | Name of the software/tool/package as written in the paper (e.g. `Python`, `Scanpy`). Not yet canonicalized — no normalizer pass exists for this field (unlike `pub_grants.funder_name`). |
| `version` | Version number if stated, else `"n/a"`. |
| `mention_type` | `created` (paper's own new tool), `used` (existing third-party tool), or `n/a`. |
| `url` | The software's **own** URL (GitHub/GitLab/Bitbucket/Zenodo/PyPI/CRAN/etc.), if given — *not* the source article's URL, despite the similar name to `source_url`. |
| `context_from_paper` | The text passage mentioning this software. |

GitHub-hosted rows from this table (`url` matching `github.com/owner/repo`)
are separately routed into `github_search`/`repo_analysis` and end up in the
`code` table too, with full tree-walk/README/FAIR-compliance enrichment — see
`scrapers.scrape_github.enrich_known_repos` in
[`api_reference.md`](api_reference.md). They aren't removed from
`pub_software` — the same GitHub repo can legitimately appear in both tables.

---

### `new_corpus` (`NewCorpusRow`) — *v1 only*

**File pattern:** `new_corpus_*.tsv`
**Role:** Resources the pipeline encountered while crawling that aren't in `resources-inventory` yet. A queue of candidates for human review and possible promotion into the curated list.
*No export provided in this batch — fields below are from the schema sheet.*

> Note the naming collision: the `new_corpus` **column** in `resources-inventory` (a per-resource crawl breadcrumb) is a different concept from the `new_corpus` **table** (newly discovered candidate resources). Both originate in the page-navigation crawler.

| Field | Notes |
|---|---|
| `Resource Name` | Newly discovered resource. |
| `Diseases Included` | Semicolon-delimited. |
| `Coarse Data Modality` | |
| `Granular Data Modality` | |
| `Sample Size` | |
| `Access URL` | |
| `Publication URLs` | Semicolon-delimited. |
| `Rationale` | Why the pipeline flagged it. |

---

## Conventions

- **Filenames** end in a timestamp wildcard (`*`); each pipeline run produces a new snapshot rather than overwriting prior state.
- **Multi-value field delimiters are not uniform** across the schema:
  - `Coarse Data Modality` → **comma** (`,`)
  - `Resource Type` → **comma** (`,`), order not normalized
  - `Diseases Included`, `Granular Data Modality`, `Authors`, `Keywords`, `Languages`, `Contributors`, `FAIR Issues` → **semicolon** (`;`)
  - `Diseases Included` in `publications` may contain commas *inside* semicolon-delimited terms — split on `;` only.
- **`Resource Name` and `Abbreviation`** are the de facto join keys from enrichment tables back to `resources-inventory`.
- **`source_url`** (the PMC link), not `PMID`, is the real join key from `pub_datasets`/`pub_supplementary`/`pub_grants`/`pub_software` back to `publications` (`PubMed Central Link`) — the schema sheet documents `Source PMID`/`PMID` for the first two, but live pipeline output never populates that field; it uses `source_url` throughout.
- **Funder-name canonicalization** (`pub_grants.funder_name` only): the LLM extracts funder names as written per-paper, which vary a lot for the same real funder. `staging.normalizer._normalize_funder_name()` collapses known high-frequency variant clusters via regex (see the `pub_grants` table section above) — treat `funder_name` as "mostly canonical for common NIH institutes and a handful of other large funders," not fully normalized.
- **LLM-generated fields** (`Code Summary`, `Biomedical Relevance`, `Data Types`, `Tooling`, `FAIR Issues`/`FAIR Score`, `About this gene`/`About this variant`, `Decision Rationale`, `pub_grants`/`pub_software`'s extracted fields) carry that provenance explicitly so downstream users know to treat them as machine annotations, not human curation.
- **`.tab` vs `.tsv`** — both are tab-separated; the `.tab` extension is reserved for the human-curated inventory while pipeline outputs use `.tsv`. The `iNDI_inventory` export is `.csv` (comma-separated).
- **Nested values appear as Python literals** in `resources-inventory`: `Alternative URLs` is a list-literal string, `new_corpus` is a dict-literal string. Both need `ast.literal_eval` to round-trip into native structures.
- **Constant fields in iNDI** (`Parental Line=KOLF2.1J`, `Genome Assembly=GRCh38`, `Procurement link=jax.org`) reflect the catalog's current single-source, single-background scope. Treat them as defaults rather than join keys.
- **Workbook schema vs. live exports may drift** (e.g., `code` has `FAIR Issues`/`FAIR Score` not in the workbook; `resources-inventory` lacks `Notes`/`Remove` documented in the workbook). When the two disagree, the live export is the operative truth.
