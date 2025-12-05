"""
Generate Figure 2 (v2): CARD Catalog Landscape - Simplified 3-Panel Version

Panel A: Coarse data types per study count, colored by FAIR compliance
Panel B: Code languages heatmap showing what's missing (README, LICENSE, etc.) with N repositories
Panel C: Multi-curve density plot of sample size distributions by coarse data type (log scale)
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import pandas as pd
import numpy as np
from pathlib import Path
import re
from collections import Counter, defaultdict
from scipy.stats import gaussian_kde

# Paths
TABLES_DIR = Path(__file__).parent.parent / "tables"
SCRAPERS_DIR = Path(__file__).parent.parent / "scrapers"
OUTPUT_DIR = Path(__file__).parent


def load_latest_file(pattern, directory=TABLES_DIR):
    """Load the most recent file matching pattern."""
    files = list(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found matching {pattern}")
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return pd.read_csv(latest, sep='\t', low_memory=False)


def extract_coarse_types(data_modalities_str):
    """Extract coarse data types from Data Modalities string."""
    if pd.isna(data_modalities_str) or not str(data_modalities_str).strip():
        return []

    modality_str = str(data_modalities_str).strip()
    bracket_match = re.match(r'^\[(.*?)\]', modality_str)
    if bracket_match:
        coarse_part = bracket_match.group(1)
        types = [t.strip() for t in coarse_part.split(',')]
        return types
    return []


def get_fair_level(fair_note):
    """Get FAIR level from compliance note."""
    if pd.isna(fair_note):
        return 'Unknown'

    note_lower = str(fair_note).lower()
    if 'excellent' in note_lower:
        return 'Excellent'
    elif 'strong' in note_lower:
        return 'Strong'
    elif 'good' in note_lower:
        return 'Good'
    else:
        return 'Unknown'


def create_figure():
    """Create the 3-panel landscape figure."""

    # Load data
    print("Loading data...")
    datasets_df = load_latest_file("dataset-inventory-*.tab")

    # Load code repos
    git_files = list(TABLES_DIR.glob("gits_batch*.tsv")) + list(TABLES_DIR.glob("gits_to_reannotate*.tsv"))
    code_dfs = [pd.read_csv(f, sep='\t', low_memory=False) for f in git_files]
    code_df = pd.concat(code_dfs, ignore_index=True).drop_duplicates(subset=['Repository Link'], keep='first')

    # Load FAIR compliance logs
    fair_files = list(SCRAPERS_DIR.glob("fair_compliance_log_*.tsv"))
    fair_issues_by_repo = {}
    if fair_files:
        print("Loading FAIR compliance logs...")
        for fair_file in fair_files:
            fair_df_temp = pd.read_csv(fair_file, sep='\t', low_memory=False)
            for _, row in fair_df_temp.iterrows():
                repo = row.get('Repository', '')
                issue_type = row.get('Issue Type', '')
                if repo and issue_type:
                    if repo not in fair_issues_by_repo:
                        fair_issues_by_repo[repo] = set()
                    fair_issues_by_repo[repo].add(issue_type)

    # Create figure - panel C as wide as A and B combined
    fig = plt.figure(figsize=(24, 9))
    gs = GridSpec(1, 3, figure=fig, left=0.05, right=0.98, top=0.85, bottom=0.10,
                  wspace=0.5, width_ratios=[1, 1, 2])

    # ==================== PANEL A: Coarse Data Types by FAIR ====================
    print("Generating Panel A: Coarse Data Types by FAIR Compliance...")
    ax1 = fig.add_subplot(gs[0, 0])

    # Count data types with FAIR levels
    datatype_fair_counts = defaultdict(lambda: {'Excellent': 0, 'Strong': 0, 'Good': 0})

    for _, row in datasets_df.iterrows():
        coarse_types = extract_coarse_types(row.get('Data Modalities', ''))
        fair_level = get_fair_level(row.get('FAIR Compliance Notes', ''))

        for dtype in coarse_types:
            datatype_fair_counts[dtype][fair_level] += 1

    # Sort by total count
    datatype_totals = {dt: sum(counts.values()) for dt, counts in datatype_fair_counts.items()}
    sorted_datatypes = sorted(datatype_totals.keys(), key=lambda x: datatype_totals[x], reverse=True)

    # Prepare stacked bar data - matching app table colors
    fair_levels = ['Excellent', 'Strong', 'Good']
    fair_colors = {'Excellent': '#006400', 'Strong': '#228B22', 'Good': '#90EE90'}

    # Create stacked bars
    bottoms = np.zeros(len(sorted_datatypes))
    for fair_level in fair_levels:
        counts = [datatype_fair_counts[dt][fair_level] for dt in sorted_datatypes]
        ax1.barh(range(len(sorted_datatypes)), counts, left=bottoms,
                label=fair_level, color=fair_colors[fair_level],
                edgecolor='black', linewidth=0.5)
        bottoms += counts

    ax1.set_yticks(range(len(sorted_datatypes)))
    ax1.set_yticklabels(sorted_datatypes, fontsize=11, rotation=15, ha='right')
    ax1.set_xlabel('Number of Datasets', fontsize=12, fontweight='bold')
    ax1.set_title('A. Data Modalities by FAIR Compliance\n(n=99 datasets)',
                  fontsize=13, fontweight='bold', pad=10)
    ax1.legend(title='FAIR Level', loc='upper right', fontsize=10)
    ax1.grid(axis='x', alpha=0.3)

    # Add total counts at end of bars
    for i, dtype in enumerate(sorted_datatypes):
        total = datatype_totals[dtype]
        ax1.text(total + 1, i, str(total), va='center', fontsize=9, fontweight='bold')

    # ==================== PANEL B: Code Languages Heatmap ====================
    print("Generating Panel B: Code Languages with FAIR Issues...")
    ax2 = fig.add_subplot(gs[0, 1])

    # Get top languages
    all_languages = []
    for langs in code_df['Languages'].dropna():
        lang_list = [l.strip() for l in str(langs).split(';')]
        all_languages.extend(lang_list)

    top_languages = [lang for lang, _ in Counter(all_languages).most_common(8)]

    # Count FAIR issues per language (using actual issue type names from logs)
    issue_types = ['No README', 'No Dependencies', 'No Version Info',
                   'No Container', 'No Environment Spec']

    # Matrix: languages × issue types
    lang_issue_matrix = np.zeros((len(top_languages), len(issue_types)))
    lang_total_repos = {lang: 0 for lang in top_languages}

    for _, row in code_df.iterrows():
        repo_link = row.get('Repository Link', '')
        langs = str(row.get('Languages', '')).split(';')
        langs = [l.strip() for l in langs if l.strip() in top_languages]

        if not langs:
            continue

        # Get issues for this repo
        repo_issues = fair_issues_by_repo.get(repo_link, set())

        for lang in langs:
            lang_idx = top_languages.index(lang)
            lang_total_repos[lang] += 1

            for issue_idx, issue_type in enumerate(issue_types):
                if issue_type in repo_issues:
                    lang_issue_matrix[lang_idx, issue_idx] += 1

    # Convert to percentages
    for i, lang in enumerate(top_languages):
        if lang_total_repos[lang] > 0:
            lang_issue_matrix[i, :] = (lang_issue_matrix[i, :] / lang_total_repos[lang]) * 100

    # Plot heatmap
    im = ax2.imshow(lang_issue_matrix, aspect='auto', cmap='YlOrRd', interpolation='nearest', vmin=0, vmax=100)

    ax2.set_xticks(range(len(issue_types)))
    ax2.set_xticklabels([it.replace('No ', '') for it in issue_types], rotation=45, ha='right', fontsize=11)
    ax2.set_yticks(range(len(top_languages)))
    ax2.set_yticklabels([f"{lang} (n={lang_total_repos[lang]})" for lang in top_languages],
                        fontsize=11, rotation=15, ha='right')
    ax2.set_xlabel('FAIR Component', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Programming Language', fontsize=12, fontweight='bold')
    ax2.set_title('B. Code Repository FAIR Issues by Language\n(% repositories missing component)',
                  fontsize=13, fontweight='bold', pad=10)

    # Add percentage annotations
    for i in range(len(top_languages)):
        for j in range(len(issue_types)):
            value = lang_issue_matrix[i, j]
            if value > 0:
                text_color = 'white' if value > 50 else 'black'
                ax2.text(j, i, f'{value:.0f}%', ha='center', va='center',
                        color=text_color, fontsize=8, fontweight='bold')

    plt.colorbar(im, ax=ax2, label='% Missing')

    # ==================== PANEL C: Sample Size Distributions ====================
    print("Generating Panel C: Sample Size Distributions by Data Type...")
    ax3 = fig.add_subplot(gs[0, 2])

    # Extract sample sizes by coarse data type
    datatype_samples = defaultdict(list)

    for _, row in datasets_df.iterrows():
        # Get sample size
        size_str = str(row.get('Sample Size', ''))
        match = re.search(r'([\d,]+)', size_str)
        if not match:
            continue

        try:
            sample_size = float(match.group(1).replace(',', ''))
            if sample_size < 1:  # Skip invalid sizes
                continue
        except ValueError:
            continue

        # Get coarse types
        coarse_types = extract_coarse_types(row.get('Data Modalities', ''))
        for dtype in coarse_types:
            datatype_samples[dtype].append(sample_size)

    # Plot density curves for top data types
    top_datatypes_for_density = sorted(datatype_samples.keys(),
                                       key=lambda x: len(datatype_samples[x]), reverse=True)[:5]

    colors_density = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

    for idx, dtype in enumerate(top_datatypes_for_density):
        samples = datatype_samples[dtype]
        if len(samples) < 3:  # Need at least 3 points for KDE
            continue

        # Log transform
        log_samples = np.log10(samples)

        # Create KDE
        kde = gaussian_kde(log_samples)
        x_range = np.linspace(log_samples.min(), log_samples.max(), 200)
        density = kde(x_range)

        ax3.plot(10**x_range, density, label=f'{dtype} (n={len(samples)})',
                color=colors_density[idx], linewidth=2)
        ax3.fill_between(10**x_range, density, alpha=0.2, color=colors_density[idx])

    ax3.set_xscale('log')
    ax3.set_xlabel('Sample Size (log scale)', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Density', fontsize=12, fontweight='bold')
    ax3.set_title('C. Sample Size Distributions by Data Modality\n(top 5 modalities)',
                  fontsize=13, fontweight='bold', pad=10)
    ax3.legend(loc='upper right', fontsize=10)
    ax3.tick_params(axis='both', labelsize=10)
    ax3.grid(True, alpha=0.3, which='both')

    # Overall title - positioned well above panel titles
    fig.suptitle('CARD Catalog Landscape: Data Modalities, Code Quality, and Sample Distributions',
                fontsize=15, fontweight='bold', y=0.93)

    output_file = OUTPUT_DIR / "figure2_landscape_v2.png"
    plt.savefig(output_file, dpi=500, bbox_inches='tight', facecolor='white')
    print(f"\nFigure 2 (v2) saved to: {output_file} (500 DPI)")

    output_pdf = OUTPUT_DIR / "figure2_landscape_v2.pdf"
    plt.savefig(output_pdf, bbox_inches='tight', facecolor='white')
    print(f"Figure 2 (v2) PDF saved to: {output_pdf}")

    plt.close()


def main():
    """Generate Figure 2 v2."""
    print("="*70)
    print("Generating Figure 2 (v2): CARD Catalog Landscape - 3 Panel Version")
    print("="*70)

    create_figure()

    print("\nFigure 2 (v2) generation complete!")
    print("="*70)


if __name__ == "__main__":
    main()
