# API Reference

Reference for the `pipelines/` and `staging/` Python modules.

---

## `orchestrator.py`

Entry point for the automation pipeline. Run directly as a script.

```
python orchestrator.py {update|full_rebuild} [options]
```

### Arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `mode` | positional | — | `update` or `full_rebuild` |
| `--inventory` | path | latest `resources-inventory*` in `tables/` | Resource inventory `.tab` file |
| `--query-method` | str | `v3` | PubMed query strategy: `original`, `v2`, `v3` |
| `--max-results` | int | `100` | Max PubMed results per resource |
| `--ncbi-api-key` | str | `$NCBI_API_KEY` | NCBI Entrez API key |
| `--github-token` | str | `$GITHUB_TOKEN` | GitHub personal access token |
| `--anthropic-key` | str | `$ANTHROPIC_API_KEY` | Anthropic API key |
| `--firefox-profile-dir` | path | `$FIREFOX_PROFILE_DIR` | Pre-authenticated Firefox profile |
| `--skip` | list | `[]` | Stage names to skip, e.g. `--skip page_navigation repo_analysis` |
| `--force` | flag | off | Re-run stages even if today's hits file exists (whole-stage skip) |
| `--no-cache` | flag | off | Bypass the per-item cache in `pub_datasets`/`pub_supplementary`/`pub_grants`/`pub_software`/`repo_analysis`/`page_navigation` — reprocess every item instead of only new ones |
| `--verbose` | flag | off | Enable DEBUG logging in subprocesses |

### Update mode

1. Runs `pubmed_search` stage with `years=0.02` (~7 days)
2. Runs normalizer → `tables/final/pubmed_central_{ts}.tsv`

### Full rebuild mode

Runs stages in dependency order:

```
pubmed_search → [normalize publications]
    └── prefetch_articles (shared PMC full-text cache, tables/cache/pub_fulltext_cache.parquet)
    └── run_stages_concurrently (thread pool):
            pub_datasets       → [normalize pub_datasets]
            pub_supplementary  → [normalize supplementary]
            pub_grants         → [normalize pub_grants]
            pub_software       → [normalize pub_software]
        └── build extra_repos_from_software (GitHub URLs among pub_software's
            mentions, joined back to pubmed_hits for Resource Name/Abbreviation)
scilite → [normalize scilite]
github_search (+ --extra-repos extra_repos_from_software) → repo_analysis → [normalize code]
page_navigation → [normalize new_corpus]
join_annotations (always runs — merges scilite + cited-dataset info into publications)
```

`pub_datasets`/`pub_supplementary`/`pub_grants`/`pub_software` are fully independent
of each other (separate `DataGatherer` instances, separate outputs, separate
per-item caches) and each just blocks on its own Anthropic Batch job, so
`orchestrator.py::run_stages_concurrently` runs them in a thread pool rather
than sequentially — wall-clock is roughly the slowest one instead of the sum
of all four.

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

### `run_stages_concurrently(specs, input_path, skip_stages, force=False) → dict[str, Path|None]`

Defined in `orchestrator.py`. Runs several independent stages concurrently via
a `ThreadPoolExecutor`, applying the same skip-if-today-file / `--skip` logic
as `run_stage()` per spec before launching only the stages that actually need
to run.

```python
results = run_stages_concurrently(
    specs=[
        ("pub_datasets", PubDatasetsStage(), "pub_datasets_*.tsv", stage_kwargs),
        ("pub_supplementary", PubSupplementaryStage(), "pub_supplementary_*.tsv", stage_kwargs),
        ("pub_grants", PubGrantsStage(), "pub_grants_*.tsv", stage_kwargs),
        ("pub_software", PubSoftwareStage(), "pub_software_*.tsv", stage_kwargs),
    ],
    input_path=pubmed_hits,
    skip_stages=skip_stages,
    force=force,
)
# results["pub_datasets"], results["pub_grants"], etc. → Path | None
```

| Parameter | Type | Description |
|---|---|---|
| `specs` | `list[tuple[str, PipelineStage, str, dict]]` | `(stage_name, stage_instance, hits_pattern, stage_kwargs)` tuples |
| `input_path` | `Path` | Shared input file passed to every stage |
| `skip_stages` | `list[str]` | Stage names to skip (same semantics as `run_stage`) |
| `force` | `bool` | Re-run even if today's hits file exists |

A failing stage is caught and logged per-stage (returns `None` for that key)
without affecting the others' results.

---

## `pipelines.pub_metadata_shared`

Shared helpers for the four concurrent publication-enrichment stages below —
all four read the same `pubmed_hits_{ts}.tsv` input and need the same PMC
link list and article full text.

### `load_pmc_links(input_path) → list[str]`

Unique, non-empty values from the `PubMed Central Link` column.

### `prefetch_articles(pmc_links, cache_path, log_level="INFO", log_file_str=None, sects_required=5) → None`

Fetches every PMC article once and reads/updates a shared parquet cache at
`cache_path` (stable filename, e.g. `tables/cache/pub_fulltext_cache.parquet`
— not timestamped, reused and updated across runs). If `cache_path` already
exists, already-cached articles are read from it instead of refetched; only
genuinely new articles hit the network, and the file is rewritten in place
with the full merged set.

`sects_required` **must match** what the four stages themselves use —
`DataGatherer.run_integrated_batch_processing()`'s own default is `5`, not
`fetch_data()`'s default of `1`. If they don't match, an article cached here
as "complete" at the lower bar fails the stricter re-check inside a stage's
own fetch call, and that stage falls through the full HTTPGetRequest/Selenium
fallback chain a second time — concurrently, since all four stages run in
threads — defeating both the cache and the point of prefetching.

Called once from `orchestrator.py::run_full_rebuild`, before
`run_stages_concurrently` launches the four stages below. Each stage passes
`cache_path` back in as `fetch_cache_path`, using it as
`DataGatherer(raw_data_df_parquet_filepath=...)` (covers `pub_supplementary`'s
`process_articles()`, which has no per-call cache parameter) and, for the
three stages using `run_integrated_batch_processing`, also as
`local_fetch_file=...`.

---

## `pipelines.pub_datasets`

### `class PubDatasetsStage(PipelineStage)`

Extracts dataset mentions from PMC articles via
`DataGatherer.run_integrated_batch_processing()` (Anthropic Batch API,
`CLAUDE_FDR_FewShot_shortDescr` prompt, semantic retrieval over the data
availability statement) or, with `batch_mode=False`, the synchronous
`process_articles()` path.

```python
from pipelines.pub_datasets import PubDatasetsStage
stage = PubDatasetsStage()
out = stage.run(
    input_path=Path("tables/hits/pubmed_hits_20260329.tsv"),
    output_path=Path("tables/hits/pub_datasets_20260329.tsv"),
    anthropic_key="sk-ant-...",
    verbose=False,
    use_cache=True,
    fetch_cache_path=Path("tables/cache/pub_fulltext_cache.parquet"),
)
```

#### `run()` kwargs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `batch_mode` | bool | `True` | Use the Anthropic Batch API path vs synchronous `process_articles()` |
| `full_document_read` | bool | `True` | Pass the entire document vs a retrieved excerpt |
| `anthropic_key` | str\|None | `None` | Anthropic API key |
| `verbose` | bool | `False` | Enable DEBUG logging |
| `use_cache` | bool | `True` | Skip PMC links already in `tables/final/pub_datasets_*.tsv` (diffed on the `source_url` column) |
| `fetch_cache_path` | Path\|None | `None` | Shared full-text parquet cache from `prefetch_articles` |

Output columns: `pub_title, source_url, raw_data_format, dataset_identifier,
data_repository, dataset_context_from_paper, dataset_keywords, citation_type`.

Requires `data_gatherer` (installed from the VIDA-NYU internal repo).

---

## `pipelines.pub_supplementary`

### `class PubSupplementaryStage(PipelineStage)`

Extracts supplementary-file mentions via the synchronous
`DataGatherer.process_articles()` path (`supplementary_files_keywords_schema`,
section filter `supplementary_material`). Same `run()` kwargs as
`PubDatasetsStage` except no `batch_mode`/`full_document_read` (this stage is
always synchronous).

Output columns: `link, source_url, download_link, title, content_type,
caption, description, context_description, source_section, file_extension,
pub_title, raw_data_format`.

---

## `pipelines.pub_grants`

### `class PubGrantsStage(PipelineStage)`

Extracts grant/funding mentions via `run_integrated_batch_processing()` using
rule-based retrieval of the funding/acknowledgments section
(`relevant_content_flag="FUND"`, `process_entire_document=False`,
`CLAUDE_FDR_FewShot_grant` prompt, `grant_response_schema_gpt`). Same `run()`
kwargs as `PubDatasetsStage` (minus `batch_mode`/`full_document_read`).

Output columns: `pub_title, source_url, raw_data_format, funder_name,
grant_number, funding_context_from_paper, recipient` (`grant_number` is
singular — `data_gatherer`'s `process_grants_response()` explodes a
`grant_numbers` array into one row per number).

`funder_name` is canonicalized by `staging.normalizer._normalize_pub_grants`
(see below) — the LLM extracts funder names as written per-paper, which vary
a lot for the same real funder.

---

## `pipelines.pub_software`

### `class PubSoftwareStage(PipelineStage)`

Extracts software/tool mentions via `run_integrated_batch_processing()`:
rule-based retrieval of the code/software-availability section plus the
references section (`relevant_content_flag="CODE"`, which `data_gatherer`
includes automatically), combined with regex-matched code-hosting URLs
(`regex_search_id_patterns=dg.get_code_hosting_id_patterns()` via a throwaway
`init_parser_by_input_type('XML')` call — `dg.parser` is `None` until a fetch
happens, so it can't be read directly off a fresh instance) and an LLM pass
for unlinked mentions (`CLAUDE_RTR_FewShot_software` prompt,
`software_mention_response_schema_gpt`).

Bypasses `DataGatherer.from_batch_resp_file_to_df()` in favor of a local
`_software_batch_results_to_df()` helper: that method's generic metadata
merge does `record[key] = value` unconditionally for every metadata key,
including `'url'` (the source article's URL) — but the software-mention
schema's own per-record field is *also* named `'url'` (the software's own
URL), so the merge would silently overwrite every extracted software URL
with the article URL. Worked around by renaming the metadata's `url` to
`article_url` before merging.

Output columns: `pub_title, source_url, raw_data_format, software_name,
version, mention_type, url, context_from_paper` (`url` here is the
software's own URL — GitHub/GitLab/Zenodo/PyPI/CRAN/etc., not the source
article).

GitHub-hosted mentions from this table are separately routed into the
`github_search`/`repo_analysis`/`code` pipeline — see
`pipelines.github_search` below and `scrapers.scrape_github.enrich_known_repos`.

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
| `extra_repos_path` | Path\|None | `None` | TSV of externally-discovered repo candidates (columns: `Resource Name`, `Abbreviation`, `Diseases Included`, `Repository Link`) — passed through as `scrape_github.py --extra-repos`. Populated by `orchestrator.py` from `pub_software`'s GitHub-hosted mentions, joined back to `pubmed_hits` for Resource Name/Abbreviation/Diseases Included. |

Output includes a `Content_For_Analysis` column consumed by `repo_analysis`.
`--extra-repos` candidates get the *same* tree-walk/README/FAIR-compliance
enrichment as Code-Search-discovered repos (see
`scrapers.scrape_github.enrich_repo`/`enrich_known_repos` below) — they're
concatenated in before the existing dedup/save logic, not a parallel output
path.

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
| `use_cache` | bool | `True` | Skip repos already in `tables/final/gits_to_reannotate_completed_*.tsv` (diffed on `Repository Link`) — only new repos go to the Batch API. Cached rows' `FAIR Score`/`FAIR Issues` are dropped before merging (normalizer-added, recomputed fresh from the current FAIR-compliance log rather than reused from a possibly-stale prior run). |

Adds columns: `Biomedical Relevance`, `Code Summary`, `Data Types`, `Tooling`.

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
| `use_cache` | bool | `True` | Skip URLs already in `tables/final/new_corpus_*.tsv` (diffed on `source_url_for_metadata`, the field `data_gatherer` sets to the visited `dataset_webpage` URL) — only new URLs get visited |

**Known issue:** `dg.process_metadata()` processes all URLs in one call and
only returns/writes results at the end — if any single URL's LLM call errors
(e.g. Anthropic content-filtering blocks one request), the whole call raises
and **every** URL's work is lost, not just the one that failed. No per-row
error isolation exists yet in `data_gatherer`.

#### Profile setup

```bash
python -m pipelines.page_navigation --setup-profile
```

Launches Firefox interactively so you can log in to restricted portals. Profile is saved to `~/.card-catalog-firefox-profile` and reused headlessly on subsequent runs.

#### Output columns

Mirrors `study_sanity_check_w_rationale_schema_claude`:

`coarse_data_modality`, `granular_data_modality`, `diseases_included`, `sample_size`, `publication_urls`, `dataset_urls`, `rationale`

---

## `scrapers.scrape_github`

### `enrich_repo(owner, repo_name, study_name, abbreviation, diseases, repo_url, languages, default_branch, headers, fair_logger, batch_mode=False) → dict | None`

FAIR-compliance check, contributors fetch, content fetch, and AI analysis (or
batch-mode placeholder) for a single GitHub repo. Extracted from
`search_github_with_query`'s per-repo loop so it's shared between repos found
via GitHub Code Search and repos discovered elsewhere (see
`enrich_known_repos`). Returns `None` if the repo has insufficient content to
analyze.

### `enrich_known_repos(repo_candidates, github_token, fair_logger, rate_limiter, batch_mode=False) → list[dict]`

Enriches externally-discovered repo URLs (e.g. GitHub links `pub_software`
found mentioned in papers, not found via Code Search) with the same
treatment as `enrich_repo`, then fans each unique repo's single enrichment
result out to one row per `(repo, Resource Name)` pairing supplied in
`repo_candidates`.

| Parameter | Type | Description |
|---|---|---|
| `repo_candidates` | `list[dict]` | Each dict has keys `Resource Name`, `Abbreviation`, `Diseases Included`, `Repository Link` (any GitHub URL shape) |

Groups candidates by normalized repo URL first (`github.com/owner/repo`,
stripping `.git` suffixes and `/blob/...`-style paths) so a repo cited by
multiple papers/resources is only fetched/enriched once, not once per
pairing. Called from `main()` when `--extra-repos <path>` is passed —
results are concatenated into `all_results` before the existing
dedup/column-ordering/save logic, so they flow through unmodified.

---

## `staging.schemas`

Pydantic row models for each output table. All string fields coerce `None`/`NaN` to `""`.

```python
from staging.schemas import (
    PublicationRow,
    CodeRepoRow,
    PubDatasetRow,
    SupplementaryRow,
    PubGrantRow,
    PubSoftwareRow,
    NewCorpusRow,
    SciLiteAnnotationRow,
    SCHEMA_REGISTRY,
)
```

> **These models aren't actually wired into `normalize()`.** `normalize()`
> renames columns via `_RENAME` and runs a per-target normalizer function, but
> never instantiates or validates against the `SCHEMA_REGISTRY` model for that
> target. The models document the *intended* app-facing shape (`COLUMNS`), but
> for several targets (`pub_datasets`, `supplementary`, `pub_grants`,
> `pub_software`) the real pipeline output uses different, lowercase
> `snake_case` column names straight from `data_gatherer` — see each stage's
> "Output columns" above for what's actually in the TSV today.

### `SCHEMA_REGISTRY`

```python
SCHEMA_REGISTRY: dict[str, type[_Base]] = {
    "publications":  PublicationRow,
    "code":          CodeRepoRow,
    "pub_datasets":  PubDatasetRow,
    "supplementary": SupplementaryRow,
    "pub_grants":    PubGrantRow,
    "pub_software":  PubSoftwareRow,
    "new_corpus":    NewCorpusRow,
    "scilite":       SciLiteAnnotationRow,
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

### `PubGrantRow`

| Field | App column |
|---|---|
| `Pub_Title` | `Pub Title` |
| `Source_URL` | `Source URL` |
| `Raw_Data_Format` | `Raw Data Format` |
| `Funder_Name` | `Funder Name` |
| `Grant_Number` | `Grant Number` |
| `Funding_Context_From_Paper` | `Funding Context From Paper` |
| `Recipient` | `Recipient` |

Real pipeline output (`pub_grants.py`) uses lowercase `snake_case` columns
matching the field names above 1:1 (e.g. `pub_title`, `funder_name`) — this
model's `COLUMNS` documents the intended app-facing casing, not yet enforced.

### `PubSoftwareRow`

| Field | App column |
|---|---|
| `Pub_Title` | `Pub Title` |
| `Source_URL` | `Source URL` |
| `Raw_Data_Format` | `Raw Data Format` |
| `Software_Name` | `Software Name` |
| `Version` | `Version` |
| `Mention_Type` | `Mention Type` |
| `Software_URL` | `Software URL` |
| `Context_From_Paper` | `Context From Paper` |

Real pipeline output uses `url` (not `software_url`) for the software's own
URL — matching the raw `data_gatherer` schema field name (see
`pipelines.pub_software`'s "Output columns" above).

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
| `code` | Semicolon-sort diseases, data types, tooling, languages; merge in FAIR Score/Issues from the latest `fair_compliance_log_*.tsv` |
| `pub_datasets` | No-op (raw `data_gatherer` output columns passed through as-is) |
| `supplementary` | No-op |
| `pub_grants` | Canonicalize `funder_name` via `_normalize_funder_name()` — an ordered list of regex patterns collapsing known variant clusters (e.g. `"National Institute on Aging"`, `"NIA"`, `"National Institute of Aging"` [typo], `"NIA/NIH"`, … → `"National Institute on Aging (NIA)"`). Specific institutes are checked before the generic NIH pattern so compound mentions attribute to the specific institute. Not exhaustive — only high-frequency variant clusters found in real data; unmatched names pass through unchanged. |
| `pub_software` | No-op |
| `new_corpus` | Extract first URL from `dataset_urls` list; join `publication_urls` list; semicolon-sort diseases/modalities |
| `scilite` | Replace `Type == "Gene Ontology"` rows with the term's GO aspect, fetched from QuickGO |

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

## `staging.cache_utils`

Shared helper for the per-item extraction cache used by
`pub_datasets`/`pub_supplementary`/`pub_grants`/`pub_software`/`repo_analysis`.

### `latest_final(pattern) → Path | None`

Most recently modified file in `tables/final/` matching `pattern` (e.g.
`"pub_grants_*.tsv"`), or `None` if nothing matches.

### `combine_cached_and_new(cached, new) → pd.DataFrame | None`

Unions cached (already-final) rows with freshly-extracted rows, dropping
whichever side is `None`/empty. Used by every cache-aware stage to build the
DataFrame it writes to `tables/hits/`, so the normalizer's next pass sees the
full accumulated set — not just this run's delta.

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
| `ANTHROPIC_API_KEY` | `repo_analysis`, `pub_datasets`, `pub_supplementary`, `pub_grants`, `pub_software`, `page_navigation`, `web/backend` (React app AI-analysis proxy) | Anthropic API key |
| `NCBI_API_KEY` | `pubmed_search` | NCBI Entrez API key (optional; raises rate limits from 3/s to 10/s) |
| `GITHUB_TOKEN` | `github_search` | GitHub personal access token (required for GitHub scraping) |
| `FIREFOX_PROFILE_DIR` | `page_navigation` | Path to pre-authenticated Firefox profile |
