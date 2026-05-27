export function AboutPage() {
  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-12 text-slate-800">

      {/* Overview */}
      <section>
        <h1 className="text-2xl font-bold mb-3">About CARD Catalog</h1>
        <p className="text-sm leading-relaxed">
          The <strong>CARD Catalog</strong> (Center for Alzheimer's and Related Dementias Data
          Catalog) is a comprehensive resource for discovering datasets, publications, and code
          repositories related to Alzheimer's Disease and Related Dementias (ADRD) research. Our
          mission is to improve data sharing, reproducibility, and collaboration in dementia
          research by providing a centralized, searchable catalog of research resources with
          quality assessments and relationship mapping.
        </p>
      </section>

      <hr className="border-slate-200" />

      {/* User Stories */}
      <section>
        <h2 className="text-xl font-semibold mb-5">User Stories</h2>
        <div className="space-y-8">

          <div>
            <h3 className="font-semibold mb-2 text-slate-700">
              Story 1 — Biomedical Researcher: From Hypothesis to Publication
            </h3>
            <p className="text-xs text-slate-500 mb-3 italic">
              Dr. Sarah Chen is investigating the role of microglial dysfunction in early-stage
              Alzheimer's disease progression.
            </p>
            <ol className="text-sm space-y-2 list-decimal list-inside text-slate-700">
              <li>
                <strong>Datasets:</strong> Search for single-cell RNA-seq + neuroimaging datasets.
                The knowledge graph surfaces connected datasets (ROSMAP, AMP-AD, spatial
                transcriptomics) she hadn't considered.
              </li>
              <li>
                <strong>Code Repositories:</strong> Filter for single-cell analysis tools. FAIR
                compliance scores help her choose a well-maintained microglial subtype
                classification pipeline.
              </li>
              <li>
                <strong>Publications:</strong> The knowledge graph connects 12 publications linking
                microglial subtypes to Aβ plaque proximity. AI gap analysis confirms early-stage
                dysfunction is understudied.
              </li>
              <li>
                <strong>Cellular Models:</strong> Filter iNDI lines for APP/PSEN1 mutations and
                locate procurement links for validation experiments.
              </li>
              <li>
                <strong>Export:</strong> Download filtered datasets, code, and publication lists for
                her grant proposal and methods section.
              </li>
            </ol>
          </div>

          <div>
            <h3 className="font-semibold mb-2 text-slate-700">
              Story 2 — Program Officer: Portfolio Analysis and Strategic Planning
            </h3>
            <p className="text-xs text-slate-500 mb-3 italic">
              Dr. Michael Torres manages ADRD research portfolio strategy at a funding agency.
            </p>
            <ol className="text-sm space-y-2 list-decimal list-inside text-slate-700">
              <li>
                <strong>Portfolio gaps:</strong> Filter datasets by funding agency; the knowledge
                graph reveals strong genomics/proteomics coverage but limited metabolomics and
                longitudinal imaging.
              </li>
              <li>
                <strong>FAIR monitoring:</strong> Code page shows 40 % of funded repos lack
                dependency specifications — evidence for new reproducibility requirements in funding
                calls.
              </li>
              <li>
                <strong>Emerging themes:</strong> Publication knowledge graph highlights
                inflammasome activation, microbiome–gut–brain axis, and vascular contributions as
                fast-growing areas with limited dataset coverage.
              </li>
              <li>
                <strong>Cell model gaps:</strong> iNDI inventory shows TREM2/APOE variants are
                under-represented despite growing publication interest — informs resource planning.
              </li>
              <li>
                <strong>Export:</strong> Dataset gap analysis, FAIR compliance summary, and emerging
                themes exported for agency leadership review.
              </li>
            </ol>
          </div>
        </div>
      </section>

      <hr className="border-slate-200" />

      {/* Data Sources */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Data Sources</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            {
              title: "Resources",
              body: "Curated inventory of neuroscience resources — studies, data catalogs, biorepositories. Covers data modalities, diseases, sample sizes, and access information. Updated quarterly.",
            },
            {
              title: "Publications (PubMed Central)",
              body: "Scientific articles automatically scraped from PMC, linked to resources by name and metadata. Enriched with SciLite bioentity annotations (diseases, genes, chemicals) and cited dataset identifiers. Updated monthly.",
            },
            {
              title: "Code Repositories (GitHub)",
              body: "Research code and analysis pipelines scraped via GitHub API. LLM-analyzed for content summary, biomedical relevance, data types, and tooling. FAIR compliance scored from automated checks.",
            },
            {
              title: "Human Cellular Models (iNDI)",
              body: "626 iPSC cell lines from the iPSC Neurodegenerative Disease Initiative. Covers gene variants, conditions, parental lines, genome assemblies, and procurement links.",
            },
          ].map(({ title, body }) => (
            <div key={title} className="border border-slate-200 rounded p-4">
              <h3 className="font-semibold text-sm mb-1">{title}</h3>
              <p className="text-xs text-slate-600 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <hr className="border-slate-200" />

      {/* FAIR Compliance */}
      <section>
        <h2 className="text-xl font-semibold mb-3">FAIR Compliance</h2>
        <p className="text-sm mb-4">
          FAIR (Findable, Accessible, Interoperable, Reusable) compliance is assessed
          automatically for code repositories during each scrape.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div>
            <h3 className="text-sm font-semibold mb-2">Checks performed</h3>
            <ul className="text-sm space-y-1 text-slate-700 list-disc list-inside">
              <li>README presence</li>
              <li>LICENSE file</li>
              <li>Dependency specification</li>
              <li>Container / environment spec</li>
              <li>Usage examples or tests</li>
              <li>Version information</li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2">Score calculation</h3>
            <p className="text-sm text-slate-700">
              Score = <strong>10 − number of issues found</strong>. Repositories with no
              identified issues receive a perfect 10. Scores are baked into the code repos table
              by the pipeline normalizer and visible in the Code Repositories page.
            </p>
          </div>
        </div>
      </section>

      <hr className="border-slate-200" />

      {/* AI-Generated Content */}
      <section>
        <h2 className="text-xl font-semibold mb-3">AI-Generated Content</h2>
        <p className="text-sm mb-4 text-slate-700">
          Several fields in the Code Repositories table are generated by Claude (Anthropic) during
          the pipeline's repo analysis stage:
        </p>
        <ul className="text-sm space-y-2 text-slate-700 list-disc list-inside">
          <li><strong>Code Summary</strong> — description of repository purpose and functionality</li>
          <li><strong>Biomedical Relevance</strong> — YES / NO / UNCLEAR classification</li>
          <li><strong>Data Types</strong> — types of data the code operates on (MRI, genomics, clinical…)</li>
          <li><strong>Tooling</strong> — frameworks and libraries identified (TensorFlow, FSL, scikit-learn…)</li>
        </ul>
        <p className="text-xs text-slate-500 mt-4">
          All AI-generated content should be verified against original sources. Scores and
          assessments assist discovery and do not replace human judgment.
        </p>
      </section>

      <hr className="border-slate-200" />

      {/* Methodology */}
      <section>
        <h2 className="text-xl font-semibold mb-4">Methodology</h2>
        <div className="space-y-5">
          <div>
            <h3 className="text-sm font-semibold mb-2">Pipeline stages</h3>
            <ol className="text-sm space-y-1 list-decimal list-inside text-slate-700">
              <li><strong>pubmed_search</strong> — PubMed Central API queries keyed on resource inventory</li>
              <li><strong>pub_metadata</strong> — supplementary file and dataset metadata extraction</li>
              <li><strong>github_search</strong> — GitHub API search with biomedical keywords</li>
              <li><strong>repo_analysis</strong> — LLM batch analysis of repository content</li>
              <li><strong>page_navigation</strong> — headless browser discovery of new resources</li>
              <li><strong>scilite</strong> — Europe PMC SciLite bioentity annotation scrape</li>
            </ol>
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2">Normalization and annotation join</h3>
            <p className="text-sm text-slate-700">
              Each stage output is validated against Pydantic schemas and written to{" "}
              <code className="text-xs bg-slate-100 px-1 rounded">tables/final/</code> by the
              normalizer. A final <strong>annotation join</strong> step (
              <code className="text-xs bg-slate-100 px-1 rounded">staging/join_annotations.py</code>)
              joins SciLite bioentity annotations and cited dataset identifiers into the publications
              table, producing the <em>Diseases (Annotated)</em>, <em>Genes / Proteins</em>,{" "}
              <em>Chemicals</em>, and <em>Cited Datasets</em> columns.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold mb-2">Normalization rules</h3>
            <ul className="text-sm space-y-1 list-disc list-inside text-slate-700">
              <li>Author names standardized across spelling variants</li>
              <li>PMC links deduplicated (PMCPMC → PMC)</li>
              <li>Multi-value fields semicolon-delimited and deduplicated</li>
              <li>Rejected rows written to <code className="text-xs bg-slate-100 px-1 rounded">tables/hits/rejected_*.tsv</code> with validation errors</li>
            </ul>
          </div>
        </div>
      </section>

      <hr className="border-slate-200" />

      {/* Contact */}
      <section>
        <h2 className="text-xl font-semibold mb-3">Contact and Updates</h2>
        <p className="text-sm text-slate-700 mb-4">
          <strong>Mike A. Nalls PhD</strong> —{" "}
          <a href="mailto:nallsm@nih.gov" className="text-accent hover:underline">nallsm@nih.gov</a>{" "}
          |{" "}
          <a href="mailto:mike@datatecnica.com" className="text-accent hover:underline">mike@datatecnica.com</a>
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            ["Resource inventory", "Quarterly"],
            ["Publications", "Monthly"],
            ["Code repositories", "Monthly"],
            ["FAIR compliance", "Each code scrape"],
          ].map(([label, cadence]) => (
            <div key={label} className="border border-slate-200 rounded p-3 text-center">
              <div className="text-xs text-slate-500">{label}</div>
              <div className="text-sm font-semibold mt-1">{cadence}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="text-xs text-center text-slate-400 pt-4 pb-8">
        CARD Catalog · Developed by DataTecnica for NIH CARD and NIA LNG
      </div>
    </div>
  );
}
