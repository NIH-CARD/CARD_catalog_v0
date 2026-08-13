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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from data_gatherer.prompts.prompt_manager import PromptManager

from logging_config import setup_logger, get_default_log_file
from scrape_publications import _paperclip_cli_raw

# Prompts live as plain-text files, not Python string literals - easier to iterate on,
# and since string.Template uses $placeholder (not str.format()'s {placeholder}), the
# literal JSON braces in few_shot_examples.md need no escaping at all, unlike before.
PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "validate_fetched_publications"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()

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
DEFAULT_DG_PROMPT_NAME = "fulltext_verification"
_dg_static_prompt_cache: Dict[str, list] = {}


def _load_dg_static_prompt(prompt_name: str) -> list:
    """Lazily load and cache a prompts/<name>.json template by name - e.g. "fulltext_verification"
    (default) or "sufficient_glue" (an alternate, more conversational framing of the same task).
    subdir="" is deliberate: prompt_dir is flat, so there's no directory layer underneath it -
    only load_prompt's subdir default ('dataset_prompts') would introduce one."""
    if prompt_name not in _dg_static_prompt_cache:
        _dg_static_prompt_cache[prompt_name] = _FULLTEXT_PROMPT_MANAGER.load_prompt(prompt_name, subdir="")
    return _dg_static_prompt_cache[prompt_name]


def load_cache(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            with open(path) as f:
                cache = json.load(f)
            logger.info(f"Loaded validation cache: {len(cache)} entries from {path}")
            return cache
        except Exception as e:
            logger.warning(f"Failed to load cache {path}: {e}")
    return {}


def save_cache(path: Path, cache: Dict[str, Any]) -> None:
    snapshot = dict(cache)
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    logger.info(f"Saved validation cache: {len(snapshot)} entries to {path}")


def cache_key(resource_name: str, doc_id: str, method: str) -> str:
    return f"{resource_name}|||{doc_id}|||{method}"


_DOC_ID_RE = re.compile(r'\b(PMC\d+|[a-z]{3}_[0-9a-f]{12})\b')


def _search_paperclip_by_exact(term: str, sources: str) -> Optional[str]:
    """Exact-phrase paperclip search for an identifier string (DOI, PMID, ...); returns
    the first doc_id found in the results, if any."""
    out = _paperclip_cli_raw("search", "-s", sources, "-e", term)
    for line in out.splitlines():
        m = _DOC_ID_RE.search(line)
        if m:
            return m.group(1)
    return None


def _resolve_doc_id(row: Dict[str, str], sources: str) -> Optional[str]:
    """Prefer an explicit Paperclip Doc ID column, then PMC ID (from PubMed Central
    Link), then fall back to a paperclip search by PMID, then by DOI. PMID is tried
    before DOI since a bare PMID is a more literal, less ambiguous search term."""
    explicit = (row.get("Paperclip Doc ID") or "").strip()
    if explicit:
        return explicit

    link = row.get("PubMed Central Link", "") or ""
    m = PMC_LINK_RE.search(link)
    if m:
        return m.group(1)

    pmid = (row.get("PMID") or "").strip()
    if pmid:
        found = _search_paperclip_by_exact(pmid, sources)
        if found:
            return found

    doi = (row.get("DOI") or "").strip()
    if doi:
        found = _search_paperclip_by_exact(doi, sources)
        if found:
            return found

    return None


def _find_latest_inventory() -> Optional[Path]:
    """Mirrors orchestrator.py's inventory-resolution pattern (inlined there too, not importable)."""
    matches = list((Path(__file__).parent.parent / "tables").glob("resources-inventory-*"))
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def load_sample_sizes(inventory_path: Optional[Path]) -> Dict[str, str]:
    """Resource Name -> Sample Size, for prompt context - not carried in query-method output TSVs."""
    if not inventory_path:
        return {}
    try:
        inv = pd.read_csv(inventory_path, sep="\t", dtype=str).fillna("")
        return dict(zip(inv["Resource Name"], inv["Sample Size"]))
    except Exception as e:
        logger.warning(f"Could not load sample sizes from {inventory_path}: {e}")
        return {}


def compose_resource_info(row: Dict[str, str], sample_size: str = "") -> str:
    """Compose a resource's non-empty attributes into a 'Label: value; Label: value' string."""
    parts = []
    for field in RESOURCE_ATTRIBUTE_FIELDS:
        value = (row.get(field) or "").strip()
        if value:
            parts.append(f"{field}: {value}")
    if sample_size:
        parts.append(f"Sample Size: {sample_size}")
    return "; ".join(parts)


def extract_query_context(row: Dict[str, str]) -> str:
    """The exact paperclip search/grep command that originally surfaced this doc_id during
    discovery (the "Fetched With" column) - the other half of the core question alongside the
    resource and the article itself. A specific accession-ID/exact-phrase grep hit is stronger
    prior evidence of a genuine connection than a broad keyword search hit; "(not resolved)" or
    blank means there's no original-query signal to weigh either way."""
    fetched_with = (row.get("Fetched With") or "").strip()
    if not fetched_with or "not resolved" in fetched_with:
        return "not available"
    return fetched_with.removeprefix("paperclip:").strip()


def _parse_final_message(response) -> Optional[dict]:
    """Pull the first message item's text out of a Responses API result and parse it as JSON."""
    for item in response.output:
        if getattr(item, "type", None) == "message":
            text = item.content[0].text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.warning(f"Model returned non-JSON message text: {text[:200]}")
                return None
    return None


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
    return (FULLTEXT_SYSTEM_PROMPT_HEAD.format(resource_info=resource_info, query_context=query_context)
            + VERIFICATION_RULES + "\n\n" + FEW_SHOT_EXAMPLES)


FULLTEXT_ARTICLE_DIR = Path(os.getenv("FULLTEXT_FETCH_DIR", "/tmp/validate_fetched_publications_raw/"))


def _row_fetch_url(row: Dict[str, str]) -> str:
    """PMC link if present, else a DOI URL - data_gatherer resolves either. Confirmed
    live: data_gatherer pulls genuine full text (~240KB of JATS/HTML) from both; paperclip's
    own `cat` truncates every corpus document to a ~1.5K char preview regardless of file or
    section, so it's never used for full text here, only for the short abstract fallback."""
    link = (row.get("PubMed Central Link") or "").strip()
    if link:
        return link
    doi = (row.get("DOI") or "").strip()
    return f"https://doi.org/{doi}" if doi else ""


def prefetch_fulltext(rows_by_url: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """One data_gatherer.fetch_data() call for every unique URL in the input, instead of
    re-instantiating DataGatherer (which reloads model weights) per row.

    Returns:
        url -> full text, or a list[str] of section-aware chunks if the document still
        exceeds the model's token limit after reference-stripping (missing/failed fetches
        are simply absent, not empty).
    """
    from data_gatherer.data_gatherer import DataGatherer

    urls = list(rows_by_url.keys())
    if not urls:
        return {}
    logger.info(f"[fulltext] fetching full text for {len(urls)} unique URL(s)")
    dg = DataGatherer(llm_name="vllm-openai/gpt-oss-20b", clear_previous_logs=False, prompt_dir="prompts")
    local_fetch_file = "tables/hits/fetched_fulltext.tsv"
    fetched = dg.fetch_data(urls, local_fetch_file=local_fetch_file, write_df_to_path=local_fetch_file)

    content_by_url: Dict[str, Any] = {}
    last_format = None
    for url in urls:
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
    n_chunked = sum(1 for c in content_by_url.values() if isinstance(c, list))
    if n_chunked:
        logger.info(f"[fulltext] {n_chunked}/{len(content_by_url)} document(s) exceeded the token limit "
                    "after reference-stripping and were split into chunks")
    logger.info(f"[fulltext] fetched {len(content_by_url)}/{len(urls)} URL(s) successfully")
    return content_by_url


def fetch_abstract_only(doc_id: str) -> str:
    """paperclip's own abstract section - a reasonable fallback since abstracts are short
    enough to rarely hit the ~1.5K char preview cap, used when there's no PMC link/DOI to
    fetch full text with at all (e.g. some OpenAlex `oa_` records)."""
    out = _paperclip_cli_raw("cat", f"/papers/{doc_id}/sections/ABSTRACT.md")
    return out if "ERR:" not in out and out.strip() else ""


def _best_chunk_verdict(results: List[dict]) -> dict:
    """Reduce one verdict per chunk of an oversized document to a single verdict - a genuine
    mention in any one chunk is enough to confirm the resource, regardless of chunk order, so
    "confirmed" beats "insufficient_evidence" beats "not_confirmed" beats "error". A no-op
    (returns results[0] unchanged) when there's only one chunk, which is the common case."""
    non_error = [r for r in results if r.get("verification_status") != "error"] or results
    for status in ("confirmed", "insufficient_evidence"):
        for r in non_error:
            if r.get("verification_status") == status:
                out = dict(r)
                if len(non_error) > 1:
                    out["rationale"] = f"[{len(non_error)} chunk(s) checked] " + out.get("rationale", "")
                return out
    out = dict(non_error[0])
    if len(non_error) > 1:
        out["rationale"] = f"[{len(non_error)} chunk(s) checked, none confirmed] " + out.get("rationale", "")
    return out


def validate_via_fulltext(client: OpenAI, resource_name: str, row: Dict[str, str],
                           doc_id: str, url_to_content: Dict[str, Any] = None,
                           sample_size: str = "") -> dict:
    """Read the candidate document once, whole, and predict a verdict directly - no tool use.
    Content may be a list[str] of chunks (see prefetch_fulltext) for a document that still
    exceeded the token limit after reference-stripping; each chunk gets its own call, reduced
    via _best_chunk_verdict."""
    url = _row_fetch_url(row)
    content = (url_to_content or {}).get(url, "")
    is_full_text = bool(content)
    if not content:
        content = fetch_abstract_only(doc_id)
    if not content:
        return {"verification_status": "error", "claim_text": "n/a",
                "rationale": f"Could not fetch any text for {doc_id} (url={url!r})"}
    if not is_full_text:
        logger.info(f"[fulltext] '{resource_name}'/{doc_id}: only an abstract is available, no full text")

    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    chunks = content if isinstance(content, list) else [content]
    instructions = _build_fulltext_system_prompt(resource_info, query_context)
    results = []
    for chunk in chunks:
        response = client.responses.create(
            model=VLLM_MODEL,
            instructions=instructions,
            input=[{"role": "user", "content": f"Publication text:\n\n{chunk}"}],
            temperature=0.0,
            text={"format": RESPONSE_FORMAT},
        )
        parsed = _parse_final_message(response)
        results.append(parsed or {"verification_status": "error", "claim_text": "n/a",
                                   "rationale": "model returned no parseable message"})

    parsed = _best_chunk_verdict(results)
    if not is_full_text:
        parsed["rationale"] = "[abstract-only, no full text available] " + parsed.get("rationale", "")
    return parsed


def validate_via_fulltext_dg_prompt(client: OpenAI, resource_name: str, row: Dict[str, str],
                                     doc_id: str, url_to_content: Dict[str, Any] = None,
                                     sample_size: str = "", prompt_name: str = DEFAULT_DG_PROMPT_NAME) -> dict:
    """Same procedure as validate_via_fulltext, but built on data_gatherer's own prompting
    machinery (PromptManager.render_prompt against an externalized JSON template) instead
    of a hardcoded Python string - a separate function rather than a drop-in swap so the two
    prompt-loading paths stay comparable against the same held-out cases. Chunk handling
    mirrors validate_via_fulltext (see _best_chunk_verdict). prompt_name selects which JSON
    template under prompts/validate_fetched_publications/publication_prompts/ to render -
    every template must accept resource_info/query_context/content/n_queries."""
    url = _row_fetch_url(row)
    content = (url_to_content or {}).get(url, "")
    is_full_text = bool(content)
    if not content:
        content = fetch_abstract_only(doc_id)
    if not content:
        return {"verification_status": "error", "claim_text": "n/a",
                "rationale": f"Could not fetch any text for {doc_id} (url={url!r})"}
    if not is_full_text:
        logger.info(f"[fulltext_dg_prompt] '{resource_name}'/{doc_id}: only an abstract is available, no full text")

    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    n_queries = row.get("Fetched With", "").count(";") + 1
    static_prompt = _load_dg_static_prompt(prompt_name)
    chunks = content if isinstance(content, list) else [content]
    results = []
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
        parsed = _parse_final_message(response)
        results.append(parsed or {"verification_status": "error", "claim_text": "n/a",
                                   "rationale": "model returned no parseable message"})

    parsed = _best_chunk_verdict(results)
    if not is_full_text:
        parsed["rationale"] = "[abstract-only, no full text available] " + parsed.get("rationale", "")
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
    return (AGENTIC_SYSTEM_PROMPT_HEAD.format(resource_info=resource_info, doc_id=doc_id, query_context=query_context)
            + VERIFICATION_RULES + "\n\n" + FEW_SHOT_EXAMPLES + "\n\n"
            + AGENTIC_SYSTEM_PROMPT_TAIL.format(max_turns=max_turns))

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
    return result


def validate_via_agentic_search(client: OpenAI, resource_name: str, row: Dict[str, str],
                                 doc_id: str, sources: str, sample_size: str = "",
                                 max_turns: int = 12) -> dict:
    """Let the model drive paperclip search/grep to corroborate the candidate doc_id against
    the resource's identifying details, then have it predict the verdict directly - paperclip's
    own repo/commit/--verify subsystem is never invoked."""
    resource_info = compose_resource_info(row, sample_size)
    query_context = extract_query_context(row)
    system_prompt = _build_agentic_system_prompt(resource_info, doc_id, query_context, max_turns)
    input_items: List[dict] = [{"role": "user", "content": "Begin the investigation."}]

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
    parsed = _parse_final_message(response)
    if parsed is not None:
        return parsed
    return {"verification_status": "error", "claim_text": "n/a",
            "rationale": "model returned no parseable final verdict"}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

METHOD_FUNCS = {
    "agentic_search": validate_via_agentic_search,
    "fulltext": validate_via_fulltext,
    "fulltext_dg_prompt": validate_via_fulltext_dg_prompt,
}

# Methods whose prompt needs the prefetched full text (vs. agentic_search, which fetches
# on demand via paperclip grep/search tool calls instead).
FULLTEXT_METHODS = {"fulltext", "fulltext_dg_prompt"}


def validate_group(client: OpenAI, resource_name: str, rows: List[Dict[str, str]], sources: str,
                    methods: List[str], cache: Dict[str, dict], sample_size: str = "",
                    max_turns: int = 12, url_to_content: Dict[str, Any] = None,
                    dg_prompt_name: str = DEFAULT_DG_PROMPT_NAME) -> List[Dict[str, dict]]:
    """Validate one resource's rows; return a list (one per row) of {method: {verification_status,
    claim_text, rationale}} dicts."""
    doc_ids = [_resolve_doc_id(row, sources) for row in rows]
    resolved = sum(1 for d in doc_ids if d)
    logger.info(f"[validate] '{resource_name}': {resolved}/{len(rows)} rows resolved to a paperclip doc_id")

    not_in_corpus = {"verification_status": "not_in_corpus", "claim_text": "n/a", "rationale": ""}
    if resolved == 0:
        return [{m: not_in_corpus for m in methods}] * len(rows)

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
            # fulltext_dg_prompt's cache entries are further keyed by which JSON template
            # produced them - switching --dg-prompt-name must not return a stale prompt's
            # cached verdict.
            cache_method = f"{method}:{dg_prompt_name}" if method == "fulltext_dg_prompt" else method
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
                if method == "fulltext_dg_prompt":
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

    return [per_doc_result.get(doc_id, {m: not_in_corpus for m in methods}) if doc_id else
            {m: not_in_corpus for m in methods} for doc_id in doc_ids]


def main():
    parser = argparse.ArgumentParser(description='Validate a fetched-publications TSV against its source '
                                                   'resource/query context, using a self-hosted vLLM model')
    parser.add_argument('--input', '-i', required=True, help='Input TSV to validate')
    parser.add_argument('--output', '-o', default=None,
                       help='Output TSV (default: tables/hits/validate_fetched_publications_<YYYYMMDD_HHMMSS>.tsv)')
    parser.add_argument('--resource-col', default='Resource Name', help='Column to group rows by (default: "Resource Name")')
    parser.add_argument('--sources', default='pmc,biorxiv,medrxiv,arxiv,trials',
                       help='Comma-separated paperclip -s/--source value(s) (default: pmc,biorxiv,medrxiv,arxiv,trials)')
    parser.add_argument('--method', choices=['agentic_search', 'fulltext', 'fulltext_dg_prompt', 'both'], default='fulltext',
                       help='Validation procedure to run (default: fulltext). fulltext_dg_prompt is the same '
                            'procedure but built on data_gatherer\'s own PromptManager.render_prompt against the '
                            'externalized JSON template rather than a hardcoded Python string.')
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
    logger.info(f"vLLM endpoint: {VLLM_BASE_URL}, model: {VLLM_MODEL}")
    client = OpenAI(base_url=VLLM_BASE_URL, api_key="not-needed")

    methods = ["agentic_search", "fulltext"] if args.method == "both" else [args.method]

    try:
        df = pd.read_csv(args.input, sep="\t", dtype=str).fillna("")
        logger.info(f"Loaded {len(df)} rows from {args.input}")
    except Exception as e:
        logger.error(f"Error reading input: {e}")
        sys.exit(1)

    if args.resource_col not in df.columns:
        logger.error(f"Column '{args.resource_col}' not found in {args.input}. Columns: {', '.join(df.columns)}")
        sys.exit(1)

    inventory_path = Path(args.inventory) if args.inventory else _find_latest_inventory()
    logger.info(f"Using inventory for prompt context: {inventory_path}")
    sample_sizes = load_sample_sizes(inventory_path)

    cache_path = Path(args.cache_file)
    cache = {} if args.no_cache else load_cache(cache_path)

    # One fetch pass for the whole input up front - validate_via_fulltext only ever
    # does a dict lookup, so re-instantiating DataGatherer (which reloads model weights)
    # per row/thread never happens.
    url_to_content: Dict[str, Any] = {}
    if FULLTEXT_METHODS & set(methods):
        rows_by_url = {u: None for u in (_row_fetch_url(row) for row in df.to_dict("records")) if u}
        url_to_content = prefetch_fulltext(rows_by_url)

    max_workers = args.workers or min(16, max(1, (os.cpu_count() or 4) - 2))
    groups = list(df.groupby(args.resource_col))
    logger.info(f"Validating {len(groups)} resources with {max_workers} concurrent workers, method(s): {methods}")

    columns: Dict[str, List[str]] = {m: [""] * len(df) for m in methods}
    claim_columns: Dict[str, List[str]] = {m: [""] * len(df) for m in methods}
    rationale_columns: Dict[str, List[str]] = {m: [""] * len(df) for m in methods}
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(validate_group, client, resource_name, group.to_dict("records"), args.sources,
                             methods, cache, sample_sizes.get(resource_name, ""), args.max_turns,
                             url_to_content, args.dg_prompt_name): (resource_name, group)
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
            logger.info(f"[validate] [{completed}/{len(groups)}] '{resource_name}' done")
            if not args.no_cache and completed % 10 == 0:
                save_cache(cache_path, cache)

    if not args.no_cache:
        save_cache(cache_path, cache)

    for method in methods:
        suffix = f" ({method})" if len(methods) > 1 else ""
        df[f"Verification Status{suffix}"] = columns[method]
        df[f"Claim Text{suffix}"] = claim_columns[method]
        df[f"Rationale{suffix}"] = rationale_columns[method]

    if args.output:
        output_path = Path(args.output)
    else:
        HITS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = HITS_DIR / f"validate_fetched_publications_{ts}.tsv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, sep="\t", index=False)

    logger.info("=" * 60)
    logger.info(f"SUCCESS: Results saved to {output_path}")
    for method in methods:
        counts = {status: columns[method].count(status) for status in
                  ("confirmed", "not_confirmed", "insufficient_evidence", "error", "not_in_corpus")}
        n_resolved = counts["confirmed"] + counts["not_confirmed"] + counts["insufficient_evidence"]
        precision = f"{counts['confirmed'] / n_resolved * 100:.1f}%" if n_resolved else "N/A"
        logger.info(f"[{method}] {counts}  (confirmed / resolved: {precision})")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
