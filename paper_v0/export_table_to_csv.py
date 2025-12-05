"""
Export main statistics table to wide-format CSV for Google Sheets/Excel.
"""

import pandas as pd
import numpy as np
from collections import Counter
import re
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import from generate_main_table
from generate_main_table import (
    analyze_datasets, analyze_publications,
    analyze_code_repos, analyze_cell_models
)

OUTPUT_DIR = Path(__file__).parent


def create_wide_csv():
    """Create wide-format CSV with statistics."""

    print("Generating statistics...")
    datasets_stats = analyze_datasets()
    pubs_stats = analyze_publications()
    code_stats = analyze_code_repos()
    cell_stats = analyze_cell_models()

    # Create list to hold all rows
    rows = []

    # DATASETS SECTION
    rows.append(['DATASETS', '', '', ''])
    rows.append(['Metric', 'Value', 'Count', 'Percentage'])
    rows.append(['Total Datasets', datasets_stats.get('n_datasets', ''), '', ''])
    rows.append(['Multi-study Datasets', datasets_stats.get('n_multi_study', ''), datasets_stats.get('n_multi_study', ''), f"{datasets_stats.get('pct_multi_study', 0):.1f}%"])
    rows.append(['Biosample Datasets', datasets_stats.get('n_biosample', ''), datasets_stats.get('n_biosample', ''), f"{datasets_stats.get('pct_biosample', 0):.1f}%"])
    rows.append(['', '', '', ''])

    # Coarse data types
    rows.append(['Coarse Data Types', '', '', ''])
    if 'coarse_data_types' in datasets_stats:
        total_types = sum(count for _, count in datasets_stats['coarse_data_types'])
        for dtype, count in datasets_stats['coarse_data_types']:
            pct = (count / total_types * 100) if total_types > 0 else 0
            rows.append([dtype, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # Sample size statistics
    rows.append(['Sample Size Statistics', '', '', ''])
    if 'sample_size_mean' in datasets_stats:
        rows.append(['Mean', f"{datasets_stats['sample_size_mean']:.0f}", '', ''])
        rows.append(['Median', f"{datasets_stats['sample_size_median']:.0f}", '', ''])
        rows.append(['Min', f"{datasets_stats['sample_size_min']:.0f}", '', ''])
        rows.append(['Max', f"{datasets_stats['sample_size_max']:.0f}", '', ''])
        rows.append(['Std Dev', f"{datasets_stats['sample_size_std']:.0f}", '', ''])
    rows.append(['', '', '', ''])

    # FAIR compliance
    rows.append(['FAIR Compliance Levels', '', '', ''])
    if 'fair_levels' in datasets_stats:
        for level, count in datasets_stats['fair_levels'].items():
            pct = datasets_stats['fair_levels_pct'][level]
            rows.append([level, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # PUBLICATIONS SECTION
    rows.append(['PUBLICATIONS', '', '', ''])
    rows.append(['', '', '', ''])

    # Top studies
    rows.append(['Five Most Prolific Studies', '', '', ''])
    if 'top_studies' in pubs_stats:
        for study, count in pubs_stats['top_studies'].items():
            rows.append([study, '', count, ''])
    rows.append(['', '', '', ''])

    # Top authors
    rows.append(['Five Most Occurring Authors', '', '', ''])
    if 'top_authors' in pubs_stats:
        for author, count in pubs_stats['top_authors']:
            rows.append([author, '', count, ''])
    rows.append(['', '', '', ''])

    # Top affiliations
    rows.append(['Five Most Occurring Affiliations', '', '', ''])
    if 'top_affiliations' in pubs_stats:
        for aff, count in pubs_stats['top_affiliations']:
            rows.append([aff, '', count, ''])
    rows.append(['', '', '', ''])

    # Top keywords
    rows.append(['Top 10 Keywords', '', '', ''])
    if 'top_keywords' in pubs_stats:
        for word, count, pct in pubs_stats['top_keywords']:
            rows.append([word, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # Data completeness
    rows.append(['Data Completeness Distribution from PubMed API', '', '', ''])
    if 'completeness_mean' in pubs_stats:
        rows.append(['Mean', f"{pubs_stats['completeness_mean']:.1f}%", '', ''])
        rows.append(['Median', f"{pubs_stats['completeness_median']:.1f}%", '', ''])
        rows.append(['Std Dev', f"{pubs_stats['completeness_std']:.1f}%", '', ''])
        if 'completeness_dist' in pubs_stats:
            rows.append(['Distribution', '', '', ''])
            for range_label, count in pubs_stats['completeness_dist'].items():
                rows.append([range_label, '', count, ''])
    rows.append(['', '', '', ''])

    # CODE REPOSITORIES SECTION
    rows.append(['CODE REPOSITORIES', '', '', ''])
    rows.append(['Total Repositories', code_stats.get('n_repositories', ''), '', ''])
    rows.append(['', '', '', ''])

    # Top languages
    rows.append(['Top Programming Languages', '', '', ''])
    if 'top_languages' in code_stats:
        total_repos = code_stats.get('n_repositories', 1)
        for lang, count in code_stats['top_languages']:
            pct = (count / total_repos * 100) if total_repos > 0 else 0
            rows.append([lang, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # Top tooling keywords
    rows.append(['Top 10 Keywords from Tooling', '', '% Repositories', ''])
    if 'top_tooling' in code_stats:
        for word, count, pct in code_stats['top_tooling']:
            rows.append([word, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # Top data types keywords
    rows.append(['Top 10 Keywords from Data Types', '', '% Repositories', ''])
    if 'top_data_types' in code_stats:
        for word, count, pct in code_stats['top_data_types']:
            rows.append([word, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # Top code summary keywords
    rows.append(['Top 10 Keywords from Code Summary', '', '% Repositories', ''])
    if 'top_code_summary' in code_stats:
        for word, count, pct in code_stats['top_code_summary']:
            rows.append([word, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # FAIR completeness
    rows.append(['FAIR Component Completeness', '', '% with component', ''])
    if 'fair_completeness' in code_stats:
        for component, pct in sorted(code_stats['fair_completeness'].items(), key=lambda x: x[1], reverse=True):
            rows.append([component, '', '', f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # HUMAN CELLULAR MODELS SECTION
    rows.append(['HUMAN CELLULAR MODELS', '', '', ''])
    rows.append(['Total Cell Models', cell_stats.get('n_cell_models', ''), '', ''])
    rows.append(['', '', '', ''])

    # Cell models per condition
    rows.append(['Cell Models per Condition (Top 10)', '', '', ''])
    if 'conditions' in cell_stats:
        for condition, count in cell_stats['conditions'].items():
            pct = cell_stats['conditions_pct'][condition]
            rows.append([condition, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # Most common genes
    rows.append(['Most Common Genes', '', '', ''])
    if 'top_genes' in cell_stats:
        for gene, count in cell_stats['top_genes']:
            rows.append([gene, '', count, ''])
    rows.append(['', '', '', ''])

    # Top gene themes
    rows.append(['Top Themes from Gene Descriptions', '', '% Cell Models', ''])
    if 'top_gene_themes' in cell_stats:
        for word, count, pct in cell_stats['top_gene_themes']:
            rows.append([word, '', count, f"{pct:.1f}%"])
    rows.append(['', '', '', ''])

    # Top variant themes
    rows.append(['Top Themes from Variant Descriptions', '', '% Cell Models', ''])
    if 'top_variant_themes' in cell_stats:
        for word, count, pct in cell_stats['top_variant_themes']:
            rows.append([word, '', count, f"{pct:.1f}%"])

    # Create DataFrame and save
    df = pd.DataFrame(rows)

    # Save to CSV
    output_file = OUTPUT_DIR / "main_statistics_table.csv"
    df.to_csv(output_file, index=False, header=False)
    print(f"\nCSV saved to: {output_file}")

    # Also save as TSV for easier pasting
    output_tsv = OUTPUT_DIR / "main_statistics_table.tsv"
    df.to_csv(output_tsv, sep='\t', index=False, header=False)
    print(f"TSV saved to: {output_tsv}")

    return df


def main():
    """Main execution function."""
    print("="*70)
    print("Exporting CARD Catalog Statistics to Wide-Format CSV/TSV")
    print("="*70)
    print()

    df = create_wide_csv()

    print()
    print(f"Export complete! Files can be imported into Google Sheets or Excel.")
    print("="*70)


if __name__ == "__main__":
    main()
