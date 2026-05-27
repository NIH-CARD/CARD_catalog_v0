# CARD Catalog Pipeline — Full Rebuild

```{mermaid}
flowchart TD
    INV[(resources-inventory-*.tab)]

    INV --> S1
    INV --> S2
    INV --> S5

    subgraph PubMed["PubMed Branch"]
        S1["[1] pubmed_search\nscrape_publications.py\nNCBI API · 3-year window"]
        H1[(pubmed_hits_*.tsv)]
        N1["normalizer\n→ pubmed_central_*.tsv"]
        S1 --> H1 --> N1
    end

    subgraph PubMeta["Publication Metadata Branch"]
        S4["[4] pub_metadata\nDataGatherer + Haiku\nDataset & supplementary extraction"]
        H4a[(pub_datasets_*.tsv)]
        H4b[(pub_supplementary_*.tsv)]
        N4a["normalizer\n→ pub_datasets_*.tsv"]
        N4b["normalizer\n→ pub_supplementary_*.tsv"]
        S4 --> H4a --> N4a
        S4 --> H4b --> N4b
    end

    subgraph SciLite["SciLite Branch"]
        S6["[6] scilite\nscrape_annotations.py\nEurope PMC API"]
        H6[(annotations_*.json\n→ scilite_annotations_*.tsv)]
        N6["normalizer\n→ scilite_annotations_*.tsv"]
        S6 --> H6 --> N6
    end

    subgraph GitHub["GitHub Branch"]
        S2["[2] github_search\nscrape_github.py\nGitHub API"]
        H2[(github_hits_*.tsv)]
        S3["[3] repo_analysis\nbatch_ai_analysis.py\nAnthropic Batch API"]
        H3[(github_analyzed_*.tsv)]
        N3["normalizer\n→ gits_to_reannotate_completed_*.tsv"]
        S2 --> H2 --> S3 --> H3 --> N3
    end

    subgraph PageNav["Page Navigation Branch"]
        S5["[5] page_navigation\nDataGatherer + headless Firefox"]
        H5[(new_corpus_*.tsv)]
        N5["normalizer\n→ new_corpus_*.tsv"]
        S5 --> H5 --> N5
    end

    H1 --> S4
    H1 --> S6

    N1 --> JA
    N4a --> JA
    N6 --> JA

    JA["join_annotations\nstaging/join_annotations.py\nJoins SciLite entities + cited datasets\ninto publications table"]

    JA --> OUT[(pubmed_central_*.tsv\nenriched with:\nDiseases Annotated\nGenes / Proteins\nChemicals\nCited Datasets)]
```

## Stage Summary

| # | Stage | Input | Tool | Output |
|---|-------|-------|------|--------|
| 1 | `pubmed_search` | inventory | NCBI API (subprocess) | `pubmed_hits_*.tsv` |
| 2 | `github_search` | inventory | GitHub API (subprocess) | `github_hits_*.tsv` |
| 3 | `repo_analysis` | github_hits | Anthropic Batch API | `github_analyzed_*.tsv` |
| 4 | `pub_metadata` | pubmed_hits | DataGatherer + Haiku | `pub_datasets_*.tsv`, `pub_supplementary_*.tsv` |
| 5 | `page_navigation` | inventory | DataGatherer + Firefox | `new_corpus_*.tsv` |
| 6 | `scilite` | pubmed_hits | Europe PMC API | `scilite_annotations_*.tsv` |
| — | `join_annotations` | pubmed_central + pub_datasets + scilite | — | pubmed_central enriched in place |

## Dependencies

- Stages **4** and **6** require stage **1** (`pubmed_hits`) to complete first
- Stage **3** requires stage **2** (`github_hits`) to complete first
- Stage **5** (`page_navigation`) requires a pre-authenticated Firefox profile (`FIREFOX_PROFILE_DIR`)
- `join_annotations` runs last, unconditionally, over whatever final files exist

## Credentials Required

| Credential | Stages |
|---|---|
| `NCBI_API_KEY` | 1 (optional — raises rate limit from 3/s to 10/s) |
| `GITHUB_TOKEN` | 2, 3 |
| `ANTHROPIC_API_KEY` | 3, 4, 5 |
| `FIREFOX_PROFILE_DIR` | 5 |
