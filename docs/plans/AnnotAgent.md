# AnnotAgent: Transformer-based Publication Metadata Annotator


---

## Context
CARD Catalog uses SciLite (Europe PMC API) to annotate publications with diseases, genes/proteins, and chemicals. These are joined into the **PubMetaData** table via `staging/publication_glue.py`. SciLite coverage is limited to articles indexed by Europe PMC and only covers three entity types.

AnnotAgent is a local/cloud Transformer NER pipeline designed to run **in parallel with SciLite for comparison** — not as a replacement. It fetches full-text PMC XML, runs configurable HuggingFace NER models, and extracts the same three SciLite types plus new ones (cell types, brain regions, variants). Output conforms to the existing `SciLiteAnnotationRow` schema so the join infrastructure works unchanged, and all results land in **PubMetaData**.

This is a design draft. Orchestrator integration is deferred to v2.

---

## Target Architecture

```
scrapers/
  scrape_annot_agent.py       # PMC BioC full-text fetcher + checkpointing
  ner_runner.py               # HuggingFace NER inference, model-agnostic
staging/
  annot_agent_compare.py      # SciLite vs AnnotAgent comparison report
  publication_glue.py         # Joins SciLite + AnnotAgent → PubMetaData
pipelines/
  annot_agent.py              # PipelineStage wrapper (defer to v2)
tables/hits/
  annot_agent_annotations_{ts}.tsv
tables/final/
  annot_agent_annotations_{ts}.tsv
  pubmetadata_{ts}.tsv        # ← PubMetaData: all annotation sources merged
```

---

## Step 1 — PMC Full-Text Fetcher (`scrapers/scrape_annot_agent.py`)

### Fetch strategy
NCBI BioC REST API — no auth, returns structured JSON with labelled sections:
```
https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{PMCID}/unicode
```
Fallback: NCBI Entrez `efetch` with `rettype=full` if BioC returns 404.

Reuse `extract_pmcid()` from `scrapers/scrape_annotations.py` to parse PMCIDs from PubMetaData.

### Rate limiting
3 req/s without key, 10/s with `NCBI_API_KEY` — same env var already used in the pipeline.

### Checkpointing
Same pattern as `scrape_annotations.py`: save `{output}.checkpoint.json` every N articles (default 100). Resume from checkpoint on restart.

### Output per article (in-memory, then flattened to TSV)
```python
{"pmcid": "PMC10238389", "sections": {"Title": "...", "Abstract": "...", "Results": "..."}}
```

---

## Step 2 — NER Runner (`scrapers/ner_runner.py`)

Model-agnostic: accepts any HuggingFace `token-classification` model name via `NER_CONFIG`.

### Config structure
```python
NER_CONFIG = {
    "model": "allenai/scibert_scivocab_uncased",  # swap freely — no code changes
    "entity_map": {
        # label → SciLite-compatible Type string
        "DISEASE":      "Diseases",
        "GENE":         "Gene_Proteins",
        "CHEMICAL":     "Chemicals",
        # New types — no SciLite equivalent
        "CELL_TYPE":    "Cell Types",
        "BRAIN_REGION": "Brain Regions",
        "VARIANT":      "Variants",
        "MUTATION":     "Variants",
    },
    "batch_size": 16,
    "stride": 64,           # overlap for sliding-window over long sections
    "max_length": 512,
    "confidence_threshold": 0.80,
}
```

### Inference loop
1. Sliding-window tokenise each section with `stride` overlap
2. `pipeline("ner", model=..., aggregation_strategy="simple")`
3. Filter by `confidence_threshold`
4. Extract span, char offsets, section label, confidence score
5. Build prefix/postfix context (±50 chars)

---

## Step 3 — Output Schema

Conforms to existing `SciLiteAnnotationRow`. Add `score` field to the Pydantic model for AnnotAgent-specific provenance.

| Column | Source |
|---|---|
| PMC ID | pmcid |
| Type | `entity_map[label]` |
| Exact | matched span text |
| Prefix | ±50 char context |
| Postfix | ±50 char context |
| Section | BioC passage type |
| Provider | `"AnnotAgent"` |
| Annotation ID | `{pmcid}_{char_start}_{type}` |
| Tag Name | v1: `exact.lower()` — entity linker in v2 |
| Tag URI | v1: empty — entity linker in v2 |

**Normalizer target**: `"annot_agent"` — trivial passthrough, new entry in `_NORMALIZERS`.  
**Schema**: `AnnotAgentAnnotationRow` in `staging/schemas.py` (clone of `SciLiteAnnotationRow` + `score: str`).

---

## Step 4 — Comparison Module (`staging/annot_agent_compare.py`)

Reads both `scilite_annotations_*.tsv` and `annot_agent_annotations_*.tsv`, reports per-type per-PMCID:

- **Overlap rate**: % of SciLite entities also found by AnnotAgent (exact or lowercased match)
- **AnnotAgent-only**: entities AnnotAgent found that SciLite missed
- **SciLite-only**: entities SciLite found that AnnotAgent missed
- **New-type coverage**: Cell Types, Brain Regions, Variants (no SciLite baseline)
- **Article coverage**: % of PMCIDs with ≥1 annotation in each system

Output: `tables/hits/annot_agent_comparison_{ts}.tsv` + summary to stdout.

```bash
python -m staging.annot_agent_compare
```

---

## Step 5 — PubMetaData Integration (`staging/publication_glue.py`)

`publication_glue.py` is the step that writes to **PubMetaData** (`pubmetadata_{ts}.tsv`). Add a second pass that reads `annot_agent_annotations_*.tsv` and joins into **separate columns** alongside SciLite (preserves provenance for comparison):

```python
_ANNOT_AGENT_TYPE_TO_COLUMN = {
    "Diseases":      "Diseases (AnnotAgent)",
    "Gene_Proteins": "Genes / Proteins (AnnotAgent)",
    "Chemicals":     "Chemicals (AnnotAgent)",
    "Cell Types":    "Cell Types",
    "Brain Regions": "Brain Regions",
    "Variants":      "Variants",
}
```

When both SciLite and AnnotAgent are present, PubMetaData will carry:

| Column | Source |
|---|---|
| `Diseases (Annotated)` | SciLite |
| `Diseases (AnnotAgent)` | AnnotAgent |
| `Genes / Proteins` | SciLite |
| `Genes / Proteins (AnnotAgent)` | AnnotAgent |
| `Chemicals` | SciLite |
| `Chemicals (AnnotAgent)` | AnnotAgent |
| `Cell Types` | AnnotAgent only |
| `Brain Regions` | AnnotAgent only |
| `Variants` | AnnotAgent only |

New PubMetaData columns also require:
- `web/src/types.ts`: add fields to `Publication` interface
- `PublicationsPage.tsx`: add FACETS entries + table columns

---

## Files to Create

| File | Purpose |
|---|---|
| `scrapers/scrape_annot_agent.py` | PMC BioC fetcher + checkpointing |
| `scrapers/ner_runner.py` | HuggingFace NER, model-agnostic |
| `staging/annot_agent_compare.py` | SciLite vs AnnotAgent comparison report |
| `pipelines/annot_agent.py` | PipelineStage wrapper (defer to v2) |

## Files to Modify

| File | Change |
|---|---|
| `staging/schemas.py` | Add `AnnotAgentAnnotationRow` (SciLiteAnnotationRow + `score`) |
| `staging/normalizer.py` | Add `"annot_agent"` passthrough to `_NORMALIZERS`; rename `"publications"` output to `pubmetadata_*.tsv` |
| `staging/publication_glue.py` | Rename output to `pubmetadata_*.tsv`; add second join pass for AnnotAgent columns |
| `web/src/types.ts` | New fields on `Publication` for AnnotAgent columns |
| `web/src/pages/PublicationsPage.tsx` | FACETS + table columns for new PubMetaData annotation columns |

---

## Compute Notes

- **Local (CPU/M-series Mac)**: distilled biomedical NER model, batch size 4–8, ~1–2 sec/article
- **Cloud (GCP/Modal GPU)**: batch size 32+, <0.1 sec/article on A100
- Model name and batch size live in `NER_CONFIG` — switching compute requires no code changes

---

## Entity Linker (v2, deferred)

| Type | Ontology |
|---|---|
| Diseases | MeSH / UMLS |
| Genes/Proteins | NCBI Gene symbol normalisation |
| Chemicals | PubChem CID |
| Cell Types | Cell Ontology (CL) |
| Brain Regions | UBERON |
| Variants | ClinVar rsID / HGVS |

v1 uses `tag_name = exact.lower()`, `tag_uri = ""`.

---

## Verification

1. Fetch 10 PMCIDs → confirm sections present (Title, Abstract, Results)
2. Run NER on those 10 → inspect spans per type, confidence distribution
3. Run comparison vs SciLite on same 10 → expect ~40–70% overlap on Diseases
4. Run full pipeline → check row count in `annot_agent_annotations_{ts}.tsv`
5. Run `publication_glue.py` → verify PubMetaData (`pubmetadata_{ts}.tsv`) carries all annotation columns
6. `npm run sync-data && npm run build` → verify new columns visible in React
