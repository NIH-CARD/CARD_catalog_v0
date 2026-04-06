# CARD Catalog — Coding Conventions

Rules for anyone (human or AI agent) writing code in this repository.

Architecture and API details live in [`docs/`](docs/). Read [`docs/overview.md`](docs/overview.md) before making structural changes.

---

## Logging

Use the project logger, never `print()`.

```python
import logging
logger = logging.getLogger(__name__)
```

Pipeline stages and scrapers get their logger via the module name — this makes log lines self-identifying without extra tagging.

**Log level guidance:**

| Level | When to use |
|---|---|
| `DEBUG` | Per-row / per-item detail, only useful when diagnosing |
| `INFO` | Stage start/end, row counts, file paths written |
| `WARNING` | Recoverable issues: missing optional fields, fallback taken, row rejected |
| `ERROR` | Stage failed, file not found, API call failed — always include `exc_info=True` |

**Required INFO logs for pipeline stages:**
- Input path and row count on load
- Output path and row count on write
- Counts of valid vs rejected rows after normalization

```python
# Good
logger.info(f"Loaded {len(df)} rows from {input_path.name}")
logger.info(f"Wrote {len(out)} rows → {output_path.name}")
logger.warning(f"[pubmed_search] {n_rejected} rows rejected — see {rejected_path.name}")
logger.error(f"API call failed: {e}", exc_info=True)

# Bad
print(f"Done: {output_path}")
logger.info("Processing complete")   # no counts, no path
```

Log file location: `logs/` at project root. Never write logs to the working directory or inside `scrapers/`. Use `logging_config.get_default_log_file(prefix)` for new scrapers.

---

## Docstrings

Use **Google style** for all public functions, classes, and modules.

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

- Module-level docstrings: one paragraph of what the module does + CLI usage if applicable (see `staging/normalizer.py` as the reference).
- Skip docstrings on private helpers (`_fix_pmc_link`, `_normalize_authors`, etc.) unless the logic is non-obvious.
- No docstrings on `__init__` if the class docstring covers it.

---

## Pipeline stages

All stages subclass `PipelineStage` from `pipelines/base.py`:

```python
from pipelines.base import PipelineStage

class MyStage(PipelineStage):
    def run(self, input_path: Path, output_path: Path, **kwargs) -> Path:
        ...
        return output_path
```

Rules:
- Stages are **stateless** — no instance variables, all config passed via `kwargs`.
- A stage must always return `output_path`, even if writing failed (caller checks `.exists()`).
- Stages write to `tables/hits/`, never directly to `tables/final/`. The orchestrator calls the normalizer after each stage.
- Long-running operations (API calls, subprocess) log start and end at INFO.
- Use `subprocess.run([...], check=True)` for scraper subprocesses. Capture stderr to the logger, not the terminal.

---

## Schemas and validation

Adding a new output table:

1. Add a Pydantic model to `staging/schemas.py` subclassing `_Base`.
2. Declare `COLUMNS: ClassVar[list[str]]` — the ordered list of app-facing column names (spaces, not underscores).
3. Register it in `SCHEMA_REGISTRY`.
4. Add a rename map entry to `staging/normalizer.py::_RENAME` if scraper column names differ.
5. Add a normalizer function to `staging/normalizer.py::_NORMALIZERS`.

```python
from typing import ClassVar
from staging.schemas import _Base

class MyRow(_Base):
    COLUMNS: ClassVar[list[str]] = ["Resource Name", "My Field"]
    Resource_Name: str = ""
    My_Field: str = ""
```

**Never** use plain `list[str]` for class-level constants in Pydantic models — Pydantic v2 will treat them as model fields. Always use `ClassVar`.

---

## File and path conventions

- All paths in code are `pathlib.Path`, never bare strings.
- Intermediate outputs → `tables/hits/<stage>_hits_<YYYYMMDD>.tsv`
- Validated outputs → `tables/final/<target>_<YYYYMMDD>.tsv`
- Only one file per target in `tables/final/` — the normalizer removes older files after writing.
- Log files → `logs/<scraper>_<YYYYMMDD_HHMMSS>.log`
- FAIR compliance logs → `tables/hits/fair_compliance_log_<YYYYMMDD_HHMMSS>.tsv`

Never hardcode absolute paths. Derive from `__file__`:

```python
PROJECT_ROOT = Path(__file__).parent.parent
```

---

## Data handling

- Load TSVs with `dtype=str` and `.fillna("")` — all fields are strings at the boundary.
- Multi-value fields (diseases, modalities, authors, languages) are **semicolon-delimited**. Normalize with `staging.normalizer._normalize_list_field()`.
- Never silently drop rows. Invalid rows go to `tables/hits/rejected_{target}_{ts}.tsv` with a `_validation_errors` column.
- App data loaders are cached with `@st.cache_data(ttl=3600)`. Add a "Clear Cache" affordance if a page introduces new loaders.

---

## What not to do

- **No `print()`** anywhere in pipeline or app code.
- **No hardcoded API keys or paths** — always read from env vars or `config.py`. Keys in use: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN`, `NCBI_API_KEY`, `FIREFOX_PROFILE_DIR`.
- **No writing to `tables/final/` from a stage** — only the normalizer writes there.
- **No adding columns to Pydantic models without updating `COLUMNS`** — the normalizer uses `COLUMNS` to order the output.
- **No speculative abstractions** — don't build helpers for hypothetical future tables. Add them when needed.
- **No backwards-compatibility shims** — if a column is renamed, update the rename map in `_RENAME` and move on.

---

## Docs

Sphinx source lives in `docs/`. Build locally with:

```bash
cd docs && make html
```

Output at `docs/_build/html/` (gitignored). CI rebuilds and deploys to GitHub Pages on push to `main` when `docs/`, `pipelines/`, `staging/`, or `orchestrator.py` change.

If you add a new module to `pipelines/` or `staging/`, add an autodoc stub to `docs/autoapi/`.
