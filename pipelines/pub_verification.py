"""
Stage 4f — Publication vLLM batch verification results ingestion.

*** WORK IN PROGRESS — not yet wired into orchestrator.py. ***
Do not add this to the pub_metadata concurrent stage list (or anywhere else in
orchestrator.py) until that's explicitly requested — it's being built out first,
run and verified standalone.

Ingestion-only: assumes the offline vLLM batch verification workflow
(scripts/run_build_fulltext_batch.py builds request JSONL, an externally-run
scripts/run_vllm_jsonl_batch.py submits it to a self-hosted vLLM server) has
already completed and left results in prompts/validate_fetched_publications/.
Orchestrator does not manage that self-hosted, VPN-gated round-trip itself -
this stage only picks up whatever results already exist on disk.

Writes a standalone table (tables/hits/pub_verification_{ts}.tsv) - deliberately
separate from the Publications table's own Verification Status/Claim Text/
Rationale columns (populated by the older paperclip-based method), so the two
can be compared rather than one silently overwriting the other.

Input:  prompts/validate_fetched_publications/ (fulltext_batch_*_results.jsonl)
Output: tables/hits/pub_verification_{ts}.tsv
"""
import logging
from pathlib import Path
from typing import Optional

from pipelines.base import PipelineStage, redact_secrets
from staging.validate_fetched_publications import ingest_fulltext_batch_results

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "prompts" / "validate_fetched_publications"


def _latest_combine_hits() -> Optional[Path]:
    matches = sorted((PROJECT_ROOT / "tables" / "hits").glob("combine_hits_*.tsv"))
    return matches[-1] if matches else None


class PubVerificationStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        **kwargs,
    ) -> Path:
        logger.info(f"run called with input_path={input_path}, output_path={output_path}, "
                    f"kwargs={redact_secrets(kwargs)}")
        results_dir = input_path if input_path else DEFAULT_RESULTS_DIR
        if not results_dir.exists() or not any(results_dir.glob("fulltext_batch_*_results.jsonl")):
            logger.warning(f"no batch results found in {results_dir} — skipping")
            return output_path

        combine_hits_path = _latest_combine_hits()
        if combine_hits_path:
            logger.info(f"using {combine_hits_path.name} for query_method breakdown")
        else:
            logger.info("no combine_hits_*.tsv found — skipping query_method breakdown")

        df = ingest_fulltext_batch_results(results_dir, combine_hits_path=combine_hits_path)

        if df.empty:
            logger.warning("no verification results ingested — output not written")
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, sep="\t", index=False)
        logger.info(f"Verification results → {output_path.name} ({len(df)} rows)")
        return output_path