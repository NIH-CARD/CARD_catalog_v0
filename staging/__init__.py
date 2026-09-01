"""
CARD Catalog staging layer.

schemas.py   — Pydantic row models, one per output table.
normalizer.py — coerce hits files → validated, app-ready TSVs in tables/final/.
combine_hits.py — dedupe/collapse hits across query methods into combine_hits_*.tsv.
publication_glue.py — enrich already publication-shaped tables with derived columns:
    build_misc_publications() joins pub_verification's verdicts into a copy of
    combine_hits.tsv; join_cellular_model_publications() links cell models to the
    publications/studies that mention their variant via SciLite.
validate_fetched_publications.py — LLM-based semantic verification (is this publication
    genuinely grounded in this resource?) of combine_hits_*.tsv rows.
"""
