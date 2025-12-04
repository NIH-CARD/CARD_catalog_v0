# API Keys and Secrets Setup Guide

This guide explains how to securely configure API keys for the CARD Catalog scrapers and Streamlit app.

## ⚠️ Security First

**NEVER commit secrets to Git!** The `.gitignore` file is configured to prevent this, but always double-check before committing.

## API Keys You Need

1. **GitHub Personal Access Token**
   - Where to get: https://github.com/settings/tokens
   - Permissions needed: `public_repo` (for accessing public repositories)
   - Click "Generate new token (classic)"

2. **Anthropic API Key**
   - Where to get: https://console.anthropic.com/settings/keys
   - Click "Create Key"
   - Note: This is a paid service, monitor your usage

## Configuration Methods

### Option 1: For CLI Scrapers (Local Terminal Use)

**Using .env file:**

```bash
cd scrapers
cp .env.template .env
# Edit .env with your actual keys
nano .env
```

Then add:
```
GITHUB_TOKEN=ghp_your_actual_token_here
ANTHROPIC_API_KEY=sk-ant-api03-your_actual_key_here
```

**Load before running:**
```bash
export $(cat .env | xargs)
python3 scrape_github.py
```

### Option 2: For Streamlit App (Local Development)

**Using secrets.toml:**

```bash
cd .streamlit
cp secrets.toml.template secrets.toml
# Edit secrets.toml with your actual keys
nano secrets.toml
```

Then add:
```toml
GITHUB_TOKEN = "ghp_your_actual_token_here"
ANTHROPIC_API_KEY = "sk-ant-api03-your_actual_key_here"
```

**Run Streamlit:**
```bash
cd CARD_catalogue_beta-main/CARD_catalogue_beta-main
streamlit run app.py
```

### Option 3: For Streamlit Cloud (Production Deployment)

1. Go to https://share.streamlit.io/ and navigate to your app
2. Click on your app → "Settings" (⚙️ icon)
3. Click "Secrets" in the left sidebar
4. Paste your secrets in TOML format:

```toml
GITHUB_TOKEN = "ghp_your_actual_token_here"
ANTHROPIC_API_KEY = "sk-ant-api03-your_actual_key_here"
```

5. Click "Save"
6. Your app will automatically restart with the new secrets

## File Structure

```
CARD_catalog/
├── .gitignore                          # Prevents committing secrets
├── .streamlit/
│   ├── secrets.toml                    # Your actual secrets (gitignored)
│   └── secrets.toml.template           # Template to copy
├── scrapers/
│   ├── .env                            # Your actual keys (gitignored)
│   ├── .env.template                   # Template to copy
│   ├── scrape_github.py
│   └── scrape_publications.py
└── CARD_catalogue_beta-main/
    └── CARD_catalogue_beta-main/
        └── app.py                      # Streamlit app (uses st.secrets)
```

## Testing Your Configuration

**Test environment variables:**
```bash
echo $GITHUB_TOKEN
echo $ANTHROPIC_API_KEY
```

**Test Streamlit secrets:**
```bash
cd CARD_catalogue_beta-main/CARD_catalogue_beta-main
streamlit run app.py
# Check if the app loads without errors about missing API keys
```

**Test scrapers:**
```bash
cd scrapers
python3 scrape_publications.py --help
# Should show help without errors
```

## Troubleshooting

### "GITHUB_TOKEN not found" error

**Problem:** Environment variable not set
**Solution:**
```bash
export GITHUB_TOKEN="your_token_here"
# Or load from .env:
cd scrapers && source .env
```

### "ANTHROPIC_API_KEY not found" error

**Problem:** API key not configured
**Solution:**
```bash
export ANTHROPIC_API_KEY="your_key_here"
# Or load from .env:
cd scrapers && source .env
```

### Streamlit app shows "secrets.toml not found"

**Problem:** Secrets file not created
**Solution:**
```bash
cd .streamlit
cp secrets.toml.template secrets.toml
# Edit secrets.toml with your actual keys
```

## What's Protected

The following files are automatically ignored by Git (see `.gitignore`):

- `.env` (CLI environment variables)
- `.streamlit/secrets.toml` (Streamlit secrets)
- `scrapers/.env` (Scraper environment variables)

You can safely edit these files without risk of accidentally committing them.

## Best Practices

1. ✅ Use different tokens for development vs production
2. ✅ Rotate your keys periodically
3. ✅ Set token permissions to minimum required (principle of least privilege)
4. ✅ Monitor your API usage (especially Anthropic - it's paid)
5. ✅ Revoke old tokens when no longer needed
6. ❌ Never share keys in chat, screenshots, or public forums
7. ❌ Never commit keys to version control
8. ❌ Never hardcode keys in source code

## Cost Monitoring

**Anthropic API:**
- Monitor usage at: https://console.anthropic.com/settings/usage
- Set budget limits to avoid unexpected charges
- Claude Sonnet 4 pricing: ~$3 per million input tokens

**GitHub API:**
- Free tier: 5,000 requests/hour (authenticated)
- Monitor rate limits in response headers
- The scrapers include rate limiting to stay within bounds
