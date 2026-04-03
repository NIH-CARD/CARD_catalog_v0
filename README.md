# CARD Catalog

A data pipeline and Streamlit web application for discovering and connecting research resources — datasets, publications, code repositories, and cellular models — in the Alzheimer's Disease and Related Dementias (ADRD) / Neurodegenerative Diseases (NDD) space.

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
┌─────────────────────────────────┐
│          Pipeline               │
│  1. pubmed_extract              │
│  2. github_search               │
│  3. repo_analysis   (AI)        │
│  4. pub_metadata    (AI)        │
│  5. page_navigation (AI+browser)│
└───────────┬─────────────────────┘
            │
       tables/hits/          ← intermediate outputs
            │
       Normalizer            ← Pydantic validation + field normalization
            │
       tables/final/         ← app-ready validated TSVs
            │
     Streamlit App (app/)
```

Full architecture details: [`docs/overview.md`](docs/overview.md)

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
# Streamlit app
cp .streamlit/secrets.toml.template .streamlit/secrets.toml

# Pipeline
cp .env.template .env
# Edit .env — set ANTHROPIC_API_KEY, GITHUB_TOKEN, NCBI_API_KEY
```

### 3. Run the app

```bash
streamlit run app/Home.py
```

The app works immediately with existing data in `tables/`. Opens at http://localhost:8501.

### 4. Run the pipeline

```bash
# Weekly — last 7 days of PubMed
python orchestrator.py weekly

# Full quarterly rebuild (all 5 stages)
python orchestrator.py quarterly

# Skip stages you don't need
python orchestrator.py quarterly --skip page_navigation
```

Full pipeline docs: [`docs/getting_started.md`](docs/getting_started.md)

---

## Automation

Both modes run via cron. Weekly every Monday, quarterly on the first Monday of January, April, July, and October. See [`docs/getting_started.md#set-up-the-cron-schedule`](docs/getting_started.md) for the crontab entries.

Stages are independently restartable — if a run fails, re-running skips stages that already produced a today-dated hits file.

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/overview.md`](docs/overview.md) | Architecture, pipeline stages, directory layout, design principles |
| [`docs/getting_started.md`](docs/getting_started.md) | Setup, running the pipeline, cron, troubleshooting |
| [`docs/api_reference.md`](docs/api_reference.md) | `pipelines/`, `staging/`, `app/utils/` API reference |
| [`conventions.md`](conventions.md) | Coding conventions for contributors and AI agents |

Full Sphinx docs: https://nih-card.github.io/CARD_catalog_v0 *(requires GitHub Pages to be enabled)*

---

## Repository layout

```
CARD_catalog_v0/
├── orchestrator.py          # Pipeline entry point
├── pipelines/               # One module per pipeline stage
├── staging/                 # Pydantic schemas + normalizer
├── scrapers/                # Raw scrapers (publications, GitHub)
├── app/                     # Streamlit application
│   ├── Home.py
│   ├── pages/
│   └── utils/
├── tables/
│   ├── hits/                # Intermediate pipeline outputs
│   ├── final/               # App-ready validated TSVs
│   └── dataset-inventory-*.tab   # Resource inventory (source of truth)
├── docs/                    # Sphinx documentation source
└── logs/                    # Runtime logs (gitignored)
```

---

## Environment variables

| Variable | Required by | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `repo_analysis`, `pub_metadata`, `page_navigation`, app AI features | Required if using Anthropic models |
| `OPENAI_API_KEY` | `repo_analysis`, `pub_metadata`, `page_navigation`, app AI features | Required if using OpenAI models |
| `GITHUB_TOKEN` | `github_search` | Required for GitHub scraping |
| `NCBI_API_KEY` | `pubmed` | Optional; raises rate limit from 3/s to 10/s |
| `FIREFOX_PROFILE_DIR` | `page_navigation` | Pre-authenticated Firefox profile path |

---

## Contact

Mike A. Nalls PhD — nallsm@nih.gov | mike@datatecnica.com
GitHub: https://github.com/NIH-CARD
