"""
Stage 5 — Study page navigation (new corpus discovery).

Uses ``data_gatherer.DataGatherer.process_metadata()`` to visit each resource's
Access URL and Alternative URLs via a headless Firefox browser, extracting
verified metadata and discovering new corpus entries.

Requires a pre-authenticated Firefox profile set via the ``FIREFOX_PROFILE_DIR``
env var. To create the profile interactively run::

    python -m pipelines.page_navigation --setup-profile

Input: inventory ``.tab`` file
Output: ``tables/hits/new_corpus_{ts}.tsv``
"""
import logging
import os
import sys
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage

logger = logging.getLogger(__name__)

PROFILE_ENV_VAR = "FIREFOX_PROFILE_DIR"


def _setup_profile() -> None:
    """Interactive helper: launch Firefox so the user can log in, then save the profile."""
    import tempfile
    profile_dir = os.path.expanduser("~/.card-catalog-firefox-profile")
    print(f"\nStarting Firefox with profile: {profile_dir}")
    print("Log in to any required portals, then close Firefox.\n")
    from data_gatherer.selenium_setup import create_driver
    driver = create_driver(browser="Firefox", headless=False, profile_dir=profile_dir, logger=logging.getLogger("selenium_setup"))
    driver.get("about:blank")
    input("Press ENTER once you have finished logging in and closed Firefox...")
    try:
        driver.quit()
    except Exception:
        pass
    print(f"\nProfile saved. Add this to your crontab or .env:\n  {PROFILE_ENV_VAR}={profile_dir}\n")


class PageNavigationStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        firefox_profile_dir: str | None = None,
        anthropic_key: str | None = None,
        verbose: bool = False,
        log_file: Path | None = None,
    ) -> Path:
        from data_gatherer.data_gatherer import DataGatherer
        from data_gatherer.llm.response_schema import study_sanity_check_w_rationale_schema_claude

        profile_dir = firefox_profile_dir or os.getenv(PROFILE_ENV_VAR)
        if not profile_dir:
            raise EnvironmentError(
                f"page_navigation stage requires a pre-authenticated Firefox profile. "
                f"Set {PROFILE_ENV_VAR} env var, or run:\n"
                f"  python -m pipelines.page_navigation --setup-profile"
            )

        if anthropic_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", anthropic_key)

        log_level = "DEBUG" if verbose else "INFO"

        # Build expanded URL df (one row per alternative URL, same as notebook)
        df = pd.read_csv(input_path, sep="\t")
        expanded_rows = []
        for _, row in df.iterrows():
            alt_urls = row.get("Alternative URLs")
            if pd.isna(alt_urls):
                row = row.copy()
                row["dataset_webpage"] = row.get("Access URL", "")
                expanded_rows.append(row)
            else:
                try:
                    alt_list = eval(alt_urls) if isinstance(alt_urls, str) else []
                except Exception:
                    alt_list = [alt_urls]
                for url in alt_list:
                    new_row = row.copy()
                    new_row["dataset_webpage"] = url
                    expanded_rows.append(new_row)

        expanded_df = pd.DataFrame(expanded_rows)
        expanded_df["download_link"] = None
        logger.info(f"{len(expanded_df)} URLs to visit")

        dg = DataGatherer(llm_name="claude-haiku-4-5", log_level=log_level, log_file_override=str(log_file) if log_file else None, clear_previous_logs=False)
        outputs = dg.process_metadata(
            expanded_df,
            pass_cols_to_prompt=[
                "Resource Name", "Abbreviation", "Diseases Included",
                "Sample Size", "FAIR Compliance Notes", "Notes",
                "Resource Type", "Coarse Data Modality", "Granular Data Modality",
            ],
            display_type="console",
            interactive=False,
            return_metadata=True,
            use_portkey=False,
            prompt_name="Claude_StudyPage_SanityCheck_rationale",
            response_format=study_sanity_check_w_rationale_schema_claude,
            profile_dir=profile_dir,
            timeout=20,
            add_sitemap_to_prompt=True,
            from_metadata_to_publication_corpus=True,
        )

        if outputs:
            out_df = pd.DataFrame(outputs)
            out_df["_schema"] = "study_sanity_check_w_rationale"
            out_df.to_csv(output_path, sep="\t", index=False)
            logger.info(f"→ {output_path.name} ({len(out_df)} rows)")
        else:
            logger.warning("No outputs produced")

        return output_path


if __name__ == "__main__":
    if "--setup-profile" in sys.argv:
        _setup_profile()
    else:
        print("Usage: python -m pipelines.page_navigation --setup-profile")
