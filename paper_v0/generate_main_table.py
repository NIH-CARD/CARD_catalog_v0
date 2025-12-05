"""
Generate main descriptive statistics table for CARD Catalog paper.
"""

import pandas as pd
import numpy as np
from collections import Counter
import re
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

# Paths
TABLES_DIR = Path(__file__).parent.parent / "tables"
OUTPUT_DIR = Path(__file__).parent

# Common stopwords to exclude
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must',
    'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
    'not', 'no', 'yes', 'na', 'n/a', 'unknown', 'various', 'multiple', 'general', 'other'
}

# Domain-specific stopwords for code analysis
CODE_STOPWORDS = STOPWORDS | {
    'repository', 'specified', 'available', 'tools', 'analysis',
    'processing', 'using', 'implements', 'based', 'frameworks', 'framework', 'appears'
}

# Domain-specific stopwords for cell model themes
CELL_MODEL_STOPWORDS = STOPWORDS | {
    'variant', 'gene', 'polymorphism', 'allele', 'located',
    'genetic', 'studies', 'associated', 'including', 'role', 'disease',
    'through', 'single', 'chromosome', 'population', 'populations'
}


def load_latest_file(pattern):
    """Load the most recent file matching pattern."""
    files = list(TABLES_DIR.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found matching {pattern}")
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return pd.read_csv(latest, sep='\t', low_memory=False)


def extract_keywords(text_series, top_n=10, min_length=3, custom_stopwords=None, return_repo_pct=False):
    """Extract top keywords from text series, excluding stopwords.

    Args:
        text_series: Series of text to extract keywords from
        top_n: Number of top keywords to return
        min_length: Minimum word length
        custom_stopwords: Optional custom stopwords set
        return_repo_pct: If True, return % of repos containing word instead of % of all words
    """
    stopwords_to_use = custom_stopwords if custom_stopwords is not None else STOPWORDS
    all_words = []

    # Track which repos contain each word (for repo percentage calculation)
    word_repo_counts = Counter()
    total_repos = 0

    for text in text_series.dropna():
        total_repos += 1
        text = str(text).lower()
        # Split on common delimiters
        words = re.split(r'[;,\s\-_/()]+', text)

        # Track unique words in this repo
        unique_words_in_repo = set()

        for word in words:
            word = word.strip()
            if (len(word) >= min_length and
                word not in stopwords_to_use and
                not word.isdigit() and
                word.isalpha()):
                all_words.append(word)
                unique_words_in_repo.add(word)

        # Count this repo for each unique word it contains
        for word in unique_words_in_repo:
            word_repo_counts[word] += 1

    counter = Counter(all_words)

    results = []
    for word, count in counter.most_common(top_n):
        if return_repo_pct:
            # Calculate % of repos containing this word
            repo_count = word_repo_counts[word]
            pct = (repo_count / total_repos * 100) if total_repos > 0 else 0
            results.append((word, repo_count, pct))
        else:
            # Calculate % of all words
            total = len(all_words)
            pct = (count / total * 100) if total > 0 else 0
            results.append((word, count, pct))

    return results


def analyze_datasets():
    """Analyze datasets and return statistics."""
    print("Analyzing Datasets...")
    df = load_latest_file("dataset-inventory-*.tab")

    stats = {}

    # N studies total
    stats['n_datasets'] = len(df)

    # Dataset types (multi-study and biosample)
    if 'Dataset Type' in df.columns:
        dataset_types = df['Dataset Type'].fillna('').str.lower()
        stats['n_multi_study'] = dataset_types.str.contains('multi-study').sum()
        stats['pct_multi_study'] = (stats['n_multi_study'] / len(df) * 100)
        stats['n_biosample'] = dataset_types.str.contains('biosample').sum()
        stats['pct_biosample'] = (stats['n_biosample'] / len(df) * 100)

    # Data modalities - extract coarse types from brackets [coarse] granular format
    if 'Data Modalities' in df.columns:
        coarse_types = []
        for modality in df['Data Modalities'].dropna():
            modality_str = str(modality).strip()
            # Extract text within brackets using regex
            bracket_match = re.match(r'^\[(.*?)\]', modality_str)
            if bracket_match:
                coarse_part = bracket_match.group(1)
                # Split by comma and clean
                types = [t.strip() for t in coarse_part.split(',')]
                coarse_types.extend(types)

        stats['coarse_data_types'] = Counter(coarse_types).most_common()

    # Sample size statistics - extract numbers from strings like "856 participants"
    if 'Sample Size' in df.columns:
        sample_sizes = []
        for size_str in df['Sample Size'].dropna():
            # Extract numeric part (handle commas and + signs)
            match = re.search(r'([\d,]+)', str(size_str))
            if match:
                try:
                    num = float(match.group(1).replace(',', ''))
                    sample_sizes.append(num)
                except ValueError:
                    pass

        if sample_sizes:
            stats['sample_size_mean'] = np.mean(sample_sizes)
            stats['sample_size_median'] = np.median(sample_sizes)
            stats['sample_size_min'] = min(sample_sizes)
            stats['sample_size_max'] = max(sample_sizes)
            stats['sample_size_std'] = np.std(sample_sizes)

    # FAIR compliance levels
    if 'FAIR Compliance Notes' in df.columns:
        fair_levels = {'Excellent': 0, 'Strong': 0, 'Good': 0}
        for note in df['FAIR Compliance Notes'].dropna():
            note_lower = str(note).lower()
            if 'excellent' in note_lower:
                fair_levels['Excellent'] += 1
            elif 'strong' in note_lower:
                fair_levels['Strong'] += 1
            elif 'good' in note_lower:
                fair_levels['Good'] += 1

        stats['fair_levels'] = fair_levels
        total_with_fair = sum(fair_levels.values())
        stats['fair_levels_pct'] = {k: (v/total_with_fair*100) if total_with_fair > 0 else 0
                                    for k, v in fair_levels.items()}

    return stats


def analyze_publications():
    """Analyze publications and return statistics."""
    print("Analyzing Publications...")
    df = load_latest_file("pubmed_central_*.tsv")

    stats = {}

    # Five most prolific studies
    if 'Study Name' in df.columns:
        stats['top_studies'] = df['Study Name'].value_counts().head(5).to_dict()

    # Five most occurring authors
    if 'Authors' in df.columns:
        all_authors = []
        for authors in df['Authors'].dropna():
            author_list = [a.strip() for a in str(authors).split(';')]
            all_authors.extend(author_list)
        stats['top_authors'] = Counter(all_authors).most_common(5)

    # Five most occurring affiliations - normalize similar entries
    if 'Affiliations' in df.columns:
        all_affiliations = []
        for affs in df['Affiliations'].dropna():
            aff_list = [a.strip() for a in str(affs).split(';')]
            all_affiliations.extend(aff_list)

        # Normalize location abbreviations (IL -> Illinois, MN -> Minnesota)
        normalized_affiliations = []
        for aff in all_affiliations:
            # Normalize Chicago, IL to Chicago, Illinois for Rush entries
            if 'Rush Alzheimer\'s Disease Center' in aff and 'Chicago, IL' in aff:
                aff = aff.replace('Chicago, IL', 'Chicago, Illinois')
            # Normalize Rochester, MN to Rochester, Minnesota for Mayo Clinic entries
            if 'Mayo Clinic, Rochester, MN' in aff:
                aff = aff.replace('Rochester, MN', 'Rochester, Minnesota')
            normalized_affiliations.append(aff)

        stats['top_affiliations'] = Counter(normalized_affiliations).most_common(5)

    # Coarse data types
    if 'Coarse Data Types' in df.columns:
        data_types = []
        for dt in df['Coarse Data Types'].dropna():
            data_types.extend([x.strip() for x in str(dt).split(';')])
        stats['coarse_data_types'] = Counter(data_types).most_common()

    # Top keywords
    if 'Keywords' in df.columns:
        stats['top_keywords'] = extract_keywords(df['Keywords'], top_n=10)

    # Data completeness distribution
    completeness_fields = ['PubMed Central Link', 'Abstract', 'Keywords', 'Authors', 'Affiliations']
    available_fields = [f for f in completeness_fields if f in df.columns]

    if available_fields:
        completeness_scores = []
        for _, row in df.iterrows():
            complete_count = sum(1 for f in available_fields if pd.notna(row.get(f)) and str(row.get(f)).strip())
            completeness_pct = (complete_count / len(available_fields)) * 100
            completeness_scores.append(completeness_pct)

        stats['completeness_mean'] = np.mean(completeness_scores)
        stats['completeness_median'] = np.median(completeness_scores)
        stats['completeness_std'] = np.std(completeness_scores)

        # Distribution bins
        bins = [0, 25, 50, 75, 100]
        labels = ['0-25%', '26-50%', '51-75%', '76-100%']
        hist, _ = np.histogram(completeness_scores, bins=[0, 25, 50, 75, 100])
        stats['completeness_dist'] = dict(zip(labels, hist))

    return stats


def analyze_code_repos():
    """Analyze code repositories and return statistics."""
    print("Analyzing Code Repositories...")

    # Load all git batch files
    git_files = list(TABLES_DIR.glob("gits_batch*.tsv")) + list(TABLES_DIR.glob("gits_to_reannotate*.tsv"))

    if not git_files:
        print("No git repository files found")
        return {}

    dfs = []
    for f in git_files:
        try:
            dfs.append(pd.read_csv(f, sep='\t', low_memory=False))
        except Exception as e:
            print(f"Error loading {f}: {e}")

    if not dfs:
        return {}

    df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=['Repository Link'], keep='first')

    # Load and merge FAIR compliance data
    scrapers_dir = TABLES_DIR.parent / "scrapers"
    fair_files = list(scrapers_dir.glob("fair_compliance_log_*.tsv"))
    if fair_files:
        fair_dfs = []
        for f in fair_files:
            try:
                fair_dfs.append(pd.read_csv(f, sep='\t', low_memory=False))
            except Exception as e:
                print(f"Error loading FAIR log {f}: {e}")

        if fair_dfs:
            fair_df = pd.concat(fair_dfs, ignore_index=True)

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
            df = df.merge(
                fair_summary[['Repository Link', 'FAIR Issues', 'FAIR Score']],
                on='Repository Link',
                how='left'
            )

            # Fill NaN values
            df['FAIR Issues'] = df['FAIR Issues'].fillna("")
            df['FAIR Score'] = df['FAIR Score'].fillna(10)  # No issues = perfect score

    stats = {}
    stats['n_repositories'] = len(df)

    # Top languages
    if 'Languages' in df.columns:
        all_languages = []
        for langs in df['Languages'].dropna():
            lang_list = [l.strip() for l in str(langs).split(';')]
            all_languages.extend(lang_list)
        stats['top_languages'] = Counter(all_languages).most_common(10)

    # Top keywords from Tooling - use code-specific stopwords, return % repositories
    if 'Tooling' in df.columns:
        stats['top_tooling'] = extract_keywords(df['Tooling'], top_n=10, custom_stopwords=CODE_STOPWORDS, return_repo_pct=True)

    # Top keywords from Data Types - use code-specific stopwords, return % repositories
    if 'Data Types' in df.columns:
        stats['top_data_types'] = extract_keywords(df['Data Types'], top_n=10, custom_stopwords=CODE_STOPWORDS, return_repo_pct=True)

    # Top keywords from Code Summary - use code-specific stopwords, return % repositories
    if 'Code Summary' in df.columns:
        stats['top_code_summary'] = extract_keywords(df['Code Summary'], top_n=10, min_length=4, custom_stopwords=CODE_STOPWORDS, return_repo_pct=True)

    # FAIR completeness from FAIR Issues
    if 'FAIR Issues' in df.columns:
        # Map component names to their issue type strings
        issue_type_map = {
            'README': 'No README',
            'Dependencies': 'No Dependencies',
            'Version Info': 'No Version Info',
            'Container': 'No Container',
            'Environment Spec': 'No Environment Spec'
        }

        fair_components = {k: 0 for k in issue_type_map.keys()}
        total_repos = len(df)

        for issues in df['FAIR Issues'].dropna():
            issues_str = str(issues)
            for component, issue_type in issue_type_map.items():
                # If issue type is NOT in the issues string, component is present
                if issue_type not in issues_str:
                    fair_components[component] += 1

        # Also count repos with NO issues at all (they have everything)
        repos_without_issues = df['FAIR Issues'].isna().sum()
        for component in fair_components.keys():
            fair_components[component] += repos_without_issues

        stats['fair_completeness'] = {k: (v/total_repos*100) if total_repos > 0 else 0
                                      for k, v in fair_components.items()}

    return stats


def analyze_cell_models():
    """Analyze human cellular models and return statistics."""
    print("Analyzing Human Cellular Models...")
    df = load_latest_file("iNDI_inventory_*.tsv")

    stats = {}
    stats['n_cell_models'] = len(df)

    # N and % per condition - top 10, excluding 0 entries
    if 'Condition' in df.columns:
        condition_counts = df['Condition'].value_counts()
        # Filter out '0' entries
        condition_counts = condition_counts[condition_counts.index != '0']
        # Get top 10
        top_conditions = condition_counts.head(10)
        stats['conditions'] = top_conditions.to_dict()
        stats['conditions_pct'] = (top_conditions / len(df) * 100).to_dict()

    # Most common genes
    if 'Gene' in df.columns:
        all_genes = []
        for gene in df['Gene'].dropna():
            # Genes might be semicolon separated or single values
            if ';' in str(gene):
                gene_list = [g.strip() for g in str(gene).split(';')]
                all_genes.extend(gene_list)
            else:
                gene_str = str(gene).strip()
                if gene_str and gene_str.lower() != 'nan':
                    all_genes.append(gene_str)
        stats['top_genes'] = Counter(all_genes).most_common(10)

    # Thematic keywords from gene descriptions - use cell model-specific stopwords, return % cell models
    if 'About this gene' in df.columns:
        stats['top_gene_themes'] = extract_keywords(df['About this gene'], top_n=10, min_length=4, custom_stopwords=CELL_MODEL_STOPWORDS, return_repo_pct=True)

    if 'About this variant' in df.columns:
        stats['top_variant_themes'] = extract_keywords(df['About this variant'], top_n=10, min_length=4, custom_stopwords=CELL_MODEL_STOPWORDS, return_repo_pct=True)

    return stats


def format_output(datasets_stats, pubs_stats, code_stats, cell_stats):
    """Format all statistics into a readable report."""
    output = []

    output.append("=" * 80)
    output.append("CARD CATALOG - MAIN DESCRIPTIVE STATISTICS TABLE")
    output.append("=" * 80)
    output.append("")

    # DATASETS
    output.append("DATASETS")
    output.append("-" * 80)
    output.append(f"Total Datasets: {datasets_stats.get('n_datasets', 'N/A')}")
    output.append("")

    if 'n_multi_study' in datasets_stats:
        output.append(f"Multi-study Datasets: {datasets_stats['n_multi_study']} ({datasets_stats['pct_multi_study']:.1f}%)")
    if 'n_biosample' in datasets_stats:
        output.append(f"Biosample Datasets: {datasets_stats['n_biosample']} ({datasets_stats['pct_biosample']:.1f}%)")
    output.append("")

    if 'coarse_data_types' in datasets_stats:
        output.append("Coarse Data Types:")
        total_types = sum(count for _, count in datasets_stats['coarse_data_types'])
        for dtype, count in datasets_stats['coarse_data_types']:
            pct = (count / total_types * 100) if total_types > 0 else 0
            output.append(f"  {dtype}: {count} ({pct:.1f}%)")
        output.append("")

    if 'sample_size_mean' in datasets_stats:
        output.append("Sample Size Statistics:")
        output.append(f"  Mean: {datasets_stats['sample_size_mean']:.0f}")
        output.append(f"  Median: {datasets_stats['sample_size_median']:.0f}")
        output.append(f"  Min: {datasets_stats['sample_size_min']:.0f}")
        output.append(f"  Max: {datasets_stats['sample_size_max']:.0f}")
        output.append(f"  Std Dev: {datasets_stats['sample_size_std']:.0f}")
        output.append("")

    if 'fair_levels' in datasets_stats:
        output.append("FAIR Compliance Levels:")
        for level, count in datasets_stats['fair_levels'].items():
            pct = datasets_stats['fair_levels_pct'][level]
            output.append(f"  {level}: {count} ({pct:.1f}%)")
        output.append("")

    output.append("")

    # PUBLICATIONS
    output.append("PUBLICATIONS")
    output.append("-" * 80)

    if 'top_studies' in pubs_stats:
        output.append("Five Most Prolific Studies:")
        for study, count in pubs_stats['top_studies'].items():
            output.append(f"  {study}: {count}")
        output.append("")

    if 'top_authors' in pubs_stats:
        output.append("Five Most Occurring Authors:")
        for author, count in pubs_stats['top_authors']:
            output.append(f"  {author}: {count}")
        output.append("")

    if 'top_affiliations' in pubs_stats:
        output.append("Five Most Occurring Affiliations:")
        for aff, count in pubs_stats['top_affiliations']:
            output.append(f"  {aff}: {count}")
        output.append("")

    if 'coarse_data_types' in pubs_stats:
        output.append("Coarse Data Types:")
        total_types = sum(count for _, count in pubs_stats['coarse_data_types'])
        for dtype, count in pubs_stats['coarse_data_types'][:10]:
            pct = (count / total_types * 100) if total_types > 0 else 0
            output.append(f"  {dtype}: {count} ({pct:.1f}%)")
        output.append("")

    if 'top_keywords' in pubs_stats:
        output.append("Top 10 Keywords:")
        for word, count, pct in pubs_stats['top_keywords']:
            output.append(f"  {word}: {count} ({pct:.1f}%)")
        output.append("")

    if 'completeness_mean' in pubs_stats:
        output.append("Data Completeness Distribution from PubMed API:")
        output.append(f"  Mean: {pubs_stats['completeness_mean']:.1f}%")
        output.append(f"  Median: {pubs_stats['completeness_median']:.1f}%")
        output.append(f"  Std Dev: {pubs_stats['completeness_std']:.1f}%")
        if 'completeness_dist' in pubs_stats:
            output.append("  Distribution:")
            for range_label, count in pubs_stats['completeness_dist'].items():
                output.append(f"    {range_label}: {count}")
        output.append("")

    output.append("")

    # CODE REPOSITORIES
    output.append("CODE REPOSITORIES")
    output.append("-" * 80)
    output.append(f"Total Repositories: {code_stats.get('n_repositories', 'N/A')}")
    output.append("")

    if 'top_languages' in code_stats:
        output.append("Top Programming Languages:")
        total_repos = code_stats.get('n_repositories', 1)
        for lang, count in code_stats['top_languages']:
            pct = (count / total_repos * 100) if total_repos > 0 else 0
            output.append(f"  {lang}: {count} ({pct:.1f}%)")
        output.append("")

    if 'top_tooling' in code_stats:
        output.append("Top 10 Keywords from Tooling:")
        for word, count, pct in code_stats['top_tooling']:
            output.append(f"  {word}: {count} ({pct:.1f}%)")
        output.append("")

    if 'top_data_types' in code_stats:
        output.append("Top 10 Keywords from Data Types:")
        for word, count, pct in code_stats['top_data_types']:
            output.append(f"  {word}: {count} ({pct:.1f}%)")
        output.append("")

    if 'top_code_summary' in code_stats:
        output.append("Top 10 Keywords from Code Summary:")
        for word, count, pct in code_stats['top_code_summary']:
            output.append(f"  {word}: {count} ({pct:.1f}%)")
        output.append("")

    if 'fair_completeness' in code_stats:
        output.append("FAIR Component Completeness (% with component):")
        for component, pct in sorted(code_stats['fair_completeness'].items(), key=lambda x: x[1], reverse=True):
            output.append(f"  {component}: {pct:.1f}%")
        output.append("")

    output.append("")

    # HUMAN CELLULAR MODELS
    output.append("HUMAN CELLULAR MODELS")
    output.append("-" * 80)
    output.append(f"Total Cell Models: {cell_stats.get('n_cell_models', 'N/A')}")
    output.append("")

    if 'conditions' in cell_stats:
        output.append("Cell Models per Condition:")
        for condition, count in cell_stats['conditions'].items():
            pct = cell_stats['conditions_pct'][condition]
            output.append(f"  {condition}: {count} ({pct:.1f}%)")
        output.append("")

    if 'top_genes' in cell_stats:
        output.append("Most Common Genes:")
        for gene, count in cell_stats['top_genes']:
            output.append(f"  {gene}: {count}")
        output.append("")

    if 'top_gene_themes' in cell_stats:
        output.append("Top Themes from Gene Descriptions:")
        for word, count, pct in cell_stats['top_gene_themes']:
            output.append(f"  {word}: {count} ({pct:.1f}%)")
        output.append("")

    if 'top_variant_themes' in cell_stats:
        output.append("Top Themes from Variant Descriptions:")
        for word, count, pct in cell_stats['top_variant_themes']:
            output.append(f"  {word}: {count} ({pct:.1f}%)")
        output.append("")

    output.append("=" * 80)

    return "\n".join(output)


def main():
    """Main execution function."""
    print("Generating CARD Catalog Main Statistics Table...")
    print()

    # Run all analyses
    datasets_stats = analyze_datasets()
    pubs_stats = analyze_publications()
    code_stats = analyze_code_repos()
    cell_stats = analyze_cell_models()

    # Format output
    report = format_output(datasets_stats, pubs_stats, code_stats, cell_stats)

    # Save to file
    output_file = OUTPUT_DIR / "main_statistics_table.txt"
    with open(output_file, 'w') as f:
        f.write(report)

    print()
    print(f"Report saved to: {output_file}")
    print()
    print(report)


if __name__ == "__main__":
    main()
