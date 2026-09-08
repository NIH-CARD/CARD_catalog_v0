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

### Legacy Streamlit app (optional, reference only)

```bash
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

---

## 3. Run the app

The live app is the React app in `web/` — it's read-only against pre-generated TSVs, no API keys required to browse it:

```bash
cd web
npm install
npm run sync-data   # copies the latest tables/final/*.tsv into public/data/
npm run dev         # http://localhost:5173
```

Re-run `npm run sync-data` whenever the pipeline writes new outputs. See [`web/README.md`](../web/README.md) for routes and file layout.

<details>
<summary>Legacy Streamlit app (reference only, not deployed)</summary>

```bash
streamlit run app/Home.py
```

Opens at http://localhost:8501. Works immediately with existing data in `tables/`.
</details>

---

## 4. Run the pipeline

### Update (last 7 days of PubMed)

```bash
python orchestrator.py update
```

Fetches papers from the past 7 days, validates, and writes a new
`tables/final/pubmed_central_*.tsv`.

### Full rebuild

```bash
python orchestrator.py full_rebuild
```

Runs pubmed_search → (shared full-text prefetch) → pub_datasets / pub_supplementary / pub_grants / pub_software (concurrent) → scilite → GitHub search (also enriching any GitHub repos `pub_software` found) → AI repo analysis → study page navigation → join_annotations.

### Skip stages you don't need

```bash
python orchestrator.py full_rebuild --skip page_navigation
python orchestrator.py full_rebuild --skip repo_analysis pub_software page_navigation
```

### Force a full reprocess, ignoring per-item caches

`pub_datasets`, `pub_supplementary`, `pub_grants`, `pub_software`, `repo_analysis`, and `page_navigation` normally skip items already present in `tables/final/`. To reprocess everything:

```bash
python orchestrator.py full_rebuild --no-cache
```

### Resume a failed run

Stages that already wrote a today-dated hits file are skipped automatically on retry:

```bash
python orchestrator.py full_rebuild   # repo_analysis failed
# fix the issue, then:
python orchestrator.py full_rebuild   # earlier stages skip automatically
```

Force re-run all stages:

```bash
python orchestrator.py full_rebuild --force
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

Available targets: `publications`, `code`, `pub_datasets`, `supplementary`, `pub_grants`, `pub_software`, `new_corpus`, `scilite`.

---

## 7. Set up the cron schedule

```bash
mkdir -p logs
crontab -e
```

```bash
# Update — Monday 8am ET (12pm UTC)
0 12 * * 1 cd /path/to/CARD_catalog_v0 && set -a && source .env && set +a && venv/bin/python orchestrator.py update >> logs/update.log 2>&1

# Full rebuild — first Monday of Jan, Apr, Jul, Oct
0 12 1-7 1,4,7,10 * [ "$(date +\%u)" = "1" ] && cd /path/to/CARD_catalog_v0 && set -a && source .env && set +a && venv/bin/python orchestrator.py full_rebuild >> logs/full_rebuild.log 2>&1
```

---

## 8. Common CLI flags

| Flag | Default | Description |
|---|---|---|
| `--query-method` | `v3` | PubMed query strategy (`original`, `v2`, `v3`) |
| `--max-results` | `100` | Max PubMed hits per resource |
| `--skip STAGE [...]` | none | Skip named stages |
| `--force` | off | Re-run stages even if today's hits file exists |
| `--no-cache` | off | Disable per-item caching for pub_datasets/pub_supplementary/pub_grants/pub_software/repo_analysis/page_navigation; reprocess everything |
| `--verbose` | off | Pass `--verbose` to scraper subprocesses |
| `--inventory` | auto-detected | Override path to resource inventory `.tab` file |

---

## Troubleshooting

**"No resources-inventory file found in tables/"**
Run from the project root, or pass `--inventory path/to/file.tab`.

**"GITHUB_TOKEN not set — skipping github_search"**
Export `GITHUB_TOKEN` or use `--github-token`. GitHub scraping is optional.

**"page_navigation stage requires FIREFOX_PROFILE_DIR"**
Run `python -m pipelines.page_navigation --setup-profile`.

**Rejected rows in `tables/hits/rejected_*.tsv`**
Inspect the `_validation_errors` column. Common cause: unexpected column names from a scraper update.

**React app shows stale data after a pipeline run**
Re-run `npm run sync-data` in `web/` to refresh `public/data/` from the latest `tables/final/*.tsv`.

**Legacy Streamlit app shows stale data after a pipeline run**
Streamlit caches for 1 hour. Use the **Clear Cache** button in the sidebar.
