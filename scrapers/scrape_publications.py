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
import csv
import io
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import urllib.parse
from typing import List, Dict, Optional
import argparse
import logging
from logging_config import setup_logger, get_default_log_file
from dotenv import load_dotenv
from anthropic import Anthropic

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


def _load_synonym_lookup() -> dict:
    """Load tables/{disease,modality}_synonyms.json into a lowercase-term -> all-variants-in-its-group lookup.

    Replaces the old 19-pair hardcoded _ADRD_ABBREVIATION_PAIRS table, which only
    covered ~1% of the catalog's actual disease/modality vocabulary (see
    docs/plans/paperclip/experiments — 49/726 concept tokens got any variant at
    all under the old table). These files are built from and verified against
    every real Diseases/Data-Modality value in the catalog (no fabricated entries).
    """
    lookup = {}
    tables_dir = Path(__file__).parent.parent / "tables"
    for fname in ("disease_synonyms.json", "modality_synonyms.json"):
        path = tables_dir / fname
        try:
            with open(path) as f:
                groups = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load {path}: {e}")
            continue
        for g in groups:
            all_forms = sorted(set(g["synonyms"]) | {g["canonical"]})
            for form in all_forms:
                lookup[form.lower()] = all_forms
    return lookup


_SYNONYM_LOOKUP = _load_synonym_lookup()

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
    if lower in _SYNONYM_LOOKUP:
        variants.update(_SYNONYM_LOOKUP[lower])

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
        Concept-batch (synonym-expanded) queries first, unrestricted base name+date
        query last — order matters for attribution downstream (see _search_pubmed_fanout).
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

    queries = []
    for i in range(0, len(concepts), concepts_per_query):
        batch = concepts[i:i + concepts_per_query]
        variant_terms = []
        for concept in batch:
            variant_terms.extend(_generate_term_variants(concept))
        concept_clause = "(" + " OR ".join(f'"{v}"[tiab]' for v in sorted(set(variant_terms))) + ")"
        queries.append(f'{name_clause} AND {concept_clause} AND {date_clause}')
    queries.append(f'{name_clause} AND {date_clause}')  # base query last — see docstring

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
                           max_results: int, ncbi_api_key_suffix: str, years: float, target_db: str = "pubmed") -> List[Dict]:
    """v4: one esearch per disease/modality concept batch (synonym-expanded); the
    unrestricted base name+date query only runs as a fallback if every concept
    batch finds nothing.

    See build_search_queries_v4 for why this fans out instead of ANDing every
    facet into a single query.
    """
    queries = build_search_queries_v4(study_name, abbreviation, diseases, search_data_modalities, years=years)
    if not queries:
        return []

    # queries = [concept-batch, concept-batch, ..., base (unrestricted name+date, always last)].
    # Concept batches run first; the base query only runs as a fallback if they
    # collectively find nothing. Unioning the base query unconditionally (the old
    # behavior) made it a strict superset of every concept batch, so the
    # concept/synonym-expanded queries could never make v4's actual results differ
    # from an unrestricted name-only search — confirmed empirically (0/3642 rows
    # ever attributed to a concept batch across the full catalog). This makes v4 a
    # real test of disease/modality-restricted, synonym-expanded search instead of
    # "v2 plus an always-redundant safety net" — it can now find fewer results than
    # an unrestricted search would for resources with good concept-batch hits, not
    # just the same-or-more.
    concept_queries, base_query = queries[:-1], queries[-1]

    db = "pmc" if target_db == "pmc" else "pubmed"
    base_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'

    def run_query(query):
        found = {}
        encoded_query = urllib.parse.quote(query, safe='')
        search_url = f'{base_url}?db={db}&term={encoded_query}&retmax={max_results}&retmode=json{ncbi_api_key_suffix}'
        logger.info(f"[v4] Sub-query: {query[:120]}..." if len(query) > 120 else f"[v4] Sub-query: {query}")
        response = search_pubmed_with_retry(search_url)
        if not response:
            return found
        try:
            ids = response.json().get('esearchresult', {}).get('idlist', [])
            logger.info(f"[v4] Sub-query returned {len(ids)} {db} IDs")
            for pid in ids:
                found.setdefault(pid, query)
        except Exception as e:
            logger.error(f"[v4] Error processing sub-query results: {str(e)}")
        return found

    seen_ids = {}
    for query in concept_queries:
        seen_ids.update({k: v for k, v in run_query(query).items() if k not in seen_ids})

    if seen_ids:
        logger.info(f"[v4] {len(concept_queries)} concept-batch queries -> {len(seen_ids)} unique {db} IDs for '{study_name}' (base query skipped)")
    else:
        logger.info(f"[v4] Concept-batch queries found nothing for '{study_name}', falling back to base query")
        seen_ids = run_query(base_query)

    result_ids = list(seen_ids.keys())
    logger.info(f"[v4] {len(result_ids)} unique {db} IDs for '{study_name}'")

    if len(result_ids) > max_results:
        logger.warning(f"[v4] Union of {len(result_ids)} {db} IDs exceeds max_results={max_results}; truncating (dropped {len(result_ids) - max_results})")
        result_ids = result_ids[:max_results]

    if not result_ids:
        logger.info("[v4] No results found")
        return []

    if db == "pmc":
        results = _fetch_pmc_summaries(result_ids, ncbi_api_key_suffix)
        id_field = "PMCID"
    else:
        results = _fetch_and_parse_batch(result_ids, ncbi_api_key_suffix)
        id_field = "PMID"

    for r in results:
        r.update({
            "Resource Name": study_name,
            "Abbreviation": abbreviation,
            "Diseases Included": diseases,
            "Data Modalities": search_data_modalities,
            "Fetched With": seen_ids.get(r.get(id_field), ""),
        })

    logger.info(f"[v4] Successfully processed {len(results)} articles")
    return results


# ---------------------------------------------------------------------------
# query_method="paperclip"
# `paperclip` CLI as subprocess tools inside a manual Anthropic tool-use loop

CLAUDE_MODEL = "claude-sonnet-5"  # shared by the paperclip method and the v5 PMC query-generation step

# Structural result-line patterns only, not a blind substring scan — a bare
# substring scan mis-attributes papers whose excerpt text happens to mention
# other papers' IDs in a citation list.
_SEARCH_RESULT_LINE_RE = re.compile(r'^\s*([A-Za-z0-9_.\-]+)\s+[·|]\s')
_GREP_RESULT_LINE_RE = re.compile(r'^\s*(?:\[.*?\]\s*)?([A-Za-z0-9_.\-]+)/\s+\(\d+\s+match')

PAPERCLIP_TOOLS = [
    {
        "name": "paperclip_search",
        "description": "Semantic + keyword search across PMC/bioRxiv/medRxiv/arXiv full text (full corpus, not restricted to already-added papers).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "exact": {"type": "boolean", "description": "exact phrase match (-e)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "paperclip_grep",
        "description": "Literal/regex full-corpus grep across all papers' full text. Escalate to this whenever a search on an exact string, accession ID, or dataset slug returns nothing — this was the single highest-value move in prior runs (semantic search on an exact string often finds nothing that grep on the same string finds immediately).",
        "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]},
    },
    {
        "name": "paperclip_add_claim",
        "description": "Add a candidate paper with a verifiable claim to check against its full text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "claim": {"type": "string"},
                "lines": {"type": "string", "description": "optional line-range hint, e.g. L45-L52"},
            },
            "required": ["doc_id", "claim"],
        },
    },
    {
        "name": "finish_investigation",
        "description": "Call when done searching (found candidates or exhausted reasonable queries). Triggers commit + verification of all added claims.",
        "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
    },
]


def _paperclip_slug(text) -> str:
    text = "" if text is None or isinstance(text, float) else str(text)
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:40] or "resource"


def _paperclip_cli_raw(*args: str, timeout: int = 90) -> str:
    """Run `paperclip <args>` with no --repo scoping (only for `repo init`)."""
    cmd = ["paperclip", *args]
    logger.debug(f"[paperclip] $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired:
        logger.warning(f"[paperclip] command timed out after {timeout}s: {' '.join(cmd)}")
        return "ERROR: command timed out"
    except Exception as e:
        logger.warning(f"[paperclip] command failed: {' '.join(cmd)}: {e}")
        return f"ERROR: {e}"


def _paperclip_cli(repo_name: str, *args: str, timeout: int = 90) -> str:
    """Run `paperclip --repo <repo_name> <args>`, return combined stdout+stderr."""
    return _paperclip_cli_raw("--repo", repo_name, *args, timeout=timeout)


def _extract_result_ids(output: str) -> set:
    ids = set()
    for line in output.splitlines():
        m = _SEARCH_RESULT_LINE_RE.match(line) or _GREP_RESULT_LINE_RE.match(line)
        if m:
            ids.add(m.group(1))
    return ids


def _search_paperclip(study_name: str, abbreviation: str, diseases: str, search_data_modalities: str,
                       years: float = 3, max_turns: int = 35, anthropic_key: Optional[str] = None,
                       sources: str = "pmc,biorxiv,medrxiv,arxiv,trials", skip_verify: bool = False) -> List[Dict]:
    """Full-text fallback search via the `paperclip` CLI, for resources with zero PubMed title/abstract hits.

    Args:
        years: Unused — kept for signature parity with search_pubmed's other methods.
        sources: Comma-separated paperclip -s/--source value(s), e.g. "pmc", "fda,trials/us".
        skip_verify: If True, commit with --no-verify and return all candidates.

    Returns:
        Result dicts filtered to Verification Status == "OK".
    """
    key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        logger.error("[paperclip] ANTHROPIC_API_KEY not set; skipping paperclip search")
        return []
    if not os.getenv("PAPERCLIP_API_KEY"):
        logger.warning("[paperclip] PAPERCLIP_API_KEY not set; paperclip CLI calls will likely fail")

    client = Anthropic(api_key=key)
    repo_name = f"paperclip-{_paperclip_slug(abbreviation or study_name)}"

    init_out = _paperclip_cli_raw("repo", "init", repo_name, f"Fallback search: {study_name}"[:200])
    logger.debug(f"[paperclip] repo init {repo_name}: {init_out[:200]}")

    system_prompt = f"""You are investigating whether any published paper (source(s): {sources}) describes or uses data from this catalog resource, which has zero PubMed title/abstract hits under any query-construction method tried so far.

Resource Name: {study_name}
Abbreviation: {abbreviation}
Diseases: {diseases}
Data modality: {search_data_modalities}

## Search strategy
Start with `paperclip_search` on the resource name/abbreviation and on topical terms built from the diseases/modality fields. If a search on an exact string, accession ID, or dataset slug returns nothing, escalate to `paperclip_grep` on that same exact string — corpus-wide literal grep frequently finds real matches that semantic search on the identical string misses.

Do NOT phrase claims around the resource's catalog display name or abbreviation as a literal string if it looks like a catalog-invented label unlikely to appear verbatim in any paper (compound/constructed names, not names the field itself uses). Instead, break it into the real, independently-searchable entities it is built from (gene/protein, perturbation, assay/technique, tissue/cell type, cohort/consortium name, institution) using the diseases/modality fields as hints, and phrase claims around a specific verifiable fact the paper actually states — an accession ID, dataset slug, sample size, or cohort name — not "this paper describes/uses data from '<resource name>'". (If the abbreviation is itself a real term the field uses — e.g. a well-known public trial name — searching and claiming on it directly is fine; use judgment.)

## Verification
Use `paperclip_add_claim` for each real candidate. Call `finish_investigation` when done — this triggers `repo commit` + verification. Do not assert a candidate is confirmed yourself; the final verification_status is read from paperclip's own `repo claims` after commit, not your judgment from reading the paper.

## Budget
Hard limit: {max_turns} tool calls total (every search/grep/add counts, not just searches). After each batch of tool results you'll see how many you've used and how many remain — pace yourself against it. Don't add a duplicate or marginal candidate just because you have calls to spare; add it only if it's a real, distinct lead. If you're near the limit without having called finish_investigation, call it now with whatever candidates you have so verification still runs.
"""

    messages = [{"role": "user", "content": "Begin the investigation."}]
    command_ledger: List[tuple] = []  # (command_str, set_of_ids), most recent last
    added_claims: List[Dict] = []     # {doc_id, claim, found_via_command}
    finished = False
    turns = 0
    tool_calls_used = 0  # what max_turns actually budgets — every dispatched tool_use block, not API round trips

    while tool_calls_used < max_turns and not finished:
        turns += 1
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL, max_tokens=2000, system=system_prompt,
                messages=messages, tools=PAPERCLIP_TOOLS,
            )
        except Exception as e:
            logger.error(f"[paperclip] Anthropic API call failed for '{study_name}': {e}", exc_info=True)
            break

        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_calls_used += 1
            if block.name == "paperclip_search":
                args = ["search", "-s", sources]
                if block.input.get("exact"):
                    args.append("-e")
                args.append(block.input["query"])
                out = _paperclip_cli(repo_name, *args)
                command_ledger.append((f"paperclip search -s {sources} {'-e ' if block.input.get('exact') else ''}\"{block.input['query']}\"", _extract_result_ids(out)))
            elif block.name == "paperclip_grep":
                out = _paperclip_cli(repo_name, "grep", block.input["pattern"], "/papers/")
                command_ledger.append((f'paperclip grep "{block.input["pattern"]}" /papers/', _extract_result_ids(out)))
            elif block.name == "paperclip_add_claim":
                doc_id = block.input["doc_id"]
                add_args = ["repo", "add", doc_id, block.input["claim"]]
                if block.input.get("lines"):
                    add_args += ["--lines", block.input["lines"]]
                out = _paperclip_cli(repo_name, *add_args)
                found_via = "(not resolved)"
                for cmd_str, ids in reversed(command_ledger):
                    if doc_id in ids:
                        found_via = cmd_str
                        break
                added_claims.append({"doc_id": doc_id, "claim": block.input["claim"], "found_via_command": found_via})
            elif block.name == "finish_investigation":
                finished = True
                out = "Investigation marked finished; committing and verifying."
            else:
                out = f"Unknown tool: {block.name}"
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": out[:4000]})

        if not finished:
            remaining = max_turns - tool_calls_used
            tool_results.append({"type": "text", "text": f"[Budget status: {tool_calls_used}/{max_turns} tool calls used, {remaining} remaining]"})
        messages.append({"role": "user", "content": tool_results})

    if tool_calls_used >= max_turns and not finished:
        logger.warning(f"[paperclip] '{study_name}' hit the {max_turns}-tool-call budget before finish_investigation ({turns} turns)")

    if not added_claims:
        logger.info(f"[paperclip] '{study_name}': no candidates found ({turns} turns, {tool_calls_used} tool calls)")
        return []

    commit_args = ["repo", "commit", "-m", f"{'Candidates (unverified)' if skip_verify else 'Verify candidates'} for {study_name}"[:200]]
    if skip_verify:
        commit_args.append("--no-verify")
    commit_out = _paperclip_cli(repo_name, *commit_args)
    logger.debug(f"[paperclip] commit {repo_name}: {commit_out[:300]}")

    if skip_verify:
        verified_map = {}
    else:
        claims_out = _paperclip_cli(repo_name, "repo", "claims")
        try:
            claims = json.loads(claims_out)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[paperclip] '{study_name}': repo claims returned non-JSON output, treating as no verified claims: {claims_out[:200]}")
            claims = []
        verified_map = {c.get("paperclip_doc_id"): c.get("verified") for c in claims}

    export_out = _paperclip_cli(repo_name, "repo", "export", "csv")
    try:
        papers = list(csv.DictReader(io.StringIO(export_out)))
    except Exception as e:
        logger.warning(f"[paperclip] '{study_name}': repo export csv failed to parse: {e}")
        papers = []
    paper_by_id = {p["paper_id"]: p for p in papers}
    claim_by_doc = {c["doc_id"]: c for c in added_claims}

    def build_row(doc_id, status):
        p = paper_by_id.get(doc_id, {})
        c = claim_by_doc.get(doc_id, {})
        return {
            "PMID": "",
            "DOI": p.get("doi", ""),
            "Resource Name": study_name,
            "Abbreviation": abbreviation,
            "Diseases Included": diseases,
            "Title": p.get("title", ""),
            "Abstract": "",
            "Authors": p.get("authors", ""),
            "Affiliations": "",
            "Keywords": "",
            "Publication Date": p.get("year", ""),
            "PubMed Central Link": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{doc_id}/" if doc_id.startswith("PMC") else "",
            "Verification Status": status,
            "Claim Text": c.get("claim", p.get("annotations", "")),
            "Rationale": c.get("found_via_command", ""),
            "Fetched With": f"paperclip:{c.get('found_via_command', repo_name)}",
            "Paperclip Repo": repo_name,
        }

    results = []
    if skip_verify:
        for c in added_claims:
            results.append(build_row(c["doc_id"], "PENDING"))
        logger.info(f"[paperclip] '{study_name}': {len(added_claims)} candidates added, verification skipped ({turns} turns, {tool_calls_used} tool calls, repo={repo_name})")
        return results

    n_ok = n_x = n_uncommitted = 0
    for doc_id, verified in verified_map.items():
        if verified is not True:
            n_x += 1 if verified is False else 0
            n_uncommitted += 1 if verified is None else 0
            continue
        n_ok += 1
        results.append(build_row(doc_id, "OK"))

    logger.info(f"[paperclip] '{study_name}': {len(added_claims)} candidates added, {n_ok} verified OK, {n_x} X, {n_uncommitted} not committed ({turns} turns, {tool_calls_used} tool calls, repo={repo_name})")
    return results


# ---------------------------------------------------------------------------
# query_method="v5": Claude generates 30 full-text search queries per
# resource, run against NCBI PMC (db=pmc, full-text indexed).
# ---------------------------------------------------------------------------

GENERATE_QUERIES_TOOL = {
    "name": "return_queries",
    "description": "Return the generated list of PMC full-text search queries.",
    "input_schema": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Full-text search query strings for NCBI PMC (db=pmc). No field tags needed — PMC's default search already covers full text.",
            },
        },
        "required": ["queries"],
    },
}


def _generate_pmc_queries(study_name: str, abbreviation: str, diseases: str, search_data_modalities: str,
                           max_queries: int = 10, anthropic_key: Optional[str] = None) -> List[str]:
    """Use Claude to generate precision-focused full-text search queries for one catalog resource.

    Returns:
        List of query strings (empty list on failure).
    """
    key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        logger.error("[v5] ANTHROPIC_API_KEY not set; skipping v5 query generation")
        return []

    client = Anthropic(api_key=key)
    prompt = f"""Generate full-text search queries (up to {max_queries}) to find PMC (PubMed Central) papers that describe or use data from this catalog resource:

Resource Name: {study_name}
Abbreviation: {abbreviation}
Diseases: {diseases}
Data modality: {search_data_modalities}

These queries run against PMC's full-text index — the entire paper, not just title/abstract — so they can find mentions anywhere in the text, not any particular section.

Precision matters more than recall here: there is no downstream verification step, so whatever a query returns becomes a result directly. Each query must be specific enough that a match is actually likely to be about this resource, not just topically related — avoid single generic disease/modality terms alone, which return large volumes of loosely-related noise. Prefer quoted exact phrases and specific term combinations over broad keyword-only queries.

Use your judgment on how many queries this resource actually needs — likely well under {max_queries}. Generate more only if the resource genuinely has multiple distinct real, independently-searchable identifiers worth querying separately (e.g. the exact name/abbreviation as a phrase, and separately its real underlying entities — gene/protein, technique/assay, cohort/consortium name — when the catalog display name is an invented compound label unlikely to appear verbatim in any paper). Do not pad the list with near-duplicate rewordings or overly broad queries just to generate more of them.

Call return_queries with the query strings."""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
            tools=[GENERATE_QUERIES_TOOL],
            tool_choice={"type": "tool", "name": "return_queries"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "return_queries":
                queries = block.input.get("queries", [])
                logger.info(f"[v5] Generated {len(queries)} queries for '{study_name}'")
                return queries[:max_queries]
    except Exception as e:
        logger.error(f"[v5] Query generation failed for '{study_name}': {e}", exc_info=True)
    return []


def _fetch_pmc_summaries(pmcids: List[str], ncbi_api_key_suffix: str) -> List[Dict]:
    """Fetch article metadata directly from PMC via esummary — no PMID required."""
    results = []
    batch_size = 200
    for i in range(0, len(pmcids), batch_size):
        batch = pmcids[i:i + batch_size]
        ids_str = ",".join(batch)
        url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id={ids_str}&retmode=json{ncbi_api_key_suffix}'
        response = search_pubmed_with_retry(url)
        if not response:
            continue
        try:
            result = response.json().get("result", {})
            for uid in result.get("uids", []):
                doc = result.get(uid, {})
                article_ids = {a.get("idtype"): a.get("value") for a in doc.get("articleids", [])}
                authors = "; ".join(a.get("name", "") for a in doc.get("authors", []) if a.get("authtype") == "Author")
                results.append({
                    "PMID": article_ids.get("pmid", ""),
                    "DOI": article_ids.get("doi", ""),
                    "PMCID": uid,
                    "Title": clean_text(doc.get("title", "")),
                    "Abstract": "",
                    "Authors": authors,
                    "Affiliations": "",
                    "Keywords": "",
                    "Publication Date": doc.get("pubdate", ""),
                    "PubMed Central Link": f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{uid}/",
                })
        except Exception as e:
            logger.warning(f"[pmc] esummary parse failed for a batch: {e}")
    return results


def _search_pmc_v5(study_name: str, abbreviation: str, diseases: str, search_data_modalities: str,
                    max_results: int, ncbi_api_key_suffix: str, anthropic_key: Optional[str] = None,
                    years: float = 3) -> List[Dict]:
    """v5: Claude-generated queries fanned out against PMC full text."""
    queries = _generate_pmc_queries(study_name, abbreviation, diseases, search_data_modalities,
                                     anthropic_key=anthropic_key)
    if not queries:
        return []

    # Same date window as v1-v4 (via mindate/maxdate params, applied uniformly
    # regardless of query text — comparable across query methods).
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    date_params = f"&datetype=pdat&mindate={start_date.strftime('%Y/%m/%d')}&maxdate={end_date.strftime('%Y/%m/%d')}"

    base_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    seen_pmcids = {}
    for query in queries:
        encoded_query = urllib.parse.quote(query, safe='')
        search_url = f'{base_url}?db=pmc&term={encoded_query}&retmax={max_results}&retmode=json{date_params}{ncbi_api_key_suffix}'
        logger.info(f"[v5] Sub-query: {query[:120]}..." if len(query) > 120 else f"[v5] Sub-query: {query}")

        response = search_pubmed_with_retry(search_url)
        if not response:
            continue
        try:
            data = response.json()
            ids = data.get('esearchresult', {}).get('idlist', [])
            logger.info(f"[v5] Sub-query returned {len(ids)} PMC IDs")
            for pmcid in ids:
                seen_pmcids.setdefault(pmcid, query)
        except Exception as e:
            logger.error(f"[v5] Error processing sub-query results: {e}")
            continue

    if not seen_pmcids:
        logger.info(f"[v5] '{study_name}': no PMC hits across {len(queries)} queries")
        return []

    logger.info(f"[v5] {len(queries)} queries -> {len(seen_pmcids)} unique PMC IDs for '{study_name}'")
    pmcids = list(seen_pmcids.keys())
    if len(pmcids) > max_results:
        logger.warning(f"[v5] {len(pmcids)} PMC IDs exceeds max_results={max_results}; truncating (dropped {len(pmcids) - max_results})")
        pmcids = pmcids[:max_results]

    results = _fetch_pmc_summaries(pmcids, ncbi_api_key_suffix)
    for r in results:
        r.update({
            "Resource Name": study_name,
            "Abbreviation": abbreviation,
            "Diseases Included": diseases,
            "Fetched With": f"v5:{seen_pmcids.get(r.get('PMCID'), '')}",
        })

    logger.info(f"[v5] Successfully processed {len(results)} articles for '{study_name}'")
    return results


def search_pubmed(study_name: str, abbreviation: str, diseases: str, search_data_modalities: str, max_results: int = 100, ncbi_api_key_suffix: str = "", query_method: str = "original", years: float = 3, paperclip_max_turns: int = 35, anthropic_key: Optional[str] = None, target_db: str = "pubmed", paperclip_sources: str = "pmc,biorxiv,medrxiv,arxiv,trials", paperclip_skip_verify: bool = False) -> List[Dict]:
    """Search PubMed for articles related to the study"""
    if query_method == "paperclip":
        return _search_paperclip(study_name, abbreviation, diseases, search_data_modalities,
                                  years, paperclip_max_turns, anthropic_key, paperclip_sources, paperclip_skip_verify)

    if query_method == "v5":
        return _search_pmc_v5(study_name, abbreviation, diseases, search_data_modalities,
                               max_results, ncbi_api_key_suffix, anthropic_key, years)

    if query_method == "v4":
        return _search_pubmed_fanout(study_name, abbreviation, diseases, search_data_modalities,
                                      max_results, ncbi_api_key_suffix, years, target_db)

    # Build search query
    if query_method == "v2":
        query = build_search_query_v2(study_name, abbreviation, diseases, search_data_modalities, years=years)
    elif query_method == "v3":
        query = build_search_query_v3(study_name, abbreviation, diseases, search_data_modalities, years=years)
    else:
        query = build_search_query(study_name, abbreviation, diseases, search_data_modalities, years=years)

    # Search PubMed or PMC (URL-encode the query to handle &, parentheses, etc.)
    db = target_db
    base_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    encoded_query = urllib.parse.quote(query, safe='')
    search_url = f'{base_url}?db={db}&term={encoded_query}&retmax={max_results}&retmode=json{ncbi_api_key_suffix}'

    logger.info(f"Query ({db}): {query[:100]}..." if len(query) > 100 else f"Query ({db}): {query}")
    logger.debug(f"Query: {query}...")
    logger.debug(f"API key in URL: {'YES' if ncbi_api_key_suffix else 'NO'}")

    logger.debug(f"Max results requested: {max_results}")

    response = search_pubmed_with_retry(search_url)
    if not response:
        return []

    try:
        data = response.json()
        logger.debug(f"Successfully parsed JSON response")
        result_ids = data.get('esearchresult', {}).get('idlist', [])
        logger.debug(f"Extracted {len(result_ids)} {db} IDs")

        if not result_ids:
            logger.info("No results found")
            return []

        logger.info(f"Found {len(result_ids)} articles")

        if db == "pmc":
            results = _fetch_pmc_summaries(result_ids, ncbi_api_key_suffix)
        else:
            results = _fetch_and_parse_batch(result_ids, ncbi_api_key_suffix)

        for r in results:
            r.update({
                "Resource Name": study_name,
                "Abbreviation": abbreviation,
                "Diseases Included": diseases,
                "Data Modalities": search_data_modalities,
                "Fetched With": f"{query} [{db}]" if db == "pmc" else query,
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
    parser.add_argument('--query-method', choices=['original', 'v2', 'v3', 'v4', 'v5', 'paperclip'], default='original',
                       help='Query construction method: "original" uses [All Fields] with disease+modality '
                            'terms; "v2" uses [tiab] with no disease/modality terms; '
                            '"v3" uses [tiab] + disease + modality terms (v2 precision + original recall); '
                            '"v4" fans out one esearch per disease/modality concept and unions PMIDs, instead of ANDing every facet; '
                            '"v5" has Claude generate 30 full-text queries per resource and searches NCBI PMC (db=pmc, full-text '
                            'indexed, unlike db=pubmed) instead of PubMed title/abstract, converting PMC IDs back to PMIDs; '
                            '"paperclip" runs a full-text search (PMC/bioRxiv/medRxiv/arXiv) via  the paperclip CLI in an LLM tool-use loop'
                        )
    parser.add_argument('--years', type=float, default=3,
                       help='Date range in years to search back from today (default: 3, use 0.02 for ~7 days). Unused by --query-method paperclip (full-text search has no date restriction).')
    parser.add_argument('--paperclip-max-turns', type=int, default=35,
                       help='Tool-call budget per resource for --query-method paperclip (default: 35)')
    parser.add_argument('--paperclip-max-workers', type=int, default=None,
                       help='Concurrent resource investigations for --query-method paperclip (default: min(16, cpu_count-2), '
                            'matching the concurrency cap used for the strategy comparison in docs/plans/paperclip_variant_comparison_results.md)')
    parser.add_argument('--paperclip-sources', default='pmc,biorxiv,medrxiv,arxiv,trials',
                       help='Comma-separated paperclip -s/--source value(s) for --query-method paperclip (default: '
                            'pmc,biorxiv,medrxiv,arxiv,trials). Other paperclip sources: fda, fda/jp, fda/eu, trials/us, '
                            'trials/eu, trials/jp, trials/cn, patents, abstracts, proteins.')
    parser.add_argument('--paperclip-skip-verify', action='store_true',
                       help='For --query-method paperclip: commit with --no-verify and return all candidates as '
                            'PENDING instead of verifying and filtering to OK. Separates discovery from validation — '
                            'run validate_with_paperclip.py against the output afterward.')
    parser.add_argument('--anthropic-key', default=None,
                       help='Anthropic API key for --query-method paperclip (default: from ANTHROPIC_API_KEY env var)')
    parser.add_argument('--target-db', choices=['pubmed', 'pmc'], default='pubmed',
                       help='Database to search for --query-method original/v2/v3/v4: "pubmed" (title/abstract/MeSH-only '
                            'index, default) or "pmc" (full-text index — same query text, broader corpus). Has no effect '
                            'on v5 (already PMC-only) or paperclip.')

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
    logger.info(f"Query method: {args.query_method}" + (f" (target db: {args.target_db})" if args.query_method in ("original", "v2", "v3") else ""))
    logger.debug(f"Input file: {args.input}")

    # Read the dataset inventory
    try:
        studies_df = pd.read_csv(args.input, sep="\t", dtype=str).fillna("")
        logger.info(f"Loaded {len(studies_df)} studies from {args.input}. Columns: {', '.join(studies_df.columns)}")
    except Exception as e:
        logger.error(f"Error reading dataset inventory: {str(e)}")
        sys.exit(1)

    def process_row(idx, row):
        study_name = row.get("Resource Name", "")
        abbreviation = row.get("Abbreviation", "")
        diseases = row.get("Diseases Included", "")
        coarse = [m.strip() for m in str(row.get("Coarse Data Modality", "") or "").split(",") if m.strip()]
        logger.info(f"Processing study: {study_name} ({abbreviation}), diseases: {diseases}, coarse modalities: {coarse}")
        granular = [m.strip() for m in str(row.get("Granular Data Modality", "") or "").split(";") if m.strip()]
        search_data_modalities = ", ".join(coarse + granular)

        logger.info(f"[{idx+1}/{len(studies_df)}] Searching for publications: {study_name} ({abbreviation})")
        results = search_pubmed(study_name, abbreviation, diseases, search_data_modalities, args.max_results, ncbi_api_key_suffix, args.query_method, args.years, args.paperclip_max_turns, args.anthropic_key, args.target_db, args.paperclip_sources, args.paperclip_skip_verify)
        # For each result, the Coarse and Granular Data Modalities should be included from the from the study metadata
        return [{**r, "Coarse Data Modality": row.get("Coarse Data Modality", ""), "Granular Data Modality": row.get("Granular Data Modality", "")} for r in results]

    # Initialize results list
    all_results = []

    columns_order = [
        "PMID",
        "DOI",
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
        "Verification Status",
        "Claim Text",
        "Rationale",
        "Fetched With",
        "Paperclip Repo",
    ]

    if args.output:
        output_filename = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = os.path.join(os.path.dirname(__file__), "../tables", f"pubmed_central_{timestamp}.tsv")

    if args.query_method == "paperclip":
        # Each resource's investigation is a long, independent, I/O-bound
        # (network-call-heavy) loop — run them concurrently rather than one
        # at a time, mirroring the concurrency the strategy comparison used
        # (docs/plans/paperclip_variant_comparison_results.md ran up to 16
        # investigations in parallel; a fully sequential loop here would
        # make a full-catalog run take hours instead of minutes).
        #
        # Written incrementally, one resource at a time as it finishes, not
        # only at the very end — a run over the full catalog takes long enough
        # that losing everything to a crash partway through would be costly.
        max_workers = args.paperclip_max_workers or min(16, max(1, (os.cpu_count() or 4) - 2))
        logger.info(f"[paperclip] Running {len(studies_df)} resource investigations with {max_workers} concurrent workers")
        logger.info(f"[paperclip] Writing results incrementally to {output_filename} as each resource finishes")

        completed = 0
        with open(output_filename, "w", newline="") as out_f:
            writer = csv.DictWriter(out_f, fieldnames=columns_order, delimiter="\t", extrasaction="ignore", restval="")
            writer.writeheader()
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_row, idx, row): idx for idx, row in studies_df.iterrows()}
                for future in as_completed(futures):
                    idx = futures[future]
                    completed += 1
                    try:
                        rows = future.result()
                    except Exception as e:
                        logger.error(f"[paperclip] Resource at row {idx} failed: {e}", exc_info=True)
                        continue
                    all_results.extend(rows)
                    for r in rows:
                        writer.writerow(r)
                    out_f.flush()
                    logger.info(f"[paperclip] [{completed}/{len(studies_df)}] row {idx}: {len(rows)} result(s) written ({len(all_results)} total so far)")

        logger.info("="*60)
        logger.info(f"SUCCESS: Results saved to {output_filename}")
        logger.info(f"Total articles found: {len(all_results)}")
        logger.info("="*60)
        if not all_results:
            logger.warning("No results found")
            sys.exit(1)
        return

    # Process each study
    for idx, row in studies_df.iterrows():
        all_results.extend(process_row(idx, row))

    # Create and save results dataframe
    if all_results:
        logger.debug(f"Creating dataframe from {len(all_results)} total results")
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
