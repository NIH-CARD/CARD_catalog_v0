# CARD Catalog - Quick Start Guide

## Prerequisites

- Python 3.8 or higher
- pip package manager
- Data files in `../tables/` directory

## Installation (3 steps)

### 1. Install Dependencies

```bash
cd app
pip install -r requirements.txt
```

### 2. Set Up API Key (Optional - for AI features)

Choose one method:

**Option A: Environment Variable**
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

**Option B: .env File**
```bash
cp .env.template .env
# Edit .env and add your API key
```

**Option C: Streamlit Secrets**
```bash
mkdir -p ~/.streamlit
echo 'ANTHROPIC_API_KEY = "your-api-key-here"' > ~/.streamlit/secrets.toml
```

Get your API key from: https://www.anthropic.com/

### 3. Run the Application

```bash
streamlit run app.py
```

The app will open automatically at: **http://localhost:8501**

## Features Overview

### 📊 Datasets Page
- **Table view** with sorting and search
- Browse neuroscience research datasets
- Interactive knowledge graphs
- AI-powered analysis with Claude Sonnet 4.5
- Export data and graphs

### 📚 Publications Page
- **Table view** with sorting and search
- Search scientific literature
- Filter by study, disease, keywords
- Export publications
- AI-powered insights with Claude Sonnet 4.5

### 💻 Code Repositories Page
- Browse GitHub repositories
- **AI quality scoring with Claude Sonnet 4.5** (cleanliness, completeness, runnability)
- FAIR compliance tracking
- Advanced filtering

### ℹ️ About Page
- Complete documentation
- Methodology explanation
- Setup instructions

## Common Tasks

### Filter Data
1. Use sidebar on any page
2. Select from dropdown filters
3. Use keyword search for fuzzy matching
4. Results update automatically

### Generate Knowledge Graph
1. Go to Datasets page
2. Apply filters if desired
3. Click "Knowledge Graph" tab
4. Select connection features
5. Adjust minimum connections
6. Graph generates automatically

### AI Analysis
**Powered by Claude Sonnet 4.5** (claude-sonnet-4-5-20250929)
1. Filter data to desired subset
2. Click "AI Analysis" tab
3. Click "Analyze" button
4. Wait for results (may take 30-60 seconds)
5. Results persist until next analysis

### Score Code Quality
1. Go to Code page
2. Filter repositories if desired
3. Click "Quality Scoring" tab
4. Click one of the score buttons
5. Wait for batch processing
6. View statistics and top repos

### Export Data
1. Filter data as desired
2. Click "Export" tab
3. Choose format (CSV, TSV, JSON, or Text)
4. Click download button
5. File downloads immediately (no reload)

## Troubleshooting

### App Won't Start
- Check Python version: `python --version` (need 3.8+)
- Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
- Check port 8501 is not in use

### Data Not Loading
- Verify data files exist in `../tables/` directory
- Check file permissions (should be readable)
- Review error messages in terminal

### AI Features Not Working
- Ensure API key is set correctly
- Test connection: Go to Code page → Quality Scoring → Test API
- Check API key validity on Anthropic website
- Verify internet connection

### Knowledge Graph Not Displaying
- Reduce data with filters (max 100 nodes)
- Select at least one connection feature
- Try adjusting minimum connections
- Check browser console for errors

### Export Not Working
- Try different format
- Check browser download settings
- Ensure filtered data is not empty
- Try different browser

## Tips & Best Practices

1. **Filter First**: Apply filters before generating graphs or AI analysis for better results
2. **Save API Costs**: Filter data to relevant subset before scoring repositories
3. **Explore Connections**: Try different feature combinations in knowledge graphs
4. **Use Search**: Keyword search is fuzzy - you don't need exact matches
5. **Export Often**: Download your filtered results for offline analysis
6. **Check About Page**: Comprehensive documentation available there

## Data Updates

Data files are expected in:
- `tables/`
- `scrapers/` (FAIR logs)

To update data:
1. Replace files in tables directory
2. Restart Streamlit app
3. Cache automatically refreshes after 1 hour

## Getting Help

1. Check the **About** page in the app
2. Review **README.md** for detailed documentation
3. Review **REFACTORING_SUMMARY.md** for technical details
4. Check error messages in terminal
5. Verify data file formats match expected structure

## Next Steps

- Explore all four pages
- Try different filters and searches
- Generate knowledge graphs with various features
- Export data for external analysis
- If you have an API key, try AI features

Enjoy using CARD Catalog! 🧠🔬
