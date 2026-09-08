"""Collapse preprint/published-version duplicate rows in misc_publications.

combine_query_method_hits() (staging/combine_hits.py) dedupes rows only by
exact shared PMID/DOI/PMC-ID/Paperclip Doc ID. A paper indexed once as a
preprint (bioRxiv/medRxiv/Research Square/...) and again as its peer-reviewed
published version - or, per a PubMed quirk, twice under two different PMIDs
with no shared identifier at all - shares none of those, so both rows survive
as if they were two distinct publications. Confirmed on real data (2026-09-08
session): ~103 same-resource groups (~208 rows, ~2.1% of the 5,086-row table)
sharing an identical normalized title and matching/near-identical Authors,
with genuinely different PMID/DOI.

Policy: keep the published version, not the preprint (see the session's
dedup-policy decision). "Preprint" is detected by known preprint-server DOI
prefixes, or a bioRxiv/medRxiv-style dated DOI suffix (catches newer prefixes
the same servers have since been assigned). Among remaining candidates,
prefers the one with richer data (a non-empty DOI, then the longer Abstract)
as the more complete/authoritative record. The dropped row's own non-empty
fields backfill any blank field on the kept row (same non-destructive merge
convention as scripts/backfill_new_corpus_metadata.py) - no information is
discarded, only the duplicate row.

Only within-resource groups are touched - a paper legitimately cited by more
than one resource is one row per resource by design (see
extract_new_corpus_publications() upstream), not a duplicate.

Run from anywhere in the repo:
    python3 scripts/dedup_publications_preprints.py [--dry-run]
"""
import argparse
import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
FINAL_DIR = PROJECT_ROOT / "tables" / "final"

MIN_NORM_TITLE_LEN = 20  # below this, a short/generic title risks false-positive matches

PREPRINT_DOI_PREFIXES = (
    "10.1101/",    # bioRxiv / medRxiv
    "10.21203/",   # Research Square
    "10.31219/",   # OSF Preprints
    "10.20944/",   # Preprints.org
    "10.26434/",   # ChemRxiv
    "10.31234/",   # PsyArXiv
)
# bioRxiv/medRxiv-style dated suffix (YYYY.MM.DD.NNNNNN), regardless of DOI
# prefix - catches newer prefixes the same servers have been assigned (e.g.
# 10.64898/2026.06.05.730472, seen on real data in this table).
PREPRINT_SUFFIX_RE = re.compile(r"/\d{4}\.\d{2}\.\d{2}\.\d+")

BACKFILL_COLS = ["PMID", "DOI", "PubMed Central Link", "Authors", "Affiliations",
                 "Abstract", "Keywords", "Publication Date"]

# Fetched With is documented (validate_fetched_publications.py's _query_methods)
# as "a semicolon-joined union of every method that (re)discovered" a row -
# unioning it here on merge (not backfill-if-blank, unlike BACKFILL_COLS)
# preserves that every method which found either the preprint or the
# published version is still on record for the one surviving row.
UNION_COL = "Fetched With"


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(title).lower())


def is_preprint_doi(doi: str) -> bool:
    doi = str(doi or "").strip().lower()
    if not doi:
        return False
    return doi.startswith(PREPRINT_DOI_PREFIXES) or bool(PREPRINT_SUFFIX_RE.search(doi))


def resource_set(resource_name: str) -> frozenset:
    return frozenset(n.strip() for n in str(resource_name or "").split(";") if n.strip())


def pick_canonical_index(group: pd.DataFrame) -> int:
    """Index (into `group`) of the row to keep: published over preprint, then
    richest data (DOI present, longer Abstract) among what's left."""
    non_preprint = group[~group["DOI"].apply(is_preprint_doi)]
    pool = non_preprint if len(non_preprint) > 0 else group

    with_doi = pool[pool["DOI"].str.strip() != ""]
    pool = with_doi if len(with_doi) > 0 else pool

    return pool["Abstract"].str.len().idxmax()


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

    df["_norm_title"] = df["Title"].apply(norm_title)
    df["_resources"] = df["Resource Name"].apply(resource_set)

    to_drop: list[int] = []
    n_groups_merged = 0
    for norm_t, group in df[df["_norm_title"].str.len() >= MIN_NORM_TITLE_LEN].groupby("_norm_title"):
        if len(group) < 2:
            continue
        if group["_resources"].nunique() != 1:
            continue  # cited by different resources - legitimate, not a duplicate
        if group["PMID"].replace("", pd.NA).nunique(dropna=True) <= 1 and \
           group["DOI"].replace("", pd.NA).nunique(dropna=True) <= 1:
            continue  # already share an identifier - not the gap this script targets

        canonical_idx = pick_canonical_index(group)
        dropped = group.drop(index=canonical_idx)
        for col in BACKFILL_COLS:
            if df.at[canonical_idx, col].strip():
                continue
            filler = next((v for v in dropped[col] if str(v).strip()), "")
            if filler:
                df.at[canonical_idx, col] = filler

        existing = [m.strip() for m in df.at[canonical_idx, UNION_COL].split(";") if m.strip()]
        for fw in dropped[UNION_COL]:
            for m in str(fw).split(";"):
                m = m.strip()
                if m and m not in existing:
                    existing.append(m)
        df.at[canonical_idx, UNION_COL] = "; ".join(existing)

        to_drop.extend(dropped.index.tolist())
        n_groups_merged += 1

    logger.info(f"Merging {n_groups_merged} duplicate group(s), dropping {len(to_drop)} redundant row(s)")

    df = df.drop(index=to_drop).drop(columns=["_norm_title", "_resources"])
    logger.info(f"{len(df)} row(s) remain (was {len(df) + len(to_drop)})")

    if args.dry_run:
        logger.info("Dry run - not writing changes")
        return

    df.to_csv(pubs_path, sep="\t", index=False)
    logger.info(f"Wrote {len(df)} rows → {pubs_path.name} - run `npm run sync-data` in web/ to refresh the app's copy")


if __name__ == "__main__":
    main()
