#!/usr/bin/env bash
# Copy the latest TSV files from tables/ into web/public/data/ so the React
# dev server can serve them from /data/*.tsv. Re-run after the pipeline emits
# new outputs.
set -euo pipefail

cd "$(dirname "$0")/.."

FINAL_DIR="../tables/final"
TABLES_DIR="../tables"
DST_DIR="public/data"

mkdir -p "$DST_DIR"

# (source_pattern, dst_name, search_dir)
copy_latest() {
  local pattern="$1"
  local dst="$2"
  local src_dir="$3"
  local latest
  latest=$(ls -t "$src_dir"/$pattern 2>/dev/null | head -1 || true)
  if [[ -z "$latest" ]]; then
    echo "WARN: no $pattern in $src_dir — skipping $dst" >&2
    return
  fi
  cp "$latest" "$DST_DIR/$dst"
  echo "  $latest -> $DST_DIR/$dst"
}

echo "Syncing pipeline outputs → $DST_DIR/"
copy_latest "pubmed_central_*.tsv"             publications.tsv         "$FINAL_DIR"
copy_latest "gits_to_reannotate_completed_*.tsv" code_repos.tsv         "$FINAL_DIR"
copy_latest "pub_datasets_*.tsv"               pub_datasets.tsv         "$FINAL_DIR"
copy_latest "pub_supplementary_*.tsv"          pub_supplementary.tsv    "$FINAL_DIR"
copy_latest "scilite_annotations_*.tsv"        scilite_annotations.tsv  "$FINAL_DIR"

# Resources inventory & iNDI live at the tables/ root, not in final/
copy_latest "resources-inventory-*"            resources.tsv            "$TABLES_DIR"
copy_latest "iNDI_inventory_*"                 cellular_models.tsv      "$TABLES_DIR"

# FAIR compliance log lives in tables/hits/
HITS_DIR="../tables/hits"
copy_latest "fair_compliance_log_*.tsv"        fair_compliance.tsv      "$HITS_DIR"

# Logos for the Home page
mkdir -p public/logos
for f in ADDI.png card_logo.png stacked_DT.png; do
  if [[ -f "../logos/$f" ]]; then
    cp "../logos/$f" "public/logos/$f"
    echo "  ../logos/$f -> public/logos/$f"
  fi
done

echo "Done. Sizes:"
ls -lh "$DST_DIR"
