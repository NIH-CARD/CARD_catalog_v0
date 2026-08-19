#!/usr/bin/env python3
"""Exploratory ingestion of vLLM batch validation results (scripts/run_vllm_jsonl_batch.py
output) - parses each fulltext_batch_N_results.jsonl, reports per-batch and overall
success/error/verification_status breakdowns, and writes a combined TSV for browsing.

Not a pipeline stage - just for understanding what happened across batches 1-10 before
deciding how (or whether) to fold this into staging/ as a real ingestion step.

Usage:
    python scripts/ingest_batch_results.py
    python scripts/ingest_batch_results.py --output /tmp/parsed_verdicts.tsv
    python scripts/ingest_batch_results.py --combine-hits tables/hits/combine_hits_20260812_194049.tsv
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "validate_fetched_publications"
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# Fetched With prefixes that unambiguously tag a query method. scrape_publications.py's
# search_pubmed() now tags original/v2/v3/v4 too (see search_pubmed and _search_pubmed_fanout) -
# older combine_hits files predating that fix still have untagged original/v2/v3/v4 rows,
# which fall into "other" since they're indistinguishable from each other without a tag.
_TAGGED_METHOD_RE = re.compile(r"^(paperclip|v5|v4|v3|v2|original):")


def _query_methods(fetched_with: str) -> set:
    """A row's Fetched With is a semicolon-joined union of every method that (re)discovered
    it (see staging/combine_hits.py) - a single row can carry more than one method."""
    methods = set()
    for segment in fetched_with.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        m = _TAGGED_METHOD_RE.match(segment)
        methods.add(m.group(1) if m else "other")
    return methods


# The 8 pre-merge files that fed into combine_hits_20260812_194049.tsv's "other" bucket -
# q1-q4 map to query_method original/v2/v3/v4 (confirmed via the method labels in
# docs/plans/paperclip/experiments/coverage_comparison_queries.ipynb). Used to recover the
# original/v2/v3/v4 split for rows predating the Fetched With tagging fix.
_EXPERIMENTS_DIR = _REPO_ROOT / "docs" / "plans" / "paperclip" / "experiments"
_Q_FILE_METHODS = {
    "q1_pubmed_full.tsv": "original", "q1_pmc_full.tsv": "original",
    "q2_pubmed_full.tsv": "v2", "q2_pmc_full.tsv": "v2",
    "q3_pubmed_full.tsv": "v3", "q3_pmc_full.tsv": "v3",
    "q4_pubmed_full.tsv": "v4", "q4_pmc_full.tsv": "v4",
}


def _load_pre_merge_method_index(experiments_dir: Path) -> dict:
    """(key_type, value) -> set of methods, built from the pre-combine_hits.py experiment
    files - lets "other"-tagged rows (predating the Fetched With tagging fix) be resolved
    back to their real original/v2/v3/v4 method by identity-key match."""
    import pandas as pd
    from staging.combine_hits import _row_identity_keys

    index: dict = {}
    for filename, method in _Q_FILE_METHODS.items():
        path = experiments_dir / filename
        if not path.exists():
            continue
        df = pd.read_csv(path, sep="\t", dtype=str).fillna("")
        for row in df.to_dict("records"):
            for key in _row_identity_keys(row):
                index.setdefault(key, set()).add(method)
    return index


def _load_doc_id_lookup(combine_hits_path: Path, pre_merge_index: dict | None = None) -> dict:
    """(resource_name, doc_id) -> set of query methods, using the exact same doc_id
    resolution build_fulltext_batch_jsonl used when building the batch requests.

    If pre_merge_index is given, any row tagged "other" (predating the Fetched With
    tagging fix) is cross-referenced against it by identity key (PMID/DOI/PMC ID/doc_id)
    to recover its real original/v2/v3/v4 method - "other" is only kept as a last resort
    when no pre-merge file matches it at all."""
    import pandas as pd
    from staging.combine_hits import _row_identity_keys
    from staging.validate_fetched_publications import _resolve_doc_id

    df = pd.read_csv(combine_hits_path, sep="\t", dtype=str).fillna("")
    lookup = {}
    for row in df.to_dict("records"):
        doc_id = _resolve_doc_id(row)
        if not doc_id:
            continue
        methods = _query_methods(row.get("Fetched With", ""))
        if pre_merge_index is not None and "other" in methods:
            resolved = set()
            for key in _row_identity_keys(row):
                resolved.update(pre_merge_index.get(key, set()))
            if resolved:
                methods = (methods - {"other"}) | resolved
        key = (row.get("Resource Name", ""), doc_id)
        lookup.setdefault(key, set()).update(methods)
    return lookup


_SMART_QUOTES = str.maketrans({"“": '"', "”": '"'})


def _parse_output_text(output_text: str):
    """Parse a response's output_text as the {verification_status, claim_text, rationale}
    JSON object. Falls back to normalizing smart quotes (a known vLLM/gpt-oss-20b structured-
    output quirk) before giving up. Returns None if still unparseable."""
    try:
        return json.loads(output_text)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        return json.loads(output_text.translate(_SMART_QUOTES))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def _batch_number(path: Path) -> int:
    m = re.search(r"fulltext_batch_(\d+)_results\.jsonl", path.name)
    return int(m.group(1)) if m else -1


def ingest(results_dir: Path):
    """Yields (batch_num, record_dict) for every line across all result files, in batch order."""
    files = sorted(results_dir.glob("fulltext_batch_*_results.jsonl"), key=_batch_number)
    for f in files:
        batch_num = _batch_number(f)
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield batch_num, json.loads(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--output", type=Path, default=None,
                         help="Optional TSV path to write parsed verdicts for browsing")
    parser.add_argument("--combine-hits", type=Path, default=None,
                         help="Path to combine_hits_*.tsv - if given, adds a verification_status "
                              "x query_method breakdown by joining on (resource_name, doc_id)")
    parser.add_argument("--experiments-dir", type=Path, default=_EXPERIMENTS_DIR,
                         help="Pre-merge q1-q4 experiment files dir, used to resolve \"other\"-tagged "
                              "rows back to original/v2/v3/v4 (default: docs/plans/paperclip/experiments)")
    parser.add_argument("--no-recover-methods", action="store_true",
                         help="Skip cross-referencing \"other\" rows against --experiments-dir")
    args = parser.parse_args()

    pre_merge_index = None
    if args.combine_hits and not args.no_recover_methods:
        pre_merge_index = _load_pre_merge_method_index(args.experiments_dir)
    doc_id_lookup = _load_doc_id_lookup(args.combine_hits, pre_merge_index) if args.combine_hits else None
    method_status_counts = Counter()
    n_unmatched = 0

    per_batch = {}
    overall_status = Counter()
    overall_errors = Counter()
    n_unparseable = 0
    n_success = 0
    parsed_rows = []

    for batch_num, rec in ingest(args.results_dir):
        stats = per_batch.setdefault(batch_num, {"total": 0, "success": 0, "error": 0, "unparseable": 0})
        stats["total"] += 1

        if "error" in rec:
            stats["error"] += 1
            overall_errors[rec["error"][:60]] += 1
            continue

        parsed = _parse_output_text(rec.get("output_text", ""))
        meta = rec.get("metadata") or {}
        if parsed is None:
            stats["unparseable"] += 1
            n_unparseable += 1
            continue

        stats["success"] += 1
        n_success += 1
        status = parsed.get("verification_status", "(missing key)")
        overall_status[status] += 1

        if doc_id_lookup is not None:
            methods = doc_id_lookup.get((meta.get("resource_name", ""), meta.get("doc_id", "")))
            if methods:
                for method in methods:
                    method_status_counts[(method, status)] += 1
            else:
                n_unmatched += 1

        parsed_rows.append({
            "batch": batch_num,
            "custom_id": rec.get("custom_id", ""),
            "resource_name": meta.get("resource_name", ""),
            "doc_id": meta.get("doc_id", ""),
            "url": meta.get("url", ""),
            "verification_status": status,
            "claim_text": parsed.get("claim_text", ""),
            "rationale": parsed.get("rationale", ""),
        })

    print(f"{'Batch':>6}  {'Total':>6}  {'Success':>8}  {'Error':>6}  {'Unparseable':>11}")
    for batch_num in sorted(per_batch):
        s = per_batch[batch_num]
        print(f"{batch_num:>6}  {s['total']:>6}  {s['success']:>8}  {s['error']:>6}  {s['unparseable']:>11}")

    total = sum(s["total"] for s in per_batch.values())
    total_error = sum(s["error"] for s in per_batch.values())
    print(f"{'TOTAL':>6}  {total:>6}  {n_success:>8}  {total_error:>6}  {n_unparseable:>11}")

    print("\nverification_status (of parsed results):")
    for status, count in overall_status.most_common():
        print(f"  {status:25s} {count:6d}  ({100 * count / max(n_success, 1):.1f}%)")

    if overall_errors:
        print("\ntop error messages:")
        for msg, count in overall_errors.most_common(10):
            print(f"  {count:5d}x  {msg}")

    if doc_id_lookup is not None:
        methods = sorted({m for m, _ in method_status_counts})
        statuses = sorted({s for _, s in method_status_counts})
        print("\nverification_status x query_method (rows found by >1 method count in each - "
              "totals per method won't sum to n_success):")
        header = f"{'method':12s}" + "".join(f"{s:>24s}" for s in statuses) + f"{'total':>10s}"
        print(header)
        for method in methods:
            row_counts = [method_status_counts.get((method, s), 0) for s in statuses]
            print(f"{method:12s}" + "".join(f"{c:>24d}" for c in row_counts) + f"{sum(row_counts):>10d}")
        if n_unmatched:
            print(f"\n{n_unmatched} parsed result(s) had no matching (resource_name, doc_id) in "
                  f"{args.combine_hits.name} - doc_id resolution may differ (e.g. stale combine_hits file).")

    if args.output:
        import csv
        with open(args.output, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(parsed_rows[0].keys()) if parsed_rows else [], delimiter="\t")
            writer.writeheader()
            writer.writerows(parsed_rows)
        print(f"\nWrote {len(parsed_rows)} parsed verdicts -> {args.output}")


if __name__ == "__main__":
    main()