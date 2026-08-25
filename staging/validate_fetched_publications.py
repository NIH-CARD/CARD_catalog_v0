#!/usr/bin/env python3
"""
CARD Catalog - Post-retrieval publication validation

Checks any query method's output TSV for a genuine match between (resource,
query context) and the article it was fetched under. Both procedures below
answer the same question - "does this specific paper really discuss this
specific resource, not a homonym / broader-or-narrower resource / coincidental
name match?" - and share one LLM backend (a self-hosted vLLM server) and one
output schema (confirmed / not_confirmed / insufficient_evidence), so results
from either are directly comparable.

Two procedures:
    agentic_search - the model drives paperclip's own search/grep as tools to
        corroborate the candidate doc_id against the query context, then
        predicts a verdict itself. paperclip's own repo/commit/--verify
        subsystem is never used here - it's an independent, unreliable oracle
        we're deliberately bypassing (see docs/plans/paperclip/).
    fulltext - the model reads the candidate paper's full text (or abstract,
        for abstract-only corpora) in one pass and predicts a verdict
        directly, no tool use. Mirrors docs/plans/paperclip/validation/vllm_validate.py.

Requires a running vLLM server (VLLM_CLIENT env var, default localhost:8000/v1)
serving a tool-calling-capable model (e.g. `vllm serve openai/gpt-oss-20b`).
"""
import argparse
import json
import logging
import os
import re
import string
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from data_gatherer.prompts.prompt_manager import PromptManager

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # staging/ itself, for sibling imports (combine_hits)
from logging_config import setup_logger, get_default_log_file
from scrape_publications import _paperclip_cli_raw

# Prompts live as plain-text files, not Python string literals - easier to iterate on,
# and since string.Template uses $placeholder (not str.format()'s {placeholder}), the
# literal JSON braces in few_shot_examples.md need no escaping at all, unlike before.
PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "validate_fetched_publications"


def _load_prompt(name: str) -> str:
    logger.info(f"[_load_prompt] called with name={name!r}")
    result = (PROMPTS_DIR / name).read_text()
    logger.info(f"[_load_prompt] returning {len(result)} char(s)")
    return result

try:
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

PMC_LINK_RE = re.compile(r'/(PMC\d+)/?')
DEFAULT_CACHE_PATH = Path(__file__).parent / ".fetched_publication_validation_cache.json"
# Matches every other stage's intermediate-output convention (tables/hits/<stage>_<ts>.tsv,
# ts = %Y%m%d_%H%M%S) - see orchestrator.py's _ts() and any file under tables/hits/.
HITS_DIR = Path(__file__).parent.parent / "tables" / "hits"

VLLM_BASE_URL = os.getenv("VLLM_CLIENT", "http://localhost:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "openai/gpt-oss-20b")

# Claude Sonnet 5 path (see validate_via_*_dg_prompt_claude below) - a separate client since
# it's a different SDK, not a drop-in for the OpenAI-compatible vLLM client used everywhere
# else. Constructed once at import time; resolves credentials from ANTHROPIC_API_KEY or an
# `ant auth login` profile, same as any other Anthropic() client.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
_anthropic_client = anthropic.Anthropic()

RESOURCE_ATTRIBUTE_FIELDS = [
    "Resource Name", "Abbreviation", "Diseases Included",
    "Coarse Data Modality", "Granular Data Modality",
]

# Shared by both procedures so their outputs land in the same categories and
# can be compared directly. insufficient_evidence is deliberately a third
# bucket, not folded into not_confirmed - paperclip's OK/X binary collapsed
# "no corroborating detail" into a false negative, which is part of why its
# precision numbers weren't trustworthy.
RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "ResourceVerification",
    "schema": {
        "type": "object",
        "properties": {
            "verification_status": {
                "type": "string",
                "enum": ["confirmed", "not_confirmed", "insufficient_evidence"],
            },
            "claim_text": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["verification_status", "claim_text", "rationale"],
        "additionalProperties": False,
    },
    "strict": True,
}

# Claude's output_config.format takes {"type": "json_schema", "schema": ...} - no "name" or
# "strict" keys (those are the vLLM/OpenAI Responses API shape above).
ANTHROPIC_RESPONSE_FORMAT = {"type": "json_schema", "schema": RESPONSE_FORMAT["schema"]}

VERIFICATION_RULES = _load_prompt("verification_rules.md")
FEW_SHOT_EXAMPLES = _load_prompt("few_shot_examples.md")

# Alternative prompt path for validate_via_fulltext_dg_prompt: builds messages via
# data_gatherer's own PromptManager.render_prompt() against an externalized JSON template
# (prompts/<name>.json) instead of the hardcoded Python string FULLTEXT_SYSTEM_PROMPT below.
# prompt_dir is the top-level prompts/ dir - the same one passed to DataGatherer(prompt_dir=...)
# in prefetch_fulltext - not PROMPTS_DIR (which scopes only the .md files below, loaded via our
# own _load_prompt, not data_gatherer's). render_prompt's non-"parts" branch returns a fresh
# list per call rather than mutating static_prompt in place, so caching it here and reusing it
# across threads is safe.
_FULLTEXT_PROMPT_MANAGER = PromptManager(prompt_dir=str(PROMPTS_DIR.parent), logger=logger)
DEFAULT_DG_PROMPT_NAME = "sufficient_usage"
_dg_static_prompt_cache: Dict[str, list] = {}


def _load_dg_static_prompt(prompt_name: str) -> list:
    """Lazily load and cache a prompts/<name>.json template by name - e.g. "fulltext_verification"
    (default) or "sufficient_glue" (an alternate, more conversational framing of the same task).
    subdir="" is deliberate: prompt_dir is flat, so there's no directory layer underneath it -
    only load_prompt's subdir default ('dataset_prompts') would introduce one."""
    logger.info(f"[_load_dg_static_prompt] called with prompt_name={prompt_name!r}")
    if prompt_name not in _dg_static_prompt_cache:
        _dg_static_prompt_cache[prompt_name] = _FULLTEXT_PROMPT_MANAGER.load_prompt(prompt_name, subdir="")
    result = _dg_static_prompt_cache[prompt_name]
    logger.info(f"[_load_dg_static_prompt] returning {len(result)} message part(s)")
    return result


def load_cache(path: Path) -> Dict[str, Any]:
    logger.info(f"[load_cache] called with path={path}")
    if path.exists():
        try:
            with open(path) as f:
                cache = json.load(f)
            logger.info(f"Loaded validation cache: {len(cache)} entries from {path}")
            logger.info(f"[load_cache] returning {len(cache)} entries")
            return cache
        except Exception as e:
            logger.warning(f"Failed to load cache {path}: {e}")
    logger.info("[load_cache] returning {} (no cache found)")
    return {}


def save_cache(path: Path, cache: Dict[str, Any]) -> None:
    logger.info(f"[save_cache] called with path={path}, {len(cache)} entries")
    snapshot = dict(cache)
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    logger.info(f"Saved validation cache: {len(snapshot)} entries to {path}")
    logger.info(f"[save_cache] done")


def cache_key(resource_name: str, doc_id: str, method: str) -> str:
    logger.debug(f"[cache_key] called with resource_name={resource_name!r}, doc_id={doc_id!r}, method={method!r}")
    result = f"{resource_name}|||{doc_id}|||{method}"
    logger.debug(f"[cache_key] returning {result!r}")
    return result


def _resolve_doc_id(row: Dict[str, str]) -> Optional[str]:
    """Prefer PMC ID (from PubMed Central Link), then PMID, then DOI - each used directly
    as the identifier, no paperclip search needed - falling back to an explicit Paperclip
    Doc ID column only if the row has none of the above."""
    logger.debug(f"[_resolve_doc_id] called with row with {len(row)} field(s)")
    link = row.get("PubMed Central Link", "") or ""
    m = PMC_LINK_RE.search(link)
    if m:
        result = m.group(1)
        logger.debug(f"[_resolve_doc_id] returning {result!r} (PMC link)")
        return result

    pmid = (row.get("PMID") or "").strip()
    if pmid:
        logger.debug(f"[_resolve_doc_id] returning {pmid!r} (PMID)")
        return pmid

    doi = (row.get("DOI") or "").strip()
    if doi:
        logger.debug(f"[_resolve_doc_id] returning {doi!r} (DOI)")
        return doi

    explicit = (row.get("Paperclip Doc ID") or "").strip()
    if explicit:
        logger.debug(f"[_resolve_doc_id] returning {explicit!r} (explicit Paperclip Doc ID)")
        return explicit

    logger.info("[_resolve_doc_id] returning None (no identifier found)")
    return None


def _find_latest_inventory() -> Optional[Path]:
    """Mirrors orchestrator.py's inventory-resolution pattern (inlined there too, not importable)."""
    logger.info("[_find_latest_inventory] called")
    matches = list((Path(__file__).parent.parent / "tables").glob("resources-inventory-*"))
    result = max(matches, key=lambda p: p.stat().st_mtime) if matches else None
    logger.info(f"[_find_latest_inventory] returning {result}")
    return result


def load_sample_sizes(inventory_path: Optional[Path]) -> Dict[str, str]:
    """Resource Name -> Sample Size, for prompt context - not carried in query-method output TSVs."""
    logger.info(f"[load_sample_sizes] called with inventory_path={inventory_path}")
    if not inventory_path:
        logger.info("[load_sample_sizes] returning {} (no inventory_path)")
        return {}
    try:
        inv = pd.read_csv(inventory_path, sep="\t", dtype=str).fillna("")
        result = dict(zip(inv["Resource Name"], inv["Sample Size"]))
        logger.info(f"[load_sample_sizes] returning {len(result)} entries")
        return result
    except Exception as e:
        logger.warning(f"Could not load sample sizes from {inventory_path}: {e}")
        logger.info("[load_sample_sizes] returning {} (load failed)")
        return {}


def compose_resource_info(row: Dict[str, str], sample_size: str = "") -> str:
    """Compose a resource's non-empty attributes into a 'Label: value; Label: value' string."""
    logger.info(f"[compose_resource_info] called with row with {len(row)} field(s), sample_size={sample_size!r}")
    parts = []
    for field in RESOURCE_ATTRIBUTE_FIELDS:
        value = (row.get(field) or "").strip()
        if value:
            parts.append(f"{field}: {value}")
    if sample_size:
        parts.append(f"Sample Size: {sample_size}")
    result = "; ".join(parts)
    logger.info(f"[compose_resource_info] returning {len(result)} char(s)")
    return result


def extract_query_context(row: Dict[str, str]) -> str:
    """The exact paperclip search/grep command that originally surfaced this doc_id during
    discovery (the "Fetched With" column) - the other half of the core question alongside the
    resource and the article itself. A specific accession-ID/exact-phrase grep hit is stronger
    prior evidence of a genuine connection than a broad keyword search hit; "(not resolved)" or
    blank means there's no original-query signal to weigh either way."""
    logger.info(f"[extract_query_context] called with row with {len(row)} field(s)")
    fetched_with = (row.get("Fetched With") or "").strip()
    if not fetched_with or "not resolved" in fetched_with:
        logger.info("[extract_query_context] returning 'not available'")
        return "not available"
    result = fetched_with.removeprefix("paperclip:").strip()
    logger.info(f"[extract_query_context] returning {result!r}")
    return result


_QUOTED_TERM_RE = re.compile(r'"([^"]+)"')


def _derive_id_patterns(row: Dict[str, str]) -> List[str]:
    """ID_patterns for retrieve_relevant_content: resource name/abbreviation plus every
    double-quoted term in the discovery query, each re.escape()'d."""
    logger.info(f"[_derive_id_patterns] called with row with {len(row)} field(s)")
    terms = set()
    name = (row.get("Resource Name") or "").strip()
    if name:
        terms.add(name)
    abbrev = (row.get("Abbreviation") or "").strip()
    if abbrev:
        terms.add(abbrev)
    fetched_with = (row.get("Fetched With") or "").strip()
    for m in _QUOTED_TERM_RE.finditer(fetched_with):
        term = m.group(1).strip()
        if term:
            terms.add(term)
    result = [re.escape(t) for t in terms]
    logger.info(f"[_derive_id_patterns] returning {len(result)} pattern(s)")
    return result


def _extract_reasoning(response) -> str:
    """Concatenate every reasoning item's text from a Responses API result - the model's own
    chain-of-thought, distinct from "rationale" (its post-hoc explanation of the verdict)."""
    logger.info("[_extract_reasoning] called")
    texts = []
    for item in response.output:
        if getattr(item, "type", None) == "reasoning":
            for c in getattr(item, "content", None) or []:
                if getattr(c, "text", None):
                    texts.append(c.text)
    result = "\n".join(texts)
    logger.info(f"[_extract_reasoning] returning {len(result)} char(s)")
    return result


def _extract_usage(response) -> Dict[str, int]:
    """input/output/total token counts for one API call, 0s if usage is missing."""
    logger.info("[_extract_usage] called")
    usage = getattr(response, "usage", None)
    if usage is None:
        result = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        logger.info(f"[_extract_usage] returning {result} (no usage on response)")
        return result
    result = {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }
    logger.info(f"[_extract_usage] returning {result}")
    return result


def _sum_usage(usages: List[Dict[str, int]]) -> Dict[str, int]:
    """Sum per-call usage dicts - a row's true cost across every chunk/turn it took, not
    just the winning chunk's own call."""
    logger.info(f"[_sum_usage] called with {len(usages)} usage dict(s)")
    result = {
        "input_tokens": sum(u["input_tokens"] for u in usages),
        "output_tokens": sum(u["output_tokens"] for u in usages),
        "total_tokens": sum(u["total_tokens"] for u in usages),
    }
    logger.info(f"[_sum_usage] returning {result}")
    return result


def _parse_final_message(response) -> Optional[dict]:
    """Pull the first message item's text out of a Responses API result, parse it as JSON,
    and attach the model's reasoning trace under "reasoning"."""
    logger.info("[_parse_final_message] called")
    for item in response.output:
        if getattr(item, "type", None) == "message":
            text = item.content[0].text
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                logger.warning(f"Model returned non-JSON message text: {text[:200]}")
                logger.info("[_parse_final_message] returning None (non-JSON message text)")
                return None
            parsed["reasoning"] = _extract_reasoning(response)
            logger.info(f"[_parse_final_message] returning parsed dict with keys {list(parsed.keys())}")
            return parsed
    logger.info("[_parse_final_message] returning None (no message item found)")
    return None


def _to_claude_messages(rendered: List[dict]) -> tuple:
    """Flatten a render_prompt() message list (role: system/user, OpenAI-style) into
    Claude's shape: system role isn't valid mid-conversation on Claude Sonnet 5, so every
    system-role turn is concatenated into the top-level system string, and every user-role
    turn into one user message."""
    logger.info(f"[_to_claude_messages] called with {len(rendered)} rendered message(s)")
    system_text = "\n\n".join(m["content"] for m in rendered if m["role"] == "system")
    user_text = "\n\n".join(m["content"] for m in rendered if m["role"] == "user")
    result = (system_text, [{"role": "user", "content": user_text}])
    logger.info(f"[_to_claude_messages] returning system={len(system_text)} char(s), 1 user message")
    return result


def _parse_claude_message(response) -> Optional[dict]:
    """Pull the first text block out of a Claude Messages API result, parse it as JSON,
    and attach the model's reasoning trace under "reasoning". output_config.format
    guarantees the first content block is text with valid JSON."""
    logger.info("[_parse_claude_message] called")
    for block in response.content:
        if block.type == "text":
            try:
                parsed = json.loads(block.text)
            except json.JSONDecodeError:
                logger.warning(f"Claude returned non-JSON text block: {block.text[:200]}")
                logger.info("[_parse_claude_message] returning None (non-JSON text block)")
                return None
            parsed["reasoning"] = "\n".join(
                b.thinking for b in response.content if b.type == "thinking" and b.thinking
            )
            logger.info(f"[_parse_claude_message] returning parsed dict with keys {list(parsed.keys())}")
            return parsed
    logger.info("[_parse_claude_message] returning None (no text block found)")
    return None


def _extract_claude_usage(response) -> Dict[str, int]:
    """input/output/total token counts for one Claude Messages API call."""
    logger.info("[_extract_claude_usage] called")
    u = response.usage
    input_tokens = getattr(u, "input_tokens", 0) or 0
    output_tokens = getattr(u, "output_tokens", 0) or 0
    result = {"input_tokens": input_tokens, "output_tokens": output_tokens,
              "total_tokens": input_tokens + output_tokens}
    logger.info(f"[_extract_claude_usage] returning {result}")
    return result


# ---------------------------------------------------------------------------
# Procedure: fulltext - one-shot read of the whole candidate document
# ---------------------------------------------------------------------------

# Deliberately NOT one string passed through a single .format() call: VERIFICATION_RULES and
# FEW_SHOT_EXAMPLES contain literal, unescaped JSON braces (e.g. {"verification_status": ...}),
# which .format() would try to parse as placeholders and crash on (KeyError: '"verification_status"').
# Only the head (which actually has {placeholder}s) goes through .format(); the rules/few-shot
# text is concatenated afterward, untouched.
FULLTEXT_SYSTEM_PROMPT_HEAD = (
    "You are a specialized assistant that verifies whether a specific named resource (e.g. a cohort, "
    "consortium, dataset, or research network) is genuinely discussed in a given scientific publication.\n\n"
    "You will be given a description of the resource to verify, and the full text (or abstract, if "
    "full text isn't available) of a publication. Determine whether the publication actually "
    "discusses this exact resource.\n\n"
    "Resource to verify:\n{resource_info}\n\n"
    "How this candidate paper was originally surfaced during discovery (the search/grep query that "
    "matched it - a specific accession ID or exact-phrase match here is stronger prior evidence than "
    "a broad keyword search hit; \"not available\" means there's no query signal to weigh either way): "
    "{query_context}\n\n"
)


def _build_fulltext_system_prompt(resource_info: str, query_context: str) -> str:
    logger.info(f"[_build_fulltext_system_prompt] called with resource_info={len(resource_info)} char(s), "
                f"query_context={query_context!r}")
    result = (FULLTEXT_SYSTEM_PROMPT_HEAD.format(resource_info=resource_info, query_context=query_context)
              + VERIFICATION_RULES + "\n\n" + FEW_SHOT_EXAMPLES)
    logger.info(f"[_build_fulltext_system_prompt] returning {len(result)} char(s)")
    return result


FULLTEXT_ARTICLE_DIR = Path(os.getenv("FULLTEXT_FETCH_DIR", "/tmp/validate_fetched_publications_raw/"))


def _row_fetch_url(row: Dict[str, str]) -> str:
    """PMC link if present, else a DOI URL, else an OpenAlex work page (oa_W-prefixed) or
    arXiv abstract page (arx_-prefixed) for corpus entries with neither - data_gatherer
    resolves all four. Confirmed live: data_gatherer pulls genuine full text (~240KB of
    JATS/HTML) from PMC/DOI; paperclip's own `cat` truncates every corpus document to a
    ~1.5K char preview regardless of file or section, so it's never used for full text
    here, only for the short abstract fallback."""
    logger.debug(f"[_row_fetch_url] called with row with {len(row)} field(s)")
    link = (row.get("PubMed Central Link") or "").strip()
    if link:
        logger.debug(f"[_row_fetch_url] returning {link!r} (PMC link)")
        return link
    doi = (row.get("DOI") or "").strip()
    if doi:
        result = f"https://doi.org/{doi}"
        logger.debug(f"[_row_fetch_url] returning {result!r} (DOI)")
        return result
    explicit = (row.get("Paperclip Doc ID") or "").strip()
    if explicit.startswith("oa_W"):
        result = f"https://openalex.org/works/{explicit[len('oa_'):]}"
        logger.debug(f"[_row_fetch_url] returning {result!r} (OpenAlex)")
        return result
    if explicit.startswith("arx_"):
        result = f"https://arxiv.org/abs/{explicit[len('arx_'):]}"
        logger.debug(f"[_row_fetch_url] returning {result!r} (arXiv)")
        return result
    row_ids = {k: row.get(k, "") for k in ("Resource Name", "Paperclip Doc ID", "DOI", "PMID")}
    logger.info(f"[_row_fetch_url] returning '' (no fetchable URL) for row {row_ids}")
    return ""


def _classify_fetch_url(url: str) -> str:
    """PMC / doi / other - the same three buckets prefetch_fulltext batches fetches by."""
    logger.info(f"[_classify_fetch_url] called with url={url!r}")
    if re.search(r'PMC\d+', url, re.IGNORECASE):
        logger.info("[_classify_fetch_url] returning 'pmc'")
        return "pmc"
    if url.startswith("https://doi.org/"):
        logger.info("[_classify_fetch_url] returning 'doi'")
        return "doi"
    logger.info("[_classify_fetch_url] returning 'other'")
    return "other"


def prefetch_fulltext(rows_by_url: Dict[str, Dict[str, str]], cache_path: Optional[str] = None) -> Dict[str, Any]:
    """One data_gatherer.fetch_data() call per URL-type group (PMC / DOI / other), instead of
    one call for every URL, and instead of re-instantiating DataGatherer (which reloads model
    weights) per row.

    DataGatherer.fetch_data() keeps every raw fetch for the whole call in memory
    (complete_publication_fetches) and only flushes its on-disk cache once, at the very end
    of the call (data_gatherer.data_fetcher.BackupDataStore.persist/flush - persist() buffers
    everything and flush() is only invoked after the full url list is exhausted). A single
    call over tens of thousands of URLs OOM'd a full_rebuild run and lost the entire run's
    fetches on crash. Splitting by type bounds each call to its group's size and gives each
    group its own flush, so a crash loses at most one group's unflushed fetches.

    Args:
        rows_by_url: Maps each URL to fetch to its (unused) row context.
        cache_path: Stable local_fetch_file/write_df_to_path for DataGatherer's own
            fetch cache. Defaults to the same tables/cache/fetched_fulltext_batch.parquet
            pub_datasets/pub_supplementary/pub_grants/pub_software/pub_models read from
            (via orchestrator.py's fetch_cache_path), so verification and those stages
            don't each independently re-fetch the same articles.

    Returns:
        url -> full text, or a list[str] of section-aware chunks if the document still
        exceeds the model's token limit after reference-stripping (missing/failed fetches
        are simply absent, not empty).
    """
    logger.info(f"[prefetch_fulltext] called with {len(rows_by_url)} url(s), cache_path={cache_path}")
    from data_gatherer.data_gatherer import DataGatherer

    urls = list(rows_by_url.keys())
    if not urls:
        logger.info("[prefetch_fulltext] returning {} (no urls)")
        return {}

    groups: Dict[str, List[str]] = {"pmc": [], "other": [], "doi": []}
    for url in urls:
        groups[_classify_fetch_url(url)].append(url)
    logger.info(f"[fulltext] fetching full text for {len(urls)} unique URL(s) "
                f"({len(groups['pmc'])} PMC / {len(groups['doi'])} DOI / {len(groups['other'])} other)")

    dg = DataGatherer(llm_name="vllm-openai/gpt-oss-20b", clear_previous_logs=False, prompt_dir="prompts",
                       log_level="INFO")
    local_fetch_file = cache_path or "tables/cache/fetched_fulltext_batch.parquet"

    content_by_url: Dict[str, Any] = {}
    last_format = None
    for group_name, group_urls in groups.items():
        if not group_urls:
            continue
        logger.info(f"[fulltext] fetching group '{group_name}' ({len(group_urls)} URL(s))")
        fetched = dg.fetch_data(group_urls, local_fetch_file=local_fetch_file, write_df_to_path=local_fetch_file,
                                    sects_required=0)
        for url in group_urls:
            data = fetched.get(url)
            if not data:
                logger.warning(f"[fulltext] could not fetch {url}")
                continue
            try:
                raw_format = data["raw_data_format"]
                if raw_format != last_format:
                    dg.init_parser_by_input_type(raw_format, data, full_document_read=True)
                    last_format = raw_format
                # remove_refs+enable_chunking: strip the bibliography first, then only split into
                # section-aware chunks (via intelligent_chunk_paper) if it's still over the model's
                # token limit - most docs never chunk, this is a fallback for the ones that do.
                content, _ = dg.normalize_fulltext_input(
                    data["fetched_data"], url, str(FULLTEXT_ARTICLE_DIR), raw_format,
                    remove_refs=True, enable_chunking=True,
                )
                if content:
                    content_by_url[url] = content
            except Exception as e:
                logger.warning(f"[fulltext] failed to normalize {url}: {e}")
        del fetched

    n_chunked = sum(1 for c in content_by_url.values() if isinstance(c, list))
    if n_chunked:
        logger.info(f"[fulltext] {n_chunked}/{len(content_by_url)} document(s) exceeded the token limit "
                    "after reference-stripping and were split into chunks")
    logger.info(f"[fulltext] fetched {len(content_by_url)}/{len(urls)} URL(s) successfully")
    logger.info(f"[prefetch_fulltext] returning {len(content_by_url)} entries")
    return content_by_url


def prefetch_excerpts(rows_by_resource: List[tuple]) -> Dict[tuple, str]:
    """Fetch each unique URL once, then run retrieve_relevant_content() single-threaded per
    (resource_name, url) pair - kept out of the per-resource ThreadPoolExecutor since it
    mutates shared state on dg.parser that would race under concurrent calls.

    Args:
        rows_by_resource: (resource_name, url, id_patterns) tuples, one per row.

    Returns:
        (resource_name, url) -> excerpt text (empty if no ID pattern matched at all).
    """
    logger.info(f"[prefetch_excerpts] called with {len(rows_by_resource)} (resource, url, id_patterns) tuple(s)")
    from data_gatherer.data_gatherer import DataGatherer

    if not rows_by_resource:
        logger.info("[prefetch_excerpts] returning {} (no rows_by_resource)")
        return {}
    urls = list({url for _, url, _ in rows_by_resource if url})
    if not urls:
        logger.info("[prefetch_excerpts] returning {} (no urls)")
        return {}
    logger.info(f"[excerpt] fetching raw content for {len(urls)} unique URL(s), "
                f"{len(rows_by_resource)} (resource, doc) pair(s) to extract")
    dg = DataGatherer(llm_name="vllm-openai/gpt-oss-20b", clear_previous_logs=False, prompt_dir="prompts",
                       log_level="INFO")
    local_fetch_file = "tables/hits/fetched_excerpt_raw.tsv"
    fetched = dg.fetch_data(urls, local_fetch_file=local_fetch_file, write_df_to_path=local_fetch_file)

    excerpt_by_key: Dict[tuple, str] = {}
    last_format = None
    for resource_name, url, id_patterns in rows_by_resource:
        if not url or not id_patterns:
            continue
        data = fetched.get(url)
        if not data:
            logger.warning(f"[excerpt] could not fetch {url}")
            continue
        try:
            raw_format = data["raw_data_format"]
            if raw_format != last_format:
                dg.init_parser_by_input_type(raw_format, data, full_document_read=False)
                last_format = raw_format
            excerpt = dg.parser.retrieve_relevant_content(
                data["fetched_data"],
                semantic_retrieval=False,
                top_k=5,
                output_format="text",
                skip_rule_based_retrieved_elm=False,
                include_snippets_with_ID_patterns=True,
                article_id=dg.data_fetcher.url_to_article_id(url),
                relevant_content_flag="none",
                ID_patterns=id_patterns,
            )
            excerpt_by_key[(resource_name, url)] = excerpt or ""
        except Exception as e:
            logger.warning(f"[excerpt] '{resource_name}'/{url}: retrieve_relevant_content failed: {e}")

    n_empty = sum(1 for v in excerpt_by_key.values() if not v.strip())
    if n_empty:
        logger.info(f"[excerpt] {n_empty}/{len(excerpt_by_key)} (resource, doc) pair(s) had no "
                    "ID-pattern match anywhere in the document")
    logger.info(f"[excerpt] extracted {len(excerpt_by_key)}/{len(rows_by_resource)} (resource, doc) pair(s)")
    logger.info(f"[prefetch_excerpts] returning {len(excerpt_by_key)} entries")
    return excerpt_by_key


def fetch_abstract_only(doc_id: str, row: Optional[Dict[str, str]] = None) -> str:
    """paperclip's own abstract section - a reasonable fallback since abstracts are short
    enough to rarely hit the ~1.5K char preview cap, used when there's no PMC link/DOI to
    fetch full text with at all (e.g. some OpenAlex `oa_` records). Falls back to the row's
    own Abstract column (already fetched from PubMed metadata) when doc_id isn't in
    paperclip's corpus at all - e.g. a PMID with no PMC deposit, so there is no full text
    to be had anywhere and the PubMed abstract is the genuine ceiling."""
    logger.info(f"[fetch_abstract_only] called with doc_id={doc_id!r}")
    out = _paperclip_cli_raw("cat", f"/papers/{doc_id}/sections/Abstract.lines")
    if "ERR:" not in out and out.strip():
        logger.info(f"[fetch_abstract_only] returning {len(out)} char(s) (paperclip abstract)")
        return out
    result = (row or {}).get("Abstract", "").strip()
    logger.info(f"[fetch_abstract_only] returning {len(result)} char(s) (row Abstract fallback)")
    return result


def _best_chunk_verdict(results: List[dict]) -> dict:
    """Reduce one verdict per chunk of an oversized document to a single verdict - a genuine
    mention in any one chunk is enough to confirm the resource, regardless of chunk order, so
    "confirmed" beats "insufficient_evidence" beats "not_confirmed" beats "error". A no-op
    (returns results[0] unchanged) when there's only one chunk, which is the common case."""
    logger.info(f"[_best_chunk_verdict] called with {len(results)} result(s)")
    non_error = [r for r in results if r.get("verification_status") != "error"] or results
    for status in ("confirmed", "insufficient_evidence"):
        for r in non_error:
            if r.get("verification_status") == status:
                out = dict(r)
                if len(non_error) > 1:
                    out["rationale"] = f"[{len(non_error)} chunk(s) checked] " + out.get("rationale", "")
                logger.info(f"[_best_chunk_verdict] returning status={out.get('verification_status')!r}")
                return out
    out = dict(non_error[0])
    if len(non_error) > 1:
        out["rationale"] = f"[{len(non_error)} chunk(s) checked, none confirmed] " + out.get("rationale", "")
    logger.info(f"[_best_chunk_verdict] returning status={out.get('verification_status')!r}")
    return out


def validate_via_fulltext(client: OpenAI, resource_name: str, row: Dict[str, str],
                           doc_id: str, url_to_content: Dict[str, Any] = None,
                           sample_size: str = "") -> dict:
    """Read the candidate document once, whole, and predict a verdict directly - no tool use.
    Content may be a list[str] of chunks (see prefetch_fulltext) for a document that still
    exceeded the token limit after reference-stripping; each chunk gets its own call, reduced
    via _best_chunk_verdict."""
    logger.info(f"[validate_via_fulltext] called with resource_name={resource_name!r}, doc_id={doc_id!r}")
    url = _row_fetch_url(row)
    content = (url_to_content or {}).get(url, "")
    is_full_text = bool(content)
    if not content:
        content = fetch_abstract_only(doc_id, row)
    if not content:
        result = {"verification_status": "error", "claim_text": "n/a",
                  "rationale": f"Could not fetch any text for {doc_id} (url={url!r})"}
        logger.info(f"[validate_via_fulltext] returning status={result['verification_status']!r} (no text fetched)")
        return result
    if not is_full_text:
        logger.info(f"[fulltext] '{resource_name}'/{doc_id}: only an abstract is available, no full text")

    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    chunks = content if isinstance(content, list) else [content]
    instructions = _build_fulltext_system_prompt(resource_info, query_context)
    results = []
    usages = []
    for chunk in chunks:
        response = client.responses.create(
            model=VLLM_MODEL,
            instructions=instructions,
            input=[{"role": "user", "content": f"Publication text:\n\n{chunk}"}],
            temperature=0.0,
            text={"format": RESPONSE_FORMAT},
        )
        usages.append(_extract_usage(response))
        parsed = _parse_final_message(response)
        results.append(parsed or {"verification_status": "error", "claim_text": "n/a",
                                   "rationale": "model returned no parseable message"})

    parsed = _best_chunk_verdict(results)
    parsed.update(_sum_usage(usages))
    if not is_full_text:
        parsed["rationale"] = "[abstract-only, no full text available] " + parsed.get("rationale", "")
    logger.info(f"[validate_via_fulltext] returning status={parsed.get('verification_status')!r}")
    return parsed


def validate_via_fulltext_dg_prompt(client: OpenAI, resource_name: str, row: Dict[str, str],
                                     doc_id: str, url_to_content: Dict[str, Any] = None,
                                     sample_size: str = "", prompt_name: str = DEFAULT_DG_PROMPT_NAME) -> dict:
    """Same procedure as validate_via_fulltext, but built on data_gatherer's own prompting
    machinery (PromptManager.render_prompt against an externalized JSON template) instead
    of a hardcoded Python string - a separate function rather than a drop-in swap so the two
    prompt-loading paths stay comparable against the same held-out cases. Chunk handling
    mirrors validate_via_fulltext (see _best_chunk_verdict). prompt_name selects which JSON
    template under prompts/ to render - every template must accept
    resource_info/query_context/content/n_queries."""
    logger.info(f"[validate_via_fulltext_dg_prompt] called with resource_name={resource_name!r}, "
                f"doc_id={doc_id!r}, prompt_name={prompt_name!r}")
    url = _row_fetch_url(row)
    content = (url_to_content or {}).get(url, "")
    is_full_text = bool(content)
    if not content:
        content = fetch_abstract_only(doc_id, row)
    if not content:
        result = {"verification_status": "error", "claim_text": "n/a",
                  "rationale": f"Could not fetch any text for {doc_id} (url={url!r})"}
        logger.info(f"[validate_via_fulltext_dg_prompt] returning status={result['verification_status']!r} "
                    "(no text fetched)")
        return result
    if not is_full_text:
        logger.info(f"[fulltext_dg_prompt] '{resource_name}'/{doc_id}: only an abstract is available, no full text")

    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    n_queries = row.get("Fetched With", "").count(";") + 1
    static_prompt = _load_dg_static_prompt(prompt_name)
    chunks = content if isinstance(content, list) else [content]
    results = []
    usages = []
    for chunk in chunks:
        messages = _FULLTEXT_PROMPT_MANAGER.render_prompt(
            static_prompt, entire_doc=False,
            resource_info=resource_info, query_context=query_context, content=chunk,
            n_queries=n_queries,
        )
        response = client.responses.create(
            model=VLLM_MODEL,
            input=messages,
            temperature=0.0,
            text={"format": RESPONSE_FORMAT},
        )
        usages.append(_extract_usage(response))
        parsed = _parse_final_message(response)
        results.append(parsed or {"verification_status": "error", "claim_text": "n/a",
                                   "rationale": "model returned no parseable message"})

    parsed = _best_chunk_verdict(results)
    parsed.update(_sum_usage(usages))
    if not is_full_text:
        parsed["rationale"] = "[abstract-only, no full text available] " + parsed.get("rationale", "")
    logger.info(f"[validate_via_fulltext_dg_prompt] returning status={parsed.get('verification_status')!r}")
    return parsed


def validate_via_excerpt_dg_prompt(client: OpenAI, resource_name: str, row: Dict[str, str],
                                    doc_id: str, excerpt_to_content: Dict[tuple, str] = None,
                                    sample_size: str = "", prompt_name: str = DEFAULT_DG_PROMPT_NAME) -> dict:
    """Like validate_via_fulltext_dg_prompt, but feeds only the resource-relevant excerpt (see
    prefetch_excerpts) instead of the whole document. excerpt_to_content is keyed by
    (resource_name, url), not just url."""
    logger.info(f"[validate_via_excerpt_dg_prompt] called with resource_name={resource_name!r}, "
                f"doc_id={doc_id!r}, prompt_name={prompt_name!r}")
    url = _row_fetch_url(row)
    excerpt = (excerpt_to_content or {}).get((resource_name, url), "")
    if not excerpt.strip():
        result = {"verification_status": "not_confirmed", "claim_text": "n/a",
                  "rationale": "No occurrence of the resource's name, abbreviation, or discovery-query "
                                "terms found anywhere in the document's full text."}
        logger.info(f"[validate_via_excerpt_dg_prompt] returning status={result['verification_status']!r} "
                    "(empty excerpt)")
        return result

    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    n_queries = row.get("Fetched With", "").count(";") + 1
    static_prompt = _load_dg_static_prompt(prompt_name)
    messages = _FULLTEXT_PROMPT_MANAGER.render_prompt(
        static_prompt, entire_doc=False,
        resource_info=resource_info, query_context=query_context, content=excerpt,
        n_queries=n_queries,
    )
    response = client.responses.create(
        model=VLLM_MODEL,
        input=messages,
        temperature=0.0,
        text={"format": RESPONSE_FORMAT},
    )
    usage = _extract_usage(response)
    parsed = _parse_final_message(response)
    if parsed is None:
        result = {"verification_status": "error", "claim_text": "n/a",
                  "rationale": "model returned no parseable message", **usage}
        logger.info(f"[validate_via_excerpt_dg_prompt] returning status={result['verification_status']!r} "
                    "(unparseable model output)")
        return result
    parsed.update(usage)
    logger.info(f"[validate_via_excerpt_dg_prompt] returning status={parsed.get('verification_status')!r}")
    return parsed


def validate_via_fulltext_dg_prompt_claude(client, resource_name: str, row: Dict[str, str],
                                            doc_id: str, url_to_content: Dict[str, Any] = None,
                                            sample_size: str = "", prompt_name: str = DEFAULT_DG_PROMPT_NAME) -> dict:
    """Same as validate_via_fulltext_dg_prompt, but calls Claude Sonnet 5 via the Anthropic
    SDK instead of vLLM - a separate function, not a drop-in swap, so the two backends stay
    comparable on the same held-out cases. client is accepted for calling-convention parity
    with every other METHOD_FUNCS entry but unused; this always calls _anthropic_client, a
    different SDK's client object."""
    logger.info(f"[validate_via_fulltext_dg_prompt_claude] called with resource_name={resource_name!r}, "
                f"doc_id={doc_id!r}, prompt_name={prompt_name!r}")
    url = _row_fetch_url(row)
    content = (url_to_content or {}).get(url, "")
    is_full_text = bool(content)
    if not content:
        content = fetch_abstract_only(doc_id, row)
    if not content:
        result = {"verification_status": "error", "claim_text": "n/a",
                  "rationale": f"Could not fetch any text for {doc_id} (url={url!r})"}
        logger.info(f"[validate_via_fulltext_dg_prompt_claude] returning status={result['verification_status']!r} "
                    "(no text fetched)")
        return result
    if not is_full_text:
        logger.info(f"[fulltext_dg_prompt_claude] '{resource_name}'/{doc_id}: only an abstract is available, no full text")

    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    n_queries = row.get("Fetched With", "").count(";") + 1
    static_prompt = _load_dg_static_prompt(prompt_name)
    chunks = content if isinstance(content, list) else [content]
    results = []
    usages = []
    for chunk in chunks:
        rendered = _FULLTEXT_PROMPT_MANAGER.render_prompt(
            static_prompt, entire_doc=False,
            resource_info=resource_info, query_context=query_context, content=chunk,
            n_queries=n_queries,
        )
        system_text, claude_messages = _to_claude_messages(rendered)
        response = _anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=system_text,
            messages=claude_messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"format": ANTHROPIC_RESPONSE_FORMAT},
        )
        usages.append(_extract_claude_usage(response))
        parsed = _parse_claude_message(response)
        results.append(parsed or {"verification_status": "error", "claim_text": "n/a",
                                   "rationale": "model returned no parseable message"})

    parsed = _best_chunk_verdict(results)
    parsed.update(_sum_usage(usages))
    if not is_full_text:
        parsed["rationale"] = "[abstract-only, no full text available] " + parsed.get("rationale", "")
    logger.info(f"[validate_via_fulltext_dg_prompt_claude] returning status={parsed.get('verification_status')!r}")
    return parsed


def validate_via_excerpt_dg_prompt_claude(client, resource_name: str, row: Dict[str, str],
                                           doc_id: str, excerpt_to_content: Dict[tuple, str] = None,
                                           sample_size: str = "", prompt_name: str = DEFAULT_DG_PROMPT_NAME) -> dict:
    """Like validate_via_fulltext_dg_prompt_claude, but feeds only the resource-relevant
    excerpt (see prefetch_excerpts) instead of the whole document. client is accepted for
    calling-convention parity but unused - see validate_via_fulltext_dg_prompt_claude."""
    logger.info(f"[validate_via_excerpt_dg_prompt_claude] called with resource_name={resource_name!r}, "
                f"doc_id={doc_id!r}, prompt_name={prompt_name!r}")
    url = _row_fetch_url(row)
    excerpt = (excerpt_to_content or {}).get((resource_name, url), "")
    if not excerpt.strip():
        result = {"verification_status": "not_confirmed", "claim_text": "n/a",
                  "rationale": "No occurrence of the resource's name, abbreviation, or discovery-query "
                                "terms found anywhere in the document's full text."}
        logger.info(f"[validate_via_excerpt_dg_prompt_claude] returning status={result['verification_status']!r} "
                    "(empty excerpt)")
        return result

    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    n_queries = row.get("Fetched With", "").count(";") + 1
    static_prompt = _load_dg_static_prompt(prompt_name)
    rendered = _FULLTEXT_PROMPT_MANAGER.render_prompt(
        static_prompt, entire_doc=False,
        resource_info=resource_info, query_context=query_context, content=excerpt,
        n_queries=n_queries,
    )
    system_text, claude_messages = _to_claude_messages(rendered)
    response = _anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=system_text,
        messages=claude_messages,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"format": ANTHROPIC_RESPONSE_FORMAT},
    )
    usage = _extract_claude_usage(response)
    parsed = _parse_claude_message(response)
    if parsed is None:
        result = {"verification_status": "error", "claim_text": "n/a",
                  "rationale": "model returned no parseable message", **usage}
        logger.info(f"[validate_via_excerpt_dg_prompt_claude] returning status={result['verification_status']!r} "
                    "(unparseable model output)")
        return result
    parsed.update(usage)
    logger.info(f"[validate_via_excerpt_dg_prompt_claude] returning status={parsed.get('verification_status')!r}")
    return parsed


# ---------------------------------------------------------------------------
# Procedure: agentic_search - model drives paperclip search/grep as tools
# ---------------------------------------------------------------------------

# Same reasoning as _build_fulltext_system_prompt above: VERIFICATION_RULES/FEW_SHOT_EXAMPLES's
# literal JSON braces must never pass through .format() - only HEAD and TAIL (which actually
# contain {placeholder}s) do, formatted separately and stitched around the literal rules/few-shot
# text.
AGENTIC_SYSTEM_PROMPT_HEAD = (
    "You are a specialized assistant that verifies whether a specific named resource (e.g. a cohort, "
    "consortium, dataset, or research network) is genuinely discussed in a specific candidate paper.\n\n"
    "Resource to verify:\n{resource_info}\n\n"
    "Candidate paper: {doc_id}\n\n"
    "How this candidate was originally surfaced during discovery (the search/grep query that matched "
    "it - \"not available\" means there's no query signal to weigh either way): {query_context}\n\n"
    "## Investigation strategy\n"
    "You MUST call `paperclip_grep_document` at least once before answering - this is the step that "
    "demonstrates a claim rather than assuming it. Start with the exact pattern from the discovery "
    "query above if there is one (re-running it against this specific paper, not the whole corpus), "
    "otherwise start with the resource's name/abbreviation/accession ID. Read the returned passage(s) "
    "and judge whether they genuinely discuss this resource, not just contain the string. If that "
    "grep finds nothing, use `paperclip_search`/`paperclip_grep_corpus` to check how the term is used "
    "across the wider corpus - this helps you tell a genuine mention that grep missed (e.g. paraphrased) "
    "from a term that simply doesn't appear in this specific paper.\n\n"
    "Do not conclude \"confirmed\" from a corpus-wide search or from the discovery query alone - only "
    "`paperclip_grep_document` results (from the candidate paper itself) count as evidence the paper "
    "discusses this resource.\n\n"
)

AGENTIC_SYSTEM_PROMPT_TAIL = (
    "## Budget\n"
    "Hard limit: {max_turns} tool calls. Once you have called `paperclip_grep_document` and have enough "
    "evidence (or have exhausted reasonable queries), answer directly with the JSON verdict instead of "
    "calling another tool."
)


def _build_agentic_system_prompt(resource_info: str, doc_id: str, query_context: str, max_turns: int) -> str:
    logger.info(f"[_build_agentic_system_prompt] called with doc_id={doc_id!r}, max_turns={max_turns}")
    result = (AGENTIC_SYSTEM_PROMPT_HEAD.format(resource_info=resource_info, doc_id=doc_id, query_context=query_context)
              + VERIFICATION_RULES + "\n\n" + FEW_SHOT_EXAMPLES + "\n\n"
              + AGENTIC_SYSTEM_PROMPT_TAIL.format(max_turns=max_turns))
    logger.info(f"[_build_agentic_system_prompt] returning {len(result)} char(s)")
    return result

AGENT_TOOLS = [
    {
        "type": "function",
        "name": "paperclip_grep_document",
        "description": "Grep the candidate paper's own full text for a pattern, with surrounding "
                        "context lines. This is the primary evidence-gathering tool - a hit here is "
                        "the paper itself discussing the term, not just corpus-wide correlation.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "context_lines": {"type": "integer", "description": "lines of context before/after each match (default 3)"},
            },
            "required": ["pattern"],
        },
    },
    {
        "type": "function",
        "name": "paperclip_grep_corpus",
        "description": "Literal/regex grep across the whole paperclip corpus (not just this paper). "
                        "Use to judge how common/ambiguous a name or acronym is, or to find how the "
                        "term is used elsewhere when it's absent from the candidate paper.",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]},
    },
    {
        "type": "function",
        "name": "paperclip_search",
        "description": "Semantic + keyword search across the corpus (sources given at startup). "
                        "Broader than grep but can miss exact-string matches - escalate to grep on "
                        "no results.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "exact": {"type": "boolean", "description": "exact phrase match (-e)"},
            },
            "required": ["query"],
        },
    },
]


def _execute_agent_tool(name: str, args: dict, doc_id: str, sources: str) -> str:
    logger.info(f"[_execute_agent_tool] called with name={name!r}, doc_id={doc_id!r}")
    if name == "paperclip_grep_document":
        context = args.get("context_lines", 3)
        out = _paperclip_cli_raw("grep", "-n", "-C", str(context), args["pattern"], f"/papers/{doc_id}/content.lines")
        result = out[:4000] or "(no matches)"
    elif name == "paperclip_grep_corpus":
        out = _paperclip_cli_raw("grep", "-n", args["pattern"], "/papers/")
        result = out[:4000] or "(no matches)"
    elif name == "paperclip_search":
        cmd = ["search", "-s", sources]
        if args.get("exact"):
            cmd.append("-e")
        cmd.append(args["query"])
        result = _paperclip_cli_raw(*cmd)[:4000] or "(no matches)"
    else:
        result = f"Unknown tool: {name}"
    # DEBUG, not INFO: this is the per-tool-call trail that's only useful when diagnosing
    # a specific doc_id's verdict (why it went confirmed/not_confirmed) - too fine-grained
    # for the default log level across a run of hundreds of docs.
    logger.debug(f"[agentic] {doc_id}: {name}({args}) -> {len(result)} chars: {result[:200]!r}")
    logger.info(f"[_execute_agent_tool] returning {len(result)} char(s)")
    return result


def validate_via_agentic_search(client: OpenAI, resource_name: str, row: Dict[str, str],
                                 doc_id: str, sources: str, sample_size: str = "",
                                 max_turns: int = 12) -> dict:
    """Let the model drive paperclip search/grep to corroborate the candidate doc_id against
    the resource's identifying details, then have it predict the verdict directly - paperclip's
    own repo/commit/--verify subsystem is never invoked."""
    logger.info(f"[validate_via_agentic_search] called with resource_name={resource_name!r}, "
                f"doc_id={doc_id!r}, max_turns={max_turns}")
    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    system_prompt = _build_agentic_system_prompt(resource_info, doc_id, query_context, max_turns)
    input_items: List[dict] = [{"role": "user", "content": "Begin the investigation."}]
    usages = []

    # Two phases, deliberately never combined in one call - confirmed live against this
    # vLLM/gpt-oss deployment: a forced json_schema `text.format` alongside `tools` on the
    # same request suppresses tool-calling entirely (the model's own reasoning says "call
    # paperclip_grep_document", then it emits the schema-shaped JSON directly instead - same
    # prompt with `text.format` dropped produces a real function_call). So phase 1 drives
    # tool use with no format constraint; phase 2 asks once for the structured verdict with
    # tools dropped, so there's no ambiguity about whether to call one more tool vs. answer.
    for turn in range(max_turns):
        response = client.responses.create(
            model=VLLM_MODEL,
            instructions=system_prompt,
            input=input_items,
            tools=AGENT_TOOLS,
            temperature=0.0,
        )
        usages.append(_extract_usage(response))
        input_items += [item.model_dump() for item in response.output]

        function_calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        logger.debug(f"[agentic] {doc_id}: turn {turn + 1}/{max_turns}, {len(function_calls)} tool call(s)")
        if not function_calls:
            break

        for call in function_calls:
            try:
                args = json.loads(call.arguments)
                output = _execute_agent_tool(call.name, args, doc_id, sources)
            except Exception as e:
                output = f"tool error: {e}"
            input_items.append({"type": "function_call_output", "call_id": call.call_id, "output": output})
    else:
        logger.warning(f"[agentic] '{resource_name}'/{doc_id}: hit the {max_turns}-tool-call budget "
                        "still calling tools - finalizing on whatever evidence was gathered")

    input_items.append({"role": "user", "content": "Give your final verdict now, as the required JSON object."})
    response = client.responses.create(
        model=VLLM_MODEL,
        instructions=system_prompt,
        input=input_items,
        temperature=0.0,
        text={"format": RESPONSE_FORMAT},
    )
    usages.append(_extract_usage(response))
    total_usage = _sum_usage(usages)
    parsed = _parse_final_message(response)
    if parsed is not None:
        parsed.update(total_usage)
        logger.info(f"[validate_via_agentic_search] returning status={parsed.get('verification_status')!r}")
        return parsed
    result = {"verification_status": "error", "claim_text": "n/a",
              "rationale": "model returned no parseable final verdict", **total_usage}
    logger.info(f"[validate_via_agentic_search] returning status={result['verification_status']!r} "
                "(no parseable final verdict)")
    return result


def build_fulltext_batch_jsonl(df: pd.DataFrame, resource_col: str, output_path: Path, sources: str,
                                sample_sizes: Dict[str, str], prompt_name: str = DEFAULT_DG_PROMPT_NAME) -> Path:
    """Build an OpenAI-batch-format JSONL (one line per (resource, doc_id, chunk) request) for the
    fulltext_dg_prompt procedure - full document text, not an excerpt.

    Fetches/normalizes exactly like prefetch_fulltext (clean stripped text, chunked only if still
    over the token limit after ref-stripping), rendering each row's messages ourselves via
    render_prompt with the full resource_info/query_context/content/n_queries set, then hands the
    finished request list to data_gatherer's own LLMClient._handle_batch_mode - the same call
    run_integrated_batch_processing itself delegates to for writing the batch file. Bypasses only
    run_integrated_batch_processing's own render_prompt call, which passes content/repos/url/
    section_filter and has no slot for a per-row resource_info/query_context.
    """
    logger.info(f"[build_fulltext_batch_jsonl] called with {len(df)} row(s), resource_col={resource_col!r}, "
                f"output_path={output_path}, prompt_name={prompt_name!r}")
    from data_gatherer.data_gatherer import DataGatherer

    rows = df.to_dict("records")
    doc_ids = [_resolve_doc_id(row) for row in rows]
    resolved_rows = [(row, doc_id) for row, doc_id in zip(rows, doc_ids) if doc_id]
    logger.info(f"[batch] {len(resolved_rows)}/{len(rows)} rows resolved to a doc_id")

    urls = list({_row_fetch_url(row) for row, _ in resolved_rows if _row_fetch_url(row)})
    # Same file prefetch_fulltext()/prefetch_articles() read/write - the offline batch
    # builder and the live sync path share one fetch cache, not three separate ones.
    checkpoint_path = Path("tables/cache/fetched_fulltext_batch.parquet")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    if checkpoint_path.exists():
        logger.info(f"[batch] resuming from existing checkpoint {checkpoint_path}")

    # BackupDataStore (data_gatherer's data_fetcher.py) persists every successful fetch to
    # write_df_to_path incrementally (flushing - a disk merge, not an overwrite - every 200
    # fetches, plus a final flush for the remainder), so a single call over the whole URL list
    # is already crash-bounded to at most ~200 URLs of loss, with no need for our own outer
    # chunking/checkpointing loop.
    dg = DataGatherer(llm_name="vllm-openai/gpt-oss-20b", clear_previous_logs=False,
                       process_entire_document=True, prompt_dir="prompts", log_level="INFO")
    fetched = dg.fetch_data(urls, local_fetch_file=str(checkpoint_path), write_df_to_path=str(checkpoint_path))
    logger.info(f"[batch] fetched {len(fetched)}/{len(urls)} URL(s)")

    content_by_url: Dict[str, Any] = {}
    logger.info(f"[batch] normalizing full text for {len(urls)} unique URL(s)")
    last_format = None
    for idx, url in enumerate(urls):
        logger.info(f"progress: {idx}/{len(urls)}")
        data = fetched.get(url)
        if not data:
            logger.warning(f"[batch] could not fetch {url}")
            continue
        try:
            raw_format = data["raw_data_format"]
            if raw_format != last_format:
                dg.init_parser_by_input_type(raw_format, data, full_document_read=True)
                last_format = raw_format
            content, _ = dg.normalize_fulltext_input(
                data["fetched_data"], url, str(FULLTEXT_ARTICLE_DIR), raw_format,
                remove_refs=True, enable_chunking=True,
            )
            if content:
                content_by_url[url] = content
        except Exception as e:
            logger.warning(f"[batch] failed to normalize {url}: {e}")

    static_prompt = _load_dg_static_prompt(prompt_name)
    batch_requests = []
    seen = set()
    for row_idx, (row, doc_id) in enumerate(resolved_rows):
        resource_name = row.get(resource_col, "")
        if (resource_name, doc_id) in seen:
            continue
        seen.add((resource_name, doc_id))
        url = _row_fetch_url(row)
        content = content_by_url.get(url) or fetch_abstract_only(doc_id, row)
        if not content:
            logger.warning(f"[batch] '{resource_name}'/{doc_id}: no text available, skipped")
            continue
        resource_info = compose_resource_info(row, sample_sizes.get(resource_name, ""))
        query_context = extract_query_context(row)
        n_queries = row.get("Fetched With", "").count(";") + 1
        chunks = content if isinstance(content, list) else [content]
        # doc_id goes first and resource_name is truncated, not the reverse - a long compound
        # resource_name (common for catalog sub-study entries) must never swallow doc_id out of
        # the string, or two different (resource, doc) pairs collapse onto the same custom_id.
        # row_idx is the actual uniqueness guarantee; the rest is just for readability.
        safe_doc = re.sub(r'[^a-zA-Z0-9_-]', '_', doc_id)
        safe_resource = re.sub(r'[^a-zA-Z0-9_-]', '_', resource_name)[:40]
        base_custom_id = f"{safe_doc}_{safe_resource}_{row_idx}"
        for chunk_idx, chunk in enumerate(chunks):
            messages = _FULLTEXT_PROMPT_MANAGER.render_prompt(
                static_prompt, entire_doc=False,
                resource_info=resource_info, query_context=query_context, content=chunk,
                n_queries=n_queries,
            )
            batch_requests.append({
                "custom_id": f"{base_custom_id}_{chunk_idx}",
                "messages": messages,
                "metadata": {"resource_name": resource_name, "doc_id": doc_id, "url": url},
            })

    logger.info(f"[batch] rendered {len(batch_requests)} request(s), writing batch file via LLMClient")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dg.parser.llm_client._handle_batch_mode(
        batch_requests=batch_requests,
        batch_file_path=str(output_path),
        temperature=0.0,
        response_format=RESPONSE_FORMAT,
        api_provider="openai",
    )
    # _handle_batch_mode writes self.model (here "vllm-openai/gpt-oss-20b") verbatim into each
    # request's body.model - unlike the live api_call path, which strips the "vllm-" prefix before
    # sending it to the server (llm_client.py's self.model[len('vllm-'):]). The prefixed form is
    # only needed locally, for DataGatherer's own entire_document_models allowlist check; a served
    # model named "vllm-openai/gpt-oss-20b" doesn't exist, so every request would 404 unfixed.
    with open(output_path) as f:
        lines = [json.loads(line) for line in f]
    for line in lines:
        line["body"]["model"] = VLLM_MODEL
    with open(output_path, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    logger.info(f"[batch] wrote {len(batch_requests)} request(s) → {output_path}")
    logger.info(f"[build_fulltext_batch_jsonl] returning {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Batch results ingestion - the other half of the offline batch workflow:
# build_fulltext_batch_jsonl above writes requests; this reads back the results
# scripts/run_vllm_jsonl_batch.py produced from them.
# ---------------------------------------------------------------------------

_SMART_QUOTES = str.maketrans({"“": '"', "”": '"'})

# Fetched With prefixes that unambiguously tag a query method. scrape_publications.py's
# search_pubmed() tags original/v2/v3/v4 too (see search_pubmed and _search_pubmed_fanout) -
# older combine_hits files predating that fix still have untagged original/v2/v3/v4 rows,
# which fall into "other" since they're indistinguishable from each other without a tag.
_TAGGED_METHOD_RE = re.compile(r"^(paperclip|v5|v4|v3|v2|original):")

# The 8 pre-merge files that fed into the first combine_hits.tsv's "other" bucket - q1-q4
# map to query_method original/v2/v3/v4 (confirmed via the method labels in
# docs/plans/paperclip/experiments/coverage_comparison_queries.ipynb). Used to recover the
# original/v2/v3/v4 split for rows predating the Fetched With tagging fix.
_EXPERIMENTS_DIR = Path(__file__).parent.parent / "docs" / "plans" / "paperclip" / "experiments"
_Q_FILE_METHODS = {
    "q1_pubmed_full.tsv": "original", "q1_pmc_full.tsv": "original",
    "q2_pubmed_full.tsv": "v2", "q2_pmc_full.tsv": "v2",
    "q3_pubmed_full.tsv": "v3", "q3_pmc_full.tsv": "v3",
    "q4_pubmed_full.tsv": "v4", "q4_pmc_full.tsv": "v4",
}


def _parse_output_text(output_text: str) -> Optional[dict]:
    """Parse a response's output_text as the {verification_status, claim_text, rationale}
    JSON object. Falls back to normalizing smart quotes (a known vLLM/gpt-oss-20b
    structured-output quirk) before giving up. Returns None if still unparseable."""
    logger.info(f"[_parse_output_text] called with output_text of type {type(output_text).__name__}")
    try:
        result = json.loads(output_text)
        logger.info(f"[_parse_output_text] returning parsed dict with keys {list(result.keys())}")
        return result
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        result = json.loads(output_text.translate(_SMART_QUOTES))
        logger.info(f"[_parse_output_text] returning parsed dict with keys {list(result.keys())} "
                    "(smart-quote fallback)")
        return result
    except (json.JSONDecodeError, TypeError, AttributeError):
        logger.info("[_parse_output_text] returning None (unparseable)")
        return None


def _batch_number(path: Path) -> int:
    logger.info(f"[_batch_number] called with path={path}")
    m = re.search(r"fulltext_batch_(\d+)_results\.jsonl", path.name)
    result = int(m.group(1)) if m else -1
    logger.info(f"[_batch_number] returning {result}")
    return result


def _query_methods(fetched_with: str) -> set:
    """A row's Fetched With is a semicolon-joined union of every method that (re)discovered
    it (see staging/combine_hits.py) - a single row can carry more than one method."""
    logger.info(f"[_query_methods] called with fetched_with={fetched_with!r}")
    methods = set()
    for segment in fetched_with.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        m = _TAGGED_METHOD_RE.match(segment)
        methods.add(m.group(1) if m else "other")
    logger.info(f"[_query_methods] returning {methods}")
    return methods


def _load_pre_merge_method_index(experiments_dir: Path) -> dict:
    """(key_type, value) -> set of methods, built from the pre-combine_hits.py experiment
    files - lets "other"-tagged rows (predating the Fetched With tagging fix) be resolved
    back to their real original/v2/v3/v4 method by identity-key match."""
    logger.info(f"[_load_pre_merge_method_index] called with experiments_dir={experiments_dir}")
    from combine_hits import _row_identity_keys

    index: dict = {}
    for filename, method in _Q_FILE_METHODS.items():
        path = experiments_dir / filename
        if not path.exists():
            continue
        df = pd.read_csv(path, sep="\t", dtype=str).fillna("")
        for row in df.to_dict("records"):
            for key in _row_identity_keys(row):
                index.setdefault(key, set()).add(method)
    logger.info(f"[_load_pre_merge_method_index] returning {len(index)} key(s)")
    return index


def _load_doc_id_lookup(combine_hits_path: Path, pre_merge_index: Optional[dict] = None) -> dict:
    """(resource_name, doc_id) -> set of query methods, using the exact same doc_id
    resolution build_fulltext_batch_jsonl used when building the batch requests.

    If pre_merge_index is given, any row tagged "other" (predating the Fetched With
    tagging fix) is cross-referenced against it by identity key (PMID/DOI/PMC ID/doc_id)
    to recover its real original/v2/v3/v4 method - "other" is only kept as a last resort
    when no pre-merge file matches it at all."""
    logger.info(f"[_load_doc_id_lookup] called with combine_hits_path={combine_hits_path}, "
                f"pre_merge_index={'given' if pre_merge_index is not None else None}")
    from combine_hits import _row_identity_keys

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
    logger.info(f"[_load_doc_id_lookup] returning {len(lookup)} key(s)")
    return lookup


def ingest_fulltext_batch_results(results_dir: Path, combine_hits_path: Optional[Path] = None,
                                   experiments_dir: Path = _EXPERIMENTS_DIR) -> pd.DataFrame:
    """Ingest scripts/run_vllm_jsonl_batch.py output into one verdict row per (resource_name,
    doc_id) - the other half of the offline batch workflow build_fulltext_batch_jsonl starts.

    Reduces multiple oversized-document chunks to a single verdict via _best_chunk_verdict
    (confirmed > insufficient_evidence > not_confirmed > error). Logs a full diagnostic report
    (per-batch success/error/unparseable counts, verification_status breakdown, top error
    messages, and - if combine_hits_path is given - a verification_status x query_method
    breakdown) rather than returning it, since this is meant to run unattended as a pipeline
    stage.

    Args:
        results_dir: Directory of fulltext_batch_*_results.jsonl files.
        combine_hits_path: Optional combine_hits_*.tsv - enables the query_method breakdown.
        experiments_dir: Pre-merge q1-q4 experiment files dir, used to resolve "other"-tagged
            rows back to original/v2/v3/v4.

    Returns:
        DataFrame with one row per (resource_name, doc_id): resource_name, doc_id, url,
        verification_status, claim_text, rationale, method.
    """
    logger.info(f"[ingest_fulltext_batch_results] called with results_dir={results_dir}, "
                f"combine_hits_path={combine_hits_path}")
    files = sorted(results_dir.glob("fulltext_batch_*_results.jsonl"), key=_batch_number)
    logger.info(f"[ingest] found {len(files)} results file(s) in {results_dir}")

    per_batch: Dict[int, Dict[str, int]] = {}
    overall_status = Counter()
    overall_errors = Counter()
    by_key: Dict[tuple, List[dict]] = {}
    n_unparseable = 0

    for f in files:
        batch_num = _batch_number(f)
        stats = per_batch.setdefault(batch_num, {"total": 0, "success": 0, "error": 0, "unparseable": 0})
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                stats["total"] += 1
                meta = rec.get("metadata") or {}
                key = (meta.get("resource_name", ""), meta.get("doc_id", ""))

                if "error" in rec:
                    stats["error"] += 1
                    overall_errors[rec["error"][:60]] += 1
                    verdict = {"verification_status": "error", "claim_text": "n/a", "rationale": rec["error"]}
                else:
                    parsed = _parse_output_text(rec.get("output_text", ""))
                    if parsed is None:
                        stats["unparseable"] += 1
                        n_unparseable += 1
                        verdict = {
                            "verification_status": "error", "claim_text": "n/a",
                            "rationale": f"unparseable output_text: {rec.get('output_text', '')[:200]!r}",
                        }
                    else:
                        stats["success"] += 1
                        overall_status[parsed.get("verification_status", "(missing key)")] += 1
                        verdict = parsed
                verdict["url"] = meta.get("url", "")
                by_key.setdefault(key, []).append(verdict)

    rows = []
    for (resource_name, doc_id), verdicts in by_key.items():
        best = _best_chunk_verdict(verdicts)
        rows.append({
            "resource_name": resource_name,
            "doc_id": doc_id,
            "url": best.get("url", ""),
            "verification_status": best.get("verification_status", ""),
            "claim_text": best.get("claim_text", ""),
            "rationale": best.get("rationale", ""),
            "method": "vllm_fulltext_dg_prompt",
        })
    result_df = pd.DataFrame(rows)

    # --- diagnostic report, logged rather than returned ---
    total = sum(s["total"] for s in per_batch.values())
    n_success = sum(s["success"] for s in per_batch.values())
    total_error = sum(s["error"] for s in per_batch.values())
    logger.info(f"[ingest] {total} result line(s) across {len(files)} batch(es) -> "
                f"{len(by_key)} unique (resource, doc_id) pair(s)")
    logger.info(f"[ingest] {'Batch':>6}  {'Total':>6}  {'Success':>8}  {'Error':>6}  {'Unparseable':>11}")
    for batch_num in sorted(per_batch):
        s = per_batch[batch_num]
        logger.info(f"[ingest] {batch_num:>6}  {s['total']:>6}  {s['success']:>8}  "
                    f"{s['error']:>6}  {s['unparseable']:>11}")
    logger.info(f"[ingest] {'TOTAL':>6}  {total:>6}  {n_success:>8}  {total_error:>6}  {n_unparseable:>11}")

    logger.info("[ingest] verification_status (of parsed successes):")
    for status, count in overall_status.most_common():
        logger.info(f"[ingest]   {status:25s} {count:6d}  ({100 * count / max(n_success, 1):.1f}%)")

    if overall_errors:
        logger.info("[ingest] top error messages:")
        for msg, count in overall_errors.most_common(10):
            logger.info(f"[ingest]   {count:5d}x  {msg}")

    if combine_hits_path is not None:
        pre_merge_index = _load_pre_merge_method_index(experiments_dir)
        doc_id_lookup = _load_doc_id_lookup(combine_hits_path, pre_merge_index)
        method_status_counts = Counter()
        n_unmatched = 0
        for row in rows:
            methods = doc_id_lookup.get((row["resource_name"], row["doc_id"]))
            if methods:
                for method in methods:
                    method_status_counts[(method, row["verification_status"])] += 1
            else:
                n_unmatched += 1

        methods_seen = sorted({m for m, _ in method_status_counts})
        statuses_seen = sorted({s for _, s in method_status_counts})
        logger.info("[ingest] verification_status x query_method (rows found by >1 method "
                    "count in each - totals per method won't sum to n_success):")
        header = f"{'method':12s}" + "".join(f"{s:>24s}" for s in statuses_seen) + f"{'total':>10s}"
        logger.info(f"[ingest] {header}")
        for method in methods_seen:
            row_counts = [method_status_counts.get((method, s), 0) for s in statuses_seen]
            logger.info(f"[ingest] {method:12s}" + "".join(f"{c:>24d}" for c in row_counts) +
                        f"{sum(row_counts):>10d}")
        if n_unmatched:
            logger.warning(f"[ingest] {n_unmatched} row(s) had no matching (resource_name, doc_id) "
                            f"in {combine_hits_path.name}")

    logger.info(f"[ingest_fulltext_batch_results] returning {len(result_df)} row(s)")
    return result_df


def seed_cache_from_batch_results(
    results_dir: Path,
    cache_path: Path = DEFAULT_CACHE_PATH,
    dg_prompt_name: str = DEFAULT_DG_PROMPT_NAME,
    combine_hits_path: Optional[Path] = None,
) -> int:
    """One-time backfill: load the offline vLLM batch's verdicts into the same cache
    validate_group()/validate_publications_df() read from, so the live sync verification
    path (wired into orchestrator.py's misc_mode) doesn't re-verify pairs the batch already
    covered.

    The batch was built by build_fulltext_batch_jsonl() with the same per-chunk rendering
    validate_via_fulltext_dg_prompt() uses live, so its verdicts are cached under the
    "fulltext_dg_prompt:<dg_prompt_name>" method key - cache_key()'s exact format,
    matching what validate_group() looks up for method="fulltext_dg_prompt". Error verdicts
    are skipped, same as validate_group()'s own cache-write rule (a transient failure
    shouldn't become permanent across runs). Existing cache entries are merged into, not
    replaced.

    Args:
        results_dir: Directory of fulltext_batch_*_results.jsonl files.
        cache_path: Cache file to merge into (default: DEFAULT_CACHE_PATH).
        dg_prompt_name: Prompt template name the batch was built with.
        combine_hits_path: Optional combine_hits_*.tsv, enables ingest's query_method
            breakdown log (no effect on what's seeded).

    Returns:
        Number of new (non-error) entries added to the cache.
    """
    logger.info(f"[seed_cache_from_batch_results] called with results_dir={results_dir}, "
                f"cache_path={cache_path}, dg_prompt_name={dg_prompt_name!r}")
    df = ingest_fulltext_batch_results(results_dir, combine_hits_path=combine_hits_path)
    if df.empty:
        logger.warning("[seed-cache] no batch results ingested — nothing to seed")
        logger.info("[seed_cache_from_batch_results] returning 0 (no batch results)")
        return 0

    cache = load_cache(cache_path)
    method = f"fulltext_dg_prompt:{dg_prompt_name}"
    n_added = 0
    n_error = 0
    for row in df.to_dict("records"):
        if row["verification_status"] == "error":
            n_error += 1
            logger.debug(f"[seed-cache] skipping error verdict for {row['resource_name']}/{row['doc_id']}")
            continue
        key = cache_key(row["resource_name"], row["doc_id"], method)
        cache[key] = {
            "verification_status": row["verification_status"],
            "claim_text": row["claim_text"],
            "rationale": row["rationale"],
        }
        n_added += 1

    save_cache(cache_path, cache)
    logger.info(f"[seed-cache] seeded {n_added} entries under method='{method}' "
                f"({n_error} error verdict(s) skipped) -> {cache_path}")
    logger.info(f"[seed_cache_from_batch_results] returning {n_added}")
    return n_added


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

METHOD_FUNCS = {
    "agentic_search": validate_via_agentic_search,
    "fulltext": validate_via_fulltext,
    "fulltext_dg_prompt": validate_via_fulltext_dg_prompt,
    "excerpt_dg_prompt": validate_via_excerpt_dg_prompt,
    "fulltext_dg_prompt_claude": validate_via_fulltext_dg_prompt_claude,
    "excerpt_dg_prompt_claude": validate_via_excerpt_dg_prompt_claude,
}

# Methods whose prompt needs the prefetched full text (vs. agentic_search, which fetches
# on demand via paperclip grep/search tool calls instead).
FULLTEXT_METHODS = {"fulltext", "fulltext_dg_prompt", "fulltext_dg_prompt_claude"}
# excerpt_dg_prompt/_claude need the prefetched *excerpt* (see prefetch_excerpts) instead of
# full text - a different dict, keyed by (resource_name, url) rather than just url.
EXCERPT_METHODS = {"excerpt_dg_prompt", "excerpt_dg_prompt_claude"}
# Methods whose cache entries are further keyed by which JSON prompt template produced them -
# switching --dg-prompt-name must not return a stale prompt's cached verdict.
DG_PROMPT_METHODS = {"fulltext_dg_prompt", "excerpt_dg_prompt",
                      "fulltext_dg_prompt_claude", "excerpt_dg_prompt_claude"}


def validate_group(client: OpenAI, resource_name: str, rows: List[Dict[str, str]], sources: str,
                    methods: List[str], cache: Dict[str, dict], sample_size: str = "",
                    max_turns: int = 12, url_to_content: Dict[str, Any] = None,
                    dg_prompt_name: str = DEFAULT_DG_PROMPT_NAME,
                    excerpt_to_content: Dict[tuple, str] = None) -> List[Dict[str, dict]]:
    """Validate one resource's rows; return a list (one per row) of {method: {verification_status,
    claim_text, rationale}} dicts."""
    logger.info(f"[validate_group] called with resource_name={resource_name!r}, {len(rows)} row(s), "
                f"methods={methods}")
    doc_ids = [_resolve_doc_id(row) for row in rows]
    resolved = sum(1 for d in doc_ids if d)
    logger.info(f"[validate] '{resource_name}': {resolved}/{len(rows)} rows resolved to a paperclip doc_id")

    not_in_corpus = {"verification_status": "not_in_corpus", "claim_text": "n/a", "rationale": ""}
    if resolved == 0:
        result = [{m: not_in_corpus for m in methods}] * len(rows)
        logger.info(f"[validate_group] returning {len(result)} row(s), all not_in_corpus (no doc_id resolved)")
        return result

    # PMC link/DOI (needed by validate_via_fulltext to look up prefetched full text) is
    # per-row, not per-resource - unlike Abbreviation/Diseases/Modality, different rows in
    # the same resource group can point at different articles. Keep the first row seen for
    # each doc_id rather than defaulting to rows[0]'s.
    doc_id_to_row: Dict[str, Dict[str, str]] = {}
    for doc_id, row in zip(doc_ids, rows):
        if doc_id and doc_id not in doc_id_to_row:
            doc_id_to_row[doc_id] = row

    unique_doc_ids = list(doc_id_to_row.keys())
    per_doc_result: Dict[str, Dict[str, dict]] = {}
    for doc_id in unique_doc_ids:
        per_doc_result[doc_id] = {}
        for method in methods:
            cache_method = f"{method}:{dg_prompt_name}" if method in DG_PROMPT_METHODS else method
            key = cache_key(resource_name, doc_id, cache_method)
            if key in cache:
                per_doc_result[doc_id][method] = cache[key]
                continue
            fn = METHOD_FUNCS[method]
            kwargs = dict(sample_size=sample_size)
            if method == "agentic_search":
                kwargs.update(sources=sources, max_turns=max_turns)
            elif method in FULLTEXT_METHODS:
                kwargs.update(url_to_content=url_to_content)
            elif method in EXCERPT_METHODS:
                kwargs.update(excerpt_to_content=excerpt_to_content)
            if method in DG_PROMPT_METHODS:
                kwargs.update(prompt_name=dg_prompt_name)
            try:
                result = fn(client, resource_name, doc_id_to_row[doc_id], doc_id, **kwargs)
            except Exception as e:
                logger.error(f"[validate] '{resource_name}'/{doc_id} ({method}) failed: {e}", exc_info=True)
                result = {"verification_status": "error", "claim_text": "n/a", "rationale": str(e)}
            per_doc_result[doc_id][method] = result
            # "error" is a technical failure (vLLM connection drop, unparseable output), not a
            # real verdict - caching it would make a transient outage permanent across re-runs,
            # instead of the next run simply retrying it.
            if result["verification_status"] != "error":
                cache[key] = result
        logger.info(f"[validate] '{resource_name}'/{doc_id}: "
                    f"{ {m: r['verification_status'] for m, r in per_doc_result[doc_id].items()} }")

    # Per-resource tally as each group finishes, not just once at the very end of the whole
    # run - for a run spanning hours, this is what lets a systematic problem (e.g. every doc
    # landing on "error") surface after the first resource instead of after all of them.
    for method in methods:
        counts: Dict[str, int] = {}
        for doc_id in unique_doc_ids:
            status = per_doc_result[doc_id][method]["verification_status"]
            counts[status] = counts.get(status, 0) + 1
        logger.info(f"[validate] '{resource_name}' [{method}] this resource's outcomes — {counts}")

    result = [per_doc_result.get(doc_id, {m: not_in_corpus for m in methods}) if doc_id else
              {m: not_in_corpus for m in methods} for doc_id in doc_ids]
    logger.info(f"[validate_group] returning {len(result)} row(s)")
    return result


def _urls_needing_fulltext(df: pd.DataFrame, resource_col: str, methods: List[str],
                            cache: Dict[str, dict], dg_prompt_name: str) -> Dict[str, None]:
    """URLs actually worth prefetching full text for - excludes documents whose verification
    is already cached for every fulltext method requested, for every resource that references
    them (the same (resource_name, doc_id, method) triple validate_group() itself checks
    before deciding whether to call the LLM at all)."""
    logger.info(f"[_urls_needing_fulltext] called with {len(df)} row(s), resource_col={resource_col!r}, "
                f"methods={methods}, cache with {len(cache)} entries")
    fulltext_methods = [m for m in methods if m in FULLTEXT_METHODS]
    if not fulltext_methods:
        logger.info("[_urls_needing_fulltext] returning {} (no fulltext methods requested)")
        return {}
    needed: Dict[str, None] = {}
    for resource_name, group in df.groupby(resource_col):
        doc_id_to_row: Dict[str, Dict[str, str]] = {}
        for row in group.to_dict("records"):
            doc_id = _resolve_doc_id(row)
            if doc_id and doc_id not in doc_id_to_row:
                doc_id_to_row[doc_id] = row
        for doc_id, row in doc_id_to_row.items():
            for method in fulltext_methods:
                cache_method = f"{method}:{dg_prompt_name}" if method in DG_PROMPT_METHODS else method
                if cache_key(resource_name, doc_id, cache_method) not in cache:
                    url = _row_fetch_url(row)
                    if url:
                        needed[url] = None
                    break
    logger.info(f"[_urls_needing_fulltext] returning {len(needed)} url(s)")
    return needed


def validate_publications_df(
    df: pd.DataFrame,
    resource_col: str = "Resource Name",
    sources: str = "pmc,biorxiv,medrxiv,arxiv,trials",
    methods: Optional[List[str]] = None,
    cache_path: Path = DEFAULT_CACHE_PATH,
    no_cache: bool = False,
    max_turns: int = 12,
    dg_prompt_name: str = DEFAULT_DG_PROMPT_NAME,
    workers: Optional[int] = None,
    inventory_path: Optional[Path] = None,
    fetch_cache_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Validate a fetched-publications DataFrame in place, with caching.

    Extracted from main() so orchestrator.py can drive the same cache-aware,
    concurrent validate_group() flow synchronously, without going through the
    CLI or the offline batch+external-vLLM workflow (which has no caching).

    Args:
        df: One row per (resource, paper), e.g. combine_hits() output.
        resource_col: Column to group rows by.
        sources: Comma-separated paperclip -s/--source value(s).
        methods: Validation procedure(s) to run (default: ["fulltext"]).
        cache_path: Cache of already-verified (resource, doc_id, method) results.
        no_cache: Ignore and do not update the cache (always re-verify).
        max_turns: Tool-call budget for method agentic_search.
        dg_prompt_name: JSON template under prompts/ for method fulltext_dg_prompt.
        workers: Concurrent resource validations (default: min(16, cpu_count-2)).
        inventory_path: Resource inventory TSV, for Sample Size prompt context
            (default: latest tables/resources-inventory-* by mtime).
        fetch_cache_path: Shared full-text cache to read/write (e.g. orchestrator.py's
            tables/cache/fetched_fulltext_batch.parquet) - passed through to
            prefetch_fulltext() so this run's verification and the pub_metadata stages
            that follow it don't each independently re-fetch the same articles (default:
            prefetch_fulltext's own tables/cache/fetched_fulltext_batch.parquet).

    Returns:
        df with Verification Status/Claim Text/Rationale/... columns added
        (suffixed " (<method>)" when len(methods) > 1).

    Raises:
        ValueError: If resource_col is not in df.
    """
    logger.info(f"[validate_publications_df] called with {len(df)} row(s), resource_col={resource_col!r}, "
                f"methods={methods}, no_cache={no_cache}")
    methods = methods or ["fulltext"]
    if resource_col not in df.columns:
        raise ValueError(f"Column '{resource_col}' not found in input. Columns: {', '.join(df.columns)}")

    inventory_path = inventory_path or _find_latest_inventory()
    logger.info(f"Using inventory for prompt context: {inventory_path}")
    sample_sizes = load_sample_sizes(inventory_path)

    cache = {} if no_cache else load_cache(cache_path)

    url_to_content: Dict[str, Any] = {}
    if FULLTEXT_METHODS & set(methods):
        all_urls = {u for u in (_row_fetch_url(row) for row in df.to_dict("records")) if u}
        rows_by_url = _urls_needing_fulltext(df, resource_col, methods, cache, dg_prompt_name)
        logger.info(f"[fulltext] {len(rows_by_url)}/{len(all_urls)} URL(s) need fetching after cache filter "
                    f"({len(all_urls) - len(rows_by_url)} already fully verified in cache)")
        fetch_cache_str = str(fetch_cache_path) if fetch_cache_path else None
        url_to_content = prefetch_fulltext(rows_by_url, cache_path=fetch_cache_str)

    excerpt_to_content: Dict[tuple, str] = {}
    if EXCERPT_METHODS & set(methods):
        rows_by_resource = [
            (row.get(resource_col, ""), _row_fetch_url(row), _derive_id_patterns(row))
            for row in df.to_dict("records")
        ]
        rows_by_resource = [r for r in rows_by_resource if r[1]]
        excerpt_to_content = prefetch_excerpts(rows_by_resource)

    logger.info(f"vLLM endpoint: {VLLM_BASE_URL}, model: {VLLM_MODEL}")
    client = OpenAI(base_url=VLLM_BASE_URL, api_key="not-needed")
    max_workers = workers or min(16, max(1, (os.cpu_count() or 4) - 2))
    groups = list(df.groupby(resource_col))
    logger.info(f"Validating {len(groups)} resources with {max_workers} concurrent workers, method(s): {methods}")

    columns: Dict[str, List[str]] = {m: [""] * len(df) for m in methods}
    claim_columns: Dict[str, List[str]] = {m: [""] * len(df) for m in methods}
    rationale_columns: Dict[str, List[str]] = {m: [""] * len(df) for m in methods}
    reasoning_columns: Dict[str, List[str]] = {m: [""] * len(df) for m in methods}
    input_tok_columns: Dict[str, List[int]] = {m: [0] * len(df) for m in methods}
    output_tok_columns: Dict[str, List[int]] = {m: [0] * len(df) for m in methods}
    total_tok_columns: Dict[str, List[int]] = {m: [0] * len(df) for m in methods}
    completed = 0
    run_total_tokens = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(validate_group, client, resource_name, group.to_dict("records"), sources,
                             methods, cache, sample_sizes.get(resource_name, ""), max_turns,
                             url_to_content, dg_prompt_name, excerpt_to_content): (resource_name, group)
            for resource_name, group in groups
        }
        for future in as_completed(futures):
            resource_name, group = futures[future]
            completed += 1
            try:
                group_results = future.result()
            except Exception as e:
                logger.error(f"[validate] Resource '{resource_name}' failed: {e}", exc_info=True)
                continue
            for idx, row_result in zip(group.index, group_results):
                pos = df.index.get_loc(idx)
                for method in methods:
                    r = row_result.get(method, {})
                    columns[method][pos] = r.get("verification_status", "")
                    claim_columns[method][pos] = r.get("claim_text", "")
                    rationale_columns[method][pos] = r.get("rationale", "")
                    reasoning_columns[method][pos] = r.get("reasoning", "")
                    input_tok_columns[method][pos] = r.get("input_tokens", 0)
                    output_tok_columns[method][pos] = r.get("output_tokens", 0)
                    total_tok_columns[method][pos] = r.get("total_tokens", 0)
                    run_total_tokens += r.get("total_tokens", 0)
            logger.info(f"[validate] [{completed}/{len(groups)}] '{resource_name}' done "
                        f"({run_total_tokens:,} tokens spent so far)")
            if not no_cache and completed % 10 == 0:
                save_cache(cache_path, cache)

    if not no_cache:
        save_cache(cache_path, cache)

    for method in methods:
        suffix = f" ({method})" if len(methods) > 1 else ""
        df[f"Verification Status{suffix}"] = columns[method]
        df[f"Claim Text{suffix}"] = claim_columns[method]
        df[f"Rationale{suffix}"] = rationale_columns[method]
        df[f"Reasoning{suffix}"] = reasoning_columns[method]
        df[f"Input Tokens{suffix}"] = input_tok_columns[method]
        df[f"Output Tokens{suffix}"] = output_tok_columns[method]
        df[f"Total Tokens{suffix}"] = total_tok_columns[method]

    logger.info("=" * 60)
    for method in methods:
        counts = {status: columns[method].count(status) for status in
                  ("confirmed", "not_confirmed", "insufficient_evidence", "error", "not_in_corpus")}
        n_resolved = counts["confirmed"] + counts["not_confirmed"] + counts["insufficient_evidence"]
        precision = f"{counts['confirmed'] / n_resolved * 100:.1f}%" if n_resolved else "N/A"
        method_tokens = sum(total_tok_columns[method])
        logger.info(f"[{method}] {counts}  (confirmed / resolved: {precision}, tokens: {method_tokens:,})")
    logger.info(f"Total tokens spent across this run: {run_total_tokens:,}")
    logger.info("=" * 60)

    logger.info(f"[validate_publications_df] returning df with {len(df)} row(s)")
    return df


def main():
    logger.info("[main] called")
    parser = argparse.ArgumentParser(description='Validate a fetched-publications TSV against its source '
                                                   'resource/query context, using a self-hosted vLLM model')
    parser.add_argument('--input', '-i', required=True, help='Input TSV to validate')
    parser.add_argument('--output', '-o', default=None,
                       help='Output TSV (default: tables/hits/validate_fetched_publications_<YYYYMMDD_HHMMSS>.tsv)')
    parser.add_argument('--resource-col', default='Resource Name', help='Column to group rows by (default: "Resource Name")')
    parser.add_argument('--sources', default='pmc,biorxiv,medrxiv,arxiv,trials',
                       help='Comma-separated paperclip -s/--source value(s) (default: pmc,biorxiv,medrxiv,arxiv,trials)')
    parser.add_argument('--method', choices=['agentic_search', 'fulltext', 'fulltext_dg_prompt', 'excerpt_dg_prompt',
                                              'fulltext_dg_prompt_claude', 'excerpt_dg_prompt_claude', 'both'],
                       default='fulltext',
                       help='Validation procedure to run (default: fulltext). _dg_prompt: externalized JSON prompt '
                            'template. excerpt_*: fed only the resource-matching excerpt, not the whole document. '
                            '_claude variants run on Claude Sonnet 5 instead of vLLM.')
    parser.add_argument('--max-turns', type=int, default=12, help='Tool-call budget for --method agentic_search (default: 12)')
    parser.add_argument('--dg-prompt-name', default=DEFAULT_DG_PROMPT_NAME,
                       help=f'JSON template under prompts/ for --method fulltext_dg_prompt (default: {DEFAULT_DG_PROMPT_NAME})')
    parser.add_argument('--workers', type=int, default=None,
                       help='Concurrent resource validations (default: min(16, cpu_count-2))')
    parser.add_argument('--inventory', default=None,
                       help='Resource inventory TSV, for Sample Size prompt context (default: latest tables/resources-inventory-* by mtime)')
    parser.add_argument('--cache-file', default=str(DEFAULT_CACHE_PATH),
                       help=f'Cache of already-verified (resource, doc_id, method) results, shared across runs (default: {DEFAULT_CACHE_PATH})')
    parser.add_argument('--no-cache', action='store_true', help='Ignore and do not update the cache (always re-verify)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose (DEBUG) logging')
    parser.add_argument('--quiet', '-q', action='store_true', help='Show only warnings and errors')
    parser.add_argument('--log-file', default=None, help='Log file path')
    parser.add_argument('--clear-log', action='store_true', help='Clear log file before writing (default: append)')
    args = parser.parse_args()

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARNING
    log_file = args.log_file or get_default_log_file("fetched_publication_validation")
    setup_logger(__name__, log_file=log_file, level=level, clear=args.clear_log)
    logger.info(f"Logging initialized. Log file: {log_file}")

    if not os.getenv("PAPERCLIP_API_KEY"):
        logger.warning("PAPERCLIP_API_KEY not set; paperclip CLI calls will fail unless "
                        "already signed in via `paperclip login`")

    methods = ["agentic_search", "fulltext"] if args.method == "both" else [args.method]

    try:
        df = pd.read_csv(args.input, sep="\t", dtype=str).fillna("")
        logger.info(f"Loaded {len(df)} rows from {args.input}")
    except Exception as e:
        logger.error(f"Error reading input: {e}")
        sys.exit(1)

    try:
        df = validate_publications_df(
            df, resource_col=args.resource_col, sources=args.sources, methods=methods,
            cache_path=Path(args.cache_file), no_cache=args.no_cache, max_turns=args.max_turns,
            dg_prompt_name=args.dg_prompt_name, workers=args.workers,
            inventory_path=Path(args.inventory) if args.inventory else None,
        )
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        HITS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = HITS_DIR / f"validate_fetched_publications_{ts}.tsv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, sep="\t", index=False)
    logger.info(f"SUCCESS: Results saved to {output_path}")
    logger.info("[main] done")


if __name__ == "__main__":
    main()
