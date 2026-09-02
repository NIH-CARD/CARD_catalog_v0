import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Header } from "../components/Header";
import {
  loadAnnotationSummary,
  loadCellularModels,
  loadCodeRepos,
  loadPublications,
  loadResources,
} from "../lib/loaders";
import type { AnnotationSummary } from "../types";

interface Counts {
  resources: number | null;
  publications: number | null;
  code: number | null;
  cellLines: number | null;
}

interface Feature {
  to: string;
  icon: string;
  label: string;
  caption: string;
  count?: number | null;
}

function MenuRow({ to, icon, label, caption, count }: Feature) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-5 px-6 py-5 hover:bg-slate-50 transition"
    >
      <span className="text-2xl shrink-0" aria-hidden>{icon}</span>
      <span className="flex-1 min-w-0">
        <span className="block text-lg font-semibold text-slate-800 group-hover:text-accent">
          {label}
        </span>
        <span className="block text-base text-slate-500 leading-snug">{caption}</span>
      </span>
      {count !== undefined && (
        <span className="text-2xl font-semibold text-accent tabular-nums shrink-0">
          {count === null ? "—" : count.toLocaleString()}
        </span>
      )}
      <span className="text-slate-300 group-hover:text-accent group-hover:translate-x-1 transition-transform text-xl shrink-0">
        →
      </span>
    </Link>
  );
}

const STAGE_ROUTES: Record<string, string> = {
  Datasets: "/annotations",
  "Supplementary Files": "/annotations/supplementary",
  Grants: "/annotations/grants",
  Software: "/annotations/software",
  Models: "/annotations/models",
};

function AnnotationsRow({ summary }: { summary: AnnotationSummary | null }) {
  return (
    <div className="px-6 py-5">
      <Link to="/annotations" className="group flex items-center gap-5">
        <span className="text-2xl shrink-0" aria-hidden>🗂️</span>
        <span className="flex-1 min-w-0">
          <span className="block text-lg font-semibold text-slate-800 group-hover:text-accent">
            Annotations
          </span>
          <span className="block text-base text-slate-500 leading-snug">
            Per-publication datasets, supplementary files, grants, software, models, and
            SciLite bioentity annotations.
          </span>
        </span>
        <span className="text-slate-300 group-hover:text-accent group-hover:translate-x-1 transition-transform text-xl shrink-0">
          →
        </span>
      </Link>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mt-4 pl-11">
        <div>
          <div className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">
            By pipeline stage
          </div>
          <ul className="space-y-1.5">
            {Object.entries(summary?.stages ?? {}).map(([stage, count]) => (
              <li key={stage} className="flex items-baseline justify-between text-base">
                <Link to={STAGE_ROUTES[stage] ?? "/annotations"} className="text-slate-700 hover:text-accent">
                  {stage}
                </Link>
                <span className="tabular-nums text-slate-500">{count.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">
            SciLite annotations — top 5 types
          </div>
          <ul className="space-y-1.5">
            {(summary?.scilite_top_types ?? []).map(({ type, count }) => (
              <li key={type} className="flex items-baseline justify-between text-base">
                <Link
                  to={`/annotations/scilite?Type=${encodeURIComponent(type)}`}
                  className="text-slate-700 hover:text-accent"
                >
                  {type}
                </Link>
                <span className="tabular-nums text-slate-500">{count.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export function HomePage() {
  const [counts, setCounts] = useState<Counts>({
    resources: null,
    publications: null,
    code: null,
    cellLines: null,
  });
  const [annotationSummary, setAnnotationSummary] = useState<AnnotationSummary | null>(null);

  useEffect(() => {
    loadResources().then((r) =>
      setCounts((c) => ({ ...c, resources: r.length })),
    );
    loadPublications().then((p) =>
      setCounts((c) => ({ ...c, publications: p.length })),
    );
    loadCodeRepos().then((r) =>
      setCounts((c) => ({ ...c, code: r.length })),
    );
    loadCellularModels().then((m) =>
      setCounts((c) => ({ ...c, cellLines: m.length })),
    );
    loadAnnotationSummary().then(setAnnotationSummary).catch(() => setAnnotationSummary(null));
  }, []);

  const features: Feature[] = [
    {
      to: "/resources",
      icon: "📊",
      label: "Resources",
      caption: "Research resources with knowledge graphs, modality filtering, and AI-powered analysis.",
      count: counts.resources,
    },
    {
      to: "/publications",
      icon: "📚",
      label: "Publications",
      caption: "Scientific publications from PubMed Central, normalized and linked.",
      count: counts.publications,
    },
    {
      to: "/code",
      icon: "💻",
      label: "Code",
      caption: "GitHub repositories with AI-powered quality scoring and FAIR compliance tracking.",
      count: counts.code,
    },
    {
      to: "/cellular-models",
      icon: "🧬",
      label: "Cellular Models",
      caption: "iNDI iPSC cell lines with genotype and procurement details.",
      count: counts.cellLines,
    },
    {
      to: "/connections",
      icon: "🔗",
      label: "Connections",
      caption: "Traverse verified column-level joins to build cross-table graphs — from any table to any other.",
    },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 px-6 py-8 w-full max-w-full">
        {/* Supported By */}
        <h4 className="text-center text-sm font-semibold text-slate-600 uppercase tracking-wider mb-4">
          Supported By
        </h4>
        <div className="grid grid-cols-3 gap-6 items-center mb-8 max-w-3xl mx-auto px-4">
          <div className="flex justify-center min-w-0">
            <img
              src="/logos/ADDI.png"
              alt="ADDI"
              className="object-contain w-full h-auto max-h-24"
            />
          </div>
          <div className="flex justify-center min-w-0">
            <img
              src="/logos/card_logo.png"
              alt="CARD"
              className="object-contain w-full h-auto max-h-40"
            />
          </div>
          <div className="flex justify-center min-w-0">
            <img
              src="/logos/stacked_DT.png"
              alt="DataTecnica"
              className="object-contain w-full h-auto max-h-16"
            />
          </div>
        </div>

        <hr className="border-slate-200 mb-8" />

        {/* Title */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-semibold text-slate-900 mb-2">CARD Catalog</h1>
          <h3 className="text-lg text-slate-500 font-normal">
            Center for Alzheimer&apos;s and Related Dementias Catalog
          </h3>
        </div>

        <hr className="border-slate-200 mb-8" />

        {/* Introduction */}
        <p className="text-slate-700 max-w-3xl mx-auto text-center mb-10">
          A comprehensive catalog of research resources with related publications,
          code repositories, and cellular models for Alzheimer&apos;s Disease and
          Related Dementias (ADRD) research.
        </p>

        {/* Navigation menu: one row per section, counts folded in */}
        <div className="max-w-3xl mx-auto border border-slate-200 rounded-lg divide-y divide-slate-200 bg-white mb-4">
          {features.map((f) => (
            <MenuRow key={f.to} {...f} />
          ))}
          <AnnotationsRow summary={annotationSummary} />
        </div>

        <p className="text-sm text-slate-500 text-center mb-8">
          Use the navigation above to explore each section — filtering, keyword
          search, sortable tables, and shareable URLs throughout.
        </p>

        <hr className="border-slate-200 my-8" />

        {/* Footer */}
        <footer className="text-center text-sm text-slate-500 space-y-3 pb-8 max-w-3xl mx-auto">
          <p>
            CARD Catalog is part of the Center for Alzheimer&apos;s and Related
            Dementias (CARD) initiative to improve data sharing and collaboration
            in dementia research. Additional support from collaborators including
            the Alzheimer&apos;s Disease Data Initiative (ADDI), DataTecnica
            teammates, and the 2025 workshop participants.
          </p>
          <p>
            Data sourced from multiple repositories and regularly updated
            (quarterly scrapes). See{" "}
            <Link to="/docs" className="text-accent hover:underline">Docs</Link>{" "}
            for details on data collection and processing.
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
