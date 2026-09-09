"""Backfill blank Title/Abstract/etc. in misc_publications for page_navigation rows.

extract_new_corpus_publications() (staging/publication_glue.py) previously only
backfilled full metadata for bare-PMID references; DOI/PMC-only references
extracted directly from a resource's own publications page kept no Title/
Abstract/Authors at all, even though they're independently verified against
full text downstream (confirmed genuine - see the session's cache spot-check
across 6 resources, all "confirmed"). That gap is now fixed in
extract_new_corpus_publications() itself; this script re-runs the (now-fixed)
extraction and patches the already-normalized misc_publications table in
place with whatever new metadata it resolved, rather than re-running the full
orchestrator merge/verify pipeline (which would re-touch every row, not just
these ~286, and risk a live LLM call for anything not already cached).

No live Anthropic calls: only NCBI's ID Converter + efetch (already run once
by extract_new_corpus_publications() itself) are hit, and only Title/Abstract/
Authors/Affiliations/Keywords/Publication Date are patched - Verification
Status, Resource Name, and every other column are left untouched.

Run from anywhere in the repo:
    python3 scripts/backfill_new_corpus_metadata.py [--dry-run]
"""
import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from staging.publication_glue import extract_new_corpus_publications  # noqa: E402

logger = logging.getLogger(__name__)

FINAL_DIR = PROJECT_ROOT / "tables" / "final"

BACKFILL_COLS = ["Title", "Abstract", "Authors", "Affiliations", "Keywords", "Publication Date"]

PMCID_RE = re.compile(r"PMC\d+")


def pmcid_from(value: str) -> str:
    m = PMCID_RE.search(str(value or ""))
    return m.group(0) if m else ""


def identifiers_for(row: pd.Series) -> list[str]:
    """Every identifier a row could be matched on, most specific first."""
    ids = []
    if row.get("PMID", "").strip():
        ids.append(row["PMID"].strip())
    if row.get("DOI", "").strip():
        ids.append(row["DOI"].strip())
    pmc = pmcid_from(row.get("PubMed Central Link", ""))
    if pmc:
        ids.append(pmc)
    return ids


def latest_final(pattern: str) -> Path | None:
    matches = sorted(FINAL_DIR.glob(pattern))
    return matches[-1] if matches else None


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    pubs_path = latest_final("misc_publications_*.tsv")
    if not pubs_path:
        logger.error("No misc_publications_*.tsv found in tables/final/")
        return
    df = pd.read_csv(pubs_path, sep="\t", dtype=str).fillna("")
    logger.info(f"Loaded {len(df)} rows from {pubs_path.name}")

    is_nav = df["Fetched With"].str.startswith("page navigation")
    blank_mask = is_nav & (df["Title"].str.strip() == "")
    n_blank = int(blank_mask.sum())
    logger.info(f"{n_blank} page-navigation row(s) with blank Title")
    if n_blank == 0:
        return

    logger.info("Re-running extract_new_corpus_publications() with the metadata-backfill fix…")
    nav_pubs = extract_new_corpus_publications().fillna("").astype(str)

    # Index nav_pubs by every identifier it carries, for lookup by whichever
    # identifier the misc_publications row happens to have.
    lookup: dict[str, pd.Series] = {}
    for _, r in nav_pubs.iterrows():
        if not str(r.get("Title", "")).strip():
            continue  # only rows the fix actually resolved are useful as a source
        for ident in identifiers_for(r):
            lookup.setdefault(ident, r)

    n_resolved = 0
    for idx in df[blank_mask].index:
        row = df.loc[idx]
        match = next((lookup[i] for i in identifiers_for(row) if i in lookup), None)
        if match is None:
            continue
        for col in BACKFILL_COLS:
            val = str(match.get(col, "")).strip()
            if val:
                df.at[idx, col] = val
        n_resolved += 1

    logger.info(f"Resolved {n_resolved}/{n_blank} previously-blank row(s) from the re-extraction")
    still_blank = int((blank_mask & (df["Title"].str.strip() == "")).sum())
    logger.info(f"{still_blank} row(s) remain blank (idconv/PubMed has no record for their DOI/PMC ID)")

    if args.dry_run:
        logger.info("Dry run - not writing changes")
        return

    df.to_csv(pubs_path, sep="\t", index=False)
    logger.info(f"Wrote {len(df)} rows → {pubs_path.name} - run `npm run sync-data` in web/ to refresh the app's copy")


if __name__ == "__main__":
    main()
