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
from typing import List, Dict, Optional
import argparse

def clean_text(text):
    """Remove newlines and extra whitespace from text"""
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', text.strip())

def search_pubmed_with_retry(url: str, max_retries: int = 3, base_delay: int = 60) -> Optional[requests.Response]:
    """Make a request to PubMed API with exponential backoff retry logic"""
    for attempt in range(max_retries):
        try:
            time.sleep(1)  # Rate limiting: minimum 1 second between requests
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                delay = base_delay * (2 ** attempt)
                print(f"Rate limited (attempt {attempt + 1}/{max_retries}). Waiting {delay} seconds...", file=sys.stderr)
                time.sleep(delay)
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Request failed (attempt {attempt + 1}/{max_retries}): {str(e)}. Retrying in {delay} seconds...", file=sys.stderr)
                time.sleep(delay)
            else:
                print(f"Request failed after {max_retries} attempts: {str(e)}", file=sys.stderr)
                return None
    return None

def extract_article_details(article_xml: ET.Element) -> Optional[Dict]:
    """Extract article details from PubMed XML"""
    try:
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

        # Get keywords
        keywords = []
        keyword_list = article_xml.find('.//KeywordList')
        if keyword_list is not None:
            keywords = [k.text for k in keyword_list.findall('.//Keyword') if k.text]

        # Get PMC ID if available
        pmc_id = None
        article_ids = article_xml.findall('.//ArticleId')
        for article_id in article_ids:
            if article_id.get('IdType') == 'pmc':
                pmc_id = article_id.text
                break

        # Create PMC link if available
        pmc_link = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/" if pmc_id else ""

        return {
            "Title": title_text,
            "Abstract": abstract,
            "Authors": "; ".join(authors),
            "Affiliations": "; ".join(affiliations),
            "Keywords": "; ".join(keywords),
            "PubMed Central Link": pmc_link
        }
    except Exception as e:
        print(f"Error extracting article details: {str(e)}", file=sys.stderr)
        return None

def build_search_query(study_name: str, abbreviation: str, diseases: str, data_modalities: str, years: int = 3) -> str:
    """Build optimized PubMed search query"""
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*years)
    date_range = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}"

    # Core disease keywords for neurodegenerative diseases
    disease_keywords = ["alzheimer", "parkinson", "dementia", "brain", "neurodegenerative",
                       "neurodegeneration", "tremor", "amyotrophic", "als", "cognitive impairment",
                       "mild cognitive impairment", "mci", "lewy body"]

    # Extract disease terms from the Diseases Included column
    disease_terms = []
    if pd.notna(diseases) and isinstance(diseases, str):
        disease_terms = [d.strip().lower() for d in diseases.split(";")
                        if any(kw in d.lower() for kw in disease_keywords)]

    # Fall back to general keywords if no specific diseases found
    if not disease_terms:
        disease_terms = disease_keywords[:5]  # Use top 5 general keywords

    # Extract data modalities
    modalities = []
    if pd.notna(data_modalities) and isinstance(data_modalities, str):
        # Handle both semicolon-separated and bracket-enclosed formats
        clean_modalities = data_modalities.strip('[]')
        modalities = [m.strip() for m in clean_modalities.split(';') if m.strip()]

    # Build query terms
    study_terms = []
    if study_name and pd.notna(study_name):
        study_terms.append(f'"{study_name}"[All Fields]')
    if abbreviation and pd.notna(abbreviation) and abbreviation != study_name:
        study_terms.append(f'"{abbreviation}"[All Fields]')

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

    return " AND ".join(query_parts)

def search_pubmed(study_name: str, abbreviation: str, diseases: str, data_modalities: str, max_results: int = 100) -> List[Dict]:
    """Search PubMed for articles related to the study"""
    # Build search query
    query = build_search_query(study_name, abbreviation, diseases, data_modalities)

    # Search PubMed
    base_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    search_url = f'{base_url}?db=pubmed&term={query}&retmax={max_results}&retmode=json'

    print(f"  Query: {query[:100]}..." if len(query) > 100 else f"  Query: {query}", file=sys.stderr)

    response = search_pubmed_with_retry(search_url)
    if not response:
        return []

    try:
        data = response.json()
        pubmed_ids = data.get('esearchresult', {}).get('idlist', [])

        if not pubmed_ids:
            print(f"  No results found", file=sys.stderr)
            return []

        print(f"  Found {len(pubmed_ids)} articles", file=sys.stderr)

        results = []
        # Fetch articles in batches to improve efficiency
        batch_size = 20
        for i in range(0, len(pubmed_ids), batch_size):
            batch_ids = pubmed_ids[i:i+batch_size]
            ids_str = ",".join(batch_ids)

            fetch_url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml'
            fetch_response = search_pubmed_with_retry(fetch_url)

            if not fetch_response:
                continue

            try:
                # Parse XML
                root = ET.fromstring(fetch_response.text)
                articles = root.findall('.//PubmedArticle')

                for article in articles:
                    article_data = extract_article_details(article)
                    if article_data:
                        # Add study information
                        article_data.update({
                            "Study Name": study_name,
                            "Abbreviation": abbreviation,
                            "Diseases Included": diseases,
                            "Data Modalities": data_modalities
                        })
                        results.append(article_data)

            except Exception as e:
                print(f"  Error parsing batch: {str(e)}", file=sys.stderr)
                continue

        print(f"  Successfully processed {len(results)} articles", file=sys.stderr)
        return results

    except Exception as e:
        print(f"  Error processing search results: {str(e)}", file=sys.stderr)
        return []

def main():
    parser = argparse.ArgumentParser(description='Scrape PubMed for publications related to neurodegenerative disease studies')
    parser.add_argument('--input', '-i', default='../tables/dataset-inventory-June_20_2025.tab',
                       help='Input TSV file with study inventory (default: ../tables/dataset-inventory-June_20_2025.tab)')
    parser.add_argument('--output', '-o', default=None,
                       help='Output TSV file (default: pubmed_central_{timestamp}.tsv)')
    parser.add_argument('--max-results', '-m', type=int, default=100,
                       help='Maximum results per study (default: 100)')

    args = parser.parse_args()

    # Read the dataset inventory
    try:
        studies_df = pd.read_csv(args.input, sep="\t")
        print(f"Loaded {len(studies_df)} studies from {args.input}", file=sys.stderr)
    except Exception as e:
        print(f"Error reading dataset inventory: {str(e)}", file=sys.stderr)
        sys.exit(1)

    # Initialize results list
    all_results = []

    # Process each study
    for idx, row in studies_df.iterrows():
        study_name = row.get("Study Name", "")
        abbreviation = row.get("Abbreviation", "")
        diseases = row.get("Diseases Included", "")
        data_modalities = row.get("Data Modalities", "")

        print(f"\n[{idx+1}/{len(studies_df)}] Searching for publications related to {study_name} ({abbreviation})...", file=sys.stderr)
        results = search_pubmed(study_name, abbreviation, diseases, data_modalities, args.max_results)
        all_results.extend(results)

    # Create and save results dataframe
    if all_results:
        # Reorder columns to match previous format exactly
        columns_order = [
            "Study Name",
            "Abbreviation",
            "Diseases Included",
            "Data Modalities",
            "PubMed Central Link",
            "Authors",
            "Affiliations",
            "Title",
            "Abstract",
            "Keywords"
        ]

        results_df = pd.DataFrame(all_results)

        # Ensure all columns exist
        for col in columns_order:
            if col not in results_df.columns:
                results_df[col] = ""

        # Reorder columns
        results_df = results_df[columns_order]

        # Generate output filename
        if args.output:
            output_filename = args.output
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"../tables/pubmed_central_{timestamp}.tsv"

        results_df.to_csv(output_filename, sep="\t", index=False)

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"SUCCESS: Results saved to {output_filename}", file=sys.stderr)
        print(f"Total articles found: {len(all_results)}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
    else:
        print("\nNo results found", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
