"""
LLM interaction utilities for AI-powered analysis and scoring.
Handles Anthropic API calls with token limit checks.
"""

import os
import pandas as pd
import streamlit as st
from typing import Dict, Optional, List
import anthropic

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    ANTHROPIC_MODEL,
    MAX_TOKENS_ANALYSIS,
    MAX_TOKENS_SCORING,
    MAX_INPUT_TOKENS,
    TEMPERATURE,
    PROMPTS
)


def get_anthropic_client() -> Optional[anthropic.Anthropic]:
    """
    Initialize Anthropic client with API key from environment or Streamlit secrets.

    Returns:
        Anthropic client or None if API key not found
    """
    api_key = None

    # Try environment variable first
    if "ANTHROPIC_API_KEY" in os.environ:
        api_key = os.environ["ANTHROPIC_API_KEY"]

    # Try Streamlit secrets
    elif hasattr(st, "secrets") and "ANTHROPIC_API_KEY" in st.secrets:
        api_key = st.secrets["ANTHROPIC_API_KEY"]

    if not api_key:
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        return client
    except Exception as e:
        st.error(f"Error initializing Anthropic client: {e}")
        return None


def check_token_limit(text: str, max_tokens: int = MAX_INPUT_TOKENS) -> bool:
    """
    Check if text is within token limits.
    Uses rough estimate of 4 characters per token.

    Args:
        text: Input text
        max_tokens: Maximum allowed tokens

    Returns:
        True if within limits, False otherwise
    """
    estimated_tokens = len(text) // 4

    return estimated_tokens <= max_tokens


def truncate_text(text: str, max_tokens: int = MAX_INPUT_TOKENS) -> str:
    """
    Truncate text to fit within token limits.

    Args:
        text: Input text
        max_tokens: Maximum allowed tokens

    Returns:
        Truncated text
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "..."


def analyze_datasets(df: pd.DataFrame, full_df: Optional[pd.DataFrame] = None) -> Optional[str]:
    """
    Use LLM to analyze a collection of datasets.

    Args:
        df: DataFrame with dataset information (filtered)
        full_df: Full dataset for comparison (optional)

    Returns:
        Analysis text or None if failed
    """
    client = get_anthropic_client()
    if not client:
        return "API key not configured. Please add ANTHROPIC_API_KEY to environment or Streamlit secrets."

    # Prepare dataset information
    dataset_info = prepare_dataset_summary(df)

    # Prepare comparison info if full dataset provided
    comparison_info = ""
    if full_df is not None and len(df) < len(full_df):
        comparison_info = f"\n\nComparative Context:\n"
        comparison_info += f"- Analyzing {len(df)} of {len(full_df)} total datasets ({len(df)/len(full_df)*100:.1f}%)\n"
        comparison_info += f"- Full catalog diseases: {', '.join(full_df['Diseases Included'].str.split(';').explode().str.strip().value_counts().head(5).index.tolist())}\n"
        if 'Coarse Data Types' in full_df.columns:
            comparison_info += f"- Full catalog coarse data types: {', '.join(full_df['Coarse Data Types'].str.split(',').explode().str.strip().value_counts().head(5).index.tolist())}\n"

    # Check token limits
    combined_info = dataset_info + comparison_info
    if not check_token_limit(combined_info):
        st.warning("Dataset information exceeds token limits. Truncating...")
        combined_info = truncate_text(combined_info)

    # Format prompt with comparison context
    prompt = PROMPTS["dataset_analysis"].format(dataset_info=combined_info)

    try:
        with st.spinner("Analyzing datasets with AI..."):
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS_ANALYSIS,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text

    except Exception as e:
        st.error(f"Error calling Anthropic API: {e}")
        return None


def analyze_publications(df: pd.DataFrame, full_df: Optional[pd.DataFrame] = None) -> Optional[str]:
    """
    Use LLM to analyze a collection of publications.

    Args:
        df: DataFrame with publication information (filtered)
        full_df: Full dataset for comparison (optional)

    Returns:
        Analysis text or None if failed
    """
    client = get_anthropic_client()
    if not client:
        return "API key not configured. Please add ANTHROPIC_API_KEY to environment or Streamlit secrets."

    # Prepare publication information
    pub_info = prepare_publication_summary(df)

    # Prepare comparison info if full dataset provided
    comparison_info = ""
    if full_df is not None and len(df) < len(full_df):
        comparison_info = f"\n\nComparative Context:\n"
        comparison_info += f"- Analyzing {len(df)} of {len(full_df)} total publications ({len(df)/len(full_df)*100:.1f}%)\n"

        # Top studies comparison
        if 'Study Name' in full_df.columns:
            top_studies_full = full_df['Study Name'].value_counts().head(5).index.tolist()
            comparison_info += f"- Full catalog top studies: {', '.join(top_studies_full)}\n"

        # Keyword comparison
        if 'Keywords' in full_df.columns and 'Keywords' in df.columns:
            full_keywords = full_df['Keywords'].str.split(';').explode().str.strip().value_counts().head(5).index.tolist()
            comparison_info += f"- Full catalog top keywords: {', '.join(full_keywords)}\n"

    # Check token limits
    combined_info = pub_info + comparison_info
    if not check_token_limit(combined_info):
        st.warning("Publication information exceeds token limits. Truncating...")
        combined_info = truncate_text(combined_info)

    # Format prompt with comparison context
    prompt = PROMPTS["publication_analysis"].format(publication_info=combined_info)

    try:
        with st.spinner("Analyzing publications with AI..."):
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS_ANALYSIS,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text

    except Exception as e:
        st.error(f"Error calling Anthropic API: {e}")
        return None


def summarize_knowledge_graph(
    graph_stats: Dict,
    filtered_df: Optional[pd.DataFrame] = None,
    full_df: Optional[pd.DataFrame] = None,
    edge_details: Optional[pd.DataFrame] = None
) -> Optional[str]:
    """
    Use LLM to summarize knowledge graph patterns with enhanced connection analysis.

    Args:
        graph_stats: Dictionary with graph statistics
        filtered_df: Filtered dataset dataframe (optional)
        full_df: Full dataset dataframe for comparison (optional)
        edge_details: DataFrame with edge connection details (optional)

    Returns:
        Summary text or None if failed
    """
    client = get_anthropic_client()
    if not client:
        return "API key not configured. Please add ANTHROPIC_API_KEY to environment or Streamlit secrets."

    # Format graph information
    num_nodes = graph_stats.get("num_nodes", 0)
    num_edges = graph_stats.get("num_edges", 0)
    top_nodes = graph_stats.get("top_nodes", [])

    # Format top nodes with connection strength
    top_nodes_str = "\n".join([
        f"- {node}: {degree} connections"
        for node, degree in top_nodes[:10]
    ])

    # Analyze connection drivers from edge details
    connection_drivers = "Shared diseases, coarse data types, granular data types, and FAIR compliance characteristics"
    if edge_details is not None and not edge_details.empty:
        # Extract most common shared features
        feature_counts = {}
        for features_str in edge_details['Shared Features'].dropna():
            for feature_pair in features_str.split(';'):
                if ':' in feature_pair:
                    feature_type = feature_pair.split(':')[0].strip()
                    feature_counts[feature_type] = feature_counts.get(feature_type, 0) + 1

        if feature_counts:
            top_drivers = sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            connection_drivers = ", ".join([f"{driver} ({count} connections)" for driver, count in top_drivers])

    # Add comparative context
    comparison_context = ""
    if filtered_df is not None and full_df is not None and len(filtered_df) < len(full_df):
        comparison_context = f"\n\nComparative Context:\n- Graph shows {num_nodes} of {len(full_df)} total datasets\n- Connection density: {graph_stats.get('density', 0):.2%}"

    # Format prompt
    prompt = PROMPTS["knowledge_graph_summary"].format(
        num_nodes=num_nodes,
        num_edges=num_edges,
        edge_types=connection_drivers,
        top_nodes=top_nodes_str
    ) + comparison_context

    try:
        with st.spinner("Generating graph summary..."):
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS_ANALYSIS,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text

    except Exception as e:
        st.error(f"Error calling Anthropic API: {e}")
        return None


def score_code_repository(row: pd.Series, score_type: str) -> str:
    """
    Use LLM to score a code repository.

    Args:
        row: DataFrame row with repository information
        score_type: Type of score (cleanliness, completeness, runnable)

    Returns:
        Score (1-10) or "N/A"
    """
    client = get_anthropic_client()
    if not client:
        return "N/A"

    # Get repository information
    repo_name = row.get('Repository Link', 'Unknown')
    languages = row.get('Languages', 'Unknown')
    summary = row.get('Code Summary', 'No summary available')

    # Limit summary length
    if len(summary) > 1000:
        summary = summary[:1000] + "..."

    # Select appropriate prompt
    if score_type == "cleanliness":
        prompt_template = PROMPTS["code_cleanliness_score"]
    elif score_type == "completeness":
        prompt_template = PROMPTS["code_completeness_score"]
    elif score_type == "runnable":
        prompt_template = PROMPTS["code_runnable_score"]
    else:
        return "N/A"

    prompt = prompt_template.format(
        repo_name=repo_name,
        languages=languages,
        summary=summary
    )

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=MAX_TOKENS_SCORING,
            temperature=0.3,  # Lower temperature for scoring
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        score_text = response.content[0].text.strip()

        # Extract numeric score
        try:
            score = int(score_text)
            if 1 <= score <= 10:
                return str(score)
            else:
                return "N/A"
        except ValueError:
            return "N/A"

    except Exception as e:
        return "N/A"


def deep_dive_code_analysis(df: pd.DataFrame) -> Optional[str]:
    """
    Perform comprehensive code quality analysis with detailed summaries.

    Args:
        df: DataFrame with repository information

    Returns:
        Comprehensive analysis text covering all three quality dimensions
    """
    client = get_anthropic_client()
    if not client:
        st.error("AI analysis unavailable. Please check your API key configuration.")
        return None

    # Prepare repository summary
    summary = prepare_repository_summary(df, max_items=20)

    prompt = f"""Analyze these {len(df)} code repositories for quality and best practices.

{summary}

Provide a comprehensive analysis covering:

## 1. Code Cleanliness Assessment
- Overall code organization and structure patterns
- Style consistency across repositories
- Readability and maintainability trends
- Common issues or anti-patterns identified
- Best practices observed

## 2. Documentation & Completeness
- Documentation quality and coverage
- README comprehensiveness
- Dependency specification practices
- Test coverage and examples
- Common gaps in completeness

## 3. Usability & Runnability
- Setup and installation clarity
- Configuration requirements
- Ease of getting started
- Reproducibility considerations
- Barriers to adoption

## 4. Summary Scores & Recommendations
- Provide average scores (1-10) for each dimension
- Highlight exemplary repositories
- Key recommendations for improvement
- Priorities for researchers using these tools

Be specific with repository names and quantify findings. Use exact counts and percentages."""

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=MAX_TOKENS_ANALYSIS,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text

    except Exception as e:
        st.error(f"Analysis failed: {str(e)}")
        return None


def batch_score_repositories(df: pd.DataFrame, score_type: str) -> pd.DataFrame:
    """
    Score multiple repositories in batch with progress tracking.

    Args:
        df: DataFrame with repository information
        score_type: Type of score (cleanliness, completeness, runnable)

    Returns:
        DataFrame with added score column
    """
    score_column = f"LLM {score_type.capitalize()} Score"

    # Check if already scored
    if score_column in df.columns:
        st.info(f"{score_column} already exists. Skipping scoring.")
        return df

    # Add new column
    df[score_column] = "N/A"

    # Score each repository
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, (idx, row) in enumerate(df.iterrows()):
        status_text.text(f"Scoring repository {i + 1} of {len(df)}...")

        score = score_code_repository(row, score_type)
        df.at[idx, score_column] = score

        progress_bar.progress(min((i + 1) / len(df), 1.0))

    progress_bar.empty()
    status_text.empty()

    return df


def prepare_dataset_summary(df: pd.DataFrame, max_items: int = 50) -> str:
    """
    Prepare a concise summary of datasets for LLM analysis.

    Args:
        df: DataFrame with dataset information
        max_items: Maximum number of datasets to include

    Returns:
        Formatted summary string
    """
    # Limit to max_items
    df_subset = df.head(max_items)

    summary_parts = []

    for idx, row in df_subset.iterrows():
        name = row.get('Study Name', 'Unknown')
        abbrev = row.get('Abbreviation', '')
        diseases = row.get('Diseases Included', '')
        modalities = row.get('Data Modalities', '')
        sample_size = row.get('Sample Size', '')

        summary = f"{name}"
        if abbrev:
            summary += f" ({abbrev})"
        summary += f"\n  Diseases: {diseases}"
        summary += f"\n  Modalities: {modalities}"
        if sample_size:
            summary += f"\n  Sample Size: {sample_size}"

        summary_parts.append(summary)

    # Add count if truncated
    if len(df) > max_items:
        summary_parts.append(f"\n... and {len(df) - max_items} more datasets")

    return "\n\n".join(summary_parts)


def prepare_publication_summary(df: pd.DataFrame, max_items: int = 50) -> str:
    """
    Prepare a concise summary of publications for LLM analysis.

    Args:
        df: DataFrame with publication information
        max_items: Maximum number of publications to include

    Returns:
        Formatted summary string
    """
    # Limit to max_items
    df_subset = df.head(max_items)

    summary_parts = []

    for idx, row in df_subset.iterrows():
        title = row.get('Title', 'Unknown')
        authors = row.get('Authors', '')
        keywords = row.get('Keywords', '')
        abstract = row.get('Abstract', '')

        # Limit abstract length
        if abstract and len(abstract) > 200:
            abstract = abstract[:200] + "..."

        summary = f"Title: {title}"
        if authors:
            # Show first 3 authors
            author_list = authors.split(';')[:3]
            summary += f"\n  Authors: {'; '.join(author_list)}"
            if len(authors.split(';')) > 3:
                summary += " et al."
        if keywords:
            summary += f"\n  Keywords: {keywords}"
        if abstract:
            summary += f"\n  Abstract: {abstract}"

        summary_parts.append(summary)

    # Add count if truncated
    if len(df) > max_items:
        summary_parts.append(f"\n... and {len(df) - max_items} more publications")

    return "\n\n".join(summary_parts)


def analyze_repositories(df: pd.DataFrame, full_df: Optional[pd.DataFrame] = None) -> Optional[str]:
    """
    Use LLM to analyze a collection of code repositories.

    Args:
        df: DataFrame with repository information (filtered)
        full_df: Full dataset for comparison (optional)

    Returns:
        Analysis text or None if failed
    """
    client = get_anthropic_client()
    if not client:
        return "API key not configured. Please add ANTHROPIC_API_KEY to environment or Streamlit secrets."

    # Prepare repository information
    repo_info = prepare_repository_summary(df)

    # Prepare comparison info if full dataset provided
    comparison_info = ""
    if full_df is not None and len(df) < len(full_df):
        comparison_info = f"\n\nComparative Context:\n"
        comparison_info += f"- Analyzing {len(df)} of {len(full_df)} total repositories ({len(df)/len(full_df)*100:.1f}%)\n"

        # Top studies comparison
        if 'Study Name' in full_df.columns:
            top_studies_full = full_df['Study Name'].value_counts().head(5).index.tolist()
            comparison_info += f"- Full catalog top studies: {', '.join(top_studies_full)}\n"

        # Language comparison
        if 'Languages' in full_df.columns and 'Languages' in df.columns:
            full_languages = full_df['Languages'].str.split(',').explode().str.strip().value_counts().head(5).index.tolist()
            comparison_info += f"- Full catalog top languages: {', '.join(full_languages)}\n"

    # Check token limits
    combined_info = repo_info + comparison_info
    if not check_token_limit(combined_info):
        st.warning("Repository information exceeds token limits. Truncating...")
        combined_info = truncate_text(combined_info)

    # Format prompt with comparison context
    prompt = PROMPTS["repository_analysis"].format(repository_info=combined_info)

    try:
        with st.spinner("Analyzing repositories with AI..."):
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS_ANALYSIS,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text

    except Exception as e:
        st.error(f"Error calling Anthropic API: {e}")
        return None


def prepare_repository_summary(df: pd.DataFrame, max_items: int = 50) -> str:
    """
    Prepare a concise summary of repositories for LLM analysis.

    Args:
        df: DataFrame with repository information
        max_items: Maximum number of repositories to include

    Returns:
        Formatted summary string
    """
    # Limit to max_items
    df_subset = df.head(max_items)

    summary_parts = []

    for idx, row in df_subset.iterrows():
        repo_link = row.get('Repository Link', 'Unknown')
        study = row.get('Study Name', 'Unknown Study')
        languages = row.get('Languages', '')
        data_types = row.get('Data Types', '')
        tooling = row.get('Tooling', '')
        biomedical = row.get('Biomedical Relevance', '')
        fair_score = row.get('FAIR Score', '')

        # Extract repo name from link
        repo_name = repo_link.split('/')[-1] if '/' in repo_link else repo_link

        summary = f"{repo_name} ({study})"
        if languages:
            summary += f"\n  Languages: {languages}"
        if data_types:
            summary += f"\n  Data Types: {data_types}"
        if tooling:
            summary += f"\n  Tooling: {tooling}"
        if biomedical:
            summary += f"\n  Biomedical Relevance: {biomedical}"
        if fair_score:
            summary += f"\n  FAIR Score: {fair_score}/10"

        summary_parts.append(summary)

    # Add count if truncated
    if len(df) > max_items:
        summary_parts.append(f"\n... and {len(df) - max_items} more repositories")

    return "\n\n".join(summary_parts)


def analyze_cellular_models(df: pd.DataFrame, full_df: Optional[pd.DataFrame] = None) -> Optional[str]:
    """
    Use LLM to analyze a collection of cellular models.

    Args:
        df: DataFrame with cellular model information (filtered)
        full_df: Full dataset for comparison (optional)

    Returns:
        Analysis text or None if failed
    """
    client = get_anthropic_client()
    if not client:
        st.error("AI analysis unavailable. Please check your API key configuration.")
        return None

    # Prepare cellular models summary
    summary = prepare_cellular_models_summary(df, max_items=30)

    # Prepare comparison info if full dataset provided
    comparison_info = ""
    if full_df is not None and len(df) < len(full_df):
        comparison_info = f"\n\nComparative Context:\n"
        comparison_info += f"- Analyzing {len(df)} of {len(full_df)} total cell lines ({len(df)/len(full_df)*100:.1f}%)\n"

        # Gene distribution comparison
        if 'Gene' in df.columns and 'Gene' in full_df.columns:
            subset_genes = df['Gene'].value_counts().head(5).index.tolist()
            full_genes = full_df['Gene'].value_counts().head(5).index.tolist()
            comparison_info += f"- Subset top genes: {', '.join(subset_genes)}\n"
            comparison_info += f"- Full catalog top genes: {', '.join(full_genes)}\n"

        # Condition distribution comparison
        if 'Condition' in df.columns and 'Condition' in full_df.columns:
            subset_conditions = [c for c in df['Condition'].value_counts().head(5).index.tolist()
                                if c and str(c).strip() and str(c) != "0"]
            full_conditions = [c for c in full_df['Condition'].value_counts().head(5).index.tolist()
                              if c and str(c).strip() and str(c) != "0"]
            if subset_conditions:
                comparison_info += f"- Subset top conditions: {', '.join(subset_conditions)}\n"
            if full_conditions:
                comparison_info += f"- Full catalog top conditions: {', '.join(full_conditions)}\n"

    # Check token limits
    combined_info = summary + comparison_info
    if not check_token_limit(combined_info):
        st.warning("Cellular model information exceeds token limits. Truncating...")
        combined_info = truncate_text(combined_info)

    # Format prompt with comparison context
    prompt = PROMPTS["cellular_models_analysis"].format(
        summary=combined_info,
        comparison=comparison_info
    )

    try:
        with st.spinner("Analyzing cellular models with AI..."):
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_TOKENS_ANALYSIS,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text

    except Exception as e:
        st.error(f"Error calling Anthropic API: {e}")
        return None


def prepare_cellular_models_summary(df: pd.DataFrame, max_items: int = 30) -> str:
    """
    Prepare a concise summary of cellular models for LLM analysis.

    Args:
        df: DataFrame with cellular model information
        max_items: Maximum number of cell lines to include

    Returns:
        Formatted summary string
    """
    # Limit to max_items
    df_subset = df.head(max_items)

    summary_parts = []

    for idx, row in df_subset.iterrows():
        product_code = row.get('Product Code', 'Unknown')
        gene = row.get('Gene', 'N/A')
        variant = row.get('Gene Variant', 'N/A')
        condition = row.get('Condition', 'N/A')
        about_gene = row.get('About this gene', '')
        about_variant = row.get('About this variant', '')

        # Format condition display
        if condition == "0" or not condition or str(condition).strip() == "":
            condition_display = "Control/Wildtype"
        else:
            condition_display = condition

        # Truncate About sections for summary
        if about_gene and len(str(about_gene)) > 200:
            about_gene = str(about_gene)[:200] + "..."
        if about_variant and len(str(about_variant)) > 200:
            about_variant = str(about_variant)[:200] + "..."

        summary = f"{product_code} - {gene} {variant}"
        summary += f"\n  Condition: {condition_display}"
        if about_gene and str(about_gene).strip():
            summary += f"\n  About gene: {about_gene}"
        if about_variant and str(about_variant).strip():
            summary += f"\n  About variant: {about_variant}"

        summary_parts.append(summary)

    # Add count if truncated
    if len(df) > max_items:
        summary_parts.append(f"\n... and {len(df) - max_items} more cell lines")

    return "\n\n".join(summary_parts)


def test_api_connection() -> bool:
    """
    Test if Anthropic API is properly configured and accessible.

    Returns:
        True if successful, False otherwise
    """
    client = get_anthropic_client()
    if not client:
        return False

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=100,
            messages=[
                {"role": "user", "content": "Hello, respond with 'OK' if you can read this."}
            ]
        )
        return True
    except Exception as e:
        st.error(f"API connection test failed: {e}")
        return False
