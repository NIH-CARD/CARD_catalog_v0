# Known Issues

## 1. Abbreviation Specificity Tradeoff in GitHub and PubMed Queries

**Affected scrapers**: `scrapers/scrape_github.py`, `scrapers/scrape_publications.py`

The scraper uses the `Abbreviation` column as the primary search term. Short abbreviations return false positives; internal catalog IDs return zero results. Neither extreme is reliable.

**Examples**:

| Study | Short abbrev | Problem | Long ID | Problem |
|---|---|---|---|---|
| Brain Energy for Amyloid transformation in AD | `BEAM` | Generic physics term — false positives | `AGMP_BEAM` | Not on GitHub/PubMed — zero results |
| The Microbiome in Alzheimer's Risk Study | `MARS` | Common acronym — false positives | `AGMP_MARS_WISCONSIN` | Not on GitHub/PubMed — zero results |
| Northern Ireland Cohort for Longitudinal Study of Ageing | `NICOLA` | Common first name — false positives in PubMed | — | — |
| Aging, Demographics, and Memory Study | `ADAMS` | Common surname — false positives | — | — |

**Effect on results**:
- Feb 2026 run (short abbreviations): BEAM returned 6 repos, MARS returned 11 repos — likely inflated with false positives
- Mar 2026 run (AGMP-prefixed IDs): BEAM returned 0, MARS returned 0 — real repos missed

**Proposed fix**: Add a dedicated `Search Term` column to the inventory with a manually curated, specific but findable search string (e.g. `"BEAM alzheimer"`, `"MARS microbiome alzheimer"`). Keep internal catalog IDs separate from search terms.

---

## 2. Per-Study Result Count Differences Between Feb and Mar Scrape Runs

**Comparison**: `scrapers/old/github_scrape.log` (Feb 9, 2026) vs `scrapers/github_scraper_20260311_222308.log` (Mar 11, 2026)

Overall counts: **862 repos (Feb)** → **699 repos (Mar)**. Explained by:

1. **Inventory consolidation**: ADNI phases 1/2/3 merged into single entry; OASIS variants consolidated — fewer study rows means fewer searches
2. **Abbreviation changes**: See Issue 1 — AGMP-prefixed IDs return zero results
3. **AI classification variance**: Small ±1–4 differences on other studies are expected stochastic noise

---

## 3. Data Modality Filter Broken in PubMed Scraper

**Affected scraper**: `scrapers/scrape_publications.py`, line 439

After column renaming in the Mar_11 inventory (`Data Modalities` → `Coarse Data Modality` + `Granular Data Modality`), the modality extraction used a broken pattern (`.split().extend()` returns `None`), silently disabling the 4th `AND (modality terms)` clause from all queries.

**Effect**: PubMed results went from ~1195 articles (Feb run) to ~3978 (Mar run) for the same 248 studies with `--query-method original`.

**Fix applied** (2026-03-12): Updated line 439 to correctly join both columns with `"; ".join(filter(None, [...]))`.

---

## 4. App

**Filters** Parenthesis values split does not separate all the value correctly (e.g. granular data modality --> "Cognitive assessment (CASI)")