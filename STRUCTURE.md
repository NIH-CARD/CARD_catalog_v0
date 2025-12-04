# CARD Catalog v0.1 - Project Structure

## Overview

The CARD Catalog is a Streamlit web application for exploring datasets, publications, code repositories, and cellular models related to Alzheimer's Disease and Related Dementias (ADRD) research.

**Key Features:**
- Interactive knowledge graphs
- AI-powered analysis (Claude Sonnet 4.5)
- FAIR compliance tracking
- Multi-format data export

## Directory Structure

```
CARD_catalog/                          # Project root
│
├── README.md                          # Main project documentation
├── QUICK_START.md                     # 5-minute quick start guide
├── SETUP_SECRETS.md                   # API key setup guide
├── STRUCTURE.md                       # This file - project organization
├── MIGRATION_COMPLETE.md              # Migration notes from beta
├── requirements.txt                   # Python dependencies
├── .gitignore                         # Protects secrets & scrapers
│
├── .streamlit/                        # Streamlit configuration
│   ├── config.toml                    # Streamlit settings
│   ├── secrets.toml                   # Your API keys (gitignored)
│   └── secrets.toml.template          # Template for secrets
│
├── logos/                             # Organization logos
│   ├── ADDI.png
│   ├── card_logo.png
│   └── stacked_DT.png
│
├── tables/                            # Data files (committed to repo)
│   ├── dataset-inventory-*.tab        # Study inventories
│   ├── pubmed_central_*.tsv           # Publications data
│   ├── gits_to_reannotate_*.tsv       # GitHub repository data
│   ├── gits_batch*of4_*.tsv           # Batch processing outputs
│   ├── insufficient_reprocessed_*.tsv # Reprocessed repositories
│   └── iNDI_inventory_*.tsv           # iNDI cellular models data
│
├── app/                               # Streamlit web application
│   ├── Home.py                        # Main entry point (run from project root)
│   ├── config.py                      # Configuration & AI prompts
│   ├── requirements.txt               # App-specific dependencies
│   ├── .env.template                  # Environment variable template
│   │
│   ├── pages/                         # Streamlit pages
│   │   ├── 1_Datasets.py              # Dataset explorer
│   │   ├── 2_Publications.py          # Publication explorer
│   │   ├── 3_Code.py                  # Code repository explorer
│   │   ├── 5_Human_Cellular_Models.py # iNDI cell line explorer
│   │   └── 6_About.py                 # Documentation & methodology
│   │
│   ├── utils/                         # Utility modules
│   │   ├── data_loader.py             # Data loading & caching
│   │   ├── graph_builder.py           # Knowledge graph generation
│   │   ├── llm_utils.py               # AI/LLM interactions
│   │   └── export_utils.py            # Export functionality
│   │
│   ├── assets/                        # Static assets
│   │   └── style.css                  # Custom CSS styling
│   │
│   └── [documentation files]          # Additional docs
│       ├── README.md
│       ├── QUICK_START.md
│       └── REFACTORING_SUMMARY.md
│
└── scrapers/                          # Data collection scripts (gitignored)
    ├── README.md                      # Scraper documentation
    ├── .env                           # API keys (gitignored)
    ├── .env.template                  # Template for .env
    ├── scrape_publications.py         # PubMed scraper
    ├── scrape_github.py               # GitHub scraper
    └── reprocess_insufficient_info_githubs.py  # Deep search script
```

## Important Notes

### Security & Privacy
🔒 **Protected by .gitignore:**
- `.streamlit/secrets.toml` - Your Anthropic API key
- `scrapers/` directory - Entire directory excluded from git
- `.env` files - Environment variables

✅ **Safe to commit:**
- `.streamlit/secrets.toml.template` - Shows required format
- `scrapers/.env.template` - Template only (if accessible)
- `tables/` directory - Data files are committed
- All application code in `app/`

### Scrapers Directory
The `scrapers/` directory is **excluded from the repository** to keep data collection logic private. If you have local access to scrapers:

**Location:** `scrapers/` (gitignored)

**Purpose:** Data collection scripts for gathering publications and code repositories

**Note:** The scrapers are only needed if you want to collect new data. The app works with existing data files in `tables/`.

## Running the Application

### Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API keys
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml and add your Anthropic API key

# 3. Run the app (from project root)
streamlit run app/Home.py
```

The app will open at http://localhost:8501

### Running from Project Root
**Always run from the project root directory:**

```bash
# Correct (from CARD_catalog/)
streamlit run app/Home.py

# Incorrect (don't cd into app/)
cd app && streamlit run Home.py  # Don't do this
```

This ensures proper path resolution for data files in `tables/`.

## Data Files

### Input Data
All data files are stored in `tables/` directory:

- **Dataset inventories:** `dataset-inventory-*.tab`
- **Publications:** `pubmed_central_*.tsv`
- **Code repositories:** `gits_to_reannotate_*.tsv` and batch files
- **Cellular models:** `iNDI_inventory_*.tsv`

### Data Updates
Data files can be updated by:
1. Running scrapers locally (if you have access to `scrapers/`)
2. Manually replacing files in `tables/`
3. The app automatically detects new timestamped files

## Configuration

### API Keys
Required for AI-powered features:

**Anthropic API Key** (required):
- Get from: https://console.anthropic.com/
- Store in: `.streamlit/secrets.toml`
- Format:
  ```toml
  ANTHROPIC_API_KEY = "sk-ant-api03-..."
  ```

**For Streamlit Cloud deployment:**
- Add secrets via App Settings → Secrets in Streamlit Cloud UI
- No local secrets file needed

### Application Settings
Streamlit configuration in `.streamlit/config.toml`:
- Theme settings
- Server configuration
- Browser settings

## Deployment

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Configure secrets
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Add your API key

# Run app
streamlit run app/Home.py
```

### Streamlit Cloud
1. Push repository to GitHub
2. Connect to Streamlit Cloud
3. Point to `app/Home.py` as entry point
4. Add secrets via Cloud UI:
   ```toml
   ANTHROPIC_API_KEY = "your-key-here"
   ```

## File Organization Philosophy

✅ **Clean separation:**
- Application code: `app/`
- Data files: `tables/`
- Configuration: `.streamlit/`
- Documentation: Root directory

✅ **Security first:**
- All secrets gitignored
- Template files provided
- Clear documentation

✅ **User-friendly:**
- Single command to run: `streamlit run app/Home.py`
- Clear directory structure
- Comprehensive documentation

## Git Workflow

### Before Committing

Check that these are NOT being committed:
- `.streamlit/secrets.toml`
- `scrapers/` directory
- Any `.env` files

### Safe to Commit
- All application code
- Template files
- Data files in `tables/`
- Documentation

### Verifying Gitignore
```bash
# Check what would be committed
git status

# Verify secrets are ignored
git check-ignore .streamlit/secrets.toml  # Should show the file
git check-ignore scrapers/                 # Should show the directory
```

## Migration Notes

The project has been migrated from the beta version:
- ✅ Beta directory removed
- ✅ All functionality preserved
- ✅ Improved structure and security
- ✅ Better documentation

See `MIGRATION_COMPLETE.md` for details.

## Contact & Support

**Contact:** Mike A. Nalls PhD via nallsm@nih.gov | mike@datatecnica.com | find us on GitHub.

**Documentation:**
- Main README: `README.md`
- Quick start: `QUICK_START.md`
- API setup: `SETUP_SECRETS.md`
- App documentation: `app/README.md`

## Quick Reference Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Setup secrets
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Edit the file and add your Anthropic API key

# Run application
streamlit run app/Home.py

# Clear cache and restart
# Use the sidebar buttons in the app, or:
rm -rf ~/.streamlit/cache
streamlit run app/Home.py
```
