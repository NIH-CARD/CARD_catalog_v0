# CARD Catalog v0 → v1

Data pipeline + Streamlit app for discovering and connecting research resources (datasets, publications, code repos, cellular models) in the ADRD/NDD space. Maintained by DataTecnica for NIH CARD and NIA LNG.

## Directory Layout

```
CARD_catalog_v0/
├── orchestrator.py          # Pipeline entry point
├── pipelines/               # One module per stage (base.py + 5 stages)
├── staging/                 # schemas.py (Pydantic row models) + normalizer.py
├── scrapers/                # Raw scrapers called as subprocesses
├── app/
│   ├── Home.py
│   ├── config.py            # DATA_FILES_PTRS, TABLES_DIR, HITS_DIR
│   ├── pages/               # 1_Resources, 2_Publications, 3_Code, 4_Datasets* (EMPTY), 5_Human_Cellular_Models, 6_About
│   └── utils/               # data_loader.py, graph_builder.py, llm_utils.py, export_utils.py
├── tables/
│   ├── hits/                # Intermediate outputs (committed)
│   ├── final/               # App-ready validated TSVs (committed)
│   └── *.tsv / *.tab        # Legacy v0 files + resource inventory
└── scripts/                 # Exploratory work
```

## Running Things

```bash
# App
streamlit run app/Home.py

# Pipeline — update (last 7 days of PubMed)
python orchestrator.py update

# Pipeline — full rebuild (all 5 stages, 3-year window)
python orchestrator.py full_rebuild

# Skip stages
python orchestrator.py full_rebuild --skip page_navigation repo_analysis

# Force re-run even if today's hits file exists
python orchestrator.py full_rebuild --force

# Normalizer standalone
python -m staging.normalizer --input tables/hits/pubmed_hits_YYYYMMDD.tsv \
    --target publications --output tables/final/pubmed_central_YYYYMMDD.tsv

# Firefox profile setup (one-time, for page_navigation)
python -m pipelines.page_navigation --setup-profile
```

## Pipeline Stages

| Stage | Input | Output (hits/) | Tool |
|---|---|---|---|
| `pubmed_search` | inventory.tab | `pubmed_hits_*.tsv` | scrapers/scrape_publications.py subprocess |
| `pub_metadata` | pubmed_hits | `pub_datasets_*.tsv`, `pub_supplementary_*.tsv` | data_gatherer (internal pkg) |
| `github_search` | inventory.tab | `github_hits_*.tsv` | scrapers/scrape_github.py subprocess |
| `repo_analysis` | github_hits | `github_analyzed_*.tsv` | scrapers/batch_ai_analysis.py (Batch API) |
| `page_navigation` | inventory.tab | `new_corpus_*.tsv` | data_gatherer + headless Firefox |

After each stage, the normalizer validates and writes to `tables/final/`. Rejected rows go to `tables/hits/rejected_*.tsv`.

## Staging Schemas (SCHEMA_REGISTRY keys)

`publications` → `PublicationRow` → `pubmed_central_*.tsv`  
`code` → `CodeRepoRow` → `gits_to_reannotate_completed_*.tsv`  
`pub_datasets` → `PubDatasetRow` → `pub_datasets_*.tsv`  
`supplementary` → `SupplementaryRow` → `pub_supplementary_*.tsv`  
`new_corpus` → `NewCorpusRow` → `new_corpus_*.tsv`

## Environment Variables

```bash
ANTHROPIC_API_KEY    # repo_analysis, pub_metadata, page_navigation, app AI features
NCBI_API_KEY         # optional; raises rate limit from 3/s to 10/s
GITHUB_TOKEN         # required for github_search
FIREFOX_PROFILE_DIR  # path to pre-authenticated Firefox profile (page_navigation)
```

Streamlit secrets: `.streamlit/secrets.toml` (template at `.streamlit/secrets.toml.template`).  
Pipeline secrets: `scrapers/.env` (template at `scrapers/.env.template`).

## Logging Rules

Every module must have a module-level logger and emit log statements throughout:

```python
import logging
logger = logging.getLogger(__name__)
```

- `logger.info()` — stage start/end, file paths written, row counts, key decisions
- `logger.debug()` — per-item progress, intermediate values, skipped items
- `logger.warning()` — missing optional inputs, fallback behaviour, partial failures
- `logger.error()` — unrecoverable failures before raising or returning `None`
- **Never use `print()`** — always use the module logger
- Pipeline stages receive a `log_file` kwarg from the orchestrator and must forward it to subprocesses; the orchestrator writes to `logs/orchestrator_{timestamp}.log` by default

## Gotchas

- **Orchestrator modes are `update` / `full_rebuild`** — the api_reference.md incorrectly says `weekly`/`quarterly`.
- **Page 4 (Datasets & Supplementary) is an empty file** — pipeline produces the TSVs, schemas exist, data_loader can load them, but the Streamlit page has not been implemented yet.
- **`data_gatherer` is a DataTecnica internal package** — not on PyPI; required by `pub_metadata` and `page_navigation`. Install from the internal repo before running those stages.
- **Normalizer auto-deletes old files for the same target** — running normalize twice for `publications` keeps only the latest `pubmed_central_*.tsv` in `tables/final/`.
- **Restartability**: stages skip automatically if a today-dated hits file already exists. Use `--force` to override.
- **App fallback**: `get_latest_file()` accepts a list of patterns; the app checks `final/` first, falls back to `tables/` root for legacy v0 files.
- **Page 5 is iNDI** (Human Cellular Models), not a datasets page — numbering matters for navigation.

## Current Status (April 2026)

Branch `from_v0_to_v1` — active migration. All pipeline stages and normalizer are implemented and producing output in `tables/final/`. App pages 1–3 and 5–6 are functional. Page 4 (Datasets & Supplementary) is next to implement. Next milestone: NDD expansion and automated weekly/quarterly cron on server.
