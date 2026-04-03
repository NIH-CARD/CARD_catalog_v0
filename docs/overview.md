# CARD Catalog — Architecture Overview

## What It Is

The **CARD Catalog** is a data pipeline + Streamlit web application for discovering and connecting research resources (datasets, publications, code repositories, cellular models) in the Alzheimer's Disease and Related Dementias (ADRD) / Neurodegenerative Diseases (NDD) space.

It is maintained by DataTecnica for NIH's Center for Alzheimer's and Related Dementias (CARD) and NIA's Laboratory of Neurogenetics (LNG).

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CARD Catalog v1                                 │
│                                                                         │
│  ┌──────────────┐    ┌──────────────────────────────────────────────┐   │
│  │  Resources   │    │                 Pipeline                     │   │
│  │  Inventory   │───▶│  Stage 1: pubmed_extract                     │   │
│  │  (.tab file) │    │  Stage 2: github_search                      │   │
│  │              │    │  Stage 3: repo_analysis  (AI)                │   │
│  │  - name      │    │  Stage 4: pub_metadata   (AI)                │   │
│  │  - type      │    │  Stage 5: page_navigation (AI + browser)     │   │
│  │  - diseases  │    └───────────────────┬──────────────────────────┘   │
│  │  - modality  │                        │                              │
│  │  - access URL│              ┌─────────▼──────────┐                   │
│  └──────────────┘              │  tables/hits/      │                   │
│                                │  (intermediate)    │                   │
│                                └─────────┬──────────┘                   │
│                                          │                              │
│                                 ┌────────▼───────┐                      │
│                                 │   Normalizer   │  Pydantic validate   │
│                                 │  (staging/)    │  + field normalize   │
│                                 └────────┬───────┘                      │
│                                          │                              │
│                                ┌─────────▼──────────┐                   │
│                                │  tables/final/     │                   │
│                                │  (app-ready TSVs)  │                   │
│                                └─────────┬──────────┘                   │
│                                          │                              │
│                       ┌──────────────────▼─────────────────────────┐    │
│                       │           Streamlit App (app/)             │    │
│                       │  Resources · Publications · Code · iNDI    │    │
│                       └────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Stages

The pipeline is a staged DAG. Each stage is independently restartable: if a today-dated hits file already exists in `tables/hits/`, the orchestrator skips that stage.

| Stage | Input | Output (hits/) | Description |
|---|---|---|---|
| `pubmed` | inventory.tab | `pubmed_hits_*.tsv` | PubMed search (3 queries: original, v2, v3) |
| `github_search` | inventory.tab | `github_hits_*.tsv` | GitHub search, content fetch, no AI |
| `repo_analysis` | github_hits | `github_analyzed_*.tsv` | AI analysis via external inference engines |
| `pub_metadata` | pubmed_hits | `pub_datasets_*.tsv`, `pub_supplementary_*.tsv` | Dataset + supplementary file extraction from PMC articles |
| `page_navigation` | inventory.tab | `new_corpus_*.tsv` | Study page visits via browser + LLM for metadata verification and new resource discovery |

After each stage, the **normalizer** validates and coerces the hits file to a schema-conformant TSV in `tables/final/`.

---

## Automation Modes

### Weekly (incremental)
Runs every Monday. Fetches only papers from the last 7 days, deduplicates against the existing corpus, and appends new papers to a new timestamped `pubmed_central_*.tsv`.

### Quarterly (full rebuild)
Runs on the first Monday of January, April, July, October. Full 3-year PubMed window plus all other stages (GitHub, pub_metadata, page_navigation).

Both modes are triggered via cron:

```bash
# Weekly — Monday 8am ET
0 12 * * 1 cd /path/to/CARD_catalog_v0 && venv/bin/python orchestrator.py weekly

# Quarterly — first Monday of Jan/Apr/Jul/Oct
0 12 1-7 1,4,7,10 * [ "$(date +\%u)" = "1" ] && cd /path/to/CARD_catalog_v0 && venv/bin/python orchestrator.py quarterly
```

---

## Directory Layout

```
CARD_catalog_v0/
│
├── orchestrator.py          # Pipeline coordinator (entry point)
│
├── pipelines/               # One module per pipeline stage
│   ├── base.py              # PipelineStage ABC
│   ├── pubmed.py            # Stage 1
│   ├── github_search.py     # Stage 2
│   ├── repo_analysis.py     # Stage 3
│   ├── pub_metadata.py      # Stage 4
│   └── page_navigation.py   # Stage 5
│
├── staging/                 # Schema validation + normalization
│   ├── schemas.py           # Pydantic row models per output table
│   └── normalizer.py        # Coerce → validate → write final TSV
│
├── scrapers/                # Raw scrapers (gitignored)
│   ├── scrape_publications.py
│   ├── scrape_github.py
│   ├── batch_ai_analysis.py
│   └── logging_config.py
│
├── app/                     # Streamlit web application
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
│   ├── hits/                # Intermediate pipeline outputs (committed)
│   ├── final/               # App-ready validated outputs (committed)
│   ├── dataset-inventory-*.tab     # Resource inventory (source of truth)
│   ├── iNDI_inventory_*.tsv        # iNDI cellular models (external)
│   └── *.tsv                       # Legacy v0 outputs (still served by app)
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
| `pub_datasets_*.tsv` | `PubDatasetRow` | (future Datasets page) |
| `pub_supplementary_*.tsv` | `SupplementaryRow` | (future Datasets page) |
| `new_corpus_*.tsv` | `NewCorpusRow` | (feeds back into inventory) |

The app resolves the **latest** file matching each pattern, checking `tables/final/` first for v1 outputs and falling back to `tables/` root for legacy v0 files.

---

## External Dependencies

| Dependency | Used by | Notes |
|---|---|---|
| NCBI Entrez API | `pubmed.py` | Free; NCBI API key raises rate limits |
| GitHub REST API | `github_search.py` | Requires `GITHUB_TOKEN` |
| Anthropic API | `repo_analysis.py`, `pub_metadata.py`, app AI features | `ANTHROPIC_API_KEY` |
| `data_gatherer` (pip) | `pub_metadata.py`, `page_navigation.py` | DataTecnica internal package |
| Firefox + geckodriver | `page_navigation.py` | For browser automation; profile auth required |

---

## Design Principles

**Separation of concerns** — scraping, inference, normalization, and presentation are independent layers. A schema change does not require a re-scrape.

**Restartability** — every stage checks for a today-dated hits file before running. A failed quarterly run can be resumed from the last successful stage with `--skip`.

**Backwards compatibility** — the app reads from both `tables/final/` (v1) and `tables/` root (v0). No breakage during migration.

**Validation at the boundary** — raw scraper output is treated as untrusted. Pydantic validates every row before writing to `final/`. Invalid rows are written to `hits/rejected_*.tsv` for inspection, never silently dropped.
