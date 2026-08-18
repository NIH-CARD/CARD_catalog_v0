import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Header } from "../components/Header";
import {
  loadCellularModels,
  loadCodeRepos,
  loadPublications,
  loadResources,
} from "../lib/loaders";

interface Counts {
  resources: number | null;
  publications: number | null;
  code: number | null;
  cellLines: number | null;
}

function StatCard({ value, label, to }: { value: number | null; label: string; to: string }) {
  return (
    <Link
      to={to}
      className="block bg-white border border-slate-200 rounded p-5 hover:border-accent hover:shadow-sm transition"
    >
      <div className="text-3xl font-semibold text-accent tabular-nums">
        {value === null ? "—" : value.toLocaleString()}
      </div>
      <div className="text-sm text-slate-600 mt-1">{label}</div>
    </Link>
  );
}

export function HomePage() {
  const [counts, setCounts] = useState<Counts>({
    resources: null,
    publications: null,
    code: null,
    cellLines: null,
  });

  useEffect(() => {
    loadResources().then((r) =>
      setCounts((c) => ({ ...c, resources: r.length })),
    );
    loadPublications().then((p) => {
      const pmids = new Set(p.map((r) => r.PMID).filter(Boolean));
      setCounts((c) => ({ ...c, publications: pmids.size || p.length }));
    });
    loadCodeRepos().then((r) => {
      const repos = new Set(
        r.map((row) => row["Repository Link"]).filter(Boolean),
      );
      setCounts((c) => ({ ...c, code: repos.size || r.length }));
    });
    loadCellularModels().then((m) =>
      setCounts((c) => ({ ...c, cellLines: m.length })),
    );
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <Header query="" onQueryChange={() => undefined} />

      <main className="flex-1 max-w-5xl mx-auto px-6 py-8 w-full">
        {/* Supported By */}
        <h4 className="text-center text-sm font-semibold text-slate-600 uppercase tracking-wider mb-4">
          Supported By
        </h4>
        <div className="grid grid-cols-3 gap-6 items-center mb-8 px-4">
          <div className="flex justify-center">
            <img
              src="/logos/ADDI.png"
              alt="ADDI"
              className="object-contain w-auto h-auto max-w-[200px] max-h-24"
            />
          </div>
          <div className="flex justify-center">
            <img
              src="/logos/card_logo.png"
              alt="CARD"
              className="object-contain w-auto h-auto max-w-[340px] max-h-40"
            />
          </div>
          <div className="flex justify-center">
            <img
              src="/logos/stacked_DT.png"
              alt="DataTecnica"
              className="object-contain w-auto h-auto max-w-[200px] max-h-16"
            />
          </div>
        </div>

        <hr className="border-slate-200 mb-8" />

        {/* Title */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-semibold text-slate-900 mb-2">CARD Catalog</h1>
          <h3 className="text-lg text-slate-500 font-normal">
            Center for Alzheimer&apos;s and Related Dementias Data Catalog
          </h3>
        </div>

        <hr className="border-slate-200 mb-8" />

        {/* Introduction */}
        <section className="prose prose-slate max-w-none">
          <h2 className="text-2xl font-semibold text-slate-800 mb-2">
            Welcome to CARD Catalog
          </h2>
          <p className="text-slate-700">
            A comprehensive catalog of research resources with related publications,
            code repositories, and cellular models related to Alzheimer&apos;s Disease
            and Related Dementias (ADRD) research.
          </p>

          <h3 className="text-lg font-semibold text-slate-800 mt-6 mb-2">Features</h3>
          <ul className="space-y-1.5 text-slate-700 list-none pl-0">
            <li>
              <Link to="/resources" className="text-accent hover:underline">
                <strong>📊 Resources</strong>
              </Link>
              : Browse neuroscience research resources with knowledge graphs, coarse
              and granular data type filtering, and AI-powered analysis.
            </li>
            <li>
              <Link to="/publications" className="text-accent hover:underline">
                <strong>📚 Publications</strong>
              </Link>
              : Search scientific publications from PubMed Central with normalized
              author names and fixed PMC links.
            </li>
            <li>
              <Link to="/code" className="text-accent hover:underline">
                <strong>💻 Code</strong>
              </Link>
              : Discover GitHub repositories with AI-powered quality scoring
              (cleanliness, completeness, runnability) and FAIR compliance tracking.
            </li>
            <li>
              <Link to="/cellular-models" className="text-accent hover:underline">
                <strong>🧬 Human Cellular Models</strong>
              </Link>
              : Browse iNDI iPSC cell lines for neurodegenerative disease research
              with detailed genotype and procurement information.
            </li>
            <li>
              <Link to="/annotations" className="text-accent hover:underline">
                <strong>🗂️ Annotations</strong>
              </Link>
              : Per-publication datasets, supplementary files, and Europe PMC SciLite
              annotations.
            </li>
          </ul>

          <h3 className="text-lg font-semibold text-slate-800 mt-6 mb-2">What&apos;s New</h3>
          <ul className="space-y-1.5 text-slate-700 list-none pl-0">
            <li>
              ✨ <strong>GNPC Update</strong>: Global Neurodegeneration Proteomics
              Consortium with 35,000+ biofluid samples across 23 cohorts and 250+
              million protein measurements.
            </li>
            <li>
              📊 <strong>Table Views</strong>: Interactive data tables with sorting
              and search on all main pages.
            </li>
            <li>
              🔍 <strong>Coarse &amp; Granular Data Types</strong>: Filter by
              high-level categories or detailed modalities.
            </li>
            <li>
              💻 <strong>Alternative URLs &amp; New Corpus</strong>: External links
              related to main resources used to augment the catalog.
            </li>
          </ul>

          <h3 className="text-lg font-semibold text-slate-800 mt-6 mb-2">Getting Started</h3>
          <p className="text-slate-700">
            Use the navigation above to explore different sections. Each section
            includes filtering, keyword search, sortable tables, and shareable URLs.
          </p>
        </section>

        <hr className="border-slate-200 my-8" />

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard value={counts.resources} label="Resources" to="/resources" />
          <StatCard value={counts.publications} label="Publications" to="/publications" />
          <StatCard value={counts.code} label="Code Repositories" to="/code" />
          <StatCard value={counts.cellLines} label="Cell Lines" to="/cellular-models" />
        </div>

        <hr className="border-slate-200 my-8" />

        {/* Footer */}
        <footer className="text-center text-sm text-slate-500 space-y-3 pb-8">
          <p>
            CARD Catalog is part of the Center for Alzheimer&apos;s and Related
            Dementias (CARD) initiative to improve data sharing and collaboration
            in dementia research. Additional support from collaborators including
            the Alzheimer&apos;s Disease Data Initiative (ADDI), DataTecnica
            teammates, and the 2025 workshop participants.
          </p>
          <p>
            Data sourced from multiple repositories and regularly updated
            (quarterly scrapes). See the About page for details on data collection
            and processing.
          </p>
          <p>
            <strong>Contact:</strong>{" "}
            <a className="text-accent hover:underline" href="mailto:nallsm@nih.gov">
              Mike A. Nalls PhD — nallsm@nih.gov
            </a>{" "}
            |{" "}
            <a className="text-accent hover:underline" href="mailto:mike@datatecnica.com">
              mike@datatecnica.com
            </a>
            . Find us on GitHub at{" "}
            <a
              className="text-accent hover:underline"
              href="https://github.com/NIH-CARD"
              target="_blank"
              rel="noreferrer"
            >
              @NIH-CARD
            </a>
            .
          </p>
        </footer>
      </main>
    </div>
  );
}
