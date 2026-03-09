#!/usr/bin/env python3
"""
CARD Catalog - Publications Scraper
Searches PubMed for publications related to neurodegenerative disease studies
"""
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time
import re
import sys
import os
import urllib.parse
from typing import List, Dict, Optional
import argparse
import logging
from logging_config import setup_logger, get_default_log_file
from dotenv import load_dotenv

try:
    load_dotenv()
except ImportError:
    pass

# Module-level logger - will be configured in main()
logger = logging.getLogger(__name__)

def clean_text(text):
    """Remove newlines and extra whitespace from text"""
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', text.strip())

def mask_api_key(text: str) -> str:
    """Mask API keys in any text (URLs, error messages, etc.)"""
    return re.sub(r'api_key=[^&\s]+', 'api_key=***', text)

def search_pubmed_with_retry(url: str, max_retries: int = 3, base_delay: int = 60) -> Optional[requests.Response]:
    """Make a request to PubMed API with exponential backoff retry logic"""
    logged_url = mask_api_key(url)
    logger.info(f"Fetching URL: {logged_url}")
    for attempt in range(max_retries):
        try:
            logger.debug(f"Attempt {attempt + 1}/{max_retries}, sleeping 1 second for rate limiting")
            time.sleep(0.1)  # Rate limiting: minimum 0.1 second between requests
            response = requests.get(url, timeout=30)

            logger.debug(f"Response status code: {response.status_code}")
            if response.status_code == 200:
                logger.debug(f"Successfully received response, content length: {len(response.content)} bytes")
                return response
            elif response.status_code == 429:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Rate limited (attempt {attempt + 1}/{max_retries}). Waiting {delay} seconds...")
                time.sleep(delay)
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            masked_error = mask_api_key(str(e))
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {masked_error}. Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"Request failed after {max_retries} attempts: {masked_error}")
                return None
    return None

def extract_article_details(article_xml: ET.Element) -> Optional[Dict]:
    """Extract article details from PubMed XML"""
    try:
        # Get PMID for tracking
        pmid_elem = article_xml.find('.//PMID')
        pmid = pmid_elem.text if pmid_elem is not None else ""
        logger.debug(f"Extracting details for PMID: {pmid}")

        # Get title
        title = article_xml.find('.//ArticleTitle')
        title_text = clean_text(title.text if title is not None and title.text else "")

        if not title_text:
            return None

        # Get abstract
        abstract = ""
        abstract_elements = article_xml.findall('.//AbstractText')
        if abstract_elements:
            abstract_parts = []
            for elem in abstract_elements:
                if elem.text:
                    # Check if abstract section has a label
                    label = elem.get('Label')
                    if label:
                        abstract_parts.append(f"{label}: {clean_text(elem.text)}")
                    else:
                        abstract_parts.append(clean_text(elem.text))
            abstract = " ".join(abstract_parts)

        # Get authors and affiliations
        authors = []
        affiliations = []
        author_list = article_xml.find('.//AuthorList')
        if author_list is not None:
            for author in author_list.findall('.//Author'):
                last_name = author.find('.//LastName')
                fore_name = author.find('.//ForeName')
                if last_name is not None and fore_name is not None:
                    authors.append(f"{last_name.text} {fore_name.text}")
                elif last_name is not None:
                    authors.append(last_name.text)

                # Get affiliation
                aff = author.find('.//Affiliation')
                if aff is not None and aff.text:
                    aff_text = clean_text(aff.text)
                    if aff_text and aff_text not in affiliations:
                        affiliations.append(aff_text)
        
        logger.debug(f"Found {len(authors)} authors and {len(affiliations)} unique affiliations")

        # Get keywords
        keywords = []
        keyword_list = article_xml.find('.//KeywordList')
        if keyword_list is not None:
            keywords = [k.text for k in keyword_list.findall('.//Keyword') if k.text]
        
        logger.debug(f"Found {len(keywords)} keywords")

        # Get PMC ID if available
        pmc_id = None
        article_ids = article_xml.findall('.//ArticleId')
        for article_id in article_ids:
            if article_id.get('IdType') == 'pmc':
                pmc_id = article_id.text
                pmc_id = re.sub(r"PMC", "", pmc_id)  # Remove PMC prefix
                logger.debug(f"Found PMC ID: {pmc_id}")
                break

        # Create PMC link if available by adding prefix
        pmc_link = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/" if pmc_id else ""

        return {
            "PMID": pmid,
            "Title": title_text,
            "Abstract": abstract,
            "Authors": "; ".join(authors),
            "Affiliations": "; ".join(affiliations),
            "Keywords": "; ".join(keywords),
            "PubMed Central Link": pmc_link
        }
    except Exception as e:
        logger.error(f"Error extracting article details: {str(e)}")
        return None

def build_search_query(study_name: str, abbreviation: str, diseases: str, data_modalities: str, years: int = 3) -> str:
    """Build optimized PubMed search query"""
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*years)
    date_range = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}"
    
    logger.debug(f"Building query for study: {study_name}, abbreviation: {abbreviation}")
    logger.debug(f"Date range: {date_range}")

    # Core disease keywords for neurodegenerative diseases
    disease_keywords = ["alzheimer", "parkinson", "dementia", "brain", "neurodegenerative",
                       "neurodegeneration", "tremor", "amyotrophic", "als", "cognitive impairment",
                       "mild cognitive impairment", "mci", "lewy body"]

    # Extract disease terms from the Diseases Included column
    disease_terms = []
    if pd.notna(diseases) and isinstance(diseases, str):
        disease_terms = [d.strip().lower() for d in diseases.split(";")
                        if any(kw in d.lower() for kw in disease_keywords)]
    
    logger.debug(f"Extracted disease terms: {disease_terms}")

    # Fall back to general keywords if no specific diseases found
    if not disease_terms:
        disease_terms = disease_keywords[:5]  # Use top 5 general keywords
        logger.debug(f"No specific diseases found, using default keywords: {disease_terms}")

    # Extract data modalities
    modalities = []
    if pd.notna(data_modalities) and isinstance(data_modalities, str):
        # Handle both semicolon-separated and bracket-enclosed formats
        clean_modalities = data_modalities.strip('[]')
        modalities = [m.strip() for m in clean_modalities.split(';') if m.strip()]
    
    logger.debug(f"Extracted modalities: {modalities}")

    # Build query terms
    study_terms = []
    if study_name and pd.notna(study_name):
        study_terms.append(f'"{study_name}"[All Fields]')
    if abbreviation and pd.notna(abbreviation) and abbreviation != study_name:
        study_terms.append(f'"{abbreviation}"[All Fields]')
    
    logger.debug(f"Study terms: {study_terms}")

    query_parts = []

    # Study name/abbreviation (at least one must match)
    if study_terms:
        query_parts.append(f'({" OR ".join(study_terms)})')

    # Disease terms
    disease_query = " OR ".join([f'"{term}"[All Fields]' for term in disease_terms])
    query_parts.append(f'({disease_query})')

    # Date range
    query_parts.append(f'({date_range}[Date - Publication])')

    # Add data modalities if available (optional - using OR to broaden search)
    if modalities:
        modality_terms = [f'"{modality}"[All Fields]' for modality in modalities[:5]]  # Limit to 5 modalities
        query_parts.append(f'({" OR ".join(modality_terms)})')

    final_query = " AND ".join(query_parts)
    logger.debug(f"Final query constructed: {final_query}")
    return final_query

# Common English words and biomedical terms that cause false-positive explosions
# when searched as abbreviations in [tiab]. Observed during v2 testing and extended
# with obvious common words. Extend this set as needed based on query results.
_NOISY_ABBREVIATIONS = frozenset({
    # Observed false-positive explosions in v2 testing (Feb 2026)
    "leads", "prevent", "identity", "map", "ros", "codes", "mars",
    "campaign", "adams", "insight", "beam", "ample", "expedition",
    "caps", "elsa", "haas", "rosiglitazone",
    # Common biomedical abbreviations with dominant non-study meanings
    "gs",       # Glutamine Synthetase, Gram Stain
    "lbp",      # Low Back Pain
    "smi",      # Serious Mental Illness
    "nph",      # Normal Pressure Hydrocephalus
    "adcp",     # Antibody-Dependent Cellular Phagocytosis
    "hbs",      # Hepatitis B Surface antigen
    "lcc",      # Left Common Carotid, Large Cell Carcinoma
    "twas",     # Generic method name (Transcriptome-Wide Association Study)
    "a4",       # Paper size, complement component
    "adcs",     # Multiple biomedical meanings beyond the AD study
    # Common English words plausibly used as study abbreviations
    "accord", "impact", "sprint", "promise", "compass", "focus",
    "vital", "spark", "echo", "grace", "hope", "care", "gait",
    "engage", "epic", "gain", "idea", "mind", "plan", "race",
    "safe", "team", "view", "act", "age", "aim", "cell", "core",
    "cure", "fast", "gene", "seed", "target", "track", "trend",
    "match", "predict", "select", "prime", "origin", "snap",
})

def build_search_query_v2(study_name: str, abbreviation: str, diseases: str, data_modalities: str, years: int = 3) -> str:
    """Build informationist-informed PubMed search query.

    - Uses [tiab] (Title/Abstract) to avoid false positives from references/affiliations
    - Omits data modality terms (catalog metadata, not PubMed vocabulary)
    - Omits disease terms (were over-restricting results)
    - Skips abbreviations that are common English words (checked against _NOISY_ABBREVIATIONS)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*years)
    date_range = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}"

    logger.debug(f"Building v2 query for study: {study_name}, abbreviation: {abbreviation}")

    # Always include full study name in [tiab] — this is the most precise signal
    study_terms = []
    if study_name and pd.notna(study_name):
        clean_name = re.sub(r'\s*\([^)]*\)\s*$', '', str(study_name)).strip()
        if clean_name:
            study_terms.append(f'"{clean_name}"[tiab]')

    # Only include abbreviation if it's not a common word
    abbrev_str = str(abbreviation).strip() if pd.notna(abbreviation) else ""
    if abbrev_str and abbrev_str != str(study_name) and abbrev_str.lower() not in _NOISY_ABBREVIATIONS:
        study_terms.append(f'"{abbrev_str}"[tiab]')
    elif abbrev_str and abbrev_str.lower() in _NOISY_ABBREVIATIONS:
        logger.info(f"Skipping noisy abbreviation '{abbrev_str}' (common word)")

    query_parts = []
    if study_terms:
        query_parts.append(f'({" OR ".join(study_terms)})')

    query_parts.append(f'({date_range}[Date - Publication])')

    final_query = " AND ".join(query_parts)
    logger.debug(f"Final v2 query: {final_query}")
    return final_query

def search_pubmed(study_name: str, abbreviation: str, diseases: str, search_data_modalities: str, max_results: int = 100, ncbi_api_key_suffix: str = "", query_method: str = "original") -> List[Dict]:
    """Search PubMed for articles related to the study"""
    # Build search query
    if query_method == "v2":
        query = build_search_query_v2(study_name, abbreviation, diseases, search_data_modalities)
    else:
        query = build_search_query(study_name, abbreviation, diseases, search_data_modalities)

    # Search PubMed (URL-encode the query to handle &, parentheses, etc.)
    base_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    encoded_query = urllib.parse.quote(query, safe='')
    search_url = f'{base_url}?db=pubmed&term={encoded_query}&retmax={max_results}&retmode=json{ncbi_api_key_suffix}'

    logger.info(f"Query: {query[:100]}..." if len(query) > 100 else f"Query: {query}")
    logger.debug(f"Query: {query}...")
    logger.debug(f"API key in URL: {'YES' if ncbi_api_key_suffix else 'NO'}")
    
    logger.debug(f"Max results requested: {max_results}")

    response = search_pubmed_with_retry(search_url)
    if not response:
        return []

    try:
        data = response.json()
        logger.debug(f"Successfully parsed JSON response")
        pubmed_ids = data.get('esearchresult', {}).get('idlist', [])
        logger.debug(f"Extracted {len(pubmed_ids)} PubMed IDs")

        if not pubmed_ids:
            logger.info("No results found")
            return []

        logger.info(f"Found {len(pubmed_ids)} articles")

        results = []
        # Fetch articles in batches to improve efficiency
        batch_size = 20
        logger.debug(f"Processing {len(pubmed_ids)} IDs in batches of {batch_size}")
        for i in range(0, len(pubmed_ids), batch_size):
            batch_ids = pubmed_ids[i:i+batch_size]
            ids_str = ",".join(batch_ids)
            
            logger.debug(f"Fetching batch {i//batch_size + 1}: IDs {i} to {i+len(batch_ids)}")

            fetch_url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml{ncbi_api_key_suffix}'
            fetch_response = search_pubmed_with_retry(fetch_url)

            if not fetch_response:
                continue

            try:
                # Parse XML
                root = ET.fromstring(fetch_response.text)
                articles = root.findall('.//PubmedArticle')
                logger.debug(f"Parsed XML, found {len(articles)} articles in batch")

                for article in articles:
                    article_data = extract_article_details(article)
                    if article_data:
                        logger.debug(f"Successfully extracted article: {article_data.get('PMID', 'unknown')}")
                        # Add study information
                        article_data.update({
                            "Study Name": study_name,
                            "Abbreviation": abbreviation,
                            "Diseases Included": diseases,
                            "Data Modalities": search_data_modalities
                        })
                        results.append(article_data)

            except Exception as e:
                logger.error(f"Error parsing batch: {str(e)}")
                continue

        logger.info(f"Successfully processed {len(results)} articles")
        return results

    except Exception as e:
        logger.error(f"Error processing search results: {str(e)}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Scrape PubMed for publications related to neurodegenerative disease studies')
    parser.add_argument('--input', '-i', default='../tables/dataset-inventory-June_20_2025.tab',
                       help='Input TSV file with study inventory (default: ../tables/dataset-inventory-June_20_2025.tab)')
    parser.add_argument('--output', '-o', default=None,
                       help='Output TSV file (default: pubmed_central_{timestamp}.tsv)')
    parser.add_argument('--max-results', '-m', type=int, default=100,
                       help='Maximum results per study (default: 100)')
    parser.add_argument('--ncbi-api-key', default=None,
                       help='NCBI API key for higher rate limits (default: from NCBI_API_KEY env var)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose (DEBUG) logging')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Show only warnings and errors')
    parser.add_argument('--log-file', default=None,
                       help='Log file path (default: publications_{timestamp}.log)')
    parser.add_argument('--clear-log', action='store_true',
                       help='Clear log file before writing (default: append)')
    parser.add_argument('--query-method', choices=['original', 'v2'], default='original',
                       help='Query construction method: "original" uses [All Fields] with disease+modality '
                            'terms; "v2" uses [tiab] with no modality terms and proper URL encoding '
                            '(informationist-informed) (default: original)')

    args = parser.parse_args()

    # Setup logging based on verbosity flags
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    
    log_file = args.log_file or get_default_log_file("publications")
    setup_logger(__name__, log_file=log_file, level=level, clear=args.clear_log)
    logger.info(f"Logging initialized. Log file: {log_file}")

    # Check for optional environment variable
    ncbi_api_key = args.ncbi_api_key or os.getenv('NCBI_API_KEY')
    if not ncbi_api_key:
        logger.warning("NCBI_API_KEY not set. You may encounter lower rate limits when accessing the NCBI Entrez Utilities API.")
        ncbi_api_key_suffix = ""
    else:
        logger.info(f"NCBI API key found (length: {len(ncbi_api_key)} characters)")
        ncbi_api_key_suffix = f"&api_key={ncbi_api_key}"
        logger.debug(f"API key suffix constructed successfully")

    # Args debug info
    logger.info(f"Query method: {args.query_method}")
    logger.debug(f"Input file: {args.input}")

    # Read the dataset inventory
    try:
        studies_df = pd.read_csv(args.input, sep="\t")
        logger.info(f"Loaded {len(studies_df)} studies from {args.input}")
    except Exception as e:
        logger.error(f"Error reading dataset inventory: {str(e)}")
        sys.exit(1)

    # Initialize results list
    all_results = []

    # Process each study
    for idx, row in studies_df.iterrows():
        study_name = row.get("Study Name", "")
        abbreviation = row.get("Abbreviation", "")
        diseases = row.get("Diseases Included", "")
        search_data_modalities = row.get("Coarse Data Modality", "").split().extend(row.get("Granular Data Modalities", "").split())

        logger.info(f"[{idx+1}/{len(studies_df)}] Searching for publications: {study_name} ({abbreviation})")
        results = search_pubmed(study_name, abbreviation, diseases, search_data_modalities, args.max_results, ncbi_api_key_suffix, args.query_method)
        all_results.extend(results)

    # Create and save results dataframe
    if all_results:
        logger.debug(f"Creating dataframe from {len(all_results)} total results")
        # Reorder columns to match previous format exactly
        columns_order = [
            "PMID",
            "Study Name",
            "Abbreviation",
            "Diseases Included",
            "Coarse Data Modality",
            "PubMed Central Link",
            "Authors",
            "Affiliations",
            "Title",
            "Abstract",
            "Keywords"
        ]

        results_df = pd.DataFrame(all_results)
        logger.debug(f"Initial dataframe shape: {results_df.shape}")

        # Ensure all columns exist
        for col in columns_order:
            if col not in results_df.columns:
                results_df[col] = ""
                logger.debug(f"Added missing column: {col}")

        # Reorder columns
        results_df = results_df[columns_order]
        logger.debug(f"Reordered columns, final shape: {results_df.shape}")

        # Generate output filename
        if args.output:
            output_filename = args.output
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = os.path.join(os.path.dirname(__file__), "../tables", f"pubmed_central_{timestamp}.tsv")

        results_df.to_csv(output_filename, sep="\t", index=False)

        logger.info("="*60)
        logger.info(f"SUCCESS: Results saved to {output_filename}")
        logger.info(f"Total articles found: {len(all_results)}")
        logger.info("="*60)
    else:
        logger.warning("No results found")
        sys.exit(1)

if __name__ == "__main__":
    main()
