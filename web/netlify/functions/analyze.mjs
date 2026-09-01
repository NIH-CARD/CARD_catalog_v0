const MODEL = "claude-sonnet-4-6";
const MAX_TOKENS = 4000;

// Server-side, at request time - real "today," not the model's training cutoff.
// Without this, a model asked to eyeball a Publication Year distribution has no
// way to know a "2026" isn't from the future - it'll flag a perfectly normal
// recent publication as a suspected date-parsing bug.
function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

const DEFAULT_SYSTEM =
  "You are a critical data curator reviewing research catalog records for the NIH Center for Alzheimer's and Related Dementias (CARD). Your role combines scientific insight with rigorous skepticism: synthesize patterns across the data provided, but flag extraction artifacts, implausible records, and unsupported inferences rather than papering over them. Ground all quantitative claims in the data you are given. Do not hallucinate details not present in the input.";

// A function, not a module-level constant - a Netlify function instance can
// stay warm across day boundaries, so today's date must be computed fresh
// per request, not baked in once at cold-start.
function crossTableSystem() {
  return `You are a senior neurodegenerative-disease researcher - a geneticist and biologist first, not a database engineer - doing exploratory discovery on a custom cross-table view of the CARD Catalog. Today's date is ${todayIso()}.

Read this the way a domain expert reads a cohort/consortium landscape, not the way a data engineer reads a table dump. When you see a cohort name (BioFINDER, ADNI, ROSMAP...), a gene, a variant, or a biomarker modality, say what it means scientifically - which disease mechanism, which biomarker class, which patient population, which consortium's known research focus - not just that it appears N times. You're given two aligned pictures for the same columns - the full catalog's baseline distribution and the current subset's - so ground comparative claims like "this subset skews toward X relative to the catalog as a whole" in that contrast, not just in raw counts from one side alone.

State comparisons directly and confidently once the evidence supports them - do not hedge every observation as "worth investigating further." Extraction artifacts, naming-variant fragmentation, and normalization issues are not your focus - mention one only in passing if it's clearly blocking a real scientific read, never as a headline finding.

A recent or even near-future publication year is completely normal in a routinely-refreshed catalog - today is ${todayIso()}, so never flag a value merely for being "in the future" relative to your own training data.`;
}

function systemPromptFor(type) {
  return type === "cross_table" ? crossTableSystem() : DEFAULT_SYSTEM;
}

function formatResources(rows) {
  return rows.map((r) =>
    `Resource: ${r.name} (${r.abbreviation})\n  Diseases: ${r.diseases}\n  Modality: ${r.modality}\n  Sample Size: ${r.sampleSize}\n  Type: ${r.type}`
  ).join("\n\n");
}

function formatPublications(rows) {
  return rows.map((p) =>
    `Title: ${p.title}\n  Authors: ${p.authors}\n  Study: ${p.study}\n  Keywords: ${p.keywords}\n  Abstract: ${p.abstract}`
  ).join("\n\n");
}

function formatCode(rows) {
  return rows.map((r) =>
    `Repo: ${r.repo}\n  Study: ${r.name}\n  Languages: ${r.languages}\n  Data Types: ${r.dataTypes}\n  Tooling: ${r.tooling}\n  Relevance: ${r.relevance}\n  FAIR Score: ${r.fairScore}`
  ).join("\n\n");
}

function formatPubDatasets(rows) {
  return rows.map((r) =>
    `Dataset: ${r.identifier}\n  Webpage: ${r.webpage || "(none)"}\n  Repository: ${r.repository}\n  Citation Type: ${r.citationType}\n  Access Mode: ${r.accessMode || "(not recorded)"}\n  Keywords: ${r.keywords}\n  Publication: ${r.pubTitle}\n  Context: ${r.context}`
  ).join("\n\n");
}

function formatCellularModels(rows) {
  return rows.map((r) =>
    `${r.productCode}: ${r.gene} ${r.geneVariant}\n  Condition: ${r.condition}\n  About gene: ${r.aboutGene}\n  About variant: ${r.aboutVariant}`
  ).join("\n\n");
}

const MAX_INPUT_CHARS = 180000 * 4; // ~180k tokens estimated at 4 chars/token

function truncateFormatted(text, label) {
  if (text.length <= MAX_INPUT_CHARS) return text;
  return text.slice(0, MAX_INPUT_CHARS) + `\n\n[Content truncated to fit token limits]`;
}

function appendOverflow(text, sentCount, filteredCount, label) {
  if (filteredCount > sentCount) {
    return text + `\n\n... and ${filteredCount - sentCount} more ${label}`;
  }
  return text;
}

function buildPrompt(type, rows, filteredCount, totalCount) {
  const isSubset = filteredCount < totalCount;
  const comparativeContext = isSubset
    ? `\nComparative context: showing ${filteredCount} of ${totalCount} total records in the catalog.`
    : "";

  switch (type) {
    case "resources": {
      const datasetInfo = (comparativeContext ? comparativeContext + "\n\n" : "") +
        truncateFormatted(appendOverflow(formatResources(rows), rows.length, filteredCount, "datasets"));
      return `You are analyzing a collection of neuroscience and brain disorder research datasets.

Dataset Information:
${datasetInfo}

Based on these datasets, provide:
1. **Key Patterns & Trends**: Identify patterns across the collection
2. **Common Modalities & Diseases**: Most frequent data types and disease focuses
3. **Gaps & Opportunities**: Notable gaps in the dataset landscape
4. **Recommendations**: Actionable guidance for researchers

5. **Comparative Analysis** (if comparative context provided above):
   - How does this selection differ from the full catalog?
   - What makes this subset unique or specialized?
   - How does it align with current research trends in the field?

Keep your response concise, insightful, and actionable. Use bullet points and clear section headers.`;
    }

    case "publications": {
      const publicationInfo = (comparativeContext ? comparativeContext + "\n\n" : "") +
        truncateFormatted(appendOverflow(formatPublications(rows), rows.length, filteredCount, "publications"));
      return `You are analyzing a collection of scientific publications related to neuroscience and brain disorders.

Publication Information:
${publicationInfo}

IMPORTANT: Clearly distinguish in your analysis between:
- **THIS FILTERED SUBSET** (quantify with exact counts and percentages)
- **THE FULL CATALOG** (when comparative context provided)
- **GENERAL FIELD TRENDS** (broader research landscape)

Based on these publications, provide:

1. **Major Research Themes & Topics** (in THIS subset):
   - Specify: "In this subset of N publications..."
   - Quantify themes with percentages

2. **Most Active Research Areas** (in THIS subset vs full catalog):
   - Specify: "X% of this subset focuses on..."
   - Compare: "Compared to Y% in full catalog..."

3. **Authorship & Collaboration Trends** (THIS subset):
   - Quantify: "N unique authors", "Top institutions represent X%..."
   - Note if different from full catalog patterns

4. **Key Findings & Emerging Directions**:
   - Subset-specific: "These N publications show..."
   - Field context: "This aligns with/diverges from general trends in..."

5. **Research Gaps & Funding Opportunities**:
   - Identify underrepresented areas in THIS subset
   - Highlight programmatic gaps that could benefit from future funding
   - Suggest strategic research directions based on the data

Use exact numbers and percentages. Always clarify scope: "this subset", "the full catalog", or "general field trends".`;
    }

    case "code": {
      const repositoryInfo = (comparativeContext ? comparativeContext + "\n\n" : "") +
        truncateFormatted(appendOverflow(formatCode(rows), rows.length, filteredCount, "repositories"));
      return `You are analyzing a collection of code repositories related to neuroscience and brain disorder research.

Repository Information:
${repositoryInfo}

Based on these repositories, provide:

1. **Programming Languages & Technologies**: Most commonly used languages and frameworks
2. **Data Types & Research Focus**: Types of data processed and research domains
3. **Code Quality & FAIR Compliance**: Patterns in biomedical relevance, FAIR scores, and tooling maturity
4. **Collaboration & Reusability**: Insights into code sharing, documentation quality, and potential for reuse
5. **Gaps & Opportunities**: Underrepresented areas or technologies that could benefit from more development

6. **Comparative Analysis** (if comparative context provided above):
   - How does this selection differ from the full catalog?
   - What makes this subset unique in terms of technology or research focus?
   - How does it align with current trends in computational neuroscience?

Keep your response concise, insightful, and actionable. Use bullet points and clear section headers.`;
    }

    case "cellular_models": {
      const summary = truncateFormatted(appendOverflow(formatCellularModels(rows), rows.length, filteredCount, "cell lines"));
      const comparison = isSubset
        ? `Comparison context: this subset contains ${filteredCount} of ${totalCount} total iNDI cell lines.`
        : "";
      return `You are analyzing a collection of human iPSC cellular models from the iNDI (iPSC Neurodegenerative Disease Initiative) collection.

Cellular Model Information:
${summary}

${comparison}

Provide a comprehensive analysis with the following sections:

## 1. Disease & Gene Distribution
- Quantify gene representation in this subset vs full catalog (if comparison provided)
- Identify most represented conditions/diseases
- Note any specialized disease focus in this subset
- Specify exact counts and percentages

## 2. Gene Function Analysis
- Based on the "About this gene" and "About this variant" information provided
- Summarize key biological functions and pathways represented
- Identify common disease mechanisms across the gene panel
- Highlight genes involved in neurodegeneration-specific processes (protein aggregation, neuronal function, synaptic activity, etc.)

## 3. Pathway & Interaction Analysis
- Analyze potential biological pathways represented by these genes
- Identify likely protein-protein interactions between genes in this panel
- Highlight pathway convergence points (genes that may interact or affect common pathways)
- Note any potential gaps in pathway coverage (missing key interactors)
- Focus on neurodegenerative disease mechanisms: protein homeostasis, mitochondrial function, synaptic function, inflammation, etc.

## 4. Publications of Interest
- For each key gene in this collection, provide:
  - Specific PubMed search query (e.g., "GENE_NAME[Title/Abstract] AND (Alzheimer OR neurodegeneration) AND (2020:2025[pdat])")
  - Direct PubMed search link: https://pubmed.ncbi.nlm.nih.gov/?term=YOUR_SEARCH_QUERY
  - Brief explanation of why this search is relevant
- Focus on: recent papers (2020-2025), neurodegenerative disease context, functional studies
- Highlight genes with emerging therapeutic relevance
- Format as clickable markdown links: [Search: GENE_NAME neurodegeneration 2020-2025](https://pubmed.ncbi.nlm.nih.gov/?term=...)

## 5. Utility for Functional & Precision Medicine
- **CRISPR Model Utility**: How these engineered lines enable functional studies of disease variants
- **Clinical Insights**: What patient-relevant biology can be studied with these models
- **Therapeutic Development**: Potential for drug screening, mechanism studies, and personalized medicine approaches
- **Comparative Advantage**: What makes this collection valuable vs other model systems

## 6. Comparative Analysis (if comparison context provided)
- How does this subset differ from the full catalog?
- What makes this selection unique or specialized?
- Are there focused research questions this subset is particularly suited for?

Be specific with gene names, disease mechanisms, and pathway details. Use exact counts and percentages. Focus on actionable insights for neurodegenerative disease research.`;
    }

    case "pub_datasets": {
      const datasetInfo = (comparativeContext ? comparativeContext + "\n\n" : "") +
        truncateFormatted(appendOverflow(formatPubDatasets(rows), rows.length, filteredCount, "datasets"));
      return `You are analyzing a collection of datasets cited in neuroscience and brain disorder research publications.

Note: dataset context and keywords were extracted and summarized by an automated AI pipeline from the source publications — they may contain paraphrasing errors or hallucinated details. Apply appropriate skepticism, especially in section 3.

Dataset Information:
${datasetInfo}

IMPORTANT: Clearly distinguish in your analysis between:
- **THIS FILTERED SUBSET** (quantify with exact counts and percentages)
- **THE FULL CATALOG** (when comparative context provided)

Based on these cited datasets, provide:

1. **Data Repository Landscape** (in THIS subset):
   - Which repositories are most frequently cited? Use counts and percentages as supporting evidence, not as the main point.
   - Identify concentration patterns or anomalies across platforms (e.g., GEO, Synapse, institutional repositories). What does the distribution tell you about data sharing norms in this research area?

2. **Dataset Citation Types & Context**:
   - What citation types are represented (primary vs. secondary)?
   - Reading the context in which datasets are cited, can you understand how they were used (if at all)?
   - Only where the context is sufficiently informative (more than a sentence fragment), draw relations between datasets and the publication's research question. Do not infer connections from thin or ambiguous context.

3. **Extraction Quality & Red Flags**:
   - This data was extracted from scientific publications by an automated pipeline. Be adversarial: flag anything that looks wrong, incomplete, or implausible.
   - Suspect records: identifiers that look malformed, garbled, or generic; context fields that are off-topic, truncated mid-sentence, or clearly copied from the wrong passage; repositories that don't match the dataset type or field.
   - Implausible links: flag any dataset-to-publication associations that seem unlikely given the research topic.
   - Inference failures: if a record's context suggests the "dataset" is actually a tool, a method, or a figure reference — flag it. The upstream step may have hallucinated a dataset citation.
   - FAIR signal: records with no Webpage URL and only a generic or acronym-style identifier (e.g., "PPMI", "ADNI") are weakly cited — flag them as lower-confidence entries.
   - Do not synthesize findings from records you flagged as suspect. Treat this section as a data quality audit, not a research insight.

4. **Data Reuse & Access Patterns**:
   - Are datasets being reused across multiple publications (same identifier appearing under different pub_title)?
   - The "Access Mode" field is often empty. Where recorded, summarize open vs. controlled access patterns. Where missing, infer from repository name (e.g., dbGaP = controlled, GEO = open) and flag clearly that this is an inference.
   - Note any access_mode values that look garbled or out of place — those are likely extraction errors (flag them in section 3 as well).

5. **Comparative Analysis** (if comparative context provided above):
   - How does this selection differ from the full catalog?
   - What makes this subset unique in terms of data sources or research focus?

Use exact numbers and percentages. Always clarify scope: "this subset" or "the full catalog".`;
    }

    case "cross_table": {
      // Unlike the other types, the frontend sends one pre-built markdown
      // report (rows[0].report) instead of per-row structured data - the
      // wide table's shape is dynamic (depends on which tables the user
      // merged in), so there's no fixed per-row formatter to write here.
      // The report carries the query, a full-catalog baseline (every column
      // of every merged table, precomputed - see build-connections-stats.mjs),
      // and the same columns' value counts within the current subset - the
      // pairing is what makes a real contrastive claim possible without
      // needing abstract text (omitted here; may return in a future pass).
      const report = truncateFormatted(rows[0]?.report ?? "");
      return `Today's date is ${todayIso()}. Below is a merged cross-table view of the CARD Catalog, built from Publications joined with other tables via verified keys (PMC ID/DOI, Resource Name, or gene/bioentity matching): a full-catalog baseline for every column involved, followed by the same columns' value counts within the current (filtered/merged) subset.

${report}

As a domain expert, not a data auditor, provide:

1. **Key Patterns**: What do the value distributions actually mean scientifically? Name real cohorts, genes, biomarkers, or modalities and say what they represent in AD/ADRD research - not just that a value is frequent.
2. **Contrastive Read**: Compare the subset's distributions against the full-catalog baseline - is this subset over/under-representing a cohort, modality, or biomarker class relative to the whole catalog, and what would that mean scientifically?
3. **Notable Outliers**: Sparse or unusual values worth a second look - framed as scientifically interesting, not as suspected errors.
4. **Suggested Next Steps**: One or two concrete follow-up queries or filters a researcher would want to try next, based on what you found.

Be direct and specific - name real values, real counts, and real comparisons.`;
    }

    default:
      throw new Error(`Unknown analysis type: ${type}`);
  }
}

export default async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return new Response(
      JSON.stringify({ error: "ANTHROPIC_API_KEY is not configured in Netlify environment variables." }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }

  let body;
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON body" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const { type, rows, filteredCount, totalCount } = body;

  let prompt;
  try {
    prompt = buildPrompt(type, rows, filteredCount, totalCount);
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const anthropicResp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: MAX_TOKENS,
      stream: true,
      system: systemPromptFor(type),
      messages: [{ role: "user", content: prompt }],
    }),
  });

  if (!anthropicResp.ok) {
    const err = await anthropicResp.text();
    return new Response(JSON.stringify({ error: err }), {
      status: anthropicResp.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(anthropicResp.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
};
