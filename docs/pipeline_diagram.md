# CARD Catalog Pipeline — Full Rebuild

```{mermaid}
flowchart TD
    INV[(resources-inventory-*.tab)]

    INV --> S1
    INV --> S5g
    INV --> S7

    subgraph PubMed["PubMed Branch"]
        S1["[1] pubmed_search\nscrape_publications.py\nNCBI API · 3-year window"]
        H1[(pubmed_hits_*.tsv)]
        N1["normalizer\n→ pubmed_central_*.tsv"]
        S1 --> H1 --> N1
    end

    subgraph Prefetch["Shared Full-Text Cache"]
        PF["[2] prefetch_articles()\npub_metadata_shared.py\nDataGatherer fetch, read-and-update in place"]
        CACHE[(tables/cache/\npub_fulltext_cache.parquet)]
        PF --> CACHE
    end

    H1 --> PF

    subgraph PubMeta["Publication Metadata Branch — [3] CONCURRENT"]
        S3a["pub_datasets\nDataGatherer + Haiku"]
        S3b["pub_supplementary\nDataGatherer + Haiku"]
        S3c["pub_grants\nDataGatherer + Haiku"]
        S3d["pub_software\nDataGatherer + Haiku"]
        H3a[(pub_datasets_*.tsv)]
        H3b[(pub_supplementary_*.tsv)]
        H3c[(pub_grants_*.tsv)]
        H3d[(pub_software_*.tsv)]
        N3a["normalizer\n→ pub_datasets_*.tsv"]
        N3b["normalizer\n→ pub_supplementary_*.tsv"]
        N3c["normalizer\n→ pub_grants_*.tsv\n(funder_name normalized)"]
        N3d["normalizer\n→ pub_software_*.tsv"]
        S3a --> H3a --> N3a
        S3b --> H3b --> N3b
        S3c --> H3c --> N3c
        S3d --> H3d --> N3d
    end

    H1 --> S3a & S3b & S3c & S3d
    CACHE --> S3a & S3b & S3c & S3d

    subgraph SciLite["SciLite Branch"]
        S4["[4] scilite\nscrape_annotations.py\nEurope PMC API"]
        H4[(annotations_*.json\n→ scilite_annotations_*.tsv)]
        N4["normalizer\n→ scilite_annotations_*.tsv"]
        S4 --> H4 --> N4
    end

    H1 --> S4

    subgraph GitHub["GitHub Branch"]
        EXTRA[(extra_repos_from_software_*.tsv)]
        S5g["[5] github_search\nscrape_github.py\nGitHub API · --extra-repos"]
        H5[(github_hits_*.tsv)]
        S6["[6] repo_analysis\nbatch_ai_analysis.py\nAnthropic Batch API"]
        H6[(github_analyzed_*.tsv)]
        N6["normalizer\n→ gits_to_reannotate_completed_*.tsv"]
        S5g --> H5 --> S6 --> H6 --> N6
    end

    H3d -- "GitHub-hosted mentions,\nenriched same as scraped repos" --> EXTRA --> S5g

    subgraph PageNav["Page Navigation Branch"]
        S7["[7] page_navigation\nDataGatherer + headless Firefox"]
        H7[(new_corpus_*.tsv)]
        N7["normalizer\n→ new_corpus_*.tsv"]
        S7 --> H7 --> N7
    end

    N1 --> JA
    N3a --> JA
    N4 --> JA

    JA["[8] join_annotations\nstaging/publication_glue.py\nJoins SciLite entities + cited datasets\ninto publications table"]

    JA --> OUT[(pubmed_central_*.tsv\nenriched with:\nDiseases Annotated\nGenes / Proteins\nChemicals\nCited Datasets)]
```

## Stage Summary

| # | Stage | Input | Tool | Output |
|---|-------|-------|------|--------|
| 1 | `pubmed_search` | inventory | NCBI API (subprocess) | `pubmed_hits_*.tsv` |
| 2 | *(prefetch)* | pubmed_hits | DataGatherer (shared fetch) | `tables/cache/pub_fulltext_cache.parquet` |
| 3 | `pub_datasets` / `pub_supplementary` / `pub_grants` / `pub_software` (concurrent) | pubmed_hits + fetch cache | DataGatherer + Haiku | `pub_datasets_*.tsv`, `pub_supplementary_*.tsv`, `pub_grants_*.tsv`, `pub_software_*.tsv` |
| 4 | `scilite` | pubmed_hits | Europe PMC API | `scilite_annotations_*.tsv` |
| 5 | `github_search` | inventory + repos from `pub_software` | GitHub API (subprocess) | `github_hits_*.tsv` |
| 6 | `repo_analysis` | github_hits | Anthropic Batch API | `github_analyzed_*.tsv` |
| 7 | `page_navigation` | inventory | DataGatherer + Firefox | `new_corpus_*.tsv` |
| 8 | `join_annotations` | pubmed_central + pub_datasets + scilite | — | pubmed_central enriched in place |

## Dependencies

- Stage **2** (prefetch) and stage **3** (the 4 concurrent pub_* stages) and stage **4** (`scilite`) all require stage **1** (`pubmed_hits`) to complete first
- Stage **3**'s four sub-stages are mutually independent and run concurrently, each reading from the shared fetch cache written by stage **2** and caching per-item against its own `tables/final/` output (bypassed with `--no-cache`)
- Stage **5** (`github_search`) runs after stage **3** completes, so it can fold in any GitHub repos `pub_software` discovered (`extra_repos_from_software_*.tsv`) before dedup — those repos get the same tree-walk/README/FAIR-compliance enrichment as repos found via GitHub Code Search
- Stage **6** requires stage **5** (`github_hits`) to complete first
- Stage **7** (`page_navigation`) requires a pre-authenticated Firefox profile (`FIREFOX_PROFILE_DIR`)
- `join_annotations` runs last, unconditionally, over whatever final files exist

## Credentials Required

| Credential | Stages |
|---|---|
| `NCBI_API_KEY` | 1 (optional — raises rate limit from 3/s to 10/s) |
| `GITHUB_TOKEN` | 5, 6 |
| `ANTHROPIC_API_KEY` | 2, 3, 6, 7 |
| `FIREFOX_PROFILE_DIR` | 7 |
