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
                <strong>Connections:</strong> Joining SciLite gene annotations (TREM2) with Resources
                turns up 219 papers dominated by postmortem-tissue and genomics infrastructure —
                BioFINDER-2, the catalog's 2nd-largest resource, doesn't even crack the top 15.
              </li>
              <li>
                <strong>Compare:</strong> Repeating the same join for APOE shows BioFINDER-2 IS its
                #1 resource (9% of papers) — confirming TREM2's absence from biomarker cohorts is
                real, not just a rare-resource artifact.
              </li>
              <li>
                <strong>Code Repositories:</strong> Joining Software reveals two papers using an
                open-source spatial-proteomics pipeline (MIBI-TOF) to image TREM2 protein directly
                in postmortem microglia — a real, borrowable method, not just more sequencing.
              </li>
              <li>
                <strong>Resources:</strong> That method's tissue source is tagged Alzheimer's Disease
                vs. Cognitively Normal Controls — never Preclinical AD. The tool exists; nobody's
                pointed it at the presymptomatic window yet.
              </li>
              <li>
                <strong>Export:</strong> Her grant proposal isn't "build new infrastructure" anymore —
                it's "borrow this open-source pipeline, and point it two years earlier than anyone has."
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
                <strong>Connections:</strong> One query joining Grants (funder = Gates Ventures) with
                Resources turns up 25 papers, all from 2025, with zero NIH-style grant numbers — a
                private philanthropic bet, not a federal program.
              </li>
              <li>
                <strong>Contrast:</strong> The Preclinical AD tag appears 6x the catalog baseline
                (24% vs. 3.8%), while transcriptomics is below baseline (28% vs. 38%) despite
                elevated genetics and proteomics — a deliberate tilt toward scalable blood/digital
                biomarkers before symptoms start.
              </li>
              <li>
                <strong>Check the mirror:</strong> The agency's own portfolio mix looks like the
                transcriptomics-heavy catalog baseline Gates is tilting away from.
              </li>
              <li>
                <strong>Export:</strong> A portfolio-review line item, not a full pivot — is a
                smaller, newer funder out-executing us on where the field is going?
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
