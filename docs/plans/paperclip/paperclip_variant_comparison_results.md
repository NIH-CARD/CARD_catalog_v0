# Paperclip variant comparison — results

Companion to `docs/plans/paperclip_fallback.md`. Ran via the `Workflow` tool
(`wf_0857375b-f9e`), 48 runs = 12 pilot resources × 4 strategies, each a
schema-constrained Claude Code agent driving the real `paperclip` CLI against
its own repo (`cmp-<variant>-<resource-slug>`, env-scoped via `PAPERCLIP_REPO`
to avoid the sticky-checkout contamination bug — confirmed clean, 0 collisions
across 48 concurrent repos). Script: `paperclip_variant_comparison.workflow.js`
(job tmp dir). Zero agent errors, zero empty results, 3.2M subagent tokens, 773
tool calls, ~53 min wall clock.

**Data-quality note:** the `variant` and `resource_slug` fields in each run's
self-reported output are unreliable — several agents paraphrased them (e.g.
"catalog-name-phrase" instead of "control", "AUSBB" vs "ausbb") instead of
echoing the literal key. All numbers below are re-derived from `repo_name`,
which was a fixed, dictated string per run and verified unique across all 48
(no duplicates, no missing resource×variant combos) — treat `repo_name` as
ground truth if re-analyzing the raw journal.

## ⚠ Correction after live verification audit

After the run, every candidate's self-reported `verification_status` was cross-checked
against the live, authoritative `paperclip repo claims`/`repo export csv` for its actual
repo (124 real papers pulled with real titles/journals/years — see appendix below). Of
126 self-reported candidate rows, **121 check out clean**. **5 do not**: all 5 candidates
in `cmp-control-eeg-ad-ftd` (the `control` run for the EEG/ds004504 resource) were
self-reported as 4×OK + 1×X, but `repo claims` returns an empty array and `repo status`
confirms nothing was ever actually verified for that repo, despite a commit existing.
The likely mechanism: the agent read the candidate papers' full text directly (cat/grep)
and formed its own OK/X judgment, then reported that as final without it ever passing
through paperclip's own commit-triggered verification step — unlike every other run,
where self-report and live verification agree.

**Effect on the numbers above:** `eeg-ad-ftd` was one of `control`'s 7 recall wins.
Discounting the unverified run, **`control`'s true verified recall is 6/12, not 7/12** —
tied with `budget`, not ahead of it. The resource × variant table and per-variant summary
below still show the original self-reported numbers (for comparability with the raw
journal), but treat `control`'s recall figure specifically as 6/12 when reasoning about
which variant is "as good as control but cheaper."

No other resource or variant showed this issue — it's isolated to one run out of 48.

## Per-variant summary

| Variant | Recall (≥1 OK / 12) | Total OK claims | Avg tool calls | Resources hitting turn budget |
|---|---|---|---|---|
| control | 7/12 | 19 | 9.8 | 0 |
| decomp | 8/12 | 23 | 14.9 | 3 |
| budget | 6/12 | 22 | 14.2 | 0 |
| decomp_budget | 9/12 | 25 | 17.8 | 0 |

## Resource × variant (OK / X counts)

| Resource | control | decomp | budget | decomp_budget |
|---|---|---|---|---|
| a4-study | 4/0 | 5/1 | 7/0 | 4/0 |
| 1066-life2years | 0/3 | 2/1 | 4/0 | 4/0 |
| mc-caa | 0/2 | 0/0 | 0/2 | 1/0 |
| eeg-ad-ftd (ds004504) | 4/1 | 8/0 | 8/2 | 10/3 |
| freshmicro | 7/0 | 3/0 | 0/3 | 1/0 |
| r47h-trem2 | 1/0 | 0/0 (1 stuck not_committed) | 1/0 | 0/1 |
| borcs6 | 1/0 | 1/0 | 1/0 | 1/0 |
| campaign | 1/0 | 1/0 | 1/1 | 1/0 |
| mtdna-ad | 1/2 | 1/0 | 0/3 | 1/0 |
| admc-adni-metabolon | 0/3 | 2/0 | 0/5 | 2/0 |
| ausbb | 0/0 | 0/0 | 0/0 | 0/0 |
| virusresilience-lcl | 0/0 | 0/0 | 0/0 | 0/0 |

## Key findings (from the synthesis agent, verified against the matrix above)

1. **Decomposition finds real candidates control misses, but at a precision cost.** Decomp beat control on `1066-life2years` (2 OK vs 0) and `admc-adni-metabolon` (2 OK vs 0) — but those OKs are self-flagged as sibling/consortium-adjacent matches (companion lipidomics/p180 datasets for admc; the 10/66 decomp OKs never actually contain the term "Life2Years"), not confirmed identity matches.
2. **A wider budget only helps when spent on the right move — a literal full-corpus grep for the exact string/accession — not more semantic-search paraphrases.** Clearest case: `freshmicro`. Control found 7 OK candidates by grepping the literal terms "FreshMicro" and "syn25671134" directly. `budget` had ~9 extra calls of headroom but never tried that grep and returned 0 OK — more tool-call allowance without a better search strategy can underperform a cheaper, sharper one.
3. **Decomposition without extra budget runs out of room.** `decomp` hit the turn/tool-call cap on 3/12 resources (r47h-trem2, borcs6, admc-adni-metabolon). For r47h-trem2 this left a claim stuck at `not_committed` (a tool-attach bug with no turns left to retry) — turning what should have been an OK into a zero.
4. **`decomp_budget` is the strongest performer** (9/12 recall, 25 total OK claims, ds004504 alone got 10/13 candidates verified OK — the best single result in the dataset) and never hit the turn budget — but at ~1.8x the average cost of control, with the same adjacent-match caveat as decomp (mc-caa's hit is an AD Knowledge Portal *tutorial* naming the study, not a paper analyzing its data; admc-adni-metabolon's hits are sibling datasets).
5. **Genuine zero-literature resources (`virusresilience_lcl`, `ausbb`) were correctly identified as zero-candidate by all four variants**, at low cost (6-19 calls) — no variant hallucinated a false positive here, a good precision signal across the board. These true negatives don't need extra budget.

## Recommendation (synthesis agent's, worth a sanity check before adopting)

Adopt a `decomp_budget`-style strategy as the base, but harden it with two cheap fixes rather than shipping `decomp` or `budget` alone:

- **(a) Make a full-corpus literal/exact-string grep (catalog name, abbreviation, any accession/ID) a mandatory step in every run, independent of budget tier.** This was the single highest-value, lowest-cost move in the whole dataset — it's what actually surfaced the real hits for Life2Years, FreshMicro/syn25671134, and borcs6_kd_transcriptomics_on_ineurons. Its *absence*, not budget size, is why plain `budget` underperformed `control` on freshmicro.
- **(b) Use an adaptive rather than flat budget:** let true zero-hit resources terminate early and cheaply (as control/budget did on virusresilience_lcl/ausbb, ~6-9 calls) rather than spending the full decomp_budget allowance everywhere; reserve the larger budget for resources where the literal grep or decomposition actually turns up a lead worth chasing.
- **Add a post-verification confidence tag** distinguishing "exact resource match" from "same-cohort/consortium/sibling-dataset match" — decomp and decomp_budget both produce OKs of the weaker kind (admc-adni-metabolon, mc-caa, 10-66-life2years) that a downstream consumer (chunk 1's `pubmed_central_*.tsv` output) should not treat identically to a literal accession/name match.

## Where the raw evidence lives

- `journal.jsonl` in the workflow's transcript dir has every run's full structured return (queries tried, every candidate + verdict + rationale).
- All 48 comparison repos (`cmp-control-a4-study`, `cmp-decomp-freshmicro`, etc.) are live on the paperclip account — inspect any of them independently with `paperclip --repo <name> repo status` / `repo claims` / `repo log`, same as the original `pilot-*` repos.

## Open items this raises for chunk 1 of `paperclip_fallback.md`

- The `RESULT_SCHEMA`'s `variant`/`resource_slug` fields should have been enums, not free strings — worth fixing before running a comparison like this again; `repo_name` alone saved this run.
- Chunk 1's design currently defaults to filtering on `Verification Status == OK` — this run shows OK is not uniformly "exact resource match," so the confidence-tag recommendation above should feed into that design decision, not just this comparison.


## Appendix: full candidate table with per-paper query attribution

Every candidate paper (126 self-reported, 124 actually added to a repo), with real
title/journal/year pulled live from `paperclip repo export csv`, the `verified` flag
from `repo claims` (ground truth — 121/126 clean against self-report, 5 mismatched in
`eeg-ad-ftd/control` per the correction above), and — reconstructed retroactively from
each agent's raw tool-call transcript, not from `repo history` (which only logs
`search_papers`, missing `grep`/`add`/`commit` entirely) — the exact `search`/`grep`
command whose output first surfaced that specific paper.

**Attribution coverage: 110/126 (87%) resolved.** Method: parsed every Bash command +
its output from each agent's transcript, extracted doc_ids from *structural* result-line
patterns only (e.g. `PMC8374591 · PMC · 2021-12-01` for search, `med_1c4d8c98.../ (1
matches)` for grep) — not a blind substring scan, which produces false attributions when
a single-paper grep's excerpt happens to mention other papers' IDs in a citation list
(caught and fixed this exact failure mode on `freshmicro/control` before trusting the
output). Then matched each `repo add <doc_id>` call to the nearest preceding
search/grep command whose output contained that doc_id. Validated against a manual
spot-check of `freshmicro/control` — matched exactly, and actually caught one match the
manual read missed (truncated output). The 16 unresolved are mostly the already-flagged
`eeg-ad-ftd/control` run (5 — expected, that run's self-verification was never backed by
real paperclip verification either) plus a handful where the query's output used a
listing format the two structural patterns didn't cover (`(not resolved)` in the table).
`Verified: —` = added but never got a claim recorded (the `r47h-trem2/decomp` tool-attach
bug, or `eeg-ad-ftd/control`'s unverified rows).

| Resource | Variant | Title | Journal | Year | Verified | Found via |
|---|---|---|---|---|---|---|
| 1066-life2years | control | Cohort Profile: The 10/66 study | International Journal of Epidemiology | 2017 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Cuba 10/66 population-based cohort dementia incidence" 2>&1` |
| 1066-life2years | control | The protocols for the 10/66 dementia research group population-based r | BMC Public Health | 2007 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Cuba 10/66 population-based cohort dementia incidence" 2>&1` |
| 1066-life2years | control | Dementia incidence and mortality in middle-income countries, and assoc | Lancet | 2012 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Cuba 10/66 population-based cohort dementia incidence" 2>&1` |
| 1066-life2years | decomp | The protocols for the 10/66 dementia research group population-based r | BMC Public Health | 2007 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "10/66 dementia baseline cohort sample size 6917 participants" 2>&1` |
| 1066-life2years | decomp | Dementia incidence and mortality in middle-income countries, and assoc | Lancet | 2012 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "10/66 dementia baseline cohort sample size 6917 participants" 2>&1` |
| 1066-life2years | decomp | Cohort Profile: The 10/66 study | International Journal of Epidemiology | 2017 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "10/66 dementia baseline cohort sample size 6917 participants" 2>&1` |
| 1066-life2years | budget | “I don’t want to make trouble”: Emotional Distress, Disconnection, and | The Journals of Gerontology Series B: Psychological Sciences and Social Sciences | 2025 | true | `paperclip grep "Life2Years" /papers/ --exhaustive 2>&1 / head -50` |
| 1066-life2years | budget | AD Workbench: Transforming Alzheimer's research with secure, global, a | Alzheimer's & Dementia | 2025 | true | `paperclip grep "Life2Years" /papers/ --exhaustive 2>&1 / head -50` |
| 1066-life2years | budget | Dependence- and Disability-Free Life Expectancy Across Eight Low- and  | Journal of Aging and Health | 2019 | true | `paperclip grep "Life2Years" /papers/ --exhaustive 2>&1 / head -50` |
| 1066-life2years | budget | A review of the 10/66 dementia research group | Social Psychiatry and Psychiatric Epidemiology | 2018 | true | `paperclip grep "Life2Years" /papers/ --exhaustive 2>&1 / head -50` |
| 1066-life2years | decomp_budget | Cohort Profile: The 10/66 study | International Journal of Epidemiology | 2017 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "10/66 Dementia Research Group 6917 participants cohort" -n 10` |
| 1066-life2years | decomp_budget | Dementia incidence and mortality in middle-income countries, and assoc | Lancet | 2012 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "10/66 Dementia Research Group 6917 participants cohort" -n 10` |
| 1066-life2years | decomp_budget | The protocols for the 10/66 dementia research group population-based r | BMC Public Health | 2007 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "10/66 Dementia Research Group 6917 participants cohort" -n 10` |
| 1066-life2years | decomp_budget | Prevalence, Distribution, and Impact of Mild Cognitive Impairment in L | PLoS Medicine | 2012 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "10/66 Dementia Research Group 6917 participants cohort" -n 10` |
| a4-study | control | Change in Digital Cognitive Test Performance between Solanezumab and P | The Journal of Prevention of Alzheimer's Disease | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study amyloid-positive cognitively normal solanezumab" -n 10` |
| a4-study | control | Longitudinal Regional Flortaucipir Profiles in Preclinical Alzheimer’s | Alzheimer's & Dementia | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study amyloid-positive cognitively normal solanezumab" -n 10` |
| a4-study | control | The A4 study:  β ‐amyloid and cognition in 4432 cognitively unimpaired | Annals of Clinical and Translational Neurology | 2020 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study amyloid-positive cognitively normal solanezumab" -n 10` |
| a4-study | control | Disclosure of elevated amyloid status is not associated with long‐term | Alzheimer's & Dementia | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Anti-Amyloid Treatment in Asymptomatic Alzheimer's Study" -e -n 10` |
| a4-study | control | Evaluation of Amyloid Removal as a Surrogate for Cognitive Decline: Pi | preprint | 2025 | — | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study amyloid-positive cognitively normal solanezumab" -n 10` |
| a4-study | decomp | Longitudinal Regional Flortaucipir Profiles in Preclinical Alzheimer’s | Alzheimer's & Dementia | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "1169 participants amyloid PET cognitively unimpaired trial" 2>&1 / tail -30` |
| a4-study | decomp | Safety Profile of a Cognitively Unimpaired Older Population with Eleva | The Journal of Prevention of Alzheimer's Disease | 2024 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study solanezumab amyloid-positive cognitively normal" 2>&1 / tail -40` |
| a4-study | decomp | Incremental Value of Plasma Biomarkers in Predicting Clinical Decline  | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 trial" -e 2>&1 / head -60` |
| a4-study | decomp | Pre-Randomization Predictors of Study Discontinuation in a Preclinical | The Journal of Prevention of Alzheimer's Disease | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 trial" -e 2>&1 / head -60` |
| a4-study | decomp | Tau-Connectome Subtypes and Solanezumab Response in Preclinical Alzhei | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 trial" -e 2>&1 / head -60` |
| a4-study | decomp | Longitudinal Phospho-tau217 Predicts Amyloid Positron Emission Tomogra | The Journal of Prevention of Alzheimer's Disease | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 trial" -e 2>&1 / head -60` |
| a4-study | budget | Change in Digital Cognitive Test Performance between Solanezumab and P | The Journal of Prevention of Alzheimer's Disease | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study solanezumab preclinical Alzheimer" 2>&1` |
| a4-study | budget | Evaluation of Amyloid Removal as a Surrogate for Cognitive Decline: Pi | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study solanezumab preclinical Alzheimer" 2>&1` |
| a4-study | budget | Incremental Value of Plasma Biomarkers in Predicting Clinical Decline  | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study solanezumab preclinical Alzheimer" 2>&1` |
| a4-study | budget | Longitudinal Trajectories of the Cognitive Function Index in the A4 St | The Journal of Prevention of Alzheimer's Disease | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study solanezumab preclinical Alzheimer" 2>&1` |
| a4-study | budget | Longitudinal Regional Flortaucipir Profiles in Preclinical Alzheimer’s | Alzheimer's & Dementia | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "A4 study solanezumab preclinical Alzheimer" 2>&1` |
| a4-study | budget | Safety Profile of a Cognitively Unimpaired Older Population with Eleva | The Journal of Prevention of Alzheimer's Disease | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Anti-Amyloid Treatment in Asymptomatic Alzheimer's Study" -e 2>&1` |
| a4-study | budget | Disclosure of elevated amyloid status is not associated with long‐term | Alzheimer's & Dementia | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Anti-Amyloid Treatment in Asymptomatic Alzheimer's Study" -e 2>&1` |
| a4-study | decomp_budget | Heterogeneity in Preclinical Alzheimer’s Disease Trial Cohort Identifi | preprint | 2023 | true | `(not resolved)` |
| a4-study | decomp_budget | Multi-organ AI Endophenotypes Chart the Heterogeneity of Pan-disease i | preprint | 2025 | true | `(not resolved)` |
| a4-study | decomp_budget | Change in Digital Cognitive Test Performance between Solanezumab and P | The Journal of Prevention of Alzheimer's Disease | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "solanezumab preclinical Alzheimer's disease amyloid PET asymptomatic trial" -n 10 2>&1` |
| a4-study | decomp_budget | Longitudinal Regional Flortaucipir Profiles in Preclinical Alzheimer’s | Alzheimer's & Dementia | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "solanezumab preclinical Alzheimer's disease amyloid PET asymptomatic trial" -n 10 2>&1` |
| a4-study | decomp_budget | (not in export - never actually added) | preprint |  | — | `(not resolved)` |
| a4-study | decomp_budget | (not in export - never actually added) | preprint |  | — | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "solanezumab preclinical Alzheimer's disease amyloid PET asymptomatic trial" -n 10 2>&1` |
| admc-adni-metabolon | control | Metabolic Alteration in Oxylipins and Endocannabinoids Point to an Imp | preprint | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "HD4 platform Metabolon Alzheimer's Disease Neuroimaging Initiative" 2>&1 / head -40` |
| admc-adni-metabolon | control | Best practices and lessons learned from reuse of 4 patient-derived met | Pacific Symposium on Biocomputing. Pacific Symposium on Biocomputing | 2017 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv -e "This paper describes or uses data from the 'The Alzheimer's Disease Metabolomics Consortium Longitudinal Alzheimer's Disease Neuroimaging Initiative Metabolon Study' study" 2>&1 / head -40` |
| admc-adni-metabolon | control | Targeted metabolomics and medication classification data from particip | Scientific Data | 2017 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "global metabolomics profiling ADNI-1 serum Metabolon Alzheimer's Disease Metabolomics Consortium" 2>&1 / head -50` |
| admc-adni-metabolon | decomp | Generation and quality control of lipidomics data for the alzheimer’s  | Scientific Data | 2018 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "acylcarnitine sphingolipid untargeted metabolomics ADNI plasma Alzheimer's disease progression risk" -n 10` |
| admc-adni-metabolon | decomp | Targeted metabolomics and medication classification data from particip | Scientific Data | 2017 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Kaddurah-Daouk Alzheimer's Disease Metabolomics Consortium global untargeted plasma metabolomics ADNI biochemical" -n 10` |
| admc-adni-metabolon | budget | Sex and  APOE  ε4 genotype modify the Alzheimer’s disease serum metabo | Nature Communications | 2020 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "The Alzheimer's Disease Metabolomics Consortium Longitudinal Alzheimer's Disease Neuroimaging Initiative Metabolon Study" -e` |
| admc-adni-metabolon | budget | Serum Metabolites Associated with Brain Amyloid Beta Deposition, Cogni | preprint | 2020 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "The Alzheimer's Disease Metabolomics Consortium Longitudinal Alzheimer's Disease Neuroimaging Initiative Metabolon Study" -e` |
| admc-adni-metabolon | budget | Central and Peripheral Biochemical Changes in Alzheimer's Disease: Ins | Alzheimer's & Dementia | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "The Alzheimer's Disease Metabolomics Consortium Longitudinal Alzheimer's Disease Neuroimaging Initiative Metabolon Study" -e` |
| admc-adni-metabolon | budget | A seven-year longitudinal study of the Alzheimer’s disease blood metab | preprint | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Alzheimer's Disease Metabolomics Consortium ADNI plasma untargeted 800 participants"` |
| admc-adni-metabolon | budget | Targeted metabolomics and medication classification data from particip | Scientific Data | 2017 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Alzheimer's Disease Metabolomics Consortium ADNI plasma untargeted 800 participants"` |
| admc-adni-metabolon | decomp_budget | Bile acids targeted metabolomics and medication classification data in | Scientific Data | 2019 | true | `(not resolved)` |
| admc-adni-metabolon | decomp_budget | A seven-year longitudinal study of the Alzheimer’s disease blood metab | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Alzheimer's Disease Metabolomics Consortium Kaddurah-Daouk ADNI plasma" 2>&1 / head -60` |
| borcs6 | control | Maintenance of neuronal TDP-43 expression requires axonal lysosome tra | eLife | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "BORCS6 knockdown TDP-43 axonal lysosome transport induced neurons RNA-seq" 2>&1 / head -30` |
| borcs6 | decomp | Maintenance of neuronal TDP-43 expression requires axonal lysosome tra | preprint | 2025 | true | `paperclip grep "BORCS6" /papers/ 2>&1 / head -80` |
| borcs6 | budget | Maintenance of neuronal TDP-43 expression requires axonal lysosome tra | eLife | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv -e "BORCS6" 2>&1` |
| borcs6 | decomp_budget | Maintenance of neuronal TDP-43 expression requires axonal lysosome tra | eLife | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "BORCS6 knockdown iPSC neuron RNA-seq accession" 2>&1` |
| campaign | control | Motor complications in Parkinson's disease: 13‐year follow‐up of the C | Movement Disorders | 2019 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "CamPaIGN cohort incident Parkinson's disease Cambridge" 2>&1 / head -40` |
| campaign | decomp | Motor complications in Parkinson's disease: 13‐year follow‐up of the C | Movement Disorders | 2019 | true | `(not resolved)` |
| campaign | budget | The Genetic Basis of Cognitive Impairment and Dementia in Parkinson’s  | Frontiers in Psychiatry | 2016 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Williams-Gray Parkinson's disease incident cohort genetic COMT cognitive decline Cambridge" 2>&1 / head -60` |
| campaign | budget | Cognitive decline and quality of life in incident Parkinson's disease: | Parkinsonism & Related Disorders | 2016 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "cognitive ability incident cohort Parkinson's disease patients UK CamPaIGN study" 2>&1 / head -60` |
| campaign | decomp_budget | Motor complications in Parkinson's disease: 13‐year follow‐up of the C | Movement Disorders | 2019 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "incident Parkinson's disease general practitioners Cambridgeshire community-based cohort Foltynie"` |
| eeg-ad-ftd | control | Multi-Threshold Recurrence Rate Plot: A Novel Methodology for EEG Anal | Brain Sciences | 2024 | — | `(not resolved)` |
| eeg-ad-ftd | control | EEG Microstate Differences Between Alzheimer’s Disease, Frontotemporal | Medicina | 2025 | — | `(not resolved)` |
| eeg-ad-ftd | control | An explainable and efficient deep learning framework for EEG-based dia | Frontiers in Medicine | 2025 | — | `(not resolved)` |
| eeg-ad-ftd | control | Resting-State EEG Reveals Regional Brain Activity Correlates in Alzhei | preprint | 2024 | — | `(not resolved)` |
| eeg-ad-ftd | control | Alzheimer’s Disease and Frontotemporal Dementia: A Robust Classificati | Diagnostics | 2021 | — | `(not resolved)` |
| eeg-ad-ftd | decomp | Classifying Alzheimer’s Disease and Dementia Patients Using Non-invasi | preprint | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease patients 23 frontotemporal dementia 29 healthy controls EEG" 2>&1` |
| eeg-ad-ftd | decomp | EEG Microstate Differences Between Alzheimer’s Disease, Frontotemporal | Medicina | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease patients 23 frontotemporal dementia 29 healthy controls EEG" 2>&1` |
| eeg-ad-ftd | decomp | Sink-index: a network-based EEG marker for frontotemporal dementia and | Brain Communications | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease patients 23 frontotemporal dementia 29 healthy controls EEG" 2>&1` |
| eeg-ad-ftd | decomp | Exploring Brain Network Organization in Alzheimer Disease and   Fronto | preprint | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "ds004504" 2>&1` |
| eeg-ad-ftd | decomp | Distinct neurodynamics of functional brain networks in Alzheimer's dis | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "ds004504" 2>&1` |
| eeg-ad-ftd | decomp | EEG features associated with Alzheimer’s disease and Frontotemporal de | Journal of Clinical Monitoring and Computing | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease patients 23 frontotemporal dementia 29 healthy controls EEG" 2>&1` |
| eeg-ad-ftd | decomp | Resting-State EEG Reveals Regional Brain Activity Correlates in Alzhei | preprint | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease patients 23 frontotemporal dementia 29 healthy controls EEG" 2>&1` |
| eeg-ad-ftd | decomp | An explainable and efficient deep learning framework for EEG-based dia | Frontiers in Medicine | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease patients 23 frontotemporal dementia 29 healthy controls EEG" 2>&1` |
| eeg-ad-ftd | budget | Sink-index: a network-based EEG marker for frontotemporal dementia and | Brain Communications | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "OpenNeuro ds004504 EEG Alzheimer's Frontotemporal dementia healthy dataset"` |
| eeg-ad-ftd | budget | Alzheimer’s Disease and Frontotemporal Dementia: A Robust Classificati | Diagnostics | 2021 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "EEG recordings from: Alzheimer's Disease, Frontotemporal dementia and Healthy subjects" -e` |
| eeg-ad-ftd | budget | An explainable and efficient deep learning framework for EEG-based dia | Frontiers in Medicine | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "OpenNeuro ds004504 EEG Alzheimer's Frontotemporal dementia healthy dataset"` |
| eeg-ad-ftd | budget | EEG-SSM: Leveraging State-Space Model for Dementia Detection | preprint | 2024 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "OpenNeuro ds004504 EEG Alzheimer's Frontotemporal dementia healthy dataset"` |
| eeg-ad-ftd | budget | Exploring Brain Network Organization in Alzheimer Disease and   Fronto | preprint | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "OpenNeuro ds004504 EEG Alzheimer's Frontotemporal dementia healthy dataset"` |
| eeg-ad-ftd | budget | Distinct neurodynamics of functional brain networks in Alzheimer's dis | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "OpenNeuro ds004504 EEG Alzheimer's Frontotemporal dementia healthy dataset"` |
| eeg-ad-ftd | budget | Evaluating EEG complexity and spectral signatures in Alzheimer’s disea | NPJ Aging | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "OpenNeuro ds004504 EEG Alzheimer's Frontotemporal dementia healthy dataset"` |
| eeg-ad-ftd | budget | EEG Microstate Differences Between Alzheimer’s Disease, Frontotemporal | Medicina | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "OpenNeuro ds004504 EEG Alzheimer's Frontotemporal dementia healthy dataset"` |
| eeg-ad-ftd | budget | CONECT: Novel Weighted Networks Framework Leveraging Angle-Relation Co | Sensors (Basel, Switzerland) | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "ds004504"` |
| eeg-ad-ftd | budget | Classifying Alzheimer’s Disease and Dementia Patients Using Non-invasi | preprint | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "OpenNeuro ds004504 EEG Alzheimer's Frontotemporal dementia healthy dataset"` |
| eeg-ad-ftd | decomp_budget | Exploring Brain Network Organization in Alzheimer Disease and   Fronto | preprint | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease 23 frontotemporal dementia 29 healthy"` |
| eeg-ad-ftd | decomp_budget | Evaluating EEG complexity and spectral signatures in Alzheimer’s disea | NPJ Aging | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous EEG Alzheimer Frontotemporal dementia"` |
| eeg-ad-ftd | decomp_budget | Privacy–preserving dementia classification from EEG via hybrid–fusion  | Frontiers in Computational Neuroscience | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous DICE-net EEG dementia"` |
| eeg-ad-ftd | decomp_budget | An explainable and efficient deep learning framework for EEG-based dia | Frontiers in Medicine | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease 23 frontotemporal dementia 29 healthy"` |
| eeg-ad-ftd | decomp_budget | Distinct neurodynamics of functional brain networks in Alzheimer's dis | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease 23 frontotemporal dementia 29 healthy"` |
| eeg-ad-ftd | decomp_budget | EEG-SSM: Leveraging State-Space Model for Dementia Detection | preprint | 2024 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous DICE-net EEG dementia"` |
| eeg-ad-ftd | decomp_budget | Sink-index: a network-based EEG marker for frontotemporal dementia and | Brain Communications | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous DICE-net EEG dementia"` |
| eeg-ad-ftd | decomp_budget | xEEGNet: Towards Explainable AI in EEG Dementia Classification | preprint | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous DICE-net EEG dementia"` |
| eeg-ad-ftd | decomp_budget | Multi-Threshold Recurrence Rate Plot: A Novel Methodology for EEG Anal | Brain Sciences | 2024 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous DICE-net EEG dementia"` |
| eeg-ad-ftd | decomp_budget | Changes of brain functional network in Alzheimer’s disease and frontot | BMC Neuroscience | 2024 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "36 Alzheimer's disease 23 frontotemporal dementia 29 healthy"` |
| eeg-ad-ftd | decomp_budget | EEG features associated with Alzheimer’s disease and Frontotemporal de | Journal of Clinical Monitoring and Computing | 2025 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous EEG Alzheimer Frontotemporal dementia"` |
| eeg-ad-ftd | decomp_budget | Using Shallow Neural Networks with Functional Connectivity from EEG    | preprint | 2023 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous DICE-net EEG dementia"` |
| eeg-ad-ftd | decomp_budget | Advancing Alzheimer’s disease detection: a novel convolutional neural  | Brain Informatics | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Miltiadous DICE-net EEG dementia"` |
| freshmicro | control | Genetics of the human microglia regulome refines Alzheimer’s disease r | preprint | 2021 | true | `paperclip grep "syn25671134" /papers/ 2>&1` |
| freshmicro | control | Single cell transcriptomes and multiscale networks from persons with a | Nature Communications | 2024 | true | `paperclip grep "syn25671134" /papers/ 2>&1` |
| freshmicro | control | A public resource of single cell transcriptomes and multiscale network | preprint | 2023 | true | `paperclip grep "syn25671134" /papers/ 2>&1` |
| freshmicro | control | A public resource of single cell transcriptomes and multiscale network | preprint | 2023 | true | `paperclip grep "syn25671134" /papers/ 2>&1` |
| freshmicro | control | Variant-to-function mapping of late-onset Alzheimer’s disease GWAS sig | bioRxiv | 2024 | true | `paperclip grep "FreshMicro" /papers/ 2>&1` |
| freshmicro | control | Variant-to-function mapping of late-onset Alzheimer’s disease GWAS sig | preprint | 2024 | true | `paperclip grep "FreshMicro" /papers/ 2>&1` |
| freshmicro | control | Cell type-specific inference from bulk RNA-sequencing data by integrat | Genome Biology | 2025 | true | `paperclip grep "FreshMicro" /papers/ 2>&1` |
| freshmicro | decomp | Regulatory landscape of Alzheimer’s disease variants in human microgli | preprint | 2025 | true | `(not resolved)` |
| freshmicro | decomp | Genetic analysis of the human microglia transcriptome across brain reg | Nature genetics | 2022 | true | `(not resolved)` |
| freshmicro | decomp | A map of transcriptional heterogeneity and regulatory variation in hum | Nature genetics | 2021 | true | `(not resolved)` |
| freshmicro | budget | Regulatory landscape of Alzheimer’s disease variants in human microgli | preprint | 2025 | false | `(not resolved)` |
| freshmicro | budget | Alzheimer’s disease transcriptional landscape in ex-vivo human microgl | Research Square | 2024 | false | `(not resolved)` |
| freshmicro | budget | Genetics of the human microglia regulome refines Alzheimer’s disease r | preprint | 2021 | false | `(not resolved)` |
| freshmicro | decomp_budget | Genetics of the human microglia regulome refines Alzheimer’s disease r | preprint | 2021 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "fresh human microglia regulome ATAC-seq eQTL Alzheimer's disease"` |
| mc-caa | control | Identification of Novel Genetic Risk Factors for Cerebral Amyloid Angi | Alzheimer's & Dementia | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Mayo Clinic Brain Bank cerebral amyloid angiopathy 932 autopsy"` |
| mc-caa | control | Cerebral amyloid angiopathy impacts neurofibrillary tangle burden and  | Brain Communications | 2024 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "Mayo Clinic Brain Bank cerebral amyloid angiopathy 932 autopsy"` |
| mc-caa | budget | Identification of Novel Genetic Risk Factors for Cerebral Amyloid Angi | Alzheimer's & Dementia | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "AD-CAA Mayo Clinic study neuropathological genomic variants gene expression"` |
| mc-caa | budget | Cell type‐specific gene expression changes are associated with cerebra | Alzheimer's & Dementia | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "AD-CAA Mayo Clinic study neuropathological genomic variants gene expression"` |
| mc-caa | decomp_budget | The AD Knowledge Portal: A Repository for Multi‐Omic Data on Alzheimer | Current Protocols in Human Genetics | 2020 | true | `paperclip grep "Mayo Clinic.{0,80}cerebral amyloid angiopathy" /papers/ 2>&1 / head -60` |
| mtdna-ad | control | Characterization of mitochondrial DNA quantity and quality in the huma | Molecular Neurodegeneration | 2021 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "whole genome sequencing mitochondrial DNA brain aging Alzheimer disease 1361 samples cohort" 2>&1 / head -50` |
| mtdna-ad | control | Mitochondrial  DNA  Variation in the Aging Human Cerebral Cortex and C | Aging Cell | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "whole genome sequencing mitochondrial DNA brain aging Alzheimer disease 1361 samples cohort" 2>&1 / head -50` |
| mtdna-ad | control | The role of mitochondrial genome abundance in Alzheimer’s disease | Alzheimer's & dementia : the journal of the Alzheimer's Association |  | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv -e "The Mitochondrial DNA in Aging and AD (mtDNA_AD) Study" 2>&1 / head -60` |
| mtdna-ad | decomp | Characterization of mitochondrial DNA quantity and quality in the huma | Molecular Neurodegeneration | 2021 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "mitochondrial DNA whole genome sequencing brain tissue Alzheimer's disease aging 1,361 samples" -n 10 2>&1` |
| mtdna-ad | budget | The role of mitochondrial genome abundance in Alzheimer’s disease | Alzheimer's & dementia : the journal of the Alzheimer's Association |  | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "mitochondrial DNA copy number 1361 samples brain Alzheimer whole genome sequencing" 2>&1` |
| mtdna-ad | budget | Characterization of mitochondrial DNA quantity and quality in the huma | Molecular Neurodegeneration | 2021 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "mitochondrial DNA copy number 1361 samples brain Alzheimer whole genome sequencing" 2>&1` |
| mtdna-ad | budget | Mitochondrial  DNA  Variation in the Aging Human Cerebral Cortex and C | Aging Cell | 2025 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "mitochondrial DNA copy number 1361 samples brain Alzheimer whole genome sequencing" 2>&1` |
| mtdna-ad | decomp_budget | Characterization of mitochondrial DNA quantity and quality in the huma | Molecular Neurodegeneration | 2021 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "mitochondrial DNA copy number aging brain 1361 samples" 2>&1 / head -60` |
| r47h-trem2 | control | AD-linked R47H- TREM2  mutation induces disease-enhancing proinflammat | preprint | 2020 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "AD-linked R47H-TREM2 mutation induces disease-enhancing microglial states via AKT hyperactivation" -n 10` |
| r47h-trem2 | decomp | AD-linked R47H- TREM2  mutation induces disease-enhancing proinflammat | preprint | 2020 | — | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "R47H TREM2 AKT microglia" 2>&1 / tail -40` |
| r47h-trem2 | budget | AD-linked R47H- TREM2  mutation induces disease-enhancing proinflammat | preprint | 2020 | true | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "reanalysis of single-nucleus RNA-seq data from R47H TREM2 Alzheimer's disease microglia AKT hyperactivation dataset (Sayed et al.)" -n 10 2>&1` |
| r47h-trem2 | decomp_budget | AD-linked R47H- TREM2  mutation induces disease-enhancing proinflammat | preprint | 2020 | false | `paperclip search -s pmc,biorxiv,medrxiv,arxiv "R47H TREM2 microglia AKT signaling drug target reanalysis human brain postmortem" 2>&1` |