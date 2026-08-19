"""
CARD Catalog staging layer.

schemas.py   — Pydantic row models, one per output table.
normalizer.py — coerce hits files → validated, app-ready TSVs in tables/final/.
combine_hits.py — dedupe/collapse hits across query methods into combine_hits_*.tsv.
join_annotations.py — join SciLite annotations + cited datasets into the publications table.
validate_fetched_publications.py — LLM-based semantic verification (is this publication
    genuinely grounded in this resource?) of combine_hits_*.tsv rows.
"""
