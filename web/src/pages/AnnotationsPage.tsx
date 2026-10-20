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
  loadPubGrants,
  loadPubModels,
  loadPubSoftware,
  loadPubTatorEntities,
  loadPubTatorRelations,
  loadSciLite,
  loadSupplementary,
} from "../lib/loaders";
import { pmcidFrom } from "../lib/loadPublications";
import { useFacets } from "../lib/useFacets";
import type {
  FacetSpec,
  PubDataset,
  PubGrant,
  PubModel,
  PubSoftware,
  PubTatorEntity,
  PubTatorRelation,
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
      <NavLink to="/annotations" end className={itemCls}>
        📦 Cited Datasets
      </NavLink>
      <NavLink to="/annotations/supplementary" className={itemCls}>
        📎 Supplementary
      </NavLink>
      <NavLink to="/annotations/grants" className={itemCls}>
        💰 Grants
      </NavLink>
      <NavLink to="/annotations/software" className={itemCls}>
        🧩 Software Mentions
      </NavLink>
      <NavLink to="/annotations/models" className={itemCls}>
        🤗 Models
      </NavLink>
      <NavLink to="/annotations/scilite" className={itemCls}>
        🏷️ SciLite Annotations
      </NavLink>
      <NavLink to="/annotations/pubtator" className={itemCls}>
        🧬 PubTator
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
        size: 200,
        // Many values are bare URLs (up to 260 chars, no spaces) - without
        // break-all the table has no wrap point and expands the column (and
        // the table) to fit them instead of honoring `size` above.
        cell: (info) => (
          <span className="text-xs text-slate-700 break-all">{info.getValue()}</span>
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
      title="Annotations"
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
        size: 80,
        // Some captions are underscore-joined filenames (up to 135 chars with
        // no space to wrap on) - without break-all that forces the column
        // wide despite `size` above; line-clamp-3 alone only caps height.
        cell: (info) => (
          <span
            className="text-xs text-slate-600 line-clamp-3 break-all"
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
      title="Annotations"
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
// Grants sub-page
// ---------------------------------------------------------------------------

const GR_FACETS: readonly FacetSpec<PubGrant>[] = [
  { field: "funder_name", label: "Funder", multivalue: false },
  { field: "grant_number", label: "Grant Number", multivalue: false },
  { field: "recipient", label: "Recipient", multivalue: false },
];
const GR_SEARCH: (keyof PubGrant & string)[] = [
  "funder_name",
  "grant_number",
  "recipient",
  "funding_context_from_paper",
];
const grCol = createColumnHelper<PubGrant>();

function GrantsTab() {
  const [rows, setRows] = useState<PubGrant[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sp] = useSearchParams();
  const pmcFilter = sp.get("pmc");

  useEffect(() => {
    loadPubGrants().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => GR_FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof PubGrant & string)[]);

  const scoped = useMemo(() => {
    if (!rows) return [];
    if (!pmcFilter) return rows;
    return rows.filter((r) => pmcidFrom(r.source_url) === pmcFilter);
  }, [rows, pmcFilter]);

  const filtered = useMemo(() => {
    return scoped.filter((r) => {
      for (const spec of GR_FACETS) {
        if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(r, GR_SEARCH, query);
    });
  }, [scoped, selections, query]);

  const columns = useMemo(
    () => [
      grCol.accessor("funder_name", {
        header: "Funder",
        size: 180,
        cell: (info) => (
          <span className="text-xs text-slate-700">{info.getValue()}</span>
        ),
      }),
      grCol.accessor("grant_number", {
        header: "Grant #",
        size: 120,
        cell: (info) => (
          <span className="font-mono text-xs break-all">{info.getValue()}</span>
        ),
      }),
      grCol.accessor("recipient", {
        header: "Recipient",
        size: 160,
        cell: (info) => (
          <span className="text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      grCol.accessor("funding_context_from_paper", {
        header: "Context",
        size: 480,
        cell: (info) => {
          const text = info.getValue();
          if (!text) return null;
          return (
            <p className="text-xs text-slate-700 line-clamp-6" title={text}>
              {text}
            </p>
          );
        },
      }),
      grCol.accessor("source_url", {
        header: "Publication",
        // pub_grants has no title column of its own (only the source PMC link) -
        // was previously declared on PubGrant anyway but never populated, so this
        // always fell through to the URL-as-link-text branch below regardless.
        cell: (info) => {
          const url = info.getValue();
          if (!url) return null;
            return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline line-clamp-2 max-w-md"
              title={url}
              >
              {url}
            </a>
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
      title="Annotations"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${scoped.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<PubGrant>
          specs={GR_FACETS}
          rows={scoped}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) =>
            setFacet(field as (typeof GR_FACETS)[number]["field"], next)
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
            <ExportButton rows={filtered} filename="pub_grants" />
          </div>
          <DataTable<PubGrant> rows={filtered} columns={columns} />
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading grants…</div>
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

const SCILITE_TABLE_CAP = 5000;

function SciliteTab() {
  const [rows, setRows] = useState<SciLiteAnnotation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "stats">("stats");
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
      title="Annotations"
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
            <>
              {filtered.length > SCILITE_TABLE_CAP && (
                <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-2">
                  Showing first {SCILITE_TABLE_CAP.toLocaleString()} of {filtered.length.toLocaleString()} annotations. Use filters to narrow the set, or switch to Stats view for the full picture.
                </div>
              )}
              <DataTable<SciLiteAnnotation> rows={filtered.slice(0, SCILITE_TABLE_CAP)} columns={columns} />
            </>
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
// PubTator3 sub-pages (entities + relations)
// ---------------------------------------------------------------------------

/** Link a PubTator identifier to its source database record, or null if there isn't one. */
function pubTatorIdentifierUrl(type: string, id: string): string | null {
  if (/^rs\d+$/i.test(id)) return `https://www.ncbi.nlm.nih.gov/snp/${id}`;
  if (id.startsWith("MESH:")) return `https://meshb.nlm.nih.gov/record/ui?ui=${id.slice(5)}`;
  if (type === "Gene" && /^\d+$/.test(id)) return `https://www.ncbi.nlm.nih.gov/gene/${id}`;
  if (type === "Species" && /^\d+$/.test(id))
    return `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${id}`;
  return null;
}

function PubTatorId({ type, id }: { type: string; id: string }) {
  const url = pubTatorIdentifierUrl(type, id);
  return url ? (
    <a href={url} target="_blank" rel="noreferrer" className="font-mono text-xs text-accent hover:underline">
      {id}
    </a>
  ) : (
    <span className="font-mono text-xs text-slate-600 break-all">{id}</span>
  );
}

function PaperIds({ pmid, pmc }: { pmid: string; pmc: string }) {
  return (
    <span className="font-mono text-xs text-slate-600">
      {pmc || (
        <a href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}/`} target="_blank" rel="noreferrer" className="hover:underline">
          PMID {pmid}
        </a>
      )}
    </span>
  );
}

function PubTatorViewToggle() {
  const [sp] = useSearchParams();
  const pmc = sp.get("pmc");
  const suffix = pmc ? `?pmc=${encodeURIComponent(pmc)}` : "";
  const cls = ({ isActive }: { isActive: boolean }) =>
    "px-3 py-1.5 " + (isActive ? "bg-accent text-white" : "bg-white text-slate-700 hover:bg-slate-100");
  return (
    <div className="inline-flex rounded border border-slate-200 overflow-hidden text-sm">
      <NavLink to={`/annotations/pubtator${suffix}`} end className={cls}>
        Entities
      </NavLink>
      <NavLink to={`/annotations/pubtator/relations${suffix}`} className={cls}>
        Relations
      </NavLink>
    </div>
  );
}

function PubTatorNote() {
  return (
    <p className="text-xs text-slate-500 mb-3">
      Normalised entities and typed relations from{" "}
      <a href="https://www.ncbi.nlm.nih.gov/research/pubtator3/" target="_blank" rel="noreferrer" className="text-accent hover:underline">
        PubTator3
      </a>{" "}
      (NCBI). Entities come from full text where PMC has it; relations are document-level, extracted from abstracts.
    </p>
  );
}

const PT_ENTITY_FACETS: readonly FacetSpec<PubTatorEntity>[] = [
  { field: "Type", label: "Entity Type", multivalue: false },
  { field: "Name", label: "Entity", multivalue: false },
  { field: "Sections", label: "Section", multivalue: true },
  { field: "Text Scope", multivalue: false },
];
const PT_ENTITY_SEARCH: (keyof PubTatorEntity & string)[] = ["Name", "Identifier", "Mentions", "PMID", "PMC ID"];
const ptEntCol = createColumnHelper<PubTatorEntity>();

function PubTatorEntitiesTab() {
  const [rows, setRows] = useState<PubTatorEntity[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sp] = useSearchParams();
  const pmcFilter = sp.get("pmc");

  useEffect(() => {
    loadPubTatorEntities().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => PT_ENTITY_FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof PubTatorEntity & string)[]);

  const scoped = useMemo(() => {
    if (!rows) return [];
    return pmcFilter ? rows.filter((r) => r["PMC ID"] === pmcFilter) : rows;
  }, [rows, pmcFilter]);

  const filtered = useMemo(
    () =>
      scoped.filter((r) => {
        for (const spec of PT_ENTITY_FACETS) {
          if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
        }
        return matchesQuery(r, PT_ENTITY_SEARCH, query);
      }),
    [scoped, selections, query],
  );

  const columns = useMemo(
    () => [
      ptEntCol.accessor("PMC ID", {
        header: "Paper",
        cell: (info) => <PaperIds pmid={info.row.original.PMID} pmc={info.getValue()} />,
      }),
      ptEntCol.accessor("Type", { header: "Type" }),
      ptEntCol.accessor("Name", {
        header: "Entity",
        cell: (info) => <span className="text-xs text-slate-800 font-medium">{info.getValue()}</span>,
      }),
      ptEntCol.accessor("Identifier", {
        header: "Identifier",
        cell: (info) => <PubTatorId type={info.row.original.Type} id={info.getValue()} />,
      }),
      ptEntCol.accessor((r) => Number(r["Mention Count"]) || 0, {
        id: "Mention Count",
        header: "Mentions",
        cell: (info) => <span className="text-xs text-slate-600">{info.getValue()}</span>,
      }),
      ptEntCol.accessor("Mentions", {
        header: "As written",
        cell: (info) => <Chips value={info.getValue()} />,
      }),
      ptEntCol.accessor("Sections", {
        header: "Sections",
        cell: (info) => <span className="text-xs text-slate-600">{info.getValue().split(";").join(", ")}</span>,
      }),
    ],
    [],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Annotations"
      count={rows ? `${filtered.length.toLocaleString()} of ${scoped.length.toLocaleString()}` : "Loading…"}
      rail={
        <FilterRail<PubTatorEntity>
          specs={PT_ENTITY_FACETS}
          rows={scoped}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) => setFacet(field as (typeof PT_ENTITY_FACETS)[number]["field"], next)}
          totalSelected={totalSelected}
          onClearAll={clearAll}
          error={error}
        />
      }
    >
      <SubNav />
      <PmcBanner />
      <PubTatorNote />
      {rows ? (
        <>
          <div className="mb-3 flex items-center justify-between gap-3">
            <PubTatorViewToggle />
            <ExportButton rows={filtered} filename="pubtator_entities" />
          </div>
          <DataTable<PubTatorEntity> rows={filtered} columns={columns} />
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading PubTator entities…</div>
      )}
    </PageShell>
  );
}

const PT_REL_FACETS: readonly FacetSpec<PubTatorRelation>[] = [
  { field: "Relation Type", multivalue: false },
  { field: "Entity 1 Type", multivalue: false },
  { field: "Entity 2 Type", multivalue: false },
  { field: "Entity 1 Name", label: "Entity 1", multivalue: false },
  { field: "Entity 2 Name", label: "Entity 2", multivalue: false },
];
const PT_REL_SEARCH: (keyof PubTatorRelation & string)[] = [
  "Entity 1 Name",
  "Entity 2 Name",
  "Entity 1 Identifier",
  "Entity 2 Identifier",
  "PMID",
  "PMC ID",
];
const MIN_SCORE_OPTIONS = [0, 0.5, 0.8, 0.9, 0.95, 0.99];
const ptRelCol = createColumnHelper<PubTatorRelation>();

function PubTatorRelationsTab() {
  const [rows, setRows] = useState<PubTatorRelation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sp, setSp] = useSearchParams();
  const pmcFilter = sp.get("pmc");
  const minScore = Number(sp.get("minScore")) || 0;

  useEffect(() => {
    loadPubTatorRelations().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => PT_REL_FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof PubTatorRelation & string)[]);

  const scoped = useMemo(() => {
    if (!rows) return [];
    return rows.filter(
      (r) => (!pmcFilter || r["PMC ID"] === pmcFilter) && (minScore === 0 || Number(r.Score) >= minScore),
    );
  }, [rows, pmcFilter, minScore]);

  const filtered = useMemo(
    () =>
      scoped.filter((r) => {
        for (const spec of PT_REL_FACETS) {
          if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
        }
        return matchesQuery(r, PT_REL_SEARCH, query);
      }),
    [scoped, selections, query],
  );

  const setMinScore = (v: number) => {
    const next = new URLSearchParams(sp);
    if (v === 0) next.delete("minScore");
    else next.set("minScore", String(v));
    setSp(next, { replace: true });
  };

  const columns = useMemo(
    () => [
      ptRelCol.accessor("PMC ID", {
        header: "Paper",
        cell: (info) => <PaperIds pmid={info.row.original.PMID} pmc={info.getValue()} />,
      }),
      ptRelCol.accessor("Entity 1 Name", {
        header: "Entity 1",
        cell: (info) => (
          <span className="text-xs">
            <span className="font-medium text-slate-800">{info.getValue()}</span>{" "}
            <span className="text-slate-400">({info.row.original["Entity 1 Type"]})</span>
          </span>
        ),
      }),
      ptRelCol.accessor("Relation Type", {
        header: "Relation",
        cell: (info) => <span className="text-xs text-violet-700">{info.getValue().replace(/_/g, " ")}</span>,
      }),
      ptRelCol.accessor("Entity 2 Name", {
        header: "Entity 2",
        cell: (info) => (
          <span className="text-xs">
            <span className="font-medium text-slate-800">{info.getValue()}</span>{" "}
            <span className="text-slate-400">({info.row.original["Entity 2 Type"]})</span>
          </span>
        ),
      }),
      ptRelCol.accessor((r) => Number(r.Score) || 0, {
        id: "Score",
        header: "Score",
        cell: (info) => <span className="text-xs text-slate-600">{info.getValue().toFixed(3)}</span>,
      }),
    ],
    [],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Annotations"
      count={rows ? `${filtered.length.toLocaleString()} of ${scoped.length.toLocaleString()}` : "Loading…"}
      rail={
        <FilterRail<PubTatorRelation>
          specs={PT_REL_FACETS}
          rows={scoped}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) => setFacet(field as (typeof PT_REL_FACETS)[number]["field"], next)}
          totalSelected={totalSelected}
          onClearAll={clearAll}
          error={error}
        />
      }
    >
      <SubNav />
      <PmcBanner />
      <PubTatorNote />
      {rows ? (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <PubTatorViewToggle />
              <label className="text-sm text-slate-600 flex items-center gap-2">
                Min score
                <select
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  className="border border-slate-200 rounded px-2 py-1 text-sm bg-white"
                >
                  {MIN_SCORE_OPTIONS.map((v) => (
                    <option key={v} value={v}>
                      {v === 0 ? "Any" : `≥ ${v}`}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <ExportButton rows={filtered} filename="pubtator_relations" />
          </div>
          <DataTable<PubTatorRelation> rows={filtered} columns={columns} />
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading PubTator relations…</div>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Software sub-page
// ---------------------------------------------------------------------------

const SW_FACETS: readonly FacetSpec<PubSoftware>[] = [
  { field: "software_name", label: "Software", multivalue: false },
  { field: "version", label: "Version", multivalue: false },
  { field: "mention_type", label: "Mention Type", multivalue: false },
];
const SW_SEARCH: (keyof PubSoftware & string)[] = [
  "software_name",
  "version",
  "mention_type",
  "context_from_paper",
];
const swCol = createColumnHelper<PubSoftware>();

function SoftwareTab() {
  const [rows, setRows] = useState<PubSoftware[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sp] = useSearchParams();
  const pmcFilter = sp.get("pmc");

  useEffect(() => {
    loadPubSoftware().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => SW_FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof PubSoftware & string)[]);

  const scoped = useMemo(() => {
    if (!rows) return [];
    if (!pmcFilter) return rows;
    return rows.filter((r) => pmcidFrom(r.source_url) === pmcFilter);
  }, [rows, pmcFilter]);

  const filtered = useMemo(() => {
    return scoped.filter((r) => {
      for (const spec of SW_FACETS) {
        if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(r, SW_SEARCH, query);
    });
  }, [scoped, selections, query]);

  const columns = useMemo(
    () => [
      swCol.accessor("software_name", {
        header: "Software",
        size: 180,
        cell: (info) => (
          <span className="text-xs text-slate-700">{info.getValue()}</span>
        ),
      }),
      swCol.accessor("version", {
        header: "Version",
        size: 100,
        cell: (info) => (
          <span className="font-mono text-xs">{info.getValue()}</span>
        ),
      }),
      swCol.accessor("mention_type", {
        header: "Mention Type",
        size: 120,
        cell: (info) => (
          <span className="text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      swCol.accessor("context_from_paper", {
        header: "Context",
        size: 420,
        cell: (info) => {
          const text = info.getValue();
          if (!text) return null;
          return (
            <p className="text-xs text-slate-700 line-clamp-6" title={text}>
              {text}
            </p>
          );
        },
      }),
      swCol.accessor("url", {
        header: "Software URL",
        size: 200,
        cell: (info) => {
          const url = info.getValue();
          if (!url) return null;
          return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline line-clamp-2 max-w-md"
              title={url}
            >
              {url}
            </a>
          );
        },
      }),
      swCol.accessor("source_url", {
        header: "Publication",
        cell: (info) => {
          const url = info.getValue();
          if (!url) return null;
          return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline line-clamp-2 max-w-md"
              title={url}
            >
              {url}
            </a>
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
      title="Annotations"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${scoped.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<PubSoftware>
          specs={SW_FACETS}
          rows={scoped}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) =>
            setFacet(field as (typeof SW_FACETS)[number]["field"], next)
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
            <ExportButton rows={filtered} filename="pub_software" />
          </div>
          <DataTable<PubSoftware> rows={filtered} columns={columns} />
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading software…</div>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Models sub-page
// ---------------------------------------------------------------------------

const MD_FACETS: readonly FacetSpec<PubModel>[] = [
  { field: "model_name", label: "Model", multivalue: false },
  { field: "version", label: "Version", multivalue: false },
  { field: "mention_type", label: "Mention Type", multivalue: false },
];
const MD_SEARCH: (keyof PubModel & string)[] = [
  "model_name",
  "version",
  "mention_type",
  "context_from_paper",
];
const mdCol = createColumnHelper<PubModel>();

function ModelsTab() {
  const [rows, setRows] = useState<PubModel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sp] = useSearchParams();
  const pmcFilter = sp.get("pmc");

  useEffect(() => {
    loadPubModels().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => MD_FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof PubModel & string)[]);

  const scoped = useMemo(() => {
    if (!rows) return [];
    if (!pmcFilter) return rows;
    return rows.filter((r) => pmcidFrom(r.source_url) === pmcFilter);
  }, [rows, pmcFilter]);

  const filtered = useMemo(() => {
    return scoped.filter((r) => {
      for (const spec of MD_FACETS) {
        if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(r, MD_SEARCH, query);
    });
  }, [scoped, selections, query]);

  const columns = useMemo(
    () => [
      mdCol.accessor("model_name", {
        header: "Model",
        size: 180,
        cell: (info) => (
          <span className="text-xs text-slate-700">{info.getValue()}</span>
        ),
      }),
      mdCol.accessor("version", {
        header: "Version",
        size: 100,
        cell: (info) => (
          <span className="font-mono text-xs">{info.getValue()}</span>
        ),
      }),
      mdCol.accessor("mention_type", {
        header: "Mention Type",
        size: 120,
        cell: (info) => (
          <span className="text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      mdCol.accessor("context_from_paper", {
        header: "Context",
        size: 420,
        cell: (info) => {
          const text = info.getValue();
          if (!text) return null;
          return (
            <p className="text-xs text-slate-700 line-clamp-6" title={text}>
              {text}
            </p>
          );
        },
      }),
      mdCol.accessor("url", {
        header: "Model URL",
        size: 200,
        cell: (info) => {
          const raw = info.getValue();
          if (!raw) return null;
          // A single model mention can carry more than one hosting link (e.g. a
          // GitHub repo and a Hugging Face page for the same model) - semicolon-delimited.
          const urls = raw.split(";").map((u) => u.trim()).filter(Boolean);
          return (
            <div className="flex flex-col gap-0.5 max-w-md">
              {urls.map((url) => (
                <a
                  key={url}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-accent hover:underline line-clamp-2"
                  title={url}
                >
                  {url}
                </a>
              ))}
            </div>
          );
        },
      }),
      mdCol.accessor("source_url", {
        header: "Publication",
        cell: (info) => {
          const url = info.getValue();
          if (!url) return null;
          return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-accent hover:underline line-clamp-2 max-w-md"
              title={url}
            >
              {url}
            </a>
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
      title="Annotations"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${scoped.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<PubModel>
          specs={MD_FACETS}
          rows={scoped}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) =>
            setFacet(field as (typeof MD_FACETS)[number]["field"], next)
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
            <ExportButton rows={filtered} filename="pub_models" />
          </div>
          <DataTable<PubModel> rows={filtered} columns={columns} />
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading models…</div>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Datasets section router
// ---------------------------------------------------------------------------

export function AnnotationsPage() {
  return (
    <Routes>
      <Route index element={<DatasetsTab />} />
      <Route path="supplementary" element={<SupplementaryTab />} />
      <Route path="grants" element={<GrantsTab />} />
      <Route path="software" element={<SoftwareTab />} />
      <Route path="models" element={<ModelsTab />} />
      <Route path="scilite" element={<SciliteTab />} />
      <Route path="pubtator" element={<PubTatorEntitiesTab />} />
      <Route path="pubtator/relations" element={<PubTatorRelationsTab />} />
      <Route path="*" element={<Navigate to="" replace />} />
    </Routes>
  );
}
