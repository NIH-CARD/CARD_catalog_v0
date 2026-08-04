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

        # Get publication date — prefer ArticleDate (electronic), fall back to PubDate
        pub_date = ""
        article_date = article_xml.find('.//ArticleDate')
        if article_date is not None:
            year = getattr(article_date.find('Year'), 'text', '')
            month = getattr(article_date.find('Month'), 'text', '').zfill(2)
            day = getattr(article_date.find('Day'), 'text', '').zfill(2)
            if year:
                pub_date = f"{year}-{month}-{day}" if month and day else year
        if not pub_date:
            pub_date_elem = article_xml.find('.//Journal/JournalIssue/PubDate')
            if pub_date_elem is not None:
                year = getattr(pub_date_elem.find('Year'), 'text', '')
                month = getattr(pub_date_elem.find('Month'), 'text', '').zfill(2)
                day = getattr(pub_date_elem.find('Day'), 'text', '').zfill(2)
                medline = getattr(pub_date_elem.find('MedlineDate'), 'text', '')
                if year:
                    pub_date = f"{year}-{month}-{day}" if month and day else year
                elif medline:
                    pub_date = medline

        return {
            "PMID": pmid,
            "Title": title_text,
            "Abstract": abstract,
            "Authors": "; ".join(authors),
            "Affiliations": "; ".join(affiliations),
            "Keywords": "; ".join(keywords),
            "PubMed Central Link": pmc_link,
            "Publication Date": pub_date,
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
        modalities = [m.strip() for m in data_modalities.split(',') if m.strip()]

    logger.debug(f"Extracted modalities: {modalities}")

    study_names_matching_false_positives = ['NICOLA', 'ADAMS', 'CODES']
    # Build query terms
    study_terms = []
    if study_name and pd.notna(study_name):
        study_terms.append(f'"{study_name}"[All Fields]')
    if abbreviation and pd.notna(abbreviation) and abbreviation != study_name:
        study_terms.append(f'"{abbreviation}"[All Fields]')
    
    logger.debug(f"Study terms: {study_terms}")

    query_parts = []

    # Resource Name/abbreviation (at least one must match)
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

    # Always include full Resource Name in [tiab] — this is the most precise signal
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

def build_search_query_v3(study_name: str, abbreviation: str, diseases: str, data_modalities: str, years: int = 3) -> str:
    """Build PubMed search query: v2 (tiab, noisy abbrev filter) + disease terms + modality terms.

    - Uses [tiab] like v2 to reduce false positives from references/affiliations
    - Skips noisy abbreviations like v2
    - Adds disease terms AND modality terms like the original query for precision
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*years)
    date_range = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}"

    logger.info(f"Building v3 query for study: {study_name}, abbreviation: {abbreviation}")

    # Study terms: [tiab] + noisy abbreviation filter (from v2)
    study_terms = []
    if study_name and pd.notna(study_name):
        clean_name = re.sub(r'\s*\([^)]*\)\s*$', '', str(study_name)).strip()
        if clean_name:
            study_terms.append(f'"{clean_name}"[tiab]')

    abbrev_str = str(abbreviation).strip() if pd.notna(abbreviation) else ""
    if abbrev_str and abbrev_str != str(study_name) and abbrev_str.lower() not in _NOISY_ABBREVIATIONS:
        study_terms.append(f'"{abbrev_str}"[tiab]')
    elif abbrev_str and abbrev_str.lower() in _NOISY_ABBREVIATIONS:
        logger.info(f"Skipping noisy abbreviation '{abbrev_str}' (common word)")

    # Disease terms (from original)
    disease_keywords = ["alzheimer", "parkinson", "dementia", "brain", "neurodegenerative",
                       "neurodegeneration", "tremor", "amyotrophic", "als", "cognitive impairment",
                       "mild cognitive impairment", "mci", "lewy body"]
    disease_terms = []
    if pd.notna(diseases) and isinstance(diseases, str):
        logger.info(f"Diseases: {diseases}")
        disease_terms = []
        for d in diseases.split(";"):
            for kw in disease_keywords:
                if kw in d.lower():
                    disease_terms.append(d.strip().lower())
                    #disease_terms.append(kw) if d.lower() != kw else None

    if not disease_terms:
        disease_terms = disease_keywords[:5]

    # Modality terms (from original)
    modalities = []
    if pd.notna(data_modalities) and isinstance(data_modalities, str):
        modalities = [m.strip() for m in data_modalities.split(',') if m.strip()]

    query_parts = []
    if study_terms:
        query_parts.append(f'({" OR ".join(study_terms)})')

    disease_query = " OR ".join([f'"{term}"[All Fields]' for term in disease_terms])
    query_parts.append(f'({disease_query})')

    query_parts.append(f'({date_range}[Date - Publication])')

    if modalities:
        modality_terms = [f'"{m}"[All Fields]' for m in modalities[:5]]
        query_parts.append(f'({" OR ".join(modality_terms)})')

    final_query = " AND ".join(query_parts)
    logger.debug(f"Final v3 query: {final_query}")
    return final_query


# Generic ADRD abbreviation <-> full-phrase pairs used to expand a concept to keywords liekly to appear
_ADRD_ABBREVIATION_PAIRS = [
    ("alzheimer's disease", "AD"),
    ("parkinson's disease", "PD"),
    ("mild cognitive impairment", "MCI"),
    ("frontotemporal dementia", "FTD"),
    ("amyotrophic lateral sclerosis", "ALS"),
    ("dementia with lewy bodies", "DLB"),
    ("lewy body dementia", "DLB"),
    ("progressive supranuclear palsy", "PSP"),
    ("corticobasal degeneration", "CBD"),
    ("multiple system atrophy", "MSA"),
    ("traumatic brain injury", "TBI"),
    ("frontotemporal lobar degeneration", "FTLD"),
    ("cerebral amyloid angiopathy", "CAA"),
    ("alzheimer's disease and related dementias", "ADRD"),
    ("apolipoprotein e", "APOE"),
    ("cerebrospinal fluid", "CSF"),
    ("positron emission tomography", "PET"),
    ("magnetic resonance imaging", "MRI"),
    ("induced pluripotent stem cell", "iPSC"),
]

_GENERIC_CONCEPT_STOPWORDS = frozenset({
    "controls", "control", "not specified", "biosamples", "model systems",
    "aging", "normal aging", "healthy controls", "healthy aging",
    "normal controls", "elderly controls", "cognitively unimpaired",
    "multiple conditions", "cognitively normal", "biomarker", "biomarkers",
    "resilience", "prodromal", "dementia",
})


def _split_concept_cell(value: str) -> List[str]:
    """ Split a Diseases/Modality cell into atomic concept strings. """
    if not value or pd.isna(value):
        return []
    concepts = []
    for part in re.split(r"[;,]", str(value)):
        term = part.strip()
        if len(term) < 3 or term.lower() in _GENERIC_CONCEPT_STOPWORDS:
            continue
        concepts.append(term)
    return concepts


def _generate_term_variants(term: str) -> List[str]:
    """Generate spelling/acronym OR-variants for a search term."""
    base = re.sub(r'\s*\([^)]*\)\s*$', '', term).strip()
    variants = {base}

    if "'" in base:
        variants.add(base.replace("'s", "s"))
        variants.add(re.sub(r'\s+', ' ', base.replace("'s", "")).strip())

    lower = base.lower()
    for phrase, acronym in _ADRD_ABBREVIATION_PAIRS:
        if lower == phrase:
            variants.add(acronym)
        elif lower == acronym.lower():
            variants.add(phrase)

    return sorted(v for v in variants if v)


def build_search_queries_v4(study_name: str, abbreviation: str, diseases: str, data_modalities: str,
                             years: float = 3, concepts_per_query: int = 5) -> List[str]:
    """Build PubMed queries batching disease/modality concepts as OR-groups per study.

    Args:
        study_name: Resource Name from the inventory.
        abbreviation: Abbreviation from the inventory.
        diseases: Diseases Included cell (semicolon/comma-delimited).
        data_modalities: Combined Coarse+Granular Data Modality string.
        years: Date range in years to search back from today.
        concepts_per_query: How many concepts to OR together per batched query.

    Returns:
        List of query strings; always includes a base name+date query (no concept restriction)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    date_range = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}"
    date_clause = f'({date_range}[Date - Publication])'

    name_terms = []
    if study_name and pd.notna(study_name):
        clean_name = re.sub(r'\s*\([^)]*\)\s*$', '', str(study_name)).strip()
        if clean_name:
            name_terms.extend(_generate_term_variants(clean_name))

    abbrev_str = str(abbreviation).strip() if pd.notna(abbreviation) else ""
    if abbrev_str and abbrev_str != str(study_name) and abbrev_str.lower() not in _NOISY_ABBREVIATIONS:
        name_terms.extend(_generate_term_variants(abbrev_str))
    elif abbrev_str and abbrev_str.lower() in _NOISY_ABBREVIATIONS:
        logger.info(f"Skipping noisy abbreviation '{abbrev_str}' (common word)")

    name_terms = sorted(set(name_terms))
    if not name_terms:
        logger.warning(f"No usable study name/abbreviation for v4 query on '{study_name}' — skipping")
        return []
    name_clause = "(" + " OR ".join(f'"{t}"[tiab]' for t in name_terms) + ")"

    concepts = []
    seen_lower = set()
    for cell in (diseases, data_modalities):
        for token in _split_concept_cell(cell):
            key = token.lower()
            if key in seen_lower:
                continue
            seen_lower.add(key)
            concepts.append(token)

    queries = [f'{name_clause} AND {date_clause}']
    for i in range(0, len(concepts), concepts_per_query):
        batch = concepts[i:i + concepts_per_query]
        variant_terms = []
        for concept in batch:
            variant_terms.extend(_generate_term_variants(concept))
        concept_clause = "(" + " OR ".join(f'"{v}"[tiab]' for v in sorted(set(variant_terms))) + ")"
        queries.append(f'{name_clause} AND {concept_clause} AND {date_clause}')

    logger.debug(f"Built {len(queries)} v4 queries for '{study_name}' ({len(concepts)} concepts in batches of {concepts_per_query})")
    return queries


def _fetch_and_parse_batch(pubmed_ids: List[str], ncbi_api_key_suffix: str) -> List[Dict]:
    """Fetch and parse PubMed article XML for a list of PMIDs, in batches of 20."""
    results = []
    batch_size = 20
    for i in range(0, len(pubmed_ids), batch_size):
        batch_ids = pubmed_ids[i:i + batch_size]
        ids_str = ",".join(batch_ids)
        fetch_url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml{ncbi_api_key_suffix}'
        fetch_response = search_pubmed_with_retry(fetch_url)
        if not fetch_response:
            continue
        try:
            root = ET.fromstring(fetch_response.text)
            articles = root.findall('.//PubmedArticle')
            for article in articles:
                article_data = extract_article_details(article)
                if article_data:
                    results.append(article_data)
        except Exception as e:
            logger.error(f"Error parsing batch: {str(e)}")
            continue
    return results


def _search_pubmed_fanout(study_name: str, abbreviation: str, diseases: str, search_data_modalities: str,
                           max_results: int, ncbi_api_key_suffix: str, years: float) -> List[Dict]:
    """v4: issue one esearch per (name, concept) query and union the resulting PMIDs.

    See build_search_queries_v4 for why this fans out instead of ANDing
    every facet into a single query.
    """
    queries = build_search_queries_v4(study_name, abbreviation, diseases, search_data_modalities, years=years)
    if not queries:
        return []

    base_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    seen_ids = {}
    for query in queries:
        encoded_query = urllib.parse.quote(query, safe='')
        search_url = f'{base_url}?db=pubmed&term={encoded_query}&retmax={max_results}&retmode=json{ncbi_api_key_suffix}'
        logger.info(f"[v4] Sub-query: {query[:120]}..." if len(query) > 120 else f"[v4] Sub-query: {query}")

        response = search_pubmed_with_retry(search_url)
        if not response:
            continue
        try:
            data = response.json()
            ids = data.get('esearchresult', {}).get('idlist', [])
            logger.info(f"[v4] Sub-query returned {len(ids)} PMIDs")
            for pid in ids:
                seen_ids.setdefault(pid, None)
        except Exception as e:
            logger.error(f"[v4] Error processing sub-query results: {str(e)}")
            continue

    pubmed_ids = list(seen_ids.keys())
    logger.info(f"[v4] {len(queries)} sub-queries -> {len(pubmed_ids)} unique PMIDs for '{study_name}'")

    if len(pubmed_ids) > max_results:
        logger.warning(f"[v4] Union of {len(pubmed_ids)} PMIDs exceeds max_results={max_results}; truncating (dropped {len(pubmed_ids) - max_results})")
        pubmed_ids = pubmed_ids[:max_results]

    if not pubmed_ids:
        logger.info("[v4] No results found")
        return []

    results = _fetch_and_parse_batch(pubmed_ids, ncbi_api_key_suffix)
    for r in results:
        r.update({
            "Resource Name": study_name,
            "Abbreviation": abbreviation,
            "Diseases Included": diseases,
            "Data Modalities": search_data_modalities,
        })

    logger.info(f"[v4] Successfully processed {len(results)} articles")
    return results


def search_pubmed(study_name: str, abbreviation: str, diseases: str, search_data_modalities: str, max_results: int = 100, ncbi_api_key_suffix: str = "", query_method: str = "original", years: float = 3) -> List[Dict]:
    """Search PubMed for articles related to the study"""
    if query_method == "v4":
        return _search_pubmed_fanout(study_name, abbreviation, diseases, search_data_modalities,
                                      max_results, ncbi_api_key_suffix, years)

    # Build search query
    if query_method == "v2":
        query = build_search_query_v2(study_name, abbreviation, diseases, search_data_modalities, years=years)
    elif query_method == "v3":
        query = build_search_query_v3(study_name, abbreviation, diseases, search_data_modalities, years=years)
    else:
        query = build_search_query(study_name, abbreviation, diseases, search_data_modalities, years=years)

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

        results = _fetch_and_parse_batch(pubmed_ids, ncbi_api_key_suffix)
        for r in results:
            r.update({
                "Resource Name": study_name,
                "Abbreviation": abbreviation,
                "Diseases Included": diseases,
                "Data Modalities": search_data_modalities,
            })

        logger.info(f"Successfully processed {len(results)} articles")
        return results

    except Exception as e:
        logger.error(f"Error processing search results: {str(e)}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Scrape PubMed for publications related to neurodegenerative disease studies')
    parser.add_argument('--input', '-i', default='../tables/resources-inventory-June_20_2025.tab',
                       help='Input TSV file with study inventory (default: ../tables/resources-inventory-June_20_2025.tab)')
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
    parser.add_argument('--query-method', choices=['original', 'v2', 'v3', 'v4'], default='original',
                       help='Query construction method: "original" uses [All Fields] with disease+modality '
                            'terms; "v2" uses [tiab] with no disease/modality terms; '
                            '"v3" uses [tiab] + disease + modality terms (v2 precision + original recall); '
                            '"v4" fans out one esearch per disease/modality concept and unions PMIDs, instead of ANDing every facet;'
                            '(default: original)')
    parser.add_argument('--years', type=float, default=3,
                       help='Date range in years to search back from today (default: 3, use 0.02 for ~7 days)')

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
        logger.info(f"Loaded {len(studies_df)} studies from {args.input}. Columns: {', '.join(studies_df.columns)}")
    except Exception as e:
        logger.error(f"Error reading dataset inventory: {str(e)}")
        sys.exit(1)

    # Initialize results list
    all_results = []

    # Process each study
    for idx, row in studies_df.iterrows():
        study_name = row.get("Resource Name", "")
        abbreviation = row.get("Abbreviation", "")
        diseases = row.get("Diseases Included", "")
        coarse = [m.strip() for m in str(row.get("Coarse Data Modality", "") or "").split(",") if m.strip()]
        logger.info(f"Processing study: {study_name} ({abbreviation}), diseases: {diseases}, coarse modalities: {coarse}")
        granular = [m.strip() for m in str(row.get("Granular Data Modality", "") or "").split(";") if m.strip()]
        search_data_modalities = ", ".join(coarse + granular)

        logger.info(f"[{idx+1}/{len(studies_df)}] Searching for publications: {study_name} ({abbreviation})")
        results = search_pubmed(study_name, abbreviation, diseases, search_data_modalities, args.max_results, ncbi_api_key_suffix, args.query_method, args.years)
        # For each result, the Coarse and Granular Data Modalities should be included from the from the study metadata
        results = [{**r, "Coarse Data Modality": row.get("Coarse Data Modality", ""), "Granular Data Modality": row.get("Granular Data Modality", "")} for r in results]
        all_results.extend(results)

    # Create and save results dataframe
    if all_results:
        logger.debug(f"Creating dataframe from {len(all_results)} total results")
        # Reorder columns to match previous format exactly
        columns_order = [
            "PMID",
            "Resource Name",
            "Abbreviation",
            "Diseases Included",
            "Coarse Data Modality",
            "Granular Data Modality",
            "PubMed Central Link",
            "Authors",
            "Affiliations",
            "Title",
            "Abstract",
            "Keywords",
            "Publication Date",
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
