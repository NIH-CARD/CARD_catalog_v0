"""
Data loading and caching utilities for CARD Catalog.
Handles loading all data files with proper caching and normalization.
"""

import pandas as pd
import streamlit as st
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import glob
import re

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import TABLES_DIR, SCRAPERS_DIR, DATA_FILES, FAIR_LOG_PATTERN


def split_data_modalities(data_modalities_str: str) -> Tuple[str, str]:
    """
    Split data modalities string into coarse and granular parts.

    Format: [coarse_level] granular_details
    Example: [clinical, genetics, imaging] Clinical assessments; MRI; PET

    Args:
        data_modalities_str: String containing data modalities

    Returns:
        Tuple of (coarse_data_types, granular_data_types)
    """
    if pd.isna(data_modalities_str) or not str(data_modalities_str).strip():
        return "", ""

    text = str(data_modalities_str).strip()

    # Check if there's a bracket pattern [coarse] granular
    bracket_match = re.match(r'^\[(.*?)\]\s*(.*)$', text)

    if bracket_match:
        coarse_part = bracket_match.group(1).strip()
        granular_part = bracket_match.group(2).strip()
        return coarse_part, granular_part
    else:
        # If no brackets, treat the whole thing as granular
        return "", text


@st.cache_data(ttl=3600)
def load_datasets() -> pd.DataFrame:
    """
    Load dataset inventory from tables directory.

    Returns:
        DataFrame with dataset information
    """
    file_path = TABLES_DIR / DATA_FILES["datasets"]

    if not file_path.exists():
        st.error(f"Dataset file not found: {file_path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')

        # Clean column names
        df.columns = df.columns.str.strip()

        # Handle missing values
        df = df.fillna("")

        # Normalize disease names
        df['Diseases Included'] = df['Diseases Included'].apply(normalize_list_field)

        # Split data modalities into coarse and granular
        if 'Data Modalities' in df.columns:
            split_results = df['Data Modalities'].apply(split_data_modalities)
            df['Coarse Data Types'] = [result[0] for result in split_results]
            df['Granular Data Types'] = [result[1] for result in split_results]

            # Reorder columns to put new columns after Data Modalities
            cols = list(df.columns)
            if 'Data Modalities' in cols:
                data_mod_idx = cols.index('Data Modalities')
                # Remove the new columns from their current positions
                cols.remove('Coarse Data Types')
                cols.remove('Granular Data Types')
                # Insert them after Data Modalities
                cols.insert(data_mod_idx + 1, 'Coarse Data Types')
                cols.insert(data_mod_idx + 2, 'Granular Data Types')
                df = df[cols]

        return df
    except Exception as e:
        st.error(f"Error loading datasets: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_code_repos() -> pd.DataFrame:
    """
    Load code repository data from tables directory.

    Returns:
        DataFrame with code repository information
    """
    file_path = TABLES_DIR / DATA_FILES["code_repos"]

    if not file_path.exists():
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

        return df
    except Exception as e:
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
    file_path = TABLES_DIR / DATA_FILES["publications"]

    if not file_path.exists():
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

        # Normalize diseases
        if 'Diseases Included' in df.columns:
            df['Diseases Included'] = df['Diseases Included'].apply(normalize_list_field)

        # Normalize keywords to fix duplicates
        if 'Keywords' in df.columns:
            df['Keywords'] = df['Keywords'].apply(normalize_list_field)

        # Calculate data completeness score
        df['Data Completeness'] = df.apply(calculate_publication_completeness, axis=1)

        # Split data modalities into coarse and granular
        if 'Data Modalities' in df.columns:
            split_results = df['Data Modalities'].apply(split_data_modalities)
            df['Coarse Data Types'] = [result[0] for result in split_results]
            df['Granular Data Types'] = [result[1] for result in split_results]

            # Reorder columns to put new columns after Data Modalities
            cols = list(df.columns)
            if 'Data Modalities' in cols:
                data_mod_idx = cols.index('Data Modalities')
                # Remove the new columns from their current positions
                cols.remove('Coarse Data Types')
                cols.remove('Granular Data Types')
                # Insert them after Data Modalities
                cols.insert(data_mod_idx + 1, 'Coarse Data Types')
                cols.insert(data_mod_idx + 2, 'Granular Data Types')
                df = df[cols]

        return df
    except Exception as e:
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

    if not fair_files:
        st.warning("No FAIR compliance log files found")
        return pd.DataFrame()

    # Load and concatenate all FAIR files
    dfs = []
    for file_path in fair_files:
        try:
            df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
            dfs.append(df)
        except Exception as e:
            st.warning(f"Error loading {file_path}: {e}")
            continue

    if not dfs:
        return pd.DataFrame()

    # Concatenate all dataframes
    combined_df = pd.concat(dfs, ignore_index=True)

    # Remove duplicates (keep most recent)
    if 'Timestamp' in combined_df.columns:
        combined_df = combined_df.sort_values('Timestamp', ascending=False)
        combined_df = combined_df.drop_duplicates(subset=['Repository', 'Study', 'Issue Type'], keep='first')

    return combined_df


@st.cache_data(ttl=3600)
def load_indi_inventory() -> pd.DataFrame:
    """
    Load iNDI inventory data.

    Returns:
        DataFrame with iNDI inventory information
    """
    file_path = TABLES_DIR / DATA_FILES["indi"]

    if not file_path.exists():
        st.warning(f"iNDI inventory file not found: {file_path}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
        df.columns = df.columns.str.strip()
        df = df.fillna("")
        return df
    except Exception as e:
        st.error(f"Error loading iNDI inventory: {e}")
        return pd.DataFrame()


def normalize_list_field(field: str, delimiter: str = ";") -> str:
    """
    Normalize a delimited list field by:
    - Splitting on delimiter
    - Stripping whitespace
    - Removing duplicates
    - Sorting alphabetically
    - Rejoining with delimiter

    Args:
        field: String containing delimited values
        delimiter: Delimiter character

    Returns:
        Normalized string
    """
    if not field or pd.isna(field) or field == "":
        return ""

    # Split and clean - also normalize Unicode whitespace
    import unicodedata
    items = []
    for item in str(field).split(delimiter):
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


def get_unique_values(df: pd.DataFrame, column: str, delimiter: str = ";") -> List[str]:
    """
    Get unique values from a delimited column.

    Args:
        df: DataFrame
        column: Column name
        delimiter: Delimiter character

    Returns:
        Sorted list of unique values
    """
    if column not in df.columns:
        return []

    all_values = []
    for value in df[column].dropna():
        if value and str(value).strip():
            items = [item.strip() for item in str(value).split(delimiter)]
            all_values.extend([item for item in items if item])

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
