# CARD Catalog

A data pipeline and web application for discovering and connecting research resources — datasets, publications, code repositories, and cellular models — in the Alzheimer's Disease and Related Dementias (ADRD) / Neurodegenerative Diseases (NDD) space.

The live app is a React + TypeScript app (in `web/`, deployed to Netlify). The original Streamlit app (`app/`) is the v0 predecessor, kept for reference but no longer deployed.

Maintained by [DataTecnica](https://datatecnica.com) for NIH's [Center for Alzheimer's and Related Dementias (CARD)](https://card.nih.gov) and the NIA Laboratory of Neurogenetics (LNG).

---

## What's in the catalog

| Section | Count | Description |
|---|---|---|
| Resources | 236 | Neuroscience datasets and resources with knowledge graphs and AI analysis |
| Publications | 1,288 | PubMed Central papers linked to catalog resources |
| Code Repositories | 674 | GitHub repos with AI quality scoring and FAIR compliance |
| Human Cellular Models | 626 | iNDI iPSC cell lines for neurodegenerative disease research |

---

## Architecture

```
Inventory (.tab)
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                          Pipeline                            │
│  1. pubmed_search                                            │
│  2. prefetch_articles — shared PMC full-text cache            │
│     (tables/cache/pub_fulltext_cache.parquet), read-and-      │
│     update in place across runs, before the 4 stages below    │
│  3. pub_datasets / pub_supplementary / pub_grants /            │
│     pub_software  (AI, run CONCURRENTLY — each independently   │
│     caches against its own tables/final/ output; --no-cache    │
│     forces a full reprocess)                                   │
│  4. scilite         (Europe PMC annotations)                   │
│  5. github_search   — also enriches GitHub repos discovered     │
│     by pub_software (--extra-repos), same FAIR/tree-walk        │
│     treatment as Code-Search-discovered repos                   │
│  6. repo_analysis   (AI, cache-aware)                           │
│  7. page_navigation (AI+browser, cache-aware)                   │
└───────────┬───────────────────────────────────────────────────┘
            │
       tables/hits/          ← intermediate outputs
            │
       Normalizer            ← field normalization + validation
            │
       tables/final/         ← app-ready validated TSVs
            │
   React app (web/) — live, deployed on Netlify
   (Streamlit app in app/ is the legacy v0 predecessor)
```

Full architecture details: [`docs/overview.md`](docs/overview.md), [`docs/api_reference.md`](docs/api_reference.md)

---

## Quick start

### 1. Install

```bash
git clone https://github.com/NIH-CARD/CARD_catalog_v0.git
cd CARD_catalog_v0
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
# Pipeline
cp .env.template .env
# Edit .env — set ANTHROPIC_API_KEY, GITHUB_TOKEN, NCBI_API_KEY

# Streamlit app (legacy, optional)
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```

### 3. Run the app

The live app is the React app in `web/` — it reads pre-generated TSVs, no API keys required to browse it:

```bash
cd web
npm install
npm run sync-data   # copies the latest tables/final/*.tsv into web/public/data/
npm run dev         # http://localhost:5173
```

Re-run `npm run sync-data` whenever the pipeline writes new outputs.

<details>
<summary>Legacy Streamlit app (reference only, not deployed)</summary>

```bash
streamlit run app/Home.py
```

Opens at http://localhost:8501.
</details>

### 4. Run the pipeline

```bash
# Incremental update — last 7 days of PubMed
python orchestrator.py update

# Full rebuild (all stages, 3-year window)
python orchestrator.py full_rebuild

# Skip stages you don't need
python orchestrator.py full_rebuild --skip page_navigation

# Force a full reprocess, ignoring per-item caches (pub_datasets/pub_supplementary/
# pub_grants/pub_software/repo_analysis/page_navigation all normally skip items
# already present in tables/final/)
python orchestrator.py full_rebuild --no-cache
```

Full pipeline docs: [`docs/getting_started.md`](docs/getting_started.md), [`docs/api_reference.md`](docs/api_reference.md)

---

## Automation

The pipeline is designed to run unattended via cron — see
[`docs/getting_started.md`](docs/getting_started.md) for the intended schedule
(incremental updates weekly, full rebuilds quarterly) and crontab entries.
Automated scheduling on a server is a near-term milestone, not yet live.

Stages are independently restartable — if a run fails, re-running skips stages that already produced a today-dated hits file.

`pub_datasets`/`pub_supplementary`/`pub_grants`/`pub_software`/`repo_analysis`/`page_navigation` additionally cache per-item, diffing against what's already in `tables/final/` — so even within a fresh, non-skipped stage run, only genuinely new items (new PMC articles, new repos, new URLs) get reprocessed. `--no-cache` bypasses this for a true full reprocess.

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/overview.md`](docs/overview.md) | Architecture, pipeline stages, directory layout, design principles |
| [`docs/getting_started.md`](docs/getting_started.md) | Setup, running the pipeline, cron, troubleshooting |
| [`docs/api_reference.md`](docs/api_reference.md) | `pipelines/`, `staging/`, `app/utils/` API reference |
| [`docs/conventions.md`](docs/conventions.md) | Coding conventions for contributors and AI agents |
| [`docs/pipeline_diagram.md`](docs/pipeline_diagram.md) | Visual pipeline diagram |
| [`docs/CARD_Catalog_Schema.md`](docs/CARD_Catalog_Schema.md) | Table/column schema reference |
| [`web/README.md`](web/README.md) | React app setup, routes, file layout |

Full Sphinx docs: https://nih-card.github.io/CARD_catalog_v0 *(requires GitHub Pages to be enabled)*

---

## Repository layout

```
CARD_catalog_v0/
├── orchestrator.py          # Pipeline entry point
├── pipelines/               # One module per pipeline stage
├── staging/                 # Pydantic schemas + normalizer
├── scrapers/                # Raw scrapers (publications, GitHub)
├── web/                     # LIVE APP — React + Vite + TypeScript, Netlify-deployed
│   ├── src/pages/           # PublicationsPage, ResourcesPage, CodePage, DatasetsPage, CellularModelsPage, …
│   ├── scripts/sync-data.sh # Copies latest tables/final/*.tsv into public/data/
│   └── backend/             # FastAPI stub proxying Anthropic for AI-analysis features
├── app/                     # LEGACY — Streamlit v0 app, not deployed
│   ├── Home.py
│   ├── pages/
│   └── utils/
├── tables/
│   ├── hits/                # Intermediate pipeline outputs (gitignored)
│   ├── cache/               # Shared PMC full-text parquet cache (gitignored)
│   ├── final/                # App-ready validated TSVs (source of truth for web/)
│   └── resources-inventory-*.tab   # Resource inventory (source of truth)
├── docs/                    # Sphinx documentation source
└── logs/                    # Runtime logs (gitignored)
```

---

## Environment variables

| Variable | Required by | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `repo_analysis`, `pub_datasets`, `pub_supplementary`, `pub_grants`, `pub_software`, `page_navigation`, `web/backend` AI-analysis proxy | All AI stages use Anthropic models |
| `GITHUB_TOKEN` | `github_search` | Required for GitHub scraping |
| `NCBI_API_KEY` | `pubmed_search` | Optional; raises rate limit from 3/s to 10/s |
| `FIREFOX_PROFILE_DIR` | `page_navigation` | Pre-authenticated Firefox profile path |

---

## Contact

Mike A. Nalls PhD — nallsm@nih.gov | mike@datatecnica.com
GitHub: https://github.com/NIH-CARD
