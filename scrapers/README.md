# CARD Catalog Scrapers

Improved web scrapers for collecting publications and code repositories related to neurodegenerative disease studies.

## Overview

This directory contains two main scrapers:

1. **scrape_publications.py** - Searches PubMed for scientific publications
2. **scrape_github.py** - Searches GitHub for code repositories with AI-powered analysis

Both scrapers are designed to work with the CARD catalog dataset inventory and produce output files that can be directly integrated into the main application.

## Requirements

```bash
pip install pandas requests anthropic
```

### API Keys Setup

The scrapers need API keys to function. You can configure them in two ways:

#### Option 1: Environment Variables (Recommended for CLI use)

```bash
export GITHUB_TOKEN="your_github_token_here"
export ANTHROPIC_API_KEY="your_anthropic_key_here"
```

#### Option 2: .env File

1. Copy the template:
   ```bash
   cp .env.template .env
   ```

2. Edit `.env` and add your actual API keys:
   ```
   GITHUB_TOKEN=your_actual_github_token
   ANTHROPIC_API_KEY=your_actual_anthropic_key
   ```

3. Load the .env file before running scrapers:
   ```bash
   source .env  # or use python-dotenv
   ```

**Where to get API keys:**
- **GitHub Token**: https://github.com/settings/tokens (needs `public_repo` scope)
- **Anthropic API Key**: https://console.anthropic.com/

**Security Note**: Never commit `.env` or files containing API keys to version control!

📖 **For detailed setup instructions, see [../SETUP_SECRETS.md](../SETUP_SECRETS.md)**

## Usage

### Publications Scraper

Searches PubMed for publications related to studies in the dataset inventory.

**Basic usage:**
```bash
cd scrapers
python3 scrape_publications.py
```

**With options:**
```bash
python3 scrape_publications.py \
  --input ../CARD_catalogue_beta-main/CARD_catalogue_beta-main/dataset-inventory-June_20_2025.tab \
  --output publications_output.tsv \
  --max-results 150
```

**Arguments:**
- `--input, -i` - Input TSV file with study inventory (default: dataset-inventory-June_20_2025.tab)
- `--output, -o` - Output TSV file (default: pubmed_central_{timestamp}.tsv)
- `--max-results, -m` - Maximum results per study (default: 100)

**Output format:**
```
Study Name | Abbreviation | Diseases Included | Data Modalities | PubMed Central Link | Authors | Affiliations | Title | Abstract | Keywords
```

### GitHub Repository Scraper

Searches GitHub for code repositories and analyzes them with AI for biomedical relevance.

**Basic usage:**
```bash
cd scrapers
export GITHUB_TOKEN="your_token"
export ANTHROPIC_API_KEY="your_key"
python3 scrape_github.py
```

**With options:**
```bash
python3 scrape_github.py \
  --input ../CARD_catalogue_beta-main/CARD_catalogue_beta-main/dataset-inventory-June_20_2025.tab \
  --output github_repos_output.tsv \
  --github-token YOUR_TOKEN \
  --anthropic-key YOUR_KEY
```

**Arguments:**
- `--input, -i` - Input TSV file with study inventory (default: dataset-inventory-June_20_2025.tab)
- `--output, -o` - Output TSV file (default: gits_to_reannotate_completed_{timestamp}.tsv)
- `--github-token, -g` - GitHub API token (default: from GITHUB_TOKEN env var)
- `--anthropic-key, -a` - Anthropic API key (default: from ANTHROPIC_API_KEY env var)

**Output format:**
```
Study Name | Abbreviation | Diseases Included | Repository Link | Owner | Contributors | Languages | Biomedical Relevance | Code Summary | Data Types | Tooling
```

## Features

### Publications Scraper Improvements

✓ **Exponential backoff retry logic** - Handles API rate limits gracefully
✓ **Batch fetching** - Fetches 20 articles at a time for efficiency
✓ **Enhanced error handling** - Robust XML parsing with fallbacks
✓ **Better query construction** - Improved disease keyword matching
✓ **Progress indicators** - Shows [X/99] progress for each study
✓ **Detailed logging** - All logs go to stderr, doesn't interfere with output

### GitHub Scraper Improvements

✓ **AI-powered analysis** - Uses Claude to determine biomedical relevance
✓ **FAIR compliance logging** - Tracks repositories that don't meet FAIR standards
✓ **Smart content extraction** - Fetches README + package files
✓ **Rate limit handling** - Checks headers and waits appropriately
✓ **Deduplication** - Removes duplicate repos within and across studies
✓ **Biomedical filtering** - AI determines YES/NO biomedical relevance
✓ **Comprehensive metadata** - Extracts summary, data types, and tooling

#### FAIR Compliance Checks

The GitHub scraper automatically checks each repository for FAIR (Findable, Accessible, Interoperable, Reusable) compliance:

**Issues tracked:**
- No README file
- No dependency specification (requirements.txt, package.json, etc.)
- No version information (.python-version, .nvmrc, etc.)
- No container specification (Dockerfile, docker-compose.yml, etc.)
- No environment specification (environment.yml, Pipfile, etc.)
- Insufficient content (may be incomplete or non-functional)

**Output:** `fair_compliance_log_{timestamp}.tsv`
Contains detailed issues for each repository that doesn't meet FAIR standards.

**Statistics printed** at the end of scraping showing percentages of repos with/without FAIR features.

## Output Files

All output files are TSV (tab-separated values) format and include timestamps in the filename:

- **Publications**: `pubmed_central_YYYYMMDD_HHMMSS.tsv`
- **GitHub repos**: `gits_to_reannotate_completed_YYYYMMDD_HHMMSS.tsv`
- **FAIR compliance log**: `fair_compliance_log_YYYYMMDD_HHMMSS.tsv`

These files can be directly loaded into the CARD catalog application.

### Example FAIR Compliance Log

| Repository | Study | Issue Type | Details | Timestamp |
|------------|-------|------------|---------|-----------|
| https://github.com/user/repo | ADNI | No README | Repository lacks a README file, reducing accessibility... | 2025-11-28T... |
| https://github.com/user/repo2 | ADNI | No Dependencies | No dependency file found (requirements.txt...)... | 2025-11-28T... |

## Input Requirements

Both scrapers expect a TSV file with the following columns:

**Required columns:**
- `Study Name` - Full name of the study
- `Abbreviation` - Study abbreviation/acronym
- `Diseases Included` - Semicolon-separated list of diseases
- `Data Modalities` - Semicolon-separated list of data types

**Example:**
```tsv
Study Name	Abbreviation	Data Modalities	Diseases Included
Alzheimer's Disease Neuroimaging Initiative	ADNI	[clinical, imaging] MRI; PET; CSF	Alzheimer's Disease; MCI
```

## Rate Limiting

Both scrapers implement intelligent rate limiting:

- **PubMed**: 1 second minimum between requests, exponential backoff on errors
- **GitHub**: 2 seconds minimum between requests, checks rate limit headers

## Error Handling

- All errors are logged to stderr
- Scrapers continue processing other studies if one fails
- API failures trigger exponential backoff retries (max 3 attempts)
- Results are saved even if some studies fail

## Integration with CARD Catalog

The output files from these scrapers are designed to match the exact format of previous iterations, so they can be "plugged right into the app" without any modifications.

Simply run the scrapers with the latest dataset inventory file and use the output TSV files in your application.
