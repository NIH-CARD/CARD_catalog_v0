# CARD Catalog v0.1 - Quick Start Guide

Get the CARD Catalog web application running in 5 minutes.

## Prerequisites

- Python 3.7+
- pip
- Anthropic API key (for AI-powered features)

## Quick Start

### 1️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

This installs all required packages including Streamlit, Pandas, Anthropic, and visualization libraries.

### 2️⃣ Configure API Keys

Copy the template and add your Anthropic API key:

```bash
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` and add your key:
```toml
ANTHROPIC_API_KEY = "sk-ant-api03-your-key-here"
```

**Get an API key:** https://console.anthropic.com/

**Note:** The `GITHUB_TOKEN` is only needed if you're running scrapers locally (which are gitignored).

### 3️⃣ Run the Application

From the project root directory:

```bash
streamlit run app/Home.py
```

The app will open automatically at `http://localhost:8501`

### 4️⃣ Explore the Catalog

Navigate through the sidebar to explore:

- **📊 Datasets** - Browse 99 neuroscience datasets with knowledge graphs and AI analysis
- **📚 Publications** - Search 860 scientific publications from PubMed Central
- **💻 Code** - Discover 568 GitHub repositories with quality scoring
- **🧬 Human Cellular Models** - Browse 626 iNDI iPSC cell lines
- **ℹ️ About** - Learn about methodology and FAIR compliance

## Common Tasks

### Clear Cache and Restart

Use the sidebar buttons in the app:
- **🔄 Restart App** - Restart without clearing cache
- **🗑️ Clear Cache** - Clear cached data and restart

Or from command line:
```bash
rm -rf ~/.streamlit/cache
streamlit run app/Home.py
```

### Export Data

On any page:
1. Apply filters to narrow down data
2. Use export buttons at the bottom:
   - **CSV** - For Excel and spreadsheets
   - **TSV** - For tab-separated data
   - **JSON** - For programmatic access
   - **Text Summary** - Human-readable reports

### Generate AI Analysis

1. Navigate to any page (Datasets, Publications, Code, or Cellular Models)
2. Apply filters to select items of interest
3. Go to the "AI Analysis" tab
4. Click "Analyze" button
5. Results appear below and can be downloaded

**Note:** AI analysis requires an Anthropic API key and consumes API credits.

### Build Knowledge Graphs

Available on Datasets, Publications, and Code pages:

1. Go to "Knowledge Graph" tab
2. Select features to connect items (e.g., diseases, data types)
3. Adjust minimum shared features threshold
4. Click "Generate Graph"
5. Interact with the graph:
   - Hover over nodes for details
   - Drag nodes to rearrange
   - Zoom and pan
   - Download adjacency matrix for network analysis

## Troubleshooting

### Error: "API key not configured"

**Solution:** Make sure you've set up `.streamlit/secrets.toml`:
```bash
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Edit the file and add your ANTHROPIC_API_KEY
```

### Error: "No module named 'streamlit'"

**Solution:** Install dependencies:
```bash
pip install -r requirements.txt
```

### Error: "FileNotFoundError" for data files

**Solution:** Make sure you're running from the project root:
```bash
# Correct
streamlit run app/Home.py

# Wrong - don't cd into app/
cd app && streamlit run Home.py  # Don't do this
```

### Application is slow or unresponsive

**Solutions:**
1. Clear cache using sidebar button "🗑️ Clear Cache"
2. Or manually: `rm -rf ~/.streamlit/cache`
3. Restart the application

### AI Analysis not working

**Check:**
1. API key is configured in `.streamlit/secrets.toml`
2. Key has correct format: `ANTHROPIC_API_KEY = "sk-ant-api03-..."`
3. API key is valid (check console.anthropic.com)
4. You have API credits remaining

## Data Files

The application uses data files in the `tables/` directory:

| File | Purpose | Count |
|------|---------|-------|
| `dataset-inventory-*.tab` | Neuroscience datasets | 99 |
| `pubmed_central_*.tsv` | Scientific publications | 860 |
| `gits_to_reannotate_*.tsv` | GitHub repositories | 568 |
| `iNDI_inventory_*.tsv` | iPSC cell lines | 626 |

**Note:** The app automatically uses the most recent timestamped files.

## Streamlit Cloud Deployment

To deploy on Streamlit Cloud:

1. Push repository to GitHub
2. Go to https://streamlit.io/cloud
3. Connect your GitHub repository
4. Set main file path: `app/Home.py`
5. Add secrets via App Settings → Secrets:
   ```toml
   ANTHROPIC_API_KEY = "your-key-here"
   ```
6. Deploy!

**Important:** Secrets are automatically excluded from the repository (protected by `.gitignore`).

## Next Steps

- 📖 Read [README.md](README.md) for comprehensive documentation
- 📊 Check [STRUCTURE.md](STRUCTURE.md) for project organization
- 🔑 See [SETUP_SECRETS.md](SETUP_SECRETS.md) for detailed API setup
- ℹ️ Visit the "About" page in the app for methodology details

## Quick Reference

### Essential Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Setup secrets
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Edit file and add API key

# Run application
streamlit run app/Home.py

# Clear cache
rm -rf ~/.streamlit/cache
```

### File Locations

```
CARD_catalog/
├── app/Home.py              # Main entry point
├── .streamlit/secrets.toml  # Your API keys (gitignored)
├── tables/                  # Data files
└── requirements.txt         # Dependencies
```

### Key Features

| Feature | Location | Requires API Key |
|---------|----------|------------------|
| Browse data | All pages | No |
| Filter & search | All pages | No |
| Export data | All pages | No |
| Knowledge graphs | Datasets, Pubs, Code | No |
| AI analysis | All pages | Yes |
| Code Deep Dive | Code page | Yes |

## Tips

💡 **Start exploring** without an API key - browsing, filtering, and graphs work without it
💡 **Monitor API costs** - Check usage at console.anthropic.com
💡 **Use filters first** - Narrow down data before running AI analysis to save tokens
💡 **Export results** - Download analysis results for your records
💡 **Try knowledge graphs** - Great for visualizing relationships between items

## Getting Help

**Documentation:**
- Application overview: [README.md](README.md)
- Project structure: [STRUCTURE.md](STRUCTURE.md)
- API setup details: [SETUP_SECRETS.md](SETUP_SECRETS.md)
- In-app docs: Visit the "About" page

**Contact:**
Mike A. Nalls PhD via nallsm@nih.gov | mike@datatecnica.com | find us on GitHub.

## Data Collection (Advanced)

The `scrapers/` directory contains data collection scripts but is excluded from the repository. If you have local access and want to collect new data, see the scrapers/README.md file for instructions.

**For most users:** The provided data files in `tables/` are sufficient - no scraping needed!
