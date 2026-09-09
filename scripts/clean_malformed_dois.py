"""Clean garbage-suffixed DOIs and drop the duplicates they created.

page_navigation's raw extraction (staging/publication_glue.py's
_extract_doc_ref) uses a DOI regex that doesn't stop at "?" or "\\", so a
site presenting the same paper's DOI through more than one link
construction - a plain doi.org link, a redirect/analytics wrapper
(?domain=..., ?url_ver=...), or a JS/JSON string with a stray escaped
backslash - produces one extra row per variant, each with a DOI value the
real DOI plus junk glued on. Confirmed on real data (2026-09-08 session):
NACC's publications page alone produced 3 literal DOI strings for one paper.

For each row whose DOI has this junk: if a clean-DOI row for the same paper
already exists (case-insensitive base-DOI match) with a real Title, the
garbage row is a pure duplicate and is dropped, backfilling anything blank
on the clean row from it first (same non-destructive convention as
dedup_publications_preprints.py). If no clean row exists yet, the DOI is
simply cleaned in place so normal resolution (idconv/efetch) can find it on
a future run.

Run from anywhere in the repo:
    python3 scripts/clean_malformed_dois.py [--dry-run]
"""
import argparse
import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
FINAL_DIR = PROJECT_ROOT / "tables" / "final"

CLEAN_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s?\\]+")
BACKFILL_COLS = ["PMID", "DOI", "PubMed Central Link", "Authors", "Affiliations",
                 "Abstract", "Keywords", "Publication Date"]


def clean_doi(doi: str) -> str:
    m = CLEAN_DOI_RE.match(str(doi or "").strip())
    return m.group(0) if m else str(doi or "").strip()


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

    df["_clean_doi"] = df["DOI"].apply(clean_doi)
    malformed_mask = (df["DOI"].str.strip() != "") & (df["DOI"] != df["_clean_doi"])
    n_malformed = int(malformed_mask.sum())
    logger.info(f"{n_malformed} row(s) with a garbage-suffixed DOI")

    titled_by_doi_lower = {
        doi.lower(): idx
        for idx, doi in df[df["Title"].str.strip() != ""]["DOI"].items()
        if doi.strip()
    }

    to_drop = []
    n_dupe_dropped = 0
    n_cleaned = 0
    for idx in df[malformed_mask].index:
        clean = df.at[idx, "_clean_doi"]
        match_idx = titled_by_doi_lower.get(clean.lower())
        if match_idx is not None and match_idx != idx:
            for col in BACKFILL_COLS:
                if df.at[match_idx, col].strip():
                    continue
                if df.at[idx, col].strip():
                    df.at[match_idx, col] = df.at[idx, col]
            to_drop.append(idx)
            n_dupe_dropped += 1
        else:
            df.at[idx, "DOI"] = clean
            n_cleaned += 1

    logger.info(f"Dropped {n_dupe_dropped} duplicate(s) of an already-titled clean row; "
                f"cleaned {n_cleaned} DOI(s) in place with no existing counterpart")

    df = df.drop(index=to_drop).drop(columns=["_clean_doi"])
    logger.info(f"{len(df)} row(s) remain")

    if args.dry_run:
        logger.info("Dry run - not writing changes")
        return

    df.to_csv(pubs_path, sep="\t", index=False)
    logger.info(f"Wrote {len(df)} rows → {pubs_path.name} - run `npm run sync-data` in web/ to refresh the app's copy")


if __name__ == "__main__":
    main()
