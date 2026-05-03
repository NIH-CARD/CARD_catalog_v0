#!/usr/bin/env python3
"""
scrapers/scrape_annotations.py

Fetch Europe PMC annotations for a list of PMC IDs and write JSON output.
"""

import argparse
import json
import logging
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry

logger = logging.getLogger(__name__)


def make_session(retries: int = 3, backoff: float = 0.3) -> requests.Session:
    """Create a requests Session with retry/backoff for resilient HTTP calls."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        status_forcelist=(429, 500, 502, 503, 504),
        backoff_factor=backoff,
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def normalize_id(pmc: str) -> str | None:
    pmc = (pmc or "").strip()
    if not pmc:
        return None
    pmc = pmc.upper()
    if pmc.startswith("PMC:"):
        return pmc
    return f"PMC:{pmc}"


def batch_list(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def fetch_annotations(pmc_ids: list, session: requests.Session, batch_size: int = 50, pause: float = 0.1) -> dict:
    """Fetch annotations for the provided PMC IDs in batches.

    Returns a mapping where each key is a comma-joined list of PMC IDs for the request
    and the value is the parsed JSON response from Europe PMC.
    """
    base_url = "https://www.ebi.ac.uk/europepmc/annotations_api/annotationsByArticleIds"
    results = {}
    for chunk in batch_list(pmc_ids, batch_size):
        article_ids = ",".join(chunk)
        params = {"articleIds": article_ids}
        logger.info("Requesting %d article IDs", len(chunk))
        resp = session.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        results[article_ids] = resp.json()
        time.sleep(pause)
    return results


def load_ids_from_file(path: str) -> list:
    p = Path(path)
    ids = []
    with p.open("r") as fh:
        for line in fh:
            norm = normalize_id(line)
            if norm:
                ids.append(norm)
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Europe PMC annotations for PMC IDs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pmc-ids", help="Comma-separated PMC IDs (with or without 'PMC:' prefix)")
    group.add_argument("--input-file", help="Path to file with one PMC ID per line")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of IDs per request")
    parser.add_argument("--pause", type=float, default=0.1, help="Seconds to pause between requests")
    parser.add_argument("--output", required=True, help="Path to write JSON output")
    args = parser.parse_args()

    if args.pmc_ids:
        raw = [p.strip() for p in args.pmc_ids.split(",") if p.strip()]
        ids = [normalize_id(p) for p in raw]
    else:
        ids = load_ids_from_file(args.input_file)
    ids = [i for i in ids if i]
    if not ids:
        logger.error("No PMC IDs provided")
        raise SystemExit(2)

    session = make_session()
    data = fetch_annotations(ids, session, batch_size=args.batch_size, pause=args.pause)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        json.dump(data, fh, indent=2)

    logger.info("Wrote annotations to %s", out_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
