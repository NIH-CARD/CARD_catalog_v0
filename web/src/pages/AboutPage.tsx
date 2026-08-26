import { Link } from "react-router-dom";
import { PageShell } from "../components/PageShell";

export function AboutPage() {
  return (
    <PageShell>
    <div className="max-w-3xl mx-auto space-y-12 text-slate-800">

      {/* Overview */}
      <section>
        <h1 className="text-2xl font-bold mb-3">About CARD Catalog</h1>
        <p className="text-sm leading-relaxed">
          The <strong>CARD Catalog</strong> (Center for Alzheimer's and Related Dementias
          Catalog) is a collection of research artifacts — resources, publications (enriched
          with extracted cited datasets, supplementary materials, and disease/gene annotations)
          , code repositories, and cellular models — from different studies, biorepositories,
          and data catalogs into interlinked tables, capturing how they relate to one another
          across Alzheimer's Disease and Related Dementias (ADRD) research. Its goal is to
          improve data sharing, reproducibility, traceability, and collaboration in dementia
          research through a centralized, searchable catalog with cross-table relationship mapping.
        </p>
        <p className="text-sm mt-3 text-slate-600">
          Looking for table schemas, FAIR scoring rules, or pipeline methodology instead? See{" "}
          <Link to="/docs" className="text-accent hover:underline">Docs</Link>.
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

      {/* Project History */}
      <section>
        <h2 className="text-xl font-semibold mb-3">Project History</h2>
        <p className="text-sm text-slate-700">
          CARD Catalog began as a <strong>Streamlit</strong> app (v0), which validated the
          pipeline and data model described above. This React application is its actively
          developed successor and the live, deployed version of the Catalog. The original
          Streamlit app remains available for reference at{" "}
          <a
            href="https://card-catalog-v0.streamlit.app"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            card-catalog-v0.streamlit.app
          </a>
          .
        </p>
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
    </PageShell>
  );
}
