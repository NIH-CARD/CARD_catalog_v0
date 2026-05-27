import { useEffect, useMemo, useState } from "react";
import {
  Navigate,
  NavLink,
  Route,
  Routes,
  useSearchParams,
} from "react-router-dom";
import { createColumnHelper } from "@tanstack/react-table";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { Chips } from "../components/Chips";
import { DataTable } from "../components/DataTable";
import { ExportButton } from "../components/ExportButton";
import { FilterRail } from "../components/FilterRail";
import { PageShell } from "../components/PageShell";
import { matchesFacet, matchesQuery } from "../lib/filter";
import {
  loadPubDatasets,
  loadSciLite,
  loadSupplementary,
} from "../lib/loaders";
import { pmcidFrom } from "../lib/loadPublications";
import { useFacets } from "../lib/useFacets";
import type {
  FacetSpec,
  PubDataset,
  SciLiteAnnotation,
  Supplementary,
} from "../types";

function PmcBanner() {
  const [sp, setSp] = useSearchParams();
  const pmc = sp.get("pmc");
  if (!pmc) return null;
  return (
    <div className="flex items-center justify-between bg-amber-50 border border-amber-200 text-amber-900 text-sm px-3 py-2 rounded mb-3">
      <span>
        Filtered to publication <strong>{pmc}</strong> (from Publications)
      </span>
      <button
        className="text-xs text-amber-900 underline hover:text-amber-700"
        onClick={() => {
          const next = new URLSearchParams(sp);
          next.delete("pmc");
          setSp(next, { replace: true });
        }}
      >
        Clear
      </button>
    </div>
  );
}

function SubNav() {
  const itemCls = ({ isActive }: { isActive: boolean }) =>
    "px-3 py-1.5 text-sm border-b-2 " +
    (isActive
      ? "border-accent text-accent font-medium"
      : "border-transparent text-slate-600 hover:text-slate-900");
  return (
    <nav className="flex gap-2 border-b border-slate-200 mb-4">
      <NavLink to="/datasets" end className={itemCls}>
        📦 Datasets
      </NavLink>
      <NavLink to="/datasets/supplementary" className={itemCls}>
        📎 Supplementary
      </NavLink>
      <NavLink to="/datasets/scilite" className={itemCls}>
        🏷️ SciLite Annotations
      </NavLink>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Datasets sub-page
// ---------------------------------------------------------------------------

const DS_FACETS: readonly FacetSpec<PubDataset>[] = [
  { field: "data_repository", label: "Data Repository", multivalue: false },
  { field: "citation_type", label: "Citation Type", multivalue: false },
  { field: "dataset_keywords", label: "Keywords", multivalue: true, delimiter: "," },
];
const DS_SEARCH: (keyof PubDataset & string)[] = [
  "dataset_identifier",
  "dataset_context_from_paper",
  "dataset_keywords",
  "pub_title",
];

const dsCol = createColumnHelper<PubDataset>();

function DatasetsTab() {
  const [rows, setRows] = useState<PubDataset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sp] = useSearchParams();
  const pmcFilter = sp.get("pmc");

  useEffect(() => {
    loadPubDatasets().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => DS_FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof PubDataset & string)[]);

  const scoped = useMemo(() => {
    if (!rows) return [];
    if (!pmcFilter) return rows;
    return rows.filter((r) => pmcidFrom(r.source_url) === pmcFilter);
  }, [rows, pmcFilter]);

  const filtered = useMemo(() => {
    return scoped.filter((r) => {
      for (const spec of DS_FACETS) {
        if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(r, DS_SEARCH, query);
    });
  }, [scoped, selections, query]);

  const columns = useMemo(
    () => [
      dsCol.accessor("dataset_identifier", {
        header: "Identifier",
        size: 150,
        cell: (info) => {
          const webpage = info.row.original.dataset_webpage;
          const id = info.getValue();
          return webpage ? (
            <a
              href={webpage}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline font-mono text-xs break-all"
            >
              {id}
            </a>
          ) : (
            <span className="font-mono text-xs break-all">{id}</span>
          );
        },
      }),
      dsCol.accessor("data_repository", {
        header: "Repository",
        size: 120,
        cell: (info) => (
          <span className="text-xs text-slate-700">{info.getValue()}</span>
        ),
      }),
      dsCol.accessor("citation_type", {
        header: "Citation",
        size: 90,
        cell: (info) => (
          <span className="text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      dsCol.accessor("dataset_keywords", {
        header: "Keywords",
        size: 180,
        cell: (info) => <Chips value={info.getValue()} delimiter="," />,
      }),
      dsCol.accessor("dataset_context_from_paper", {
        header: "Context",
        size: 560,
        cell: (info) => {
          const text = info.getValue();
          if (!text) return null;
          return (
            <p
              className="text-xs text-slate-700 line-clamp-6"
              title={text}
            >
              {text}
            </p>
          );
        },
      }),
      dsCol.accessor("pub_title", {
        header: "Publication",
        cell: (info) => {
          const url = info.row.original.source_url;
          const title = info.getValue();
          if (!title && !url) return null;
          return url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline line-clamp-2 max-w-md"
              title={title}
            >
              {title || url}
            </a>
          ) : (
            <span className="text-xs text-slate-600 line-clamp-2 max-w-md">
              {title}
            </span>
          );
        },
      }),
    ],
    [],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Datasets & Supplementary Files"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${scoped.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<PubDataset>
          specs={DS_FACETS}
          rows={scoped}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) =>
            setFacet(field as (typeof DS_FACETS)[number]["field"], next)
          }
          totalSelected={totalSelected}
          onClearAll={clearAll}
          error={error}
        />
      }
    >
      <SubNav />
      <PmcBanner />
      {rows ? (
        <>
          <AnalysisPanel<PubDataset>
            type="pub_datasets"
            filtered={filtered}
            total={scoped.length}
            prepare={(rs) => rs.map((r) => ({
              identifier: r.dataset_identifier,
              webpage: r.dataset_webpage,
              repository: r.data_repository,
              citationType: r.citation_type,
              accessMode: r.access_mode,
              keywords: r.dataset_keywords,
              pubTitle: r.pub_title,
              context: r.dataset_context_from_paper,
            }))}
          />
          <div className="mb-3 flex justify-end">
            <ExportButton rows={filtered} filename="pub_datasets" />
          </div>
          <DataTable<PubDataset> rows={filtered} columns={columns} />
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading datasets…</div>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Supplementary sub-page
// ---------------------------------------------------------------------------

const SP_FACETS: readonly FacetSpec<Supplementary>[] = [
  { field: "file_extension", label: "Extension", multivalue: false },
  { field: "content_type", label: "Content Type", multivalue: false },
  { field: "source_section", label: "Source Section", multivalue: false },
];
const SP_SEARCH: (keyof Supplementary & string)[] = [
  "title",
  "caption",
  "description",
  "link",
];
const spCol = createColumnHelper<Supplementary>();

function SupplementaryTab() {
  const [rows, setRows] = useState<Supplementary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sp] = useSearchParams();
  const pmcFilter = sp.get("pmc");

  useEffect(() => {
    loadSupplementary().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => SP_FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof Supplementary & string)[]);

  const scoped = useMemo(() => {
    if (!rows) return [];
    if (!pmcFilter) return rows;
    return rows.filter((r) => pmcidFrom(r.source_url) === pmcFilter);
  }, [rows, pmcFilter]);

  const filtered = useMemo(() => {
    return scoped.filter((r) => {
      for (const spec of SP_FACETS) {
        if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(r, SP_SEARCH, query);
    });
  }, [scoped, selections, query]);

  const columns = useMemo(
    () => [
      spCol.accessor("link", {
        header: "File",
        size: 300,
        cell: (info) => {
          const url = info.row.original.download_link;
          const name = info.getValue();
          return url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline font-mono text-xs break-all"
            >
              {name}
            </a>
          ) : (
            <span className="font-mono text-xs break-all">{name}</span>
          );
        },
      }),
      spCol.accessor("file_extension", {
        header: "Ext",
        size: 60,
        cell: (info) => (
          <span className="text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      spCol.accessor("caption", {
        header: "Caption",
        size: 120,
        cell: (info) => (
          <span
            className="text-xs text-slate-600 line-clamp-3"
            title={info.getValue()}
          >
            {info.getValue()}
          </span>
        ),
      }),
      spCol.accessor("context_description", {
        header: "Context",
        size: 560,
        cell: (info) => {
          const text = info.getValue();
          if (!text) return null;
          return (
            <p
              className="text-xs text-slate-700 line-clamp-6"
              title={text}
            >
              {text}
            </p>
          );
        },
      }),
      spCol.accessor("pub_title", {
        header: "Publication",
        cell: (info) => {
          const url = info.row.original.source_url;
          const title = info.getValue();
          if (!title && !url) return null;
          return url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline line-clamp-2 max-w-md"
              title={title}
            >
              {title || url}
            </a>
          ) : (
            <span className="text-xs text-slate-600 line-clamp-2 max-w-md">
              {title}
            </span>
          );
        },
      }),
    ],
    [],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Datasets & Supplementary Files"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${scoped.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<Supplementary>
          specs={SP_FACETS}
          rows={scoped}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) =>
            setFacet(field as (typeof SP_FACETS)[number]["field"], next)
          }
          totalSelected={totalSelected}
          onClearAll={clearAll}
          error={error}
        />
      }
    >
      <SubNav />
      <PmcBanner />
      {rows ? (
        <>
          <div className="mb-3 flex justify-end">
            <ExportButton rows={filtered} filename="supplementary" />
          </div>
          <DataTable<Supplementary> rows={filtered} columns={columns} />
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading supplementary files…</div>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// SciLite annotations sub-page
// ---------------------------------------------------------------------------

const SC_FACETS: readonly FacetSpec<SciLiteAnnotation>[] = [
  { field: "Type", label: "Annotation Type", multivalue: false },
  { field: "Section", multivalue: false },
  { field: "Tag Name", label: "Tag (concept)", multivalue: false },
];
const SC_SEARCH: (keyof SciLiteAnnotation & string)[] = [
  "Exact",
  "Prefix",
  "Postfix",
  "Tag Name",
];
const scCol = createColumnHelper<SciLiteAnnotation>();

function SciLiteStats({ rows }: { rows: SciLiteAnnotation[] }) {
  const typeCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) {
      if (r.Type) m.set(r.Type, (m.get(r.Type) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);

  const topTags = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) {
      if (r["Tag Name"]) m.set(r["Tag Name"], (m.get(r["Tag Name"]) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15);
  }, [rows]);

  const topPmc = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) {
      if (r["PMC ID"]) m.set(r["PMC ID"], (m.get(r["PMC ID"]) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  }, [rows]);

  const maxType = typeCounts[0]?.[1] ?? 1;
  const maxTag = topTags[0]?.[1] ?? 1;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pb-4">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-3">Type Distribution</h3>
        <div className="flex flex-col gap-2">
          {typeCounts.map(([type, count]) => (
            <div key={type} className="flex items-center gap-2">
              <span className="text-xs text-slate-700 w-32 truncate shrink-0" title={type}>{type}</span>
              <div className="flex-1 bg-slate-100 rounded h-4 overflow-hidden">
                <div
                  className="bg-accent h-full rounded"
                  style={{ width: `${(count / maxType) * 100}%` }}
                />
              </div>
              <span className="text-xs text-slate-500 w-10 text-right shrink-0">{count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-3">Top Tags</h3>
        <div className="flex flex-col gap-2">
          {topTags.map(([tag, count]) => (
            <div key={tag} className="flex items-center gap-2">
              <span className="text-xs text-slate-700 w-36 truncate shrink-0" title={tag}>{tag}</span>
              <div className="flex-1 bg-slate-100 rounded h-4 overflow-hidden">
                <div
                  className="bg-violet-400 h-full rounded"
                  style={{ width: `${(count / maxTag) * 100}%` }}
                />
              </div>
              <span className="text-xs text-slate-500 w-10 text-right shrink-0">{count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-3">Top PMCs by Annotation Count</h3>
        <div className="flex flex-col gap-1.5">
          {topPmc.map(([pmc, count]) => (
            <div key={pmc} className="flex items-center justify-between text-xs">
              <span className="font-mono text-accent">{pmc}</span>
              <span className="text-slate-500">{count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SciliteTab() {
  const [rows, setRows] = useState<SciLiteAnnotation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "stats">("table");
  const [sp] = useSearchParams();
  const pmcFilter = sp.get("pmc");

  useEffect(() => {
    loadSciLite().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => SC_FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof SciLiteAnnotation & string)[]);

  const scoped = useMemo(() => {
    if (!rows) return [];
    if (!pmcFilter) return rows;
    return rows.filter((r) => r["PMC ID"] === pmcFilter);
  }, [rows, pmcFilter]);

  const filtered = useMemo(() => {
    return scoped.filter((r) => {
      for (const spec of SC_FACETS) {
        if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(r, SC_SEARCH, query);
    });
  }, [scoped, selections, query]);

  const columns = useMemo(
    () => [
      scCol.accessor("PMC ID", {
        header: "PMC",
        cell: (info) => (
          <span className="font-mono text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      scCol.accessor("Type", { header: "Type" }),
      scCol.accessor("Exact", {
        header: "Exact",
        cell: (info) => (
          <span className="text-xs text-slate-700">{info.getValue()}</span>
        ),
      }),
      scCol.accessor("Tag Name", {
        header: "Tag",
        cell: (info) => {
          const uri = info.row.original["Tag URI"];
          const name = info.getValue();
          return uri ? (
            <a
              href={uri}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline text-xs"
            >
              {name}
            </a>
          ) : (
            <span className="text-xs">{name}</span>
          );
        },
      }),
      scCol.accessor("Section", {
        header: "Section",
        cell: (info) => <span className="text-xs text-slate-600">{info.getValue()}</span>,
      }),
    ],
    [],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Datasets & Supplementary Files"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${scoped.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<SciLiteAnnotation>
          specs={SC_FACETS}
          rows={scoped}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) =>
            setFacet(field as (typeof SC_FACETS)[number]["field"], next)
          }
          totalSelected={totalSelected}
          onClearAll={clearAll}
          error={error}
        />
      }
    >
      <SubNav />
      <PmcBanner />
      {rows ? (
        <>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="inline-flex rounded border border-slate-200 overflow-hidden text-sm">
              {(["table", "stats"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={
                    "px-3 py-1.5 " +
                    (view === v ? "bg-accent text-white" : "bg-white text-slate-700 hover:bg-slate-100")
                  }
                >
                  {v === "table" ? "📊 Table" : "📈 Stats"}
                </button>
              ))}
            </div>
            <ExportButton rows={filtered} filename="scilite_annotations" />
          </div>
          {view === "table" ? (
            <DataTable<SciLiteAnnotation> rows={filtered} columns={columns} />
          ) : (
            <SciLiteStats rows={filtered} />
          )}
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading SciLite annotations…</div>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Datasets section router
// ---------------------------------------------------------------------------

export function DatasetsPage() {
  return (
    <Routes>
      <Route index element={<DatasetsTab />} />
      <Route path="supplementary" element={<SupplementaryTab />} />
      <Route path="scilite" element={<SciliteTab />} />
      <Route path="*" element={<Navigate to="" replace />} />
    </Routes>
  );
}
