"""
Regenerates paper_v0/v0.4/resource_persistent_id_counts.tsv - per-resource
counts of Primary-citation dataset mentions carrying a DOI-form identifier,
used as evidence for the F1/persistent-identifier reviewer response.

Join chain: Datasets (pub_datasets.tsv) -> source_url's PMC ID -> Publications'
PubMed Central Link -> Publications' own (multivalue) Resource Name - the same
PMC-ID join used throughout web/src/lib/connectionsGraph.ts, reimplemented
standalone here since this is a one-off report, not part of the live app.

Run from anywhere in the repo:
    python3 paper_v0/build_resource_persistent_id_counts.py
"""
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
OUTPUT_PATH = Path(__file__).parent / "v0.4" / "resource_persistent_id_counts.tsv"

PMCID_RE = re.compile(r"PMC\d+")
# Deliberately permissive: flags a dataset-mention row as "has a DOI" if a
# DOI-shaped string appears anywhere in dataset_identifier/data_repository/
# dataset_webpage, without verifying the DOI is actually THIS dataset's own
# identifier (vs. e.g. a paper DOI captured into the wrong field during
# extraction) - a reasonable proxy, not a strict attribution check. Spot-check
# before citing an exact percentage from this report.
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")


def pmcid_from(value: str) -> str:
    m = PMCID_RE.search(str(value or ""))
    return m.group(0) if m else ""


def extract_dois(value: str) -> list[str]:
    return [m.rstrip(".,;)]") for m in DOI_RE.findall(str(value or ""))]


def main():
    datasets = pd.read_csv(DATA_DIR / "pub_datasets.tsv", sep="\t", dtype=str).fillna("")
    pubs = pd.read_csv(DATA_DIR / "publications.tsv", sep="\t", dtype=str).fillna("")

    pmc_to_resources: dict[str, set[str]] = {}
    for _, p in pubs.iterrows():
        pmcid = pmcid_from(p["PubMed Central Link"])
        if not pmcid:
            continue
        names = [n.strip() for n in str(p["Resource Name"]).split(";") if n.strip()]
        pmc_to_resources.setdefault(pmcid, set()).update(names)

    per_resource: dict[str, dict] = {}  # name -> {"total": int, "dois": set[str]}
    for _, d in datasets.iterrows():
        if d["citation_type"].strip().lower() != "primary":
            continue
        pmcid = pmcid_from(d["source_url"])
        if not pmcid:
            continue
        names = pmc_to_resources.get(pmcid)
        if not names:
            continue
        dois = (
            extract_dois(d["dataset_identifier"])
            + extract_dois(d["data_repository"])
            + extract_dois(d["dataset_webpage"])
        )
        for name in names:
            rec = per_resource.setdefault(name, {"total": 0, "dois": set()})
            rec["total"] += 1
            rec["dois"].update(dois)

    rows = [
        {"name": name, "total": rec["total"], "doi_list": sorted(rec["dois"])}
        for name, rec in per_resource.items()
        if rec["dois"]
    ]
    rows.sort(key=lambda r: len(r["doi_list"]), reverse=True)

    lines = ["Resource Name\tPrimary dataset mentions\t# distinct DOIs\tDOI links"]
    for r in rows:
        links = "; ".join(f"https://doi.org/{doi}" for doi in r["doi_list"])
        lines.append(f"{r['name']}\t{r['total']}\t{len(r['doi_list'])}\t{links}")

    OUTPUT_PATH.write_text("\n".join(lines))
    print(f"Wrote {len(rows)} resources (each with >=1 DOI) to {OUTPUT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
