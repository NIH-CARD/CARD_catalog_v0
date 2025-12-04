#!/usr/bin/env python3
"""
Merge all GitHub batch files and insufficient reprocessed repos into one combined dataset
"""
import pandas as pd
from datetime import datetime

# Read all batch files
batch1 = pd.read_csv('../tables/gits_batch1of4_20251130_121637.tsv', sep='\t')
batch2 = pd.read_csv('../tables/gits_batch2of4_20251130_223027.tsv', sep='\t')
batch3 = pd.read_csv('../tables/gits_batch3of4_20251201_023030.tsv', sep='\t')
batch4 = pd.read_csv('../tables/gits_batch4of4_20251201_063032.tsv', sep='\t')
insufficient = pd.read_csv('../tables/insufficient_reprocessed_20251202_113816.tsv', sep='\t')

print(f"Batch 1: {len(batch1)} repos")
print(f"Batch 2: {len(batch2)} repos")
print(f"Batch 3: {len(batch3)} repos")
print(f"Batch 4: {len(batch4)} repos")
print(f"Insufficient reprocessed: {len(insufficient)} repos")

# Combine all dataframes
combined = pd.concat([batch1, batch2, batch3, batch4, insufficient], ignore_index=True)
print(f"\nTotal before deduplication: {len(combined)} repos")

# Remove duplicates based on Repository Link
combined_dedup = combined.drop_duplicates(subset=['Repository Link'], keep='first')
print(f"Total after deduplication: {len(combined_dedup)} repos")
print(f"Duplicates removed: {len(combined) - len(combined_dedup)}")

# Save combined file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = f"../tables/gits_to_reannotate_completed_{timestamp}.tsv"
combined_dedup.to_csv(output_file, sep='\t', index=False)

print(f"\n{'='*60}")
print(f"✅ Combined dataset saved to: {output_file}")
print(f"📊 Final repository count: {len(combined_dedup)}")
print(f"{'='*60}")
