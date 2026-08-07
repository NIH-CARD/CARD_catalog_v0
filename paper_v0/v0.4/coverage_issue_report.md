# Publication Coverage

#Follow-up on Issue Raised by Reviewer

We are having problems with searching the biomedical literature for relevant studies with our set of keywords (Resource Name, Abbreviation, Coarse Data Modality, Granular Data Modality, Diseases Included) from our [resources table](https://github.com/NIH-CARD/CARD_catalog_v0/blob/from_v0_to_v1/tables/resources-inventory-Jun_8_2026.tab)

| | Resources matched | % of 236 |
|---|---:|---:|
| Q1 (original: All Fields + disease + modality) | 73 | 30.9% |
| Q2 (tiab only, no disease/modality) | 91 | 38.6% |
| Q3 (tiab + disease + modality) | 69 | 29.2% |
| Q4 (tiab + concept fan-out/batching) | 98 | 41.4%* |
| Study page navigation (Mar 11 snapshot) | 25 | 10.6% |

\* Q4 ran on a later, slightly different inventory (237 vs 236 resources) — not a fully controlled comparison with Q1-Q3.

## Paperclip (high-speed full-text search)

Tested on one confirmed zero-hit resource (`ADMC_ADNI_UHawaiiGutMetabolites`) — found 2 relevant papers by matching Methods-section identifiers (e.g. dataset table name), not the catalog's registered name. Works because it searches full text, not just title/abstract like PubMed.

Not yet validated: tested on 1 resource only; precision (are matches actually about the resource, or just co-occurring) unmeasured.

## Note: Precision >> Recall

We do not want to trade false positives (articles incorrectly linked to a study) for higher coverage. Any recall-improving direction — including Q4 and Paperclip — needs a precision check before being treated as a fix, not just a "found more matches" check.

## Paperclip pilot: 12-resource random sample (Q3 structural zero-hit set, seed=42)

Each row is a candidate found via an agent-driven Paperclip investigation, verified (or not) through Paperclip's own claim-verification workflow (`repo add`/`repo commit`). **[OK]** rows still need your manual spot-check per the 100%-precision bar — this table is for that check.

| Resource | Candidate | Link | Verdict | Note |
|---|---|---|---|---|
| A4 (Anti-Amyloid Treatment in Asymptomatic Alzheimer's Study) | Papp et al. 2024, J Prev Alzheimers Dis | https://pubmed.ncbi.nlm.nih.gov/39044493/ | [OK] | Title names "the A4 Study" directly |
| A4 | Zhu et al. 2025, Alzheimer's & Dementia | https://pubmed.ncbi.nlm.nih.gov/41085151/ | [OK] | N=1165 matches catalog's 1,169 participants |
| A4 | Insel et al. 2020, Ann Clin Transl Neurol | https://pubmed.ncbi.nlm.nih.gov/32315118/ | [OK] | Title: "The A4 study: β-amyloid and cognition..." |
| 10/66 Life2Years (Dementia Research Group 10/66) | Cohort Profile: The 10/66 study, IJE 2017 | https://pubmed.ncbi.nlm.nih.gov/27154633/ | [OK] | Same paper already in catalog's Alternative URLs |
| 10/66 Life2Years | J Gerontol B 2025 (nested qualitative study) | https://pubmed.ncbi.nlm.nih.gov/40197625/ | [OK] | Explicitly "nested within the 10/66 DRG LIFE2YEARS study" |
| 10/66 Life2Years | Lancet Global Health 2020 | https://pubmed.ncbi.nlm.nih.gov/32199121/ | [OK] | Uses grant name "LIFE2YEARS1066" |
| MC-CAA (Mayo Clinic AD-CAA Study) | Reddy et al., Acta Neuropathol Commun 2021 | https://pubmed.ncbi.nlm.nih.gov/34020725/ | [OK] | Founding paper that defines/names "MC-CAA" |
| MC-CAA | Oatman et al., Mol Neurodegener 2023 | https://pubmed.ncbi.nlm.nih.gov/36609403/ | [OK] | Reuses same Mayo Clinic Brain Bank cohort |
| EEG (AD/FTD/Healthy dataset, ds004504) | Del Pup et al. 2024, arXiv | https://arxiv.org/abs/2411.18392 | [OK] | Explicit reuse, exact 36/23/29 demographic breakdown |
| EEG | González-Sanz, Hallin, Yao 2025, arXiv | https://arxiv.org/abs/2510.03166 | [OK] | Same dataset, same demographic breakdown |
| FreshMicro (Fresh Microglia Regulome Study) | Kosoy et al. 2021, medRxiv | https://doi.org/10.1101/2021.10.17.21264910 | [OK] | Matched via exact Synapse ID (syn25671134), not catalog name |
| R47H-TREM2 study | Sayed et al. 2020, bioRxiv preprint | https://doi.org/10.1101/2020.07.24.218719 | [OK] | Preprint of the paper catalog's own Access URL already pointed to (PMID 34851693, not in corpus) |
| BORCS6 Knockdown Transcriptomics | Ryan, Lawton, ... Ward lab, 2024, bioRxiv | https://doi.org/10.1101/2024.09.30.615241 | [OK] | Cites exact ADWB dataset slug `borcs6_kd_transcriptomics_on_ineurons` in Data Availability |
| CamPaIGN (Cambridgeshire Parkinsons Incidence) | NLP/sleep-variable-harmonization paper, bioRxiv 2026 | https://doi.org/10.64898/2026.01.18.26344317 | [OK] — **flag for relevance** | Cohort is 1 of 20 DPUK cohorts cited, contributes <1% of variables — technically verified, thin relevance |
| mtDNA_AD (Mitochondrial DNA in Aging and AD) | Klein, Trumpff, ... Picard et al., medRxiv 2021 | https://doi.org/10.1101/2021.05.20.21257456 | **Confirmed match (human review)** | Blocked by Paperclip's `[X]` (claim phrased around catalog's own name, which the paper never uses) — Pietro manually confirmed this is a true match |
| VirusResilience_LCL | Smullen et al. 2023, Sci Rep | https://pubmed.ncbi.nlm.nih.gov/37369829/ | **Confirmed match (human review)** | Blocked by same claim-wording issue — Pietro manually confirmed this is a true match |
| EEG (AD/FTD/Healthy dataset, ds004504) | Azargoonjahromi et al. 2024, medRxiv | https://doi.org/10.1101/2024.08.05.24311520 | **BLOCKED** | Strongest textual match of the three EEG candidates; blocked by a `repo add`/claim-attach tool ID-mismatch bug, not relevance |
| AUSBB (Australian Brain Bank snRNA-seq study) | — | — | No candidates — pending review | Exhaustive search (synapse ID, brain bank names, abbreviation, consortium name) found nothing; likely too recently deposited to have a paper yet |
| ADMC-ADNI Metabolon | — | — | No candidates — pending review | Several ADNI+metabolomics papers found and actively ruled out as different ADMC sub-platforms (targeted p180, Biocrates Q500, lipidomics) |

**Yield: 10/12 resources (83%) confirmed with a real match** (8 machine-verified `[OK]` + 2 upgraded by Pietro's manual review after being blocked on a claim-wording technicality). AUSBB and ADMC-ADNI Metabolon still pending review. **Precision: spot-check of the 8 `[OK]` rows still in progress.**

Recurring process issues (not relevance failures) found across the pilot:
1. Claims phrased around the catalog's own invented resource name fail verification even on true positives — should assert verifiable facts (accession IDs, sample counts, cohort names) instead.
2. Paperclip's `repo checkout` is sticky/global on the account — running 12 agents concurrently caused cross-contamination between agents' active repos (confirmed independently 4 times); needs an explicit `--repo` flag or non-concurrent execution before scaling.
3. One apparent tool bug (`repo add` vs. claim-attach disagreeing on doc ID) blocked an otherwise-strong candidate.
