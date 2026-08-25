"""
Stage 6 — SciLite annotations (Europe PMC).

Fetches all annotations (Diseases, Gene_Proteins, Accession Numbers, …)
from the Europe PMC annotations API for each PMC article surfaced by the
pubmed_search stage.

Input:  ``tables/hits/pubmed_hits_{ts}.tsv`` (reads ``PubMed Central Link`` col)
Output: ``tables/hits/annotations_{ts}.json`` — raw nested mapping
        ``{pmcid: [annotation, ...]}``
        ``tables/hits/scilite_annotations_{ts}.tsv`` — flat form for normalization
        (one row per annotation × tag).
"""
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage, redact_secrets

logger = logging.getLogger(__name__)

SCRAPERS_DIR = Path(__file__).parent.parent / "scrapers"


class SciLiteStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        batch_size: int = 8,
        pause: float = 0.2,
        verbose: bool = False,
        log_file: Path | None = None,
    ) -> Path:
        args = {k: v for k, v in locals().items() if k not in ("self", "input_path", "output_path")}
        logger.info(f"run called with input_path={input_path}, output_path={output_path}, args={redact_secrets(args)}")
        if str(SCRAPERS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRAPERS_DIR))
        from scrape_annotations import (
            extract_pmcid,
            fetch_annotations,
            load_checkpoint,
            make_session,
            to_dataframe,
        )

        pubs_df = pd.read_csv(input_path, sep="\t", dtype=str)
        if "PubMed Central Link" not in pubs_df.columns:
            logger.error(f"'PubMed Central Link' column missing in {input_path.name}")
            return output_path

        links = (
            pubs_df["PubMed Central Link"]
            .dropna()
            .loc[lambda s: s.str.strip() != ""]
            .unique()
            .tolist()
        )

        pmcids: list[str] = []
        for url in links:
            pmcid = extract_pmcid(url)
            if pmcid:
                pmcids.append(pmcid)
        pmcids = list(dict.fromkeys(pmcids))  # dedupe, preserve order

        logger.info(f"{len(pmcids)} PMC IDs to query Europe PMC annotations API")
        if not pmcids:
            logger.warning("no PMC IDs found — skipping")
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        done = load_checkpoint(output_path)
        if done:
            logger.info(f"resuming from checkpoint: {len(done)} PMC IDs already fetched")

        session = make_session()
        data = fetch_annotations(
            pmcids,
            session,
            batch_size=batch_size,
            pause=pause,
            done=done,
            output=output_path,
        )

        with output_path.open("w") as fh:
            json.dump(data, fh, indent=2)
        n_with = sum(1 for v in data.values() if v)
        logger.info(
            f"Annotations → {output_path.name} "
            f"({len(data)} PMCs, {n_with} with annotations)"
        )

        # Sibling flattened TSV for downstream normalization / app
        flat_df = to_dataframe(data)
        tsv_path = output_path.with_name(
            output_path.name.replace("annotations_", "scilite_annotations_")
        ).with_suffix(".tsv")
        flat_df.to_csv(tsv_path, sep="\t", index=False)
        logger.info(f"Flattened → {tsv_path.name} ({len(flat_df)} rows)")

        cp = output_path.with_suffix(".checkpoint.json")
        if cp.exists():
            cp.unlink()
            logger.info(f"removed checkpoint {cp.name}")

        return output_path
