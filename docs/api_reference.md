# API Reference

Reference for the `pipelines/` and `staging/` Python modules.

---

## `orchestrator.py`

Entry point for the automation pipeline. Run directly as a script.

```
python orchestrator.py {weekly|quarterly} [options]
```

### Arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `mode` | positional | — | `weekly` or `quarterly` |
| `--inventory` | path | latest `resources-inventory*` in `tables/` | Resource inventory `.tab` file |
| `--query-method` | str | `v2` | PubMed query strategy: `original`, `v2`, `v3` |
| `--max-results` | int | `100` | Max PubMed results per resource |
| `--ncbi-api-key` | str | `$NCBI_API_KEY` | NCBI Entrez API key |
| `--github-token` | str | `$GITHUB_TOKEN` | GitHub personal access token |
| `--anthropic-key` | str | `$ANTHROPIC_API_KEY` | Anthropic API key |
| `--firefox-profile-dir` | path | `$FIREFOX_PROFILE_DIR` | Pre-authenticated Firefox profile |
| `--skip` | list | `[]` | Stage names to skip, e.g. `--skip page_navigation repo_analysis` |
| `--force` | flag | off | Re-run stages even if today's hits file exists |
| `--verbose` | flag | off | Enable DEBUG logging in subprocesses |

### Update mode

1. Runs `pubmed_search` stage with `years=0.02` (~7 days)
2. Runs normalizer → `tables/final/pubmed_central_{ts}.tsv`

### Full rebuild mode

Runs stages in dependency order:

```
pubmed_search → [normalize publications]
    └── pub_metadata → [normalize pub_datasets, supplementary]
github_search → repo_analysis → [normalize code]
page_navigation → [normalize new_corpus]
```

---

## `pipelines.base`

### `class PipelineStage` (ABC)

Abstract base class for all pipeline stages.

```python
from pipelines.base import PipelineStage
```

#### `run(input_path, output_path, **kwargs) → Path`

Execute the stage.

| Parameter | Type | Description |
|---|---|---|
| `input_path` | `Path` | Input file (inventory or previous stage's hits file) |
| `output_path` | `Path` | Destination path in `tables/hits/` |
| `**kwargs` | — | Stage-specific keyword arguments (see each stage below) |

Returns the `output_path` that was written.

---

## `pipelines.pubmed_search`

### `class PubmedStage(PipelineStage)`

Wraps `scrapers/scrape_publications.py` as a subprocess.

```python
from pipelines.pubmed_search import PubmedStage
stage = PubmedStage()
out = stage.run(
    input_path=Path("tables/resources-inventory-Mar_11_2026.tab"),
    output_path=Path("tables/hits/pubmed_hits_20260329.tsv"),
    query_method="v3",
    years=3,
    max_results=100,
    ncbi_api_key="...",
    verbose=False,
)
```

#### `run()` kwargs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query_method` | str | `"v3"` | PubMed query strategy |
| `years` | float | `3` | Date window in years (use `0.02` for ~7 days) |
| `max_results` | int | `100` | Max results per resource |
| `ncbi_api_key` | str\|None | `None` | NCBI API key; falls back to env var |
| `verbose` | bool | `False` | Enable DEBUG logging |

#### Query methods

| Method | Description |
|---|---|
| `original` | `[All Fields]` + disease terms + modality terms |
| `v2` | `[tiab]` only, noisy abbreviation filter (highest precision) |
| `v3` | `[tiab]` + disease terms + modality terms (v2 precision + broader recall) |

---

## `pipelines.github_search`

### `class GithubSearchStage(PipelineStage)`

Wraps `scrapers/scrape_github.py` with `--batch-call-ai` (search + content fetch, no inline AI). AI analysis is deferred to `repo_analysis`.

```python
from pipelines.github_search import GithubSearchStage
stage = GithubSearchStage()
out = stage.run(
    input_path=Path("tables/resources-inventory-Mar_11_2026.tab"),
    output_path=Path("tables/hits/github_hits_20260329.tsv"),
    github_token="ghp_...",
    verbose=False,
)
```

#### `run()` kwargs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `github_token` | str | — | **Required.** GitHub personal access token |
| `verbose` | bool | `False` | Enable DEBUG logging |

Output includes a `Content_For_Analysis` column consumed by `repo_analysis`.

---

## `pipelines.repo_analysis`

### `class RepoAnalysisStage(PipelineStage)`

Wraps `scrapers/batch_ai_analysis.py` (Batch API, ~50% cost savings vs synchronous).

```python
from pipelines.repo_analysis import RepoAnalysisStage
stage = RepoAnalysisStage()
out = stage.run(
    input_path=Path("tables/hits/github_hits_20260329.tsv"),
    output_path=Path("tables/hits/github_analyzed_20260329.tsv"),
    anthropic_key="sk-ant-...",
    verbose=False,
)
```

#### `run()` kwargs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `anthropic_key` | str\|None | `None` | Anthropic API key; falls back to env var |
| `verbose` | bool | `False` | Enable DEBUG logging |

Adds columns: `Biomedical Relevance`, `Code Summary`, `Data Types`, `Tooling`.

---

## `pipelines.pub_metadata`

### `class PubMetadataStage(PipelineStage)`

Calls `data_gatherer.DataGatherer.process_articles()` against PMC links from the pubmed hits file. Writes two hits files:

- `pub_datasets_{ts}.tsv` — dataset mentions (`Dataset_w_Context` schema)
- `pub_supplementary_{ts}.tsv` — supplementary file mentions (`SupplementaryFileKeywords` schema)

The supplementary file is written as a side-effect; its path is derived by replacing `pub_datasets` with `pub_supplementary` in the stem of `output_path`.

```python
from pipelines.pub_metadata import PubMetadataStage
stage = PubMetadataStage()
out = stage.run(
    input_path=Path("tables/hits/pubmed_hits_20260329.tsv"),
    output_path=Path("tables/hits/pub_datasets_20260329.tsv"),
    anthropic_key="sk-ant-...",
    verbose=False,
)
```

#### `run()` kwargs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `anthropic_key` | str\|None | `None` | Anthropic API key |
| `verbose` | bool | `False` | Enable DEBUG logging |

Requires `data_gatherer` package (installed from DataTecnica internal repo).

---

## `pipelines.page_navigation`

### `class PageNavigationStage(PipelineStage)`

Calls `data_gatherer.DataGatherer.process_metadata()` to visit each resource's Access URL and Alternative URLs with a headless Firefox browser, extracting verified metadata and discovering new corpus entries.

```python
from pipelines.page_navigation import PageNavigationStage
stage = PageNavigationStage()
out = stage.run(
    input_path=Path("tables/resources-inventory-Mar_11_2026.tab"),
    output_path=Path("tables/hits/new_corpus_20260329.tsv"),
    firefox_profile_dir="~/.card-catalog-firefox-profile",
    anthropic_key="sk-ant-...",
    verbose=False,
)
```

#### `run()` kwargs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `firefox_profile_dir` | str\|None | `$FIREFOX_PROFILE_DIR` | Pre-authenticated Firefox profile path. Raises `EnvironmentError` if not set |
| `anthropic_key` | str\|None | `None` | Anthropic API key |
| `verbose` | bool | `False` | Enable DEBUG logging |

#### Profile setup

```bash
python -m pipelines.page_navigation --setup-profile
```

Launches Firefox interactively so you can log in to restricted portals. Profile is saved to `~/.card-catalog-firefox-profile` and reused headlessly on subsequent runs.

#### Output columns

Mirrors `study_sanity_check_w_rationale_schema_claude`:

`coarse_data_modality`, `granular_data_modality`, `diseases_included`, `sample_size`, `publication_urls`, `dataset_urls`, `rationale`

---

## `staging.schemas`

Pydantic row models for each output table. All string fields coerce `None`/`NaN` to `""`.

```python
from staging.schemas import (
    PublicationRow,
    CodeRepoRow,
    PubDatasetRow,
    SupplementaryRow,
    NewCorpusRow,
    SCHEMA_REGISTRY,
)
```

### `SCHEMA_REGISTRY`

```python
SCHEMA_REGISTRY: dict[str, type[_Base]] = {
    "publications":  PublicationRow,
    "code":          CodeRepoRow,
    "pub_datasets":  PubDatasetRow,
    "supplementary": SupplementaryRow,
    "new_corpus":    NewCorpusRow,
}
```

### `PublicationRow`

| Field | App column |
|---|---|
| `PMID` | `PMID` |
| `Resource_Name` | `Resource Name` |
| `Abbreviation` | `Abbreviation` |
| `Diseases_Included` | `Diseases Included` |
| `Coarse_Data_Modality` | `Coarse Data Modality` |
| `Granular_Data_Modality` | `Granular Data Modality` |
| `PubMed_Central_Link` | `PubMed Central Link` |
| `Authors` | `Authors` |
| `Affiliations` | `Affiliations` |
| `Title` | `Title` |
| `Abstract` | `Abstract` |
| `Keywords` | `Keywords` |

### `CodeRepoRow`

| Field | App column |
|---|---|
| `Resource_Name` | `Resource Name` |
| `Abbreviation` | `Abbreviation` |
| `Diseases_Included` | `Diseases Included` |
| `Repository_Link` | `Repository Link` |
| `Owner` | `Owner` |
| `Contributors` | `Contributors` |
| `Languages` | `Languages` |
| `Biomedical_Relevance` | `Biomedical Relevance` |
| `Code_Summary` | `Code Summary` |
| `Data_Types` | `Data Types` |
| `Tooling` | `Tooling` |

### `PubDatasetRow`

| Field | App column |
|---|---|
| `Source_PMID` | `Source PMID` |
| `Source_Resource_Name` | `Source Resource Name` |
| `Dataset_Identifier` | `Dataset Identifier` |
| `Data_Repository` | `Data Repository` |
| `Dataset_Webpage` | `Dataset Webpage` |
| `Citation_Type` | `Citation Type` |
| `Usage_Description` | `Usage Description` |
| `Dataset_Scope` | `Dataset Scope` |
| `Results_Relationship` | `Results Relationship` |
| `Decision_Rationale` | `Decision Rationale` |

### `SupplementaryRow`

| Field | App column |
|---|---|
| `Source_PMID` | `Source PMID` |
| `Source_Resource_Name` | `Source Resource Name` |
| `File_URL` | `File URL` |
| `File_Name` | `File Name` |
| `File_Extension` | `File Extension` |
| `File_Format` | `File Format` |
| `Keywords` | `Keywords` |
| `Data_Repository` | `Data Repository` |
| `Number_Of_Files` | `Number Of Files` |
| `File_License` | `File License` |

### `NewCorpusRow`

| Field | App column |
|---|---|
| `Resource_Name` | `Resource Name` |
| `Diseases_Included` | `Diseases Included` |
| `Coarse_Data_Modality` | `Coarse Data Modality` |
| `Granular_Data_Modality` | `Granular Data Modality` |
| `Sample_Size` | `Sample Size` |
| `Access_URL` | `Access URL` |
| `Publication_URLs` | `Publication URLs` |
| `Rationale` | `Rationale` |

---

## `staging.normalizer`

### `normalize(input_path, target, output_path) → Path`

Normalize a hits TSV to a validated, app-ready TSV.

```python
from staging.normalizer import normalize
from pathlib import Path

out = normalize(
    input_path=Path("tables/hits/pubmed_hits_20260329.tsv"),
    target="publications",
    output_path=Path("tables/final/pubmed_central_20260329.tsv"),
)
```

| Parameter | Type | Description |
|---|---|---|
| `input_path` | `Path` | Raw hits file |
| `target` | str | Key from `SCHEMA_REGISTRY` |
| `output_path` | `Path` | Destination in `tables/final/` |

**Raises** `KeyError` if `target` is not in `SCHEMA_REGISTRY`.

**Side effects:**
- Writes rejected rows to `tables/hits/rejected_{target}_{ts}.tsv` if any rows fail validation
- Logs counts of valid vs rejected rows at INFO level

**Normalization applied per target:**

| Target | Normalizations |
|---|---|
| `publications` | Fix PMC link double-prefix; deduplicate authors; semicolon-sort diseases, keywords, modalities |
| `code` | Semicolon-sort diseases, data types, tooling, languages |
| `pub_datasets` | Column rename from `data_gatherer` output names |
| `supplementary` | Column rename; extract supplementary_file_keywords |
| `new_corpus` | Extract first URL from `dataset_urls` list; join `publication_urls` list; semicolon-sort diseases/modalities |

### CLI

```bash
python -m staging.normalizer \
    --input  tables/hits/pubmed_hits_20260329.tsv \
    --target publications \
    --output tables/final/pubmed_central_20260329.tsv
```

| Flag | Description |
|---|---|
| `--input / -i` | Input hits TSV (required) |
| `--target / -t` | Target schema name (required) |
| `--output / -o` | Output path (required) |

---

## `app.utils.data_loader`

### `get_latest_file(pattern, directory='') → Path`

Returns the most recently modified file matching one or more glob patterns.

```python
from app.utils.data_loader import get_latest_file

# Single pattern (v0 behaviour)
f = get_latest_file("pubmed_central*", "/path/to/tables")

# List of patterns — checked in order, latest across all returned
f = get_latest_file(
    ["final/pubmed_central*", "pubmed_central*"],
    "/path/to/tables"
)
```

**Raises** `FileNotFoundError` if no files match any pattern.

### `load_publications() → pd.DataFrame`

Load and normalize the latest publications TSV. Cached for 1 hour (`@st.cache_data(ttl=3600)`).

### `load_datasets() → pd.DataFrame`

Load and normalize the latest dataset inventory. Cached for 1 hour.

### `load_code_repos() → pd.DataFrame`

Load and normalize the latest code repositories TSV. Cached for 1 hour.

### `load_indi_inventory() → pd.DataFrame`

Load the latest iNDI inventory. Cached for 1 hour.

### `load_fair_compliance() → pd.DataFrame`

Load the latest FAIR compliance log from `tables/`. Cached for 1 hour.

---

## Environment Variables

| Variable | Required by | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | `repo_analysis`, `pub_metadata`, `page_navigation`, Streamlit app | Anthropic API key |
| `NCBI_API_KEY` | `pubmed_search` | NCBI Entrez API key (optional; raises rate limits from 3/s to 10/s) |
| `GITHUB_TOKEN` | `github_search` | GitHub personal access token (required for GitHub scraping) |
| `FIREFOX_PROFILE_DIR` | `page_navigation` | Path to pre-authenticated Firefox profile |
