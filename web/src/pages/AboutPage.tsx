import { Link } from "react-router-dom";
import { PageShell } from "../components/PageShell";

const SECTIONS = [
  {
    id: "user-stories",
    label: "User Stories",
    children: [
      { id: "story-1", label: "Story 1 — New Hire Onboarding" },
      { id: "story-2", label: "Story 2 — Biomedical Researcher" },
      { id: "story-3", label: "Story 3 — Program Officer" },
    ],
  },
  { id: "project-history", label: "Project History" },
  { id: "contact", label: "Contact and Updates" },
];

export function AboutPage() {
  return (
    <PageShell>
    <div className="space-y-12 text-slate-800">

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
        <nav className="mt-4 text-sm">
          <ul className="list-disc list-inside space-y-1">
            {SECTIONS.map(({ id, label, children }) => (
              <li key={id}>
                <a href={`#${id}`} className="text-accent hover:underline">
                  {label}
                </a>
                {children && (
                  <ul className="list-disc list-inside space-y-1 ml-5 mt-1">
                    {children.map((child) => (
                      <li key={child.id}>
                        <a href={`#${child.id}`} className="text-accent hover:underline">
                          {child.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </nav>
      </section>

      <hr className="border-slate-200" />

      {/* User Stories */}
      <section id="user-stories">
        <h2 className="text-xl font-semibold mb-5">User Stories</h2>
        <div className="space-y-8">

          <div id="story-1">
            <h3 className="font-semibold mb-2 text-slate-700">
              Story 1 — New Hire Onboarding: Getting Oriented on ROS
            </h3>
            <p className="text-xs text-slate-500 mb-3 italic">
              Jordan Reyes, first week at a new lab, keeps hearing "ROS" and wants to know
              what it actually is.
            </p>
            <ol className="text-sm space-y-2 list-decimal list-inside text-slate-700">
              <li>
                <strong>Publications:</strong> Filtering Resource Name = Religious Orders Study
                and freezing the results turns up 211 papers — 57% of which also tag Memory and
                Aging Project (MAP), with MAP as the top co-resource.
              </li>
              <li>
                <strong>Scientific Read:</strong> ROS and MAP turn out to be near-identical
                sister cohorts, routinely analyzed together as one unit — "ROSMAP" — not two
                separate resources.
              </li>
              <li>
                <strong>Connections:</strong> Joining SciLite gene annotations onto the 211 ROS
                papers shows 162/211 tag a gene or protein — led by tau (110) and APOE (98),
                then APP (50), TDP-43 (33), GFAP (30), and TREM2 (27).
              </li>
              <li>
                <strong>Outcome:</strong> ROS's gene/protein signal is the canonical AD
                molecular axis — tau and APOE lead, with APP, TDP-43, GFAP, and TREM2 close
                behind. It reads as post-mortem neuropathology evidence, not a living-cohort
                biomarker signal.
              </li>
            </ol>
          </div>

          <div id="story-2">
            <h3 className="font-semibold mb-2 text-slate-700">
              Story 2 — Biomedical Researcher: From Hypothesis to Publication
            </h3>
            <p className="text-xs text-slate-500 mb-3 italic">
              Dr. Sarah Chen is investigating the role of microglial dysfunction in early-stage
              Alzheimer's disease progression.
            </p>
            <ol className="text-sm space-y-2 list-decimal list-inside text-slate-700">
              <li>
                <strong>Connections:</strong> Joining SciLite gene annotations (TREM2) with
                Resources turns up 219 AD/Preclinical-linked papers dominated by
                postmortem-tissue and genomics infrastructure (AMP-AD, ROS/MAP, ADGC, ADSP) —
                BioFINDER-2, the catalog's 2nd-largest resource, doesn't even crack the top 15.
              </li>
              <li>
                <strong>Compare:</strong> Repeating the same join for APOE (1,254 papers) shows
                BioFINDER-2 IS the #1 resource there, at 9% of the subset — confirming TREM2's
                absence from biomarker cohorts is real, not just a rare-resource artifact.
              </li>
              <li>
                <strong>Code Repositories:</strong> Joining Software onto the same TREM2/AD
                papers reveals two papers (same tissue bank, overlapping author team) using an
                open-source spatial-proteomics pipeline (MIBI-TOF) to image TREM2 protein
                directly in postmortem microglia — a real, borrowable method, not just more
                sequencing.
              </li>
              <li>
                <strong>Outcome:</strong> TREM2 showed the gap; these two papers showed a way to
                close it. Her proposal isn't "build new infrastructure" — it's "borrow this
                pipeline, and point it two years earlier than anyone has."
              </li>
            </ol>
          </div>

          <div id="story-3">
            <h3 className="font-semibold mb-2 text-slate-700">
              Story 3 — Program Officer: Portfolio Analysis and Strategic Planning
            </h3>
            <p className="text-xs text-slate-500 mb-3 italic">
              Dr. Michael Torres manages ADRD research portfolio strategy at a funding agency,
              and a peer philanthropic funder just entered the space.
            </p>
            <ol className="text-sm space-y-2 list-decimal list-inside text-slate-700">
              <li>
                <strong>Connections:</strong> One query joining Grants (funder = Gates Ventures)
                with Resources — filtered to Alzheimer's Disease or Preclinical AD — turns up 25
                papers, all from 2025, with zero NIH-style grant numbers: a private philanthropic
                initiative, not a federal program.
              </li>
              <li>
                <strong>Contrast:</strong> The Preclinical AD tag appears 6x the catalog baseline
                (24% vs. 3.8%), while transcriptomics is below baseline (28% vs. 38%) despite
                elevated genetics and proteomics — a deliberate tilt toward fluid and digital
                biomarkers in presymptomatic populations, not the postmortem-tissue
                transcriptomics that dominates the field.
              </li>
              <li>
                <strong>Outcome:</strong> Gates is interested in presymptomatic screening while the
                field's own baseline still leans postmortem-tissue transcriptomics — the same
                blind spot Dr. Chen (Story 2) found independently from the science side. Peer to
                track, or sign we're behind? Our own portfolio — unchecked.
              </li>
            </ol>
          </div>
        </div>
      </section>

      <hr className="border-slate-200" />

      {/* Project History */}
      <section id="project-history">
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
      <section id="contact">
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
