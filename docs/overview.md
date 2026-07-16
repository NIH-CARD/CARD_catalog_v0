# CARD Catalog — Architecture Overview

## What It Is

The **CARD Catalog** is a data pipeline + React web application (`web/`) for discovering and connecting research resources (datasets, publications, code repositories, cellular models) in the Alzheimer's Disease and Related Dementias (ADRD) / Neurodegenerative Diseases (NDD) space. The original Streamlit app (`app/`) is the v0 predecessor, kept for reference but no longer deployed.

It is maintained by DataTecnica for NIH's Center for Alzheimer's and Related Dementias (CARD) and NIA's Laboratory of Neurogenetics (LNG).

---

## System Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                              CARD Catalog v1                                  │
│                                                                                │
│  ┌──────────────┐    ┌───────────────────────────────────────────────────┐    │
│  │  Resources   │    │                     Pipeline                      │    │
│  │  Inventory   │───▶│  1. pubmed_search                                 │    │
│  │  (.tab file) │    │  2. prefetch_articles — shared PMC full-text      │    │
│  │              │    │     cache (tables/cache/), read-and-update in     │    │
│  │  - name      │    │     place across runs                             │    │
│  │  - type      │    │  3. pub_datasets / pub_supplementary /            │    │
│  │  - diseases  │    │     pub_grants / pub_software (AI, CONCURRENT —   │    │
│  │  - modality  │    │     each caches per-item against its own          │    │
│  │  - access URL│    │     tables/final/ output)                          │    │
│  └──────────────┘    │  4. scilite          (Europe PMC annotations)     │    │
│                       │  5. github_search    — also enriches repos       │    │
│                       │     discovered by pub_software                  │    │
│                       │  6. repo_analysis    (AI, cache-aware)           │    │
│                       │  7. page_navigation  (AI + browser, cache-aware) │    │
│                       │  8. join_annotations — enriches publications     │    │
│                       │     with SciLite + cited-dataset data            │    │
│                       └───────────────────┬───────────────────────────────┘   │
│                                           │                                    │
│                                 ┌─────────▼──────────┐                        │
│                                 │  tables/hits/      │                        │
│                                 │  (intermediate)    │                        │
│                                 └─────────┬──────────┘                        │
│                                           │                                    │
│                                  ┌────────▼───────┐                           │
│                                  │   Normalizer   │  field coercion +          │
│                                  │  (staging/)    │  validation                │
│                                  └────────┬───────┘                           │
│                                           │                                    │
│                                 ┌─────────▼──────────┐                        │
│                                 │  tables/final/     │                        │
│                                 │  (app-ready TSVs)  │                        │
│                                 └─────────┬──────────┘                        │
│                                           │                                    │
│                        ┌──────────────────▼─────────────────────────┐         │
│                        │             React App (web/)               │         │
│                        │  Resources · Publications · Code ·         │         │
│                        │  Datasets & Supplementary · iNDI            │         │
│                        │  (legacy Streamlit app in app/, unused)    │         │
│                        └─────────────────────────────────────────────┘        │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Stages

The pipeline is a staged DAG. Each stage is independently restartable: if a today-dated hits file already exists in `tables/hits/`, the orchestrator skips that stage. See [Pipeline Diagram](pipeline_diagram.md) for a full visual DAG.

| Stage | Input | Output (hits/) | Description |
|---|---|---|---|
| `pubmed_search` | inventory.tab | `pubmed_hits_*.tsv` | PubMed search (3-year window) |
| *(prefetch)* | pubmed_hits | `tables/cache/pub_fulltext_cache.parquet` | Shared full-text fetch for every PMC article, once, before the 4 stages below run |
| `pub_datasets` | pubmed_hits | `pub_datasets_*.tsv` | Dataset extraction from PMC articles (DataGatherer + Haiku); runs concurrently with the 3 stages below |
| `pub_supplementary` | pubmed_hits | `pub_supplementary_*.tsv` | Supplementary-material extraction from PMC articles |
| `pub_grants` | pubmed_hits | `pub_grants_*.tsv` | Grant/funding extraction from PMC articles |
| `pub_software` | pubmed_hits | `pub_software_*.tsv` | Software/tool mention extraction from PMC articles; GitHub-hosted mentions are routed into `github_search` (see below) |
| `scilite` | pubmed_hits | `scilite_annotations_*.tsv` | Bioentity annotations from Europe PMC SciLite API |
| `github_search` | inventory.tab (+ repos from `pub_software`) | `github_hits_*.tsv` | GitHub search, content fetch, no AI |
| `repo_analysis` | github_hits | `github_analyzed_*.tsv` | AI repo analysis via Anthropic Batch API |
| `page_navigation` | inventory.tab | `new_corpus_*.tsv` | Study page visits via headless Firefox + LLM |
| `join_annotations` | pubmed_central + pub_datasets + scilite | pubmed_central (enriched) | Post-normalization join — adds Diseases (Annotated), Genes/Proteins, Chemicals, Cited Datasets to the publications table |

After each stage, the **normalizer** validates and writes to `tables/final/`. `join_annotations` runs last and enriches the publications table in place.

`pub_datasets`, `pub_supplementary`, `pub_grants`, `pub_software`, `repo_analysis`, and `page_navigation` additionally cache per-item — diffing candidate items against what's already in `tables/final/` so a fresh run only reprocesses genuinely new items. Pass `--no-cache` to force a full reprocess.

---

## Automation Modes

### Update (incremental)
Runs every Monday. Fetches only papers from the last 7 days and writes a new timestamped `pubmed_central_*.tsv`.

### Full rebuild
Runs on the first Monday of January, April, July, October. Full 3-year PubMed window plus all other stages (GitHub, the 4 concurrent pub_* stages, scilite, page_navigation).

Both modes are triggered via cron:

```bash
# Update — Monday 8am ET
0 12 * * 1 cd /path/to/CARD_catalog_v0 && venv/bin/python orchestrator.py update

# Full rebuild — first Monday of Jan/Apr/Jul/Oct
0 12 1-7 1,4,7,10 * [ "$(date +\%u)" = "1" ] && cd /path/to/CARD_catalog_v0 && venv/bin/python orchestrator.py full_rebuild
```

---

## Directory Layout

```
CARD_catalog_v0/
│
├── orchestrator.py          # Pipeline coordinator (entry point)
│
├── pipelines/               # One module per pipeline stage
│   ├── base.py                    # PipelineStage ABC
│   ├── pubmed_search.py
│   ├── pub_metadata_shared.py      # load_pmc_links(), prefetch_articles() — shared fetch cache
│   ├── pub_datasets.py             # runs concurrently with the 3 below
│   ├── pub_supplementary.py
│   ├── pub_grants.py
│   ├── pub_software.py             # also produces extra_repos for github_search
│   ├── scilite.py
│   ├── github_search.py            # accepts --extra-repos from pub_software
│   ├── repo_analysis.py
│   └── page_navigation.py
│
├── staging/                 # Schema validation + normalization
│   ├── schemas.py           # Pydantic row models per output table
│   ├── normalizer.py        # Coerce → validate → write final TSV
│   ├── cache_utils.py       # latest_final() / combine_cached_and_new() — per-item cache diffing
│   └── join_annotations.py  # Final step: joins SciLite + cited datasets into publications
│
├── scrapers/                # Raw scrapers (gitignored)
│   ├── scrape_publications.py
│   ├── scrape_github.py
│   ├── batch_ai_analysis.py
│   └── logging_config.py
│
├── web/                     # LIVE APP — React + Vite + TypeScript, Netlify-deployed
│   ├── src/pages/
│   ├── scripts/sync-data.sh # Copies latest tables/final/*.tsv into public/data/
│   └── backend/             # FastAPI stub proxying Anthropic for AI-analysis features
│
├── app/                     # LEGACY — Streamlit v0 app, not deployed
│   ├── Home.py
│   ├── config.py
│   ├── pages/
│   └── utils/
│       ├── data_loader.py
│       ├── graph_builder.py
│       ├── llm_utils.py
│       └── export_utils.py
│
├── tables/
│   ├── hits/                # Intermediate pipeline outputs (gitignored)
│   ├── cache/                # Shared PMC full-text parquet cache (gitignored)
│   ├── final/               # App-ready validated outputs (committed)
│   ├── resources-inventory-*.tab     # Resource inventory (source of truth)
│   ├── iNDI_inventory_*.tsv        # iNDI cellular models (external)
│   └── *.tsv                       # Legacy v0 outputs (still served by the legacy app)
│
├── scripts/                 # Exploratory notebooks
└── docs/                    # This folder
```

---

## Output Tables

| Final file pattern | Schema | App page |
|---|---|---|
| `pubmed_central_*.tsv` | `PublicationRow` | Publications |
| `gits_to_reannotate_completed_*.tsv` | `CodeRepoRow` | Code Repositories |
| `pub_datasets_*.tsv` | `PubDatasetRow` | Datasets & Supplementary → Datasets tab |
| `pub_supplementary_*.tsv` | `SupplementaryRow` | Datasets & Supplementary → Supplementary tab |
| `pub_grants_*.tsv` | `PubGrantRow` | Datasets & Supplementary → Grants tab |
| `pub_software_*.tsv` | `PubSoftwareRow` | Synced to `web/public/data/` but no page renders it yet — the React app's "Software" sub-nav link has no matching route |
| `scilite_annotations_*.tsv` | `SciLiteRow` | Datasets & Supplementary → SciLite tab |
| `new_corpus_*.tsv` | `NewCorpusRow` | Feeds back into inventory |

The React app (`web/`) reads pre-generated TSVs from `web/public/data/`, refreshed via `npm run sync-data`. The legacy Streamlit app resolves the **latest** file matching each pattern, checking `tables/final/` first for v1 outputs and falling back to `tables/` root for legacy v0 files.

---

## External Dependencies

| Dependency | Used by | Notes |
|---|---|---|
| NCBI Entrez API | `pubmed_search.py` | Free; NCBI API key raises rate limits |
| GitHub REST API | `github_search.py` | Requires `GITHUB_TOKEN` |
| Europe PMC SciLite API | `scilite.py` | Free, no key required |
| Anthropic API | `repo_analysis.py`, `pub_datasets.py`, `pub_supplementary.py`, `pub_grants.py`, `pub_software.py`, `page_navigation.py`, `web/backend` AI-analysis proxy | `ANTHROPIC_API_KEY` |
| `data_gatherer` (pip) | `pub_metadata_shared.py`, `pub_datasets.py`, `pub_supplementary.py`, `pub_grants.py`, `pub_software.py`, `page_navigation.py` | VIDA-NYU internal package, install from GitHub |
| Firefox + geckodriver | `page_navigation.py` | For browser automation; profile auth required |

---

## Design Principles

**Separation of concerns** — scraping, inference, normalization, and presentation are independent layers. A schema change does not require a re-scrape.

**Restartability** — every stage checks for a today-dated hits file before running. A failed quarterly run can be resumed from the last successful stage with `--skip`.

**Per-item caching** — `pub_datasets`, `pub_supplementary`, `pub_grants`, `pub_software`, `repo_analysis`, and `page_navigation` diff candidate items against `tables/final/` so a fresh run only reprocesses genuinely new items. `--no-cache` forces a full reprocess.

**Backwards compatibility** — the legacy Streamlit app reads from both `tables/final/` (v1) and `tables/` root (v0). No breakage during migration.

**Validation at the boundary** — raw scraper output is treated as untrusted. Every stage's output is coerced and validated by `staging/normalizer.py` before writing to `final/`. Invalid rows are written to `hits/rejected_*.tsv` for inspection, never silently dropped. Each output table has a corresponding Pydantic model in `staging/schemas.py` (`SCHEMA_REGISTRY`) documenting its expected shape, but the normalizer's coercion functions — not those Pydantic models — are what actually run at write time.
