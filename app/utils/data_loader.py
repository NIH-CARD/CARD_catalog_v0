"""
Data loading and caching utilities for CARD Catalog.
Handles loading all data files with proper caching and normalization.
"""

import pandas as pd
import streamlit as st
from pathlib import Path
from typing import Dict, List, Optional
import glob
import re
import logging
import unicodedata

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import TABLES_DIR, SCRAPERS_DIR, DATA_FILES_PTRS, FAIR_LOG_PATTERN

logger = logging.getLogger(__name__)

current_dir = Path.cwd()

def get_latest_file(pattern, directory=''):
    """Load the most recent file matching pattern."""
    logger.info(f"Looking for files in {directory} matching {pattern}")
    search_path = Path(directory) / pattern
    logger.info(f"Searching for files with pattern: {search_path}")
    files = glob.glob(str(search_path))
    logger.info(f"Found {len(files)} files matching pattern")
    if not files:
        raise FileNotFoundError(f"No files found matching pattern: {search_path}")
    latest_file = max(files, key=lambda x: Path(x).stat().st_mtime)
    logger.info(f"Latest file found: {latest_file}")
    assert str(latest_file).endswith(".tsv") or str(latest_file).endswith(".tab"), f"Expected a .tsv / .tab file, got: {latest_file}"
    return Path(latest_file)


@st.cache_data(ttl=3600)
def load_datasets() -> pd.DataFrame:
    """
    Load dataset inventory from tables directory.

    Returns:
        DataFrame with dataset information
    """
    logger.info("Loading datasets...")
    file_path = get_latest_file(DATA_FILES_PTRS["datasets"], TABLES_DIR)

    if not file_path.exists():
        logger.error(f"Dataset file not found: {file_path}")
        st.error(f"Dataset file not found: {file_path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')

        # Clean column names
        df.columns = df.columns.str.strip()

        # Handle missing values
        df = df.fillna("")

        # Normalize disease names (split on both ";" and "," to handle inconsistent source data)
        df['Diseases Included'] = df['Diseases Included'].apply(
            lambda x: normalize_list_field(x, delimiter=";", split_delimiters=[";", ","])
        )

        df = df.drop(columns=[c for c in ["Notes", "Remove"] if c in df.columns])

        logger.info(f"Datasets loaded: {len(df)} rows, {len(df.columns)} columns")
        return df
    except Exception as e:
        logger.error(f"Error loading datasets: {e}", exc_info=True)
        st.error(f"Error loading datasets: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_code_repos() -> pd.DataFrame:
    """
    Load code repository data from tables directory.

    Returns:
        DataFrame with code repository information
    """
    logger.info("Loading code repositories...")
    file_path = get_latest_file(DATA_FILES_PTRS["code_repos"], TABLES_DIR)

    if not file_path.exists():
        logger.error(f"Code repos file not found: {file_path}")
        st.error(f"Code repos file not found: {file_path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')

        # Clean column names
        df.columns = df.columns.str.strip()

        # Handle missing values
        df = df.fillna("")

        # Normalize diseases
        df['Diseases Included'] = df['Diseases Included'].apply(normalize_list_field)

        # Normalize data types and tooling
        if 'Data Types' in df.columns:
            df['Data Types'] = df['Data Types'].apply(normalize_list_field)

        if 'Tooling' in df.columns:
            df['Tooling'] = df['Tooling'].apply(normalize_list_field)

        # Deduplicate languages
        if 'Languages' in df.columns:
            df['Languages'] = df['Languages'].apply(normalize_list_field)

        # Drop heavy unused column
        df = df.drop(columns=[c for c in ['Content_For_Analysis'] if c in df.columns])

        logger.info(f"Code repos loaded: {len(df)} rows, {len(df.columns)} columns")
        return df
    except Exception as e:
        logger.error(f"Error loading code repos: {e}", exc_info=True)
        st.error(f"Error loading code repos: {e}")
        return pd.DataFrame()


def calculate_publication_completeness(row: pd.Series) -> float:
    """
    Calculate completeness score for a publication (0-100%).
    Checks: PMC Link, Abstract, Keywords, Authors, Affiliations.

    Args:
        row: DataFrame row

    Returns:
        Completeness percentage (0-100)
    """
    fields_to_check = ['PubMed Central Link', 'Abstract', 'Keywords', 'Authors', 'Affiliations']
    completed = 0
    total = len(fields_to_check)

    for field in fields_to_check:
        if field in row and row[field] and str(row[field]).strip() != '':
            completed += 1

    return (completed / total) * 100


@st.cache_data(ttl=3600, hash_funcs={pd.DataFrame: lambda x: None})
def load_publications() -> pd.DataFrame:
    """
    Load publications data from tables directory.
    Includes fixes for PMC links and author normalization.

    Returns:
        DataFrame with publication information
    """
    logger.info("Loading publications...")
    file_path = get_latest_file(DATA_FILES_PTRS["publications"], TABLES_DIR)

    if not file_path.exists():
        logger.error(f"Publications file not found: {file_path}")
        st.error(f"Publications file not found: {file_path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')

        # Clean column names
        df.columns = df.columns.str.strip()

        # Handle missing values
        df = df.fillna("")

        # Fix PMC links - remove duplicate PMC prefix
        if 'PubMed Central Link' in df.columns:
            df['PubMed Central Link'] = df['PubMed Central Link'].apply(fix_pmc_link)

        # Normalize author names
        if 'Authors' in df.columns:
            df['Authors'] = df['Authors'].apply(normalize_author_names)

        # Normalize diseases (split on both ";" and "," to handle inconsistent source data)
        if 'Diseases Included' in df.columns:
            df['Diseases Included'] = df['Diseases Included'].apply(
                lambda x: normalize_list_field(x, delimiter=";", split_delimiters=[";", ","])
            )

        # Normalize keywords to fix duplicates
        if 'Keywords' in df.columns:
            df['Keywords'] = df['Keywords'].apply(normalize_list_field)

        # Calculate data completeness score
        df['Data Completeness'] = df.apply(calculate_publication_completeness, axis=1)

        logger.info(f"Publications loaded: {len(df)} rows, {len(df.columns)} columns")
        return df
    except Exception as e:
        logger.error(f"Error loading publications: {e}", exc_info=True)
        st.error(f"Error loading publications: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_fair_compliance() -> pd.DataFrame:
    """
    Load FAIR compliance logs from scrapers directory.
    Merges all FAIR compliance log files.

    Returns:
        DataFrame with FAIR compliance information
    """
    pattern = str(SCRAPERS_DIR / FAIR_LOG_PATTERN)
    fair_files = glob.glob(pattern)
    logger.info(f"Loading FAIR compliance logs: found {len(fair_files)} files matching {pattern}")

    if not fair_files:
        logger.warning("No FAIR compliance log files found")
        st.warning("No FAIR compliance log files found")
        return pd.DataFrame()

    latest_file = max(fair_files, key=lambda x: Path(x).stat().st_mtime)
    logger.info(f"Loading latest FAIR compliance log: {latest_file}")

    try:
        combined_df = pd.read_csv(latest_file, sep='\t', encoding='utf-8')
    except Exception as e:
        logger.warning(f"Error loading {latest_file}: {e}")
        return pd.DataFrame()

    # Remove duplicates (keep most recent)
    if 'Timestamp' in combined_df.columns:
        combined_df = combined_df.sort_values('Timestamp', ascending=False)
        combined_df = combined_df.drop_duplicates(subset=['Repository', 'Study', 'Issue Type'], keep='first')

    logger.info(f"FAIR compliance loaded: {len(combined_df)} records")
    return combined_df


@st.cache_data(ttl=3600)
def load_indi_inventory() -> pd.DataFrame:
    """
    Load iNDI inventory data.

    Returns:
        DataFrame with iNDI inventory information
    """
    logger.info("Loading iNDI inventory...")
    file_path = get_latest_file(DATA_FILES_PTRS["indi"], TABLES_DIR)

    if not file_path.exists():
        logger.warning(f"iNDI inventory file not found: {file_path}")
        st.warning(f"iNDI inventory file not found: {file_path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
        df.columns = df.columns.str.strip()
        df = df.fillna("")
        logger.info(f"iNDI inventory loaded: {len(df)} rows, {len(df.columns)} columns")
        return df
    except Exception as e:
        logger.error(f"Error loading iNDI inventory: {e}", exc_info=True)
        st.error(f"Error loading iNDI inventory: {e}")
        return pd.DataFrame()


def normalize_list_field(field: str, delimiter: str = ";", split_delimiters: List[str] = None) -> str:
    """
    Normalize a delimited list field by:
    - Splitting on delimiter(s)
    - Stripping whitespace
    - Removing duplicates
    - Sorting alphabetically
    - Rejoining with output delimiter

    Args:
        field: String containing delimited values
        delimiter: Output delimiter character (default ";")
        split_delimiters: List of delimiters to split on (default: [delimiter])

    Returns:
        Normalized string joined with delimiter
    """
    if not field or pd.isna(field) or field == "":
        return ""

    separators = split_delimiters if split_delimiters else [delimiter]

    items = [str(field)]
    for sep in separators:
        items = [part for item in items for part in item.split(sep)]
    # Expand parenthetical content into additional items
    # e.g. "Alz(PD,AD,ADRD)" -> ["Alz", "PD", "AD", "ADRD"]
    expanded = []
    for item in items:
        paren_match = re.search(r'\(([^)]+)\)', item)
        if paren_match:
            # Add the base (without parenthetical)
            base = re.sub(r'\s*\([^)]*\)', '', item).strip()
            if base:
                expanded.append(base)
            # Add each comma-separated value inside the parentheses
            for sub in paren_match.group(1).split(','):
                sub = sub.strip()
                if sub:
                    expanded.append(sub)
        else:
            expanded.append(item)

    items_to_process = expanded
    items = []
    for item in items_to_process:
        # Strip regular and Unicode whitespace
        cleaned = item.strip()
        # Normalize Unicode characters (NFKC normalization)
        cleaned = unicodedata.normalize('NFKC', cleaned)
        # Replace all apostrophe variants with standard ASCII apostrophe
        # U+2019 ('), U+02BC (ʼ), U+0060 (`), U+00B4 (´), etc.
        apostrophe_variants = ['\u2019', '\u02BC', '\u0060', '\u00B4', '\u2018', '\u201B']
        for variant in apostrophe_variants:
            cleaned = cleaned.replace(variant, "'")
        # Strip again after normalization
        cleaned = cleaned.strip()
        if cleaned:
            items.append(cleaned)

    # Remove duplicates (case-insensitive)
    seen = {}
    unique_items = []
    for item in items:
        lower = item.lower()
        if lower not in seen:
            seen[lower] = item
            unique_items.append(item)

    items = unique_items

    # Sort and rejoin
    items.sort()
    return delimiter.join(items)


def fix_pmc_link(link: str) -> str:
    """
    Fix PMC links that have duplicate PMC prefix.
    E.g., https://www.ncbi.nlm.nih.gov/pmc/articles/PMCPMC10764118/
    Should be: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10764118/

    Args:
        link: Original PMC link

    Returns:
        Fixed PMC link
    """
    if not link or pd.isna(link):
        return ""

    # Fix duplicate PMC prefix
    link = re.sub(r'PMCPMC(\d+)', r'PMC\1', link)

    return link


def normalize_author_names(authors: str) -> str:
    """
    Normalize author names to handle variations like:
    - "Mike Nalls" and "Mike A Nalls" -> "Mike A Nalls"
    - "Smith John" and "Smith J" -> "Smith John"

    Args:
        authors: Semicolon-separated author names

    Returns:
        Normalized author string
    """
    if not authors or pd.isna(authors) or authors == "":
        return ""

    # Split authors
    author_list = [a.strip() for a in str(authors).split(';')]

    # For each author, extract last name and first/middle initials
    normalized = []
    for author in author_list:
        if not author:
            continue

        # Split into parts
        parts = author.split()
        if len(parts) == 0:
            continue

        # Last name is typically last part
        last_name = parts[-1]

        # First and middle names/initials
        first_middle = ' '.join(parts[:-1])

        # Normalize: "Last First Middle"
        normalized.append(f"{last_name} {first_middle}".strip())

    # Remove duplicates while preserving order
    seen = set()
    unique_authors = []
    for author in normalized:
        # Normalize for comparison (remove middle initials)
        normalized_key = re.sub(r'\s+[A-Z]\s+', ' ', author).lower()
        if normalized_key not in seen:
            seen.add(normalized_key)
            unique_authors.append(author)

    return '; '.join(unique_authors)


def get_unique_values(df: pd.DataFrame, column: str, delimiter: str | List[str] = ";") -> List[str]:
    """
    Get unique values from a delimited column.

    Args:
        df: DataFrame
        column: Column name
        delimiter: Delimiter character or list of delimiter characters

    Returns:
        Sorted list of unique values
    """
    if column not in df.columns:
        logger.warning(f"Column '{column}' not found in DataFrame")
        return []

    delimiters = delimiter if isinstance(delimiter, list) else [delimiter]
    logger.info(f"Extracting unique values from column '{column}' using delimiters: {delimiters}")

    all_values = []
    for value in df[column].dropna():
        if value and str(value).strip():
            items = [str(value)]
            for sep in delimiters:
                items = [part for item in items for part in item.split(sep)]
            all_values.extend([item.strip() for item in items if item.strip()])

    # Remove duplicates and sort
    unique_values = sorted(list(set(all_values)))

    return unique_values


def filter_dataframe(
    df: pd.DataFrame,
    filters: Dict[str, any]
) -> pd.DataFrame:
    """
    Filter a DataFrame based on multiple criteria.
    Supports exact match and keyword search.

    Args:
        df: DataFrame to filter
        filters: Dictionary of column: value/list filters

    Returns:
        Filtered DataFrame
    """
    filtered_df = df.copy()

    for column, value in filters.items():
        if column not in filtered_df.columns:
            continue

        if not value:
            continue

        if isinstance(value, list) and len(value) > 0:
            # Multiple selection - match any
            mask = filtered_df[column].apply(
                lambda x: any(v in str(x) for v in value)
            )
            filtered_df = filtered_df[mask]

        elif isinstance(value, str) and value:
            # Keyword search - case insensitive partial match
            mask = filtered_df[column].str.contains(
                value, case=False, na=False, regex=False
            )
            filtered_df = filtered_df[mask]

    return filtered_df


def search_across_columns(
    df: pd.DataFrame,
    search_term: str,
    columns: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Search for a keyword across multiple columns.
    Uses fuzzy matching (case-insensitive partial match).

    Args:
        df: DataFrame to search
        search_term: Search keyword
        columns: List of columns to search (None = all columns)

    Returns:
        Filtered DataFrame with matching rows
    """
    if not search_term:
        return df

    if columns is None:
        columns = df.columns.tolist()

    # Create a mask for rows matching the search term
    mask = pd.Series([False] * len(df), index=df.index)

    for column in columns:
        if column in df.columns:
            column_mask = df[column].astype(str).str.contains(
                search_term, case=False, na=False, regex=False
            )
            mask = mask | column_mask

    return df[mask]


def merge_fair_compliance(code_df: pd.DataFrame, fair_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge FAIR compliance data with code repository data.

    Args:
        code_df: DataFrame with code repositories
        fair_df: DataFrame with FAIR compliance logs

    Returns:
        Merged DataFrame with FAIR compliance information
    """
    if fair_df.empty:
        # Add empty FAIR columns
        code_df['FAIR Issues'] = ""
        code_df['FAIR Score'] = 0
        return code_df

    # Group FAIR issues by repository
    fair_summary = fair_df.groupby('Repository').agg({
        'Issue Type': lambda x: '; '.join(x.unique()),
        'Details': 'count'
    }).reset_index()

    fair_summary.columns = ['Repository Link', 'FAIR Issues', 'FAIR Issue Count']

    # Calculate FAIR score (10 - issue count, min 0)
    fair_summary['FAIR Score'] = fair_summary['FAIR Issue Count'].apply(
        lambda x: max(0, 10 - x)
    )

    # Merge with code data
    merged_df = code_df.merge(
        fair_summary[['Repository Link', 'FAIR Issues', 'FAIR Score']],
        on='Repository Link',
        how='left'
    )

    # Fill NaN values
    merged_df['FAIR Issues'] = merged_df['FAIR Issues'].fillna("")
    merged_df['FAIR Score'] = merged_df['FAIR Score'].fillna(10)  # No issues = perfect score

    return merged_df
