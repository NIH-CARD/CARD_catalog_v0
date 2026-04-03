# Getting Started

## Prerequisites

- Python 3.10+
- Git
- Firefox (for `page_navigation` stage only)
- API keys: Anthropic, NCBI (optional but recommended), GitHub

---

## 1. Clone and install

```bash
git clone https://github.com/NIH-CARD/CARD_catalog_v0.git
cd CARD_catalog_v0

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 2. Configure secrets

### Streamlit app

```bash
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

### Pipeline (scrapers)

```bash
cp scrapers/.env.template scrapers/.env
```

Edit `scrapers/.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
NCBI_API_KEY=your-ncbi-key          # optional but raises rate limits
GITHUB_TOKEN=ghp_...
FIREFOX_PROFILE_DIR=~/.card-catalog-firefox-profile
```

Load into your terminal session:

```bash
set -a && source .env && set +a
```

---

## 3. Run the Streamlit app

```bash
streamlit run app/Home.py
```

Opens at http://localhost:8501. Works immediately with existing data in `tables/`.

---

## 4. Run the pipeline

### Weekly update (last 7 days of PubMed)

```bash
python orchestrator.py weekly
```

Fetches papers from the past 7 days, validates, and writes a new
`tables/final/pubmed_central_*.tsv`.

### Full quarterly rebuild

```bash
python orchestrator.py quarterly
```

Runs all 5 stages: PubMed → publication metadata → GitHub search → AI repo analysis → study page navigation.

### Skip stages you don't need

```bash
python orchestrator.py quarterly --skip page_navigation
python orchestrator.py quarterly --skip repo_analysis pub_metadata page_navigation
```

### Resume a failed run

Stages that already wrote a today-dated hits file are skipped automatically on retry:

```bash
python orchestrator.py quarterly   # repo_analysis failed
# fix the issue, then:
python orchestrator.py quarterly   # earlier stages skip automatically
```

Force re-run all stages:

```bash
python orchestrator.py quarterly --force
```

---

## 5. Set up Firefox profile for page navigation

```bash
python -m pipelines.page_navigation --setup-profile
```

Opens Firefox for interactive login to restricted portals. Profile is saved and reused headlessly. Add the printed path to your `.env` as `FIREFOX_PROFILE_DIR`.

---

## 6. Run the normalizer standalone

```bash
python -m staging.normalizer \
    --input  tables/hits/pubmed_hits_20260329_120000.tsv \
    --target publications \
    --output tables/final/pubmed_central_20260329.tsv
```

Available targets: `publications`, `code`, `pub_datasets`, `supplementary`, `new_corpus`.

---

## 7. Set up the cron schedule

```bash
mkdir -p logs
crontab -e
```

```bash
# Weekly — Monday 8am ET (12pm UTC)
0 12 * * 1 cd /path/to/CARD_catalog_v0 && set -a && source .env && set +a && venv/bin/python orchestrator.py weekly >> logs/weekly.log 2>&1

# Quarterly — first Monday of Jan, Apr, Jul, Oct
0 12 1-7 1,4,7,10 * [ "$(date +\%u)" = "1" ] && cd /path/to/CARD_catalog_v0 && set -a && source .env && set +a && venv/bin/python orchestrator.py quarterly >> logs/quarterly.log 2>&1
```

---

## 8. Common CLI flags

| Flag | Default | Description |
|---|---|---|
| `--query-method` | `v2` | PubMed query strategy (`original`, `v2`, `v3`) |
| `--max-results` | `100` | Max PubMed hits per resource |
| `--skip STAGE [...]` | none | Skip named stages |
| `--force` | off | Re-run stages even if today's hits file exists |
| `--verbose` | off | Pass `--verbose` to scraper subprocesses |
| `--inventory` | auto-detected | Override path to resource inventory `.tab` file |

---

## Troubleshooting

**"No dataset-inventory file found in tables/"**
Run from the project root, or pass `--inventory path/to/file.tab`.

**"GITHUB_TOKEN not set — skipping github_search"**
Export `GITHUB_TOKEN` or use `--github-token`. GitHub scraping is optional.

**"page_navigation stage requires FIREFOX_PROFILE_DIR"**
Run `python -m pipelines.page_navigation --setup-profile`.

**Rejected rows in `tables/hits/rejected_*.tsv`**
Inspect the `_validation_errors` column. Common cause: unexpected column names from a scraper update.

**App shows stale data after a pipeline run**
Streamlit caches for 1 hour. Use the **Clear Cache** button in the sidebar.
