# Revision 2 — pre-submission checklist

Files regenerated in this folder are marked **[file ready]**: replace the old file in the submission with the one here.
Everything else is a manual edit, with the exact text where useful.

---

## A. Replace files in the submission

- [x] **Upload the regenerated files** from this folder in place of the old ones: Figure 1, Figure 2, Figure 3 (PDF instead of .txt), Figure 7, FAIR Compliance Rubric.xlsx, Table 1.xlsx. *(Ticked items below = file regenerated and checked.)*
- [x] **Figure 1** → `Figure 1.png` **[file ready]** — was 1,903 repositories / 1,061 via software mentions; now 1,898 / 1,056.
- [x] **Figure 2** → `Figure 2.pdf` (+ `Figure 2.png`) **[file ready]**
  - Panel a: corrected FAIR split (clinical Excellent 93, not 96).
  - Panel c: **studies only**, as the Results and the R1/R2 replies state (max ≈ 820,000, no longer 5.9 M). Legend counts are now clinical 138, genetics 58, transcriptomics 69, longitudinal 50, proteomics 35.
  - Panel labels are now lower-case **a, b, c**; Panel c colours are colour-blind safe.
- [x] **Figure 3** → `Figure 3.pdf` (+ `.png`) **[file ready]** — replaces `Figure 3.txt` (.txt is not an accepted figure format). "Peer to track… unchecked" line removed.
- [x] **Figure 7** → `Figure 7.png` / `.pdf` **[file ready]** — rubric rows 3–5 repaired ("…but lacking comprehensive standardization across all data types", "…for at least one major data modality", "…available to researchers"); Good description de-garbled.
- [x] **FAIR Compliance Rubric.xlsx** → `FAIR Compliance Rubric.xlsx` **[file ready]** (same fixes), or drop it: Figure 7 already shows it.
- [x] **Table 1** → `Table 1.xlsx` **[file ready]** — was the pre-fix version (126/58/53, 1,903 repos, R n=360, README 99.2%…). Same sections, current values.
- [x] **Table 2.xlsx and Table 2(1).xlsx** — duplicates of *Supplementary Table 3* (one says "Confirmed", the other "Corroborated"). Keep at most one, and label it **Supplementary Data 1**, or drop both (the table is already in the supplement).
- [x] **V0 - main.docx** — confirm you mean to upload the original manuscript (if the system wants a tracked-changes version, that's a different file).
- [x] **Supplementary Material** — export as a **single merged PDF** (journal requirement), after the fixes in section C.

## B. Manuscript (Manuscript.docx)

### Consistency with figures/tables
- [ ] **Table 1 content** — apply the restructure discussed: sample-size rows → studies only (n=183, median 463 [IQR 58–1,498], range 1–820,000, 120 <1,000); modality % of 237 resources; drop tooling/data-type/code-summary keyword lists and variant themes; add resource types, publication coverage, repository sources, relevance split; header row `Measure | n | %`; new legend.
- [ ] **Figure 2 legend** — replace with:
  > **Figure 2: CARD Catalog landscape.** **a** Occurrences of the eight most common coarse data modalities, stratified by FAIR compliance level. **b** Share of GitHub repositories missing each FAIR-related component, for the eight most common languages. **c** Sample-size distributions (log scale) for the five most common data modalities, restricted to studies reporting a numeric sample size; repositories, biorepositories and data catalogs are excluded because their counts aggregate or re-host participants from constituent studies.

  (This also removes the Model-AD note — Model-AD isn't in the inventory.)
- [ ] Text references "Figure 2a / Fig 2b" — use one style (e.g. **Fig. 2a**, **Fig. 2b**).

### Statements that contradict each other or the rebuttal
- [ ] **Discussion › High compliance Bias** — "While the difference between the 'Good' level and the 'Excellent' and 'Strong' level … was significant" contradicts Methods/rebuttal ("not statistically significant"). Name the measure:
  > *For dataset citations, resources rated Excellent or Strong were DOI-backed significantly more often than those rated Good (48.4% vs. 29.1%; Fisher's exact test, p = 0.013), whereas the two upper tiers did not differ from each other (Supplementary Table 1).*
- [ ] **Programmatic Insights** — delete "and may return an insufficient-evidence response when the available data do not support an interpretation" (no AI Analysis prompt has that option).
- [ ] **Model Hallucinations** — "human-in-the-loop (HitL) audits of **all results** remain part…" → "human-in-the-loop (HitL) review remains part…".
- [ ] **Model Hallucinations** — "verdicts and their rationales are released" → "the supporting evidence and rationale of every retained link are released (Claim Text, Inclusion Criteria)".
- [ ] **Hallucination Mitigation** — align with the R3 reply: scope the five safeguards to the annotation pipeline and change "for deterministic output" → "to minimise output variability".

### Missing statements
- [ ] **3-year window** (the R2 reply says it's stated; it isn't). Add to *NCBI Entrez Utilities*:
  > *Searches were restricted to publications from the three years preceding each run (e.g. 2023/08/11–2026/08/10), a limit set by the scalability of the current backend.*
- [ ] **[tiab]** — in the Q2 sentence: "restricted the fields of search to Title and Abstract only ([tiab] in PubMed syntax)".
- [ ] **LLM use, per component** (journal: document LLM use in Methods). Hallucination Mitigation names only Sonnet 4.5 / Haiku 4.5. Suggested (verify against the runs):
  > *Publication–resource verification used gpt-oss-20b (self-hosted via vLLM); extraction of cited datasets, supplementary files, grants, software and models used Claude Haiku 4.5 (Data Gatherer, full-document read); repository annotation used Claude Sonnet 4.5; LLM-assisted query generation (Q5) and agentic search used Claude Sonnet 5; the interactive AI Analysis panels use Claude Sonnet 4.6 (up to 4,000 output tokens).*
- [ ] **Acknowledgements, AI disclosure** — the Gemini/Claude Code note can stay in the Acknowledgements (language polishing is "green" in the Nature Portfolio AI policy; no Methods placement needed). But extend it to cover revision-stage help ("amber": statistical tests, drafting, literature comparison — permitted with disclosure), e.g.:
  > *Claude (Anthropic) was used via Claude Code for code review, repository management and documentation, and during revision to assist with statistical analyses, consistency checks against the data, and drafting of text; all analyses were verified and all text was reviewed and edited by the authors. Gemini in Google Docs was used to correct grammar and spelling.*
- [ ] **AI-assisted analysis** — the panel list misses **Cited Datasets**; "top N filtered rows" → "first N filtered rows in their current order"; "calls the LLM" → "calls Claude (claude-sonnet-4-6)".

### Text fixes
- [ ] Limitations: "for **11 articles** we still return an empty literature corpus" → "for **11 resources**".
- [ ] Methods, Low Resources Coverage: the "more than 36,500" sentence appears twice in a row — delete one. Check "21,983 unique articles" (recount gives 21,615 by PMID/DOI/PMC).
- [ ] Methods, Resources FAIRness: sentence fragment → "Because ratings were reconciled to consensus rather than independently double-scored, a formal inter-rater agreement statistic could not be computed. As an external check, …"; "Dementia field" → "dementia field"; "diffused" → "adopted".
- [ ] Results, Code: "whereas Jupyter vs. R**:** was not significant" → remove the colon.
- [ ] Methods, repository annotation: "327 of **1,897**… 17.2%" → "327 of **1,895** … 17.3%"; "12.2%" → "12.3%"; "GitHUb" → "GitHub"; trailing ";" after "(n = 230)".
- [ ] Supplementary Table 3 / Figure 4 call methods *original, v2–v5*; text says *Q1–Q5*. Add once: "(original = Q1, v2 = Q2, v3 = Q3, v4 = Q4, v5 = Q5)".
- [ ] Intro: "ADKB" → "ADKG" (ref 8); "…chemicals, drugs, and other diseases" (diseases twice); "National Institute **of** Aging" → "**on** Aging"; "Google Data**sets** Search" → "Google Dataset Search".
- [ ] Abstract: "237 Data resources" → "237 data resources"; "heterogenous" → "heterogeneous"; "AI-Assisted" → "AI-assisted".
- [ ] Affiliation 9: "**Board** Institute" → "**Broad** Institute".
- [ ] Author Contributions: remove the yellow highlight; "PB, PB" → distinct initials (e.g. PBr = Patrick Brannelly, PBa = Payam Barnaghi); "**RH**" is not an author — remove or fix.
- [ ] Headings not formatted as headings: "Programmatic Insights", "Current Limitations"; "High compliance Bias" → "High compliance bias".
- [ ] Future Directions: "improve the DOI agreement score" — undefined term; e.g. "add persistent-identifier use as an explicit criterion of the FAIR assessment".
- [ ] Figure legends: Figure 5 legend garbled ("…construction steps that when CARD Catalog is built"); Figure 7 "Rubic" → "Rubric"; Table 1 legend "per paginated dataset" → e.g. "per catalog table".

### References
- [ ] **Number in order of first citation** (refs 15–17 are cited before 9–14).
- [ ] Refs 15–17 are cited for ROS, MAP, NACC, ADNI — ref 17 is **PPMI** and NACC has no reference.
- [ ] Ref 24 is malformed → "Marini, P. et al. Data Gatherer Revisited: Scalable Dataset Reference Extraction from Biomedical Literature. In *VLDB 2026 Workshop: Biomedical Data Management Systems (BioDMS)* (2026)."
- [ ] Ref 8: cite only the published version (*Comput. Biol. Med.* 192, 110285 (2025)).
- [ ] Ref 19: if CARDBiomedBench is now published (the rebuttal cites doi:10.1016/j.landig.2025.100943), cite the published version.
- [ ] Remove Paperpile hyperlinks from in-text citations. (Full Nature reference style is only required at acceptance.)

## C. Supplementary Material

- [ ] **Supplementary Table 1** — paste values from `Supplementary Table 1.md` / `.xlsx` **[file ready]**. Current errors: Cited Datasets Total **102/135** → **104/133**; Software Excellent Without DOI **76** → **78**; stray "**.8**" before Strong.
- [ ] Supplementary Figure 1 — the same image appears twice; keep one.
- [ ] Supplementary Figure 3 caption: "corroborates or **refuses**" → "corroborates or **refutes**".
- [ ] Export the whole file as a single PDF.

## D. Rebuttal letter

- [ ] **R1 — embedded Figure 3**: replace with `Figure 3 (text, for the rebuttal letter).txt` **[file ready]** (old copy says 211 ROS papers, 5,086 papers, 162/211, tau 110…, and the "Peer to track…" line).
- [ ] **R1 — rubric table (Page 10 comment)**: re-paste from `FAIR Compliance Rubric.xlsx` **[file ready]**, or insert `Figure 7.png`.
- [ ] **R1 — Panel A vs Panel C counts**: "Panel C's sample-size distributions include only resources whose reported sample size is a natural number" → "…include only **studies** whose reported sample size is a natural number" (now true with the new Figure 2; e.g. clinical 184 in a vs 138 in c).
- [ ] **R2 and R3 — DOI tables**: Total row **112 / 125 / 47.3%** → **114 / 123 / 48.1%** (both copies).
- [ ] **R2 — knowledge graph**: "Publications serves as a **fixed** anchor" → "Publications is the **default** anchor (users can also start from Resources or Human Cellular Models)".
- [ ] **R2 — 3-year window**: true once the Methods sentence in section B is added.
- [ ] **R2 — "cautious responder"**: remove the yellow highlight on the DOI; say the term was removed from the manuscript; make the citation match ref 19.
- [ ] **R2 — RRIDs** (optional): one sentence, e.g. "RRIDs for cell lines and repositories are a planned addition to the Resource-level FAIR criteria."
- [ ] **R3 Major 1 — conflict of interest** (you chose to skip): note that ADDI staff are co-authors and ~half of Excellent ratings cite the ADDI platform (`../fair_excellent_platform_justified.csv`). One neutral sentence on who rated and how platform affiliation was handled would close it.
- [ ] **R3 Major 2 — "by whom"**: point to the HitL roster in Author Contributions (PM, MPe, MAN, TH, EH, EM, BB, CM).
- [ ] **R3 Major 3**: "favored precision over **performance**" → "over **coverage**".

## E. Journal requirements (npj Dementia)

- [ ] **Funding** in the Acknowledgements, **with the funder's role** (NIH CARD staff are authors — say so rather than "no role").
- [ ] **Code availability** as a Methods subsection headed "Code availability"; consider citing the release tag `zenodo-v1.0.0`.
- [x] Data Availability heading: "Data Availability" (after Methods, before References) — position already correct.
- [ ] **Reporting Summary** and **Editorial Policy Checklist** — required with the revision; not in the zip.
- [ ] **Cover letter** — corresponding-author contact; the place for confidential COI notes. Not in the zip.
- [x] Figure legends after the references in the main file — already done.
- [x] Related manuscript (VLDB paper) included — already done.

## F. Repo housekeeping (after submission)

- [ ] Commit the regenerated figures/tables and script changes: `paper_v0/figure4_landscape_v2.py`, `figure3_workflow_userstories.py`, `figure7_fair_rubric.py` (new), `export_table_to_csv.py`, and `paper_v0/v0.4/`.
- [ ] Next Zenodo release (v1.1.0): include the Data Completeness column (live data has it; v1.0.0 doesn't).
