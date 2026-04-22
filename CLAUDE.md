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

## Logging

Every module must have a module-level logger — never `print()`.

```python
import logging
logger = logging.getLogger(__name__)
```

| Level | When to use |
|---|---|
| `DEBUG` | Per-row / per-item detail, only useful when diagnosing |
| `INFO` | Stage start/end, row counts, file paths written |
| `WARNING` | Recoverable issues: missing optional fields, fallback taken, row rejected |
| `ERROR` | Stage failed, file not found, API call failed — always include `exc_info=True` |

Required INFO logs for pipeline stages: input path + row count on load, output path + row count on write, valid vs rejected counts after normalization.

```python
# Good
logger.info(f"Loaded {len(df)} rows from {input_path.name}")
logger.info(f"Wrote {len(out)} rows → {output_path.name}")
logger.warning(f"{n_rejected} rows rejected — see {rejected_path.name}")
logger.error(f"API call failed: {e}", exc_info=True)
```

Log files go in `logs/` at project root. Use `logging_config.get_default_log_file(prefix)` for new scrapers.

## Docstrings

Google style for all public functions, classes, and modules.

```python
def normalize(input_path: Path, target: str, output_path: Path) -> Path:
    """Normalize a hits TSV and write a validated, app-ready TSV.

    Args:
        input_path: Path to raw hits file in tables/hits/.
        target: Schema name from SCHEMA_REGISTRY.
        output_path: Destination path in tables/final/.

    Returns:
        output_path if successful.

    Raises:
        KeyError: If target is not in SCHEMA_REGISTRY.
    """
```

Skip docstrings on private helpers unless the logic is non-obvious. No docstring on `__init__` if the class docstring covers it.

## Pipeline Stage Rules

All stages subclass `PipelineStage` from `pipelines/base.py`. Stages are **stateless** — no instance variables, all config via `kwargs`. A stage must always return `output_path` even on failure (caller checks `.exists()`). Stages write to `tables/hits/` only; the orchestrator calls the normalizer afterward. Use `subprocess.run([...], check=True)` for scraper subprocesses and capture stderr to the logger, not the terminal.

## Schemas and Validation

Adding a new output table:

1. Add a Pydantic model to `staging/schemas.py` subclassing `_Base`.
2. Declare `COLUMNS: ClassVar[list[str]]` — ordered app-facing column names (spaces, not underscores).
3. Register it in `SCHEMA_REGISTRY`.
4. Add a rename map entry to `staging/normalizer.py::_RENAME` if scraper column names differ.
5. Add a normalizer function to `staging/normalizer.py::_NORMALIZERS`.

Use `ClassVar` for `COLUMNS` — Pydantic v2 treats plain `list[str]` class attributes as model fields.

## File and Path Conventions

- All paths in code are `pathlib.Path`, never bare strings.
- Derive project root from `__file__`: `PROJECT_ROOT = Path(__file__).parent.parent`
- Intermediate outputs → `tables/hits/<stage>_hits_<YYYYMMDD>.tsv`
- Validated outputs → `tables/final/<target>_<YYYYMMDD>.tsv` (normalizer removes older files for the same target)
- Log files → `logs/<scraper>_<YYYYMMDD_HHMMSS>.log`

## Data Handling

- Load TSVs with `dtype=str` and `.fillna("")` — all fields are strings at the boundary.
- Multi-value fields (diseases, modalities, authors, languages) are **semicolon-delimited**. Normalize with `staging.normalizer._normalize_list_field()`.
- Never silently drop rows — invalid rows go to `tables/hits/rejected_{target}_{ts}.tsv` with a `_validation_errors` column.
- App data loaders use `@st.cache_data(ttl=3600)`. Add a "Clear Cache" affordance if a page introduces new loaders.

## What Not To Do

- **No `print()`** anywhere in pipeline or app code.
- **No hardcoded API keys or paths** — always read from env vars or `config.py`.
- **No writing to `tables/final/` from a stage** — only the normalizer writes there.
- **No adding columns to Pydantic models without updating `COLUMNS`** — the normalizer uses `COLUMNS` to order output.
- **No speculative abstractions** — add helpers when needed, not for hypothetical future tables.
- **No backwards-compatibility shims** — if a column is renamed, update `_RENAME` and move on.

## Gotchas

- **Page 4 (Datasets & Supplementary) is an empty file** — pipeline produces the TSVs, schemas exist, data_loader can load them, but the Streamlit page has not been implemented yet.
- **`data_gatherer` is a DataTecnica internal package** — not on PyPI; required by `pub_metadata` and `page_navigation`. Install from the internal repo before running those stages.
- **Normalizer auto-deletes old files for the same target** — running normalize twice for `publications` keeps only the latest `pubmed_central_*.tsv` in `tables/final/`.
- **Restartability**: stages skip automatically if a today-dated hits file already exists. Use `--force` to override.
- **App fallback**: `get_latest_file()` accepts a list of patterns; the app checks `final/` first, falls back to `tables/` root for legacy v0 files.
- **Page 5 is iNDI** (Human Cellular Models), not a datasets page — numbering matters for navigation.

## Current Status (April 2026)

Branch `from_v0_to_v1` — active migration. All pipeline stages and normalizer are implemented and producing output in `tables/final/`. App pages 1–3 and 5–6 are functional. Page 4 (Datasets & Supplementary) is next to implement. Next milestone: NDD expansion and automated weekly/quarterly cron on server.
