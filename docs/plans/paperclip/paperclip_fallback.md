# Paperclip as a query method: full-text discovery for structurally zero-hit resources

## Context

`pubmed_search` (scrapers/scrape_publications.py, pipelines/pubmed_search.py) matches catalog resources to PubMed articles on title/abstract only. ~59% of the 237 AD/ADRD resources get zero hits, and most fail structurally: the resource's registered name/abbreviation never appears in any PubMed title/abstract, at any date — confirmed across four query-construction methods (v1-v4) this session, so no further query-string engineering closes the gap.

We validated a fix via a 12-resource manual pilot (random sample of the structural zero-hit set, run as 12 parallel Claude Code `Agent` tool calls): an LLM-driven investigation using the `paperclip` CLI (full-text search over 3.4M+ papers — PMC/bioRxiv/medRxiv/arXiv) finds papers that identify a resource only in their Methods/Data-Availability sections, not by name. 8/12 resources got machine-verified matches (via paperclip's own `repo add`/`repo commit` claim-verification workflow, which checks a claim against the paper's actual full text and returns `[OK]`/`[X]`). 2 more were strong candidates blocked only by a fixable claim-wording issue (claims phrased around our catalog's own invented name instead of a fact the paper states — sample size, cohort name, accession ID); a human confirmed both as true matches. One match was technically `[OK]` but thin-relevance (flagged, not auto-trusted). We also hit a real, reproducible bug: `paperclip repo checkout` is sticky/global on the account, so 12 concurrent agents cross-contaminated each other's active repo.

**We found `gxl-paperclip` on GitHub (github.com/GXL-ai/paperclip)** — the CLI is a thin `click` wrapper around an importable, typed Python client library (`gxl_paperclip.PaperclipClient`, REST-based, `pip install`-able). Every `_ReposAPI` method (`create_repo`, `add_papers`, `annotate_paper`, `commit`, `get_status`) takes an explicit `repo_id` — there is no shared "checked out repo" state anywhere in the client or backend. **The sticky-checkout bug is a CLI-layer-only artifact** — it doesn't exist when using the client library directly, since each resource investigation creates its own `repo_id`. Headless auth via `APIKeyAuth(api_key)` (`X-API-Key` header) is documented as working for MCP-routed commands, confirming non-interactive use is intended.

**Follow-up meeting with the Paperclip team (2026-08-05).** No citable paper yet; pointed to their engineering blog: [gxl.ai/blog/biomedical-literature-as-a-filesystem](https://gxl.ai/blog/biomedical-literature-as-a-filesystem) (Mar 13, 2026). Two takeaways: (1) their own benchmarks (bioRxiv Bench, 140 questions) show bash-style filesystem navigation (`grep`/`cat`/`scan` against individually-addressable sections) beats MCP-connector-style structured tools by a wide margin (100% vs 86% accuracy on Deep Paper Q&A, 80% vs 28% on Experiment Novelty Check, 2.4x lower latency, 3.6x lower cost) — reinforces building our tools as thin wrappers around the client library's primitives, not Anthropic's native MCP connector. (2) The per-resource turn/result budget can be raised — she confirmed `n` (result count) can go higher and that they offer "a very large set of entry points"; their own benchmark costs (~$0.53 avg even for cross-paper synthesis) support being less conservative than the pilot's `max_turns=20`.

**New framing (this revision): split into two chunks, chunk 1 is the priority.**

1. **The Paperclip primitive** — `paperclip` as a genuine 5th value for `query_method` inside `search_pubmed()` (scrapers/scrape_publications.py), a direct peer of `original`/`v2`/`v3`/`v4`. Runnable and testable standalone via `--query-method paperclip` on `scrape_publications.py`, exactly like every other method has been tested all session — no orchestrator involvement required for this chunk.
2. **Its integration into the full rebuild workflow** — wiring `"paperclip"` into `orchestrator.py`'s `--query-method` choices. Given chunk 1's design (below), this ends up being small: no new pipeline stage, no new schema, no new normalizer — `paperclip` rows flow through the exact same `tables/hits/pubmed_hits_*.tsv` → `normalize(..., "publications", ...)` → `tables/final/pubmed_central_*.tsv` path every other query method already uses.

**Open policy question this reframing creates — needs your call, not silently decided:** our stated bar was "100% precision, human-verified before anything enters the trusted corpus." If `paperclip` rows land directly in `pubmed_central_*.tsv` exactly like v1-v4 rows, there's no separate table left for a human review gate. The plan below defaults to **only emitting rows where `Verification Status == OK`** (paperclip's own `repo commit` verdict) as the automated stand-in — but the pilot showed that verdict isn't perfectly reliable in either direction (2/12 true positives blocked by a wording technicality that would now be silently dropped; 1/12 was a thin-relevance false-`OK` that would now silently ship). This is a real relaxation from "human-confirmed" to "paperclip's-own-verifier-confirmed" and should be an explicit decision, not a default I pick alone.

## Chunk 1 — The Paperclip primitive (priority)

### Design decisions

1. **Manual agentic loop**, not the beta `client.beta.messages.tool_runner`. Hard per-resource turn budget, raised from the pilot's 20 to **~35** per the Paperclip team's feedback that more exploration room is cheap. The Tool Runner doesn't expose message history, which we need for a graceful forced wrap-up when the budget is hit (`output_config: {format: {type: "json_schema", schema: {...}}}` on the final forced turn, to guarantee parseable output under budget pressure). This is also the first tool-use code in this repo; a manual loop is easier to debug and avoids a beta SDK dependency.

2. **Tools are thin wrappers around `PaperclipClient` methods** (`search`, `papers.grep`, `papers.cat`, `papers.scan`) — not shell commands, no subprocess, no command-string construction or whitelist-parsing needed. This shape is also what the Paperclip team's own benchmarks show outperforms MCP-style structured tools for this task (see Context) — not just an internal preference.

3. **Claim-wording rule, corrected from the pilot**: the verify-claim tool's prompt must instruct the model to phrase claims around **verifiable facts the paper actually states** (accession IDs, sample counts, cohort names) — never our catalog's own invented resource name. This was the single largest cause of true positives failing verification in the pilot.

4. **Concurrency is safe by construction.** Every `_ReposAPI` call takes an explicit `repo_id`; each resource investigation calls `client.repos.create_repo(name=f"paperclip-fallback-{resource_slug}")` up front to get its own fresh `repo_id`, so there's no shared mutable state to race on regardless of how many resources run concurrently later (relevant for chunk 2's batch orchestration, not chunk 1's per-resource function itself).

### Implementation

**`staging/schemas.py`** — extend `PublicationRow` (not a new schema) with: `DOI` (paperclip frequently surfaces bioRxiv/medRxiv preprints with no PMID — the existing schema has no DOI column at all today), `Verification Status` (`OK`/`X`/`tool-error`/blank for non-paperclip rows), `Claim Text`, `Rationale`. Blank/unused for `original`/`v2`/`v3`/`v4` rows, populated only when `Fetched With` indicates the paperclip method. Add all four to `COLUMNS` and the `to_str` validator list.

**`scrapers/scrape_publications.py`**:
- `_paperclip_client() -> PaperclipClient`: `PaperclipClient(auth=APIKeyAuth(os.environ["PAPERCLIP_API_KEY"]))`, `sys.exit(1)` with a clear message if unset (same pattern as the existing `anthropic_key` resolution).
- Tool wrapper functions: `paperclip_search(query, source, limit)`, `paperclip_grep(pattern, path)`, `paperclip_cat`/`paperclip_scan`, and `paperclip_verify_claim(repo_id, doc_id, claim, lines)` → `client.repos.add_papers(...)` + `client.repos.annotate_paper(...)`.
- `_search_paperclip(study_name, abbreviation, diseases, search_data_modalities, years) -> List[Dict]`: the per-resource manual agentic loop.
  1. `client.repos.create_repo(name=f"paperclip-{slug(study_name or abbreviation)}")` → `repo_id`.
  2. Loop: `client.messages.create(model=..., system=<brief + strategy + corrected claim-wording rule>, messages=conversation, tools=[tool_schemas])`, dispatch `tool_use` blocks to the wrapper functions, append `tool_result`s, repeat until `stop_reason == "end_turn"` or `max_turns` (35) reached (forced JSON final turn on budget exhaustion).
  3. `client.repos.commit(repo_id, "verify")` → `client.repos.get_status(repo_id)` for final `[OK]`/`[X]` per claim.
  4. Build result dicts matching the existing shape other methods return (`PMID`, `DOI`, `Title`, `Abstract`, `Authors`, `Affiliations`, `Keywords`, `Publication Date`, `PubMed Central Link`), plus `Verification Status`, `Claim Text`, `Rationale`, and `Fetched With` = the search/grep query that surfaced the candidate.
  5. **Per the open policy question above: filter to `Verification Status == "OK"` before returning**, unless/until you decide otherwise.
- Wire into `search_pubmed()`'s existing dispatch: `if query_method == "paperclip": return _search_paperclip(...)`, same pattern as the existing `if query_method == "v4": return _search_pubmed_fanout(...)`.
- Add `"paperclip"` to the `--query-method` argparse choices (currently `['original', 'v2', 'v3', 'v4']`) and help text.

### Verification plan (chunk 1)

1. Confirm `gxl-paperclip` installs and `APIKeyAuth` authenticates: `PaperclipClient(auth=APIKeyAuth(...)).health()` + one `client.search(...)` call.
2. Confirm `client.repos.create_repo()` → `add_papers()` → `annotate_paper()` → `commit()` → `get_status()` reproduces the `[OK]`/`[X]` verdict behavior observed in the pilot, against one already-known case (e.g. re-verify the A4 study's Papp et al. 2024 match).
3. Run `python scrape_publications.py --query-method paperclip` standalone against 1-2 resources already characterized by the pilot (`FreshMicro`, `A4`) and confirm comparable findings to the interactive pilot.
4. Run 3+ resource investigations concurrently, confirm each gets its own distinct `repo_id`, no cross-contamination.
5. Confirm the new `PublicationRow` columns (`DOI`, `Verification Status`, `Claim Text`, `Rationale`) round-trip correctly through `staging.normalizer.normalize(..., "publications", ...)` and stay blank (not erroring) for `original`/`v2`/`v3`/`v4` rows.

## Chunk 2 — Integration into the rebuild workflow (later)

Given chunk 1's design, this is now small:

1. Add `"paperclip"` to `orchestrator.py`'s `--query-method` choices (currently `["original", "v2", "v3", "v4"]`).
2. Decide whether `full_rebuild --query-method paperclip` should run paperclip **instead of** a PubMed method (replacing v4 entirely for that run) or **in addition to** one (e.g. run v4 first, then paperclip only on v4's zero-hit resources — closer to the original "fallback" framing this plan started from). The "instead of" reading matches "just another query_method" most literally; the "in addition to, targeted at zero-hit resources" reading is cheaper (doesn't re-run paperclip on resources PubMed already covers) but means `pubmed_search`'s single `query_method` dispatch no longer cleanly describes the run — worth deciding once chunk 1 has real yield/cost numbers to look at, not before.
3. `run_incremental_update` (7-day window) should probably still never use `paperclip` — full-text search has no date restriction, so a weekly re-run finds nothing new. Keep it `full_rebuild`-only.
4. No caching/dedup logic is strictly required to reuse `page_navigation`'s `cache_utils.latest_final()` pattern here, since `paperclip` rows now live in the same `pubmed_central_*.tsv` as everything else — a resource that already has a paperclip-sourced row would naturally need its own skip-logic if re-running is wasteful, but this can piggyback on whatever caching `pubmed_search` already does (currently none) rather than needing new machinery.
