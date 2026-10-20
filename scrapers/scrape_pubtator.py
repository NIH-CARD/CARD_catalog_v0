#!/usr/bin/env python3
"""
scrapers/scrape_pubtator.py

Fetch PubTator3 (NCBI) annotations for a list of papers and flatten them into
two tidy tables:

  entities  — one row per (paper, normalised entity), with a mention count
  relations — one row per typed, scored relation between two entities

Papers with a PMID go through the PMID export twice: full text (when PMC has
it) for entities, abstract only for relations — PubTator's relations come from
abstracts, and full-text mode returns a strict subset of them (measured
2026-10-19: 4,927/4,928 full-text relations also appear abstract-only, which
has 3,229 more). Papers with only a PMC ID go through the PMC export, which is
always full text. The ``Text Scope`` column records which one each row came from.

API docs: https://www.ncbi.nlm.nih.gov/research/pubtator3/api
(≤100 IDs per request, ≤3 requests/second.)

Usage
  python scrapers/scrape_pubtator.py \\
      --input tables/hits/misc_publications_confirmed_YYYYMMDD_HHMMSS.tsv \\
      --entities-output tables/hits/pubtator_entities.tsv \\
      --relations-output tables/hits/pubtator_relations.tsv \\
      [--abstract-only] [--batch-size 100] [--pause 0.4]
"""

import argparse
import logging
import re
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter, Retry

logger = logging.getLogger(__name__)

API_BASE = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
PMID_EXPORT_URL = f"{API_BASE}/publications/export/biocjson"
PMC_EXPORT_URL = f"{API_BASE}/publications/pmc_export/biocjson"
MAX_BATCH = 100
MAX_MENTIONS = 5  # distinct mention strings kept per entity row

_PMC_RE = re.compile(r"PMC\d+", re.IGNORECASE)

ENTITY_COLUMNS = [
    "PMID", "PMC ID", "Text Scope", "Type", "Identifier", "Database",
    "Name", "Mention Count", "Mentions", "Sections",
]
RELATION_COLUMNS = [
    "PMID", "PMC ID", "Text Scope", "Relation Type", "Score",
    "Entity 1 Type", "Entity 1 Identifier", "Entity 1 Name",
    "Entity 2 Type", "Entity 2 Identifier", "Entity 2 Name",
]


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def make_session(retries: int = 3, backoff: float = 1.0) -> requests.Session:
    """Return a requests session with retry/backoff on 429 and 5xx."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        status_forcelist=(429, 500, 502, 503, 504),
        backoff_factor=backoff,
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


# ---------------------------------------------------------------------------
# ID handling
# ---------------------------------------------------------------------------

def extract_pmcid(raw: str) -> str:
    """Return bare PMC ID (e.g. 'PMC10238389') from any string, or ''."""
    m = _PMC_RE.search(raw or "")
    return m.group(0).upper() if m else ""


def load_ids(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Split a publications table into PMIDs and PMC IDs of papers without a PMID.

    Args:
        df: Publications table with a ``PMID`` and/or ``PubMed Central Link`` column.

    Returns:
        (pmids, pmc_only_ids), each deduplicated in input order.
    """
    pmid_col = df["PMID"] if "PMID" in df.columns else pd.Series([""] * len(df))
    pmc_col = df["PubMed Central Link"] if "PubMed Central Link" in df.columns else pd.Series([""] * len(df))

    pmids: list[str] = []
    pmc_only: list[str] = []
    for pmid, pmc in zip(pmid_col.fillna("").astype(str), pmc_col.fillna("").astype(str)):
        pmid = pmid.strip().removesuffix(".0")
        if pmid.isdigit():
            pmids.append(pmid)
        elif pmcid := extract_pmcid(pmc):
            pmc_only.append(pmcid)
    return list(dict.fromkeys(pmids)), list(dict.fromkeys(pmc_only))


def pmcid_lookup(df: pd.DataFrame) -> dict[str, str]:
    """Map PMID → PMC ID from a publications table's ``PubMed Central Link`` column."""
    if "PMID" not in df.columns or "PubMed Central Link" not in df.columns:
        return {}
    lookup: dict[str, str] = {}
    for pmid, pmc in zip(df["PMID"].fillna("").astype(str), df["PubMed Central Link"].fillna("").astype(str)):
        pmid = pmid.strip().removesuffix(".0")
        if pmid.isdigit() and (pmcid := extract_pmcid(pmc)):
            lookup.setdefault(pmid, pmcid)
    return lookup


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _batches(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def fetch_documents(
    ids: list[str],
    session: requests.Session,
    *,
    by: str = "pmid",
    full_text: bool = False,
    batch_size: int = MAX_BATCH,
    pause: float = 0.4,
) -> list[dict]:
    """Fetch PubTator3 BioC JSON documents in batches.

    Args:
        ids: PMIDs (``by="pmid"``) or PMC IDs (``by="pmcid"``).
        session: HTTP session from :func:`make_session`.
        by: Which export endpoint to use, ``"pmid"`` or ``"pmcid"``.
        full_text: Request full text on the PMID endpoint (PMC endpoint is always full text).
        batch_size: IDs per request (API max 100).
        pause: Seconds between requests (API limit is 3 req/s).

    Returns:
        List of BioC documents, each tagged with a ``_text_scope`` key.
    """
    batch_size = min(batch_size, MAX_BATCH)
    url = PMID_EXPORT_URL if by == "pmid" else PMC_EXPORT_URL
    scope = "full_text" if (full_text or by == "pmcid") else "abstract"
    n_batches = (len(ids) + batch_size - 1) // batch_size
    logger.info(f"PubTator3 {by} export: {len(ids)} IDs in {n_batches} batches ({scope})")

    docs: list[dict] = []
    for i, chunk in enumerate(_batches(ids, batch_size)):
        params = {"pmids" if by == "pmid" else "pmcids": ",".join(chunk)}
        if by == "pmid" and full_text:
            params["full"] = "true"
        try:
            resp = session.get(url, params=params, timeout=120)
            resp.raise_for_status()
            batch_docs = resp.json().get("PubTator3", []) if resp.content else []
        except (requests.RequestException, ValueError) as exc:
            logger.warning(f"[{i + 1}/{n_batches}] {by} batch failed ({exc}) — skipping {len(chunk)} IDs")
            batch_docs = []
        for doc in batch_docs:
            doc["_text_scope"] = scope
        docs.extend(batch_docs)
        logger.debug(f"[{i + 1}/{n_batches}] {len(batch_docs)}/{len(chunk)} documents returned")
        time.sleep(pause)

    logger.info(f"PubTator3 {by} export: {len(docs)}/{len(ids)} documents returned")
    return docs


# ---------------------------------------------------------------------------
# Flattening
# ---------------------------------------------------------------------------

def _entity_key(infons: dict) -> str:
    """Stable identifier for an entity: rsID for variants that have one, else PubTator's identifier."""
    if infons.get("type") == "Variant" and infons.get("rsid"):
        return str(infons["rsid"])
    ident = str(infons.get("identifier") or "").strip()
    return "" if ident in ("-", "None") else ident


def _paper_ids(doc: dict) -> tuple[str, str]:
    # Abstract-mode documents leave `pmcid` empty; the title passage still carries it.
    pmid = str(doc.get("pmid") or "")
    pmcid = extract_pmcid(str(doc.get("pmcid") or ""))
    if not pmcid:
        for passage in doc.get("passages", []):
            if pmcid := extract_pmcid(str((passage.get("infons") or {}).get("article-id_pmc") or "")):
                break
    return pmid, pmcid


def entities_dataframe(docs: list[dict]) -> pd.DataFrame:
    """Flatten BioC documents to one row per (paper, Type, Identifier) with a mention count."""
    rows: list[dict] = []
    n_unnormalized = 0
    for doc in docs:
        pmid, pmcid = _paper_ids(doc)
        grouped: dict[tuple[str, str], dict] = {}
        for passage in doc.get("passages", []):
            p_infons = passage.get("infons") or {}
            section = p_infons.get("section_type") or str(p_infons.get("type") or "").upper()
            for ann in passage.get("annotations", []):
                infons = ann.get("infons") or {}
                key = _entity_key(infons)
                if not key:
                    n_unnormalized += 1
                    continue
                etype = infons.get("type", "")
                g = grouped.setdefault((etype, key), {
                    "database": infons.get("database", ""),
                    "name": infons.get("name") or "",
                    "mentions": Counter(),
                    "sections": [],
                })
                g["mentions"][ann.get("text", "")] += 1
                if section and section not in g["sections"]:
                    g["sections"].append(section)
        for (etype, key), g in grouped.items():
            mentions = g["mentions"]
            rows.append({
                "PMID": pmid,
                "PMC ID": pmcid,
                "Text Scope": doc.get("_text_scope", ""),
                "Type": etype,
                "Identifier": key,
                "Database": g["database"],
                "Name": g["name"] or mentions.most_common(1)[0][0],
                "Mention Count": sum(mentions.values()),
                "Mentions": ";".join(m for m, _ in mentions.most_common(MAX_MENTIONS) if m),
                "Sections": ";".join(g["sections"]),
            })
    if n_unnormalized:
        logger.info(f"Skipped {n_unnormalized} mentions with no normalised identifier")
    return pd.DataFrame(rows, columns=ENTITY_COLUMNS)


def relations_dataframe(docs: list[dict]) -> pd.DataFrame:
    """Flatten BioC documents to one row per typed relation."""
    rows: list[dict] = []
    for doc in docs:
        pmid, pmcid = _paper_ids(doc)
        for rel in doc.get("relations", []):
            infons = rel.get("infons") or {}
            r1 = infons.get("role1") or {}
            r2 = infons.get("role2") or {}
            rows.append({
                "PMID": pmid,
                "PMC ID": pmcid,
                "Text Scope": doc.get("_text_scope", ""),
                "Relation Type": infons.get("type", ""),
                "Score": infons.get("score", ""),
                "Entity 1 Type": r1.get("type", ""),
                "Entity 1 Identifier": _entity_key(r1),
                "Entity 1 Name": r1.get("name", ""),
                "Entity 2 Type": r2.get("type", ""),
                "Entity 2 Identifier": _entity_key(r2),
                "Entity 2 Name": r2.get("name", ""),
            })
    return pd.DataFrame(rows, columns=RELATION_COLUMNS)


def scrape(
    pmids: list[str],
    pmc_only: list[str],
    *,
    full_text: bool = True,
    batch_size: int = MAX_BATCH,
    pause: float = 0.4,
    pmcids: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch and flatten PubTator3 annotations for PMIDs plus PMC-only papers.

    Args:
        pmids: PubMed IDs.
        pmc_only: PMC IDs of papers that have no PMID.
        full_text: Take PMID entities from full text (relations always come from abstracts).
        batch_size: IDs per request (API max 100).
        pause: Seconds between requests.
        pmcids: PMID → PMC ID fallback for papers PubTator returns without one.

    Returns:
        (entities_df, relations_df).
    """
    session = make_session()
    abstract_docs = fetch_documents(pmids, session, by="pmid", batch_size=batch_size, pause=pause)
    entity_docs = (
        fetch_documents(pmids, session, by="pmid", full_text=True, batch_size=batch_size, pause=pause)
        if full_text else abstract_docs
    )
    pmc_docs = fetch_documents(pmc_only, session, by="pmcid", batch_size=batch_size, pause=pause) if pmc_only else []
    entities = entities_dataframe(entity_docs + pmc_docs)
    relations = relations_dataframe(abstract_docs + pmc_docs)
    if pmcids:
        for frame in (entities, relations):
            missing = frame["PMC ID"] == ""
            frame.loc[missing, "PMC ID"] = frame.loc[missing, "PMID"].map(pmcids).fillna("")
    return entities, relations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PubTator3 entities and relations for a publications TSV")
    parser.add_argument("--input", required=True, help="TSV with PMID and/or 'PubMed Central Link' columns")
    parser.add_argument("--entities-output", required=True, help="Path to write the entities TSV")
    parser.add_argument("--relations-output", required=True, help="Path to write the relations TSV")
    parser.add_argument("--abstract-only", action="store_true", help="Take PMID entities from abstracts, not full text")
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH, help="IDs per request — API max 100")
    parser.add_argument("--pause", type=float, default=0.4, help="Seconds between requests (default 0.4)")
    args = parser.parse_args()

    df = pd.read_csv(args.input, sep="\t", dtype=str).fillna("")
    pmids, pmc_only = load_ids(df)
    logger.info(f"Loaded {len(df)} rows from {Path(args.input).name}: {len(pmids)} PMIDs, {len(pmc_only)} PMC-only")
    if not pmids and not pmc_only:
        logger.error(f"No PMIDs or PMC IDs found in {args.input}")
        raise SystemExit(2)

    entities, relations = scrape(
        pmids, pmc_only, full_text=not args.abstract_only, batch_size=args.batch_size, pause=args.pause,
        pmcids=pmcid_lookup(df),
    )
    for out, frame in ((args.entities_output, entities), (args.relations_output, relations)):
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(out, sep="\t", index=False)
        logger.info(f"Wrote {len(frame)} rows → {out}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
