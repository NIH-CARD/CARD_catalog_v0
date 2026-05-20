import { useEffect, useMemo, useState } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { Chips } from "../components/Chips";
import { DataTable } from "../components/DataTable";
import { FilterRail } from "../components/FilterRail";
import { KnowledgeGraph } from "../components/KnowledgeGraph";
import { PageShell } from "../components/PageShell";
import { matchesFacet, matchesQuery } from "../lib/filter";
import { loadResources } from "../lib/loaders";
import { useFacets } from "../lib/useFacets";
import type { FacetSpec, Resource } from "../types";

const FACETS: readonly FacetSpec<Resource>[] = [
  { field: "Resource Type", multivalue: true, delimiter: "," },
  { field: "Diseases Included", multivalue: true },
  { field: "Coarse Data Modality", multivalue: true, delimiter: "," },
  { field: "Granular Data Modality", multivalue: true },
];

const SEARCH_FIELDS: (keyof Resource & string)[] = [
  "Resource Name",
  "Abbreviation",
  "Notes",
  "FAIR Compliance Notes",
];

const col = createColumnHelper<Resource>();

export function ResourcesPage() {
  const [rows, setRows] = useState<Resource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "graph">("table");

  useEffect(() => {
    loadResources().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof Resource & string)[]);

  const filtered = useMemo(() => {
    if (!rows) return [];
    return rows.filter((r) => {
      for (const spec of FACETS) {
        if (!matchesFacet(r, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(r, SEARCH_FIELDS, query);
    });
  }, [rows, selections, query]);

  const columns = useMemo(
    () => [
      col.accessor("Resource Name", {
        header: "Resource",
        cell: (info) => {
          const url = info.row.original["Access URL"];
          const name = info.getValue();
          return url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline"
            >
              {name}
            </a>
          ) : (
            name
          );
        },
      }),
      col.accessor("Abbreviation", {
        header: "Abbrev",
        cell: (info) => (
          <span className="font-mono text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      col.accessor("Resource Type", {
        header: "Type",
        cell: (info) => <Chips value={info.getValue()} max={2} delimiter="," />,
      }),
      col.accessor("Diseases Included", {
        header: "Diseases",
        cell: (info) => <Chips value={info.getValue()} />,
      }),
      col.accessor("Coarse Data Modality", {
        header: "Modality",
        cell: (info) => <Chips value={info.getValue()} delimiter="," />,
      }),
      col.accessor("Sample Size", {
        header: "N",
        cell: (info) => (
          <span className="text-xs tabular-nums text-slate-700">{info.getValue()}</span>
        ),
      }),
    ],
    [],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Resources"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${rows.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<Resource>
          specs={FACETS}
          rows={rows ?? []}
          selections={selections as Record<string, Set<string>>}
          onFacetChange={(field, next) =>
            setFacet(field as (typeof FACETS)[number]["field"], next)
          }
          totalSelected={totalSelected}
          onClearAll={clearAll}
          error={error}
        />
      }
    >
      {rows ? (
        <>
          <div className="mb-3 inline-flex rounded border border-slate-200 overflow-hidden text-sm">
            {(["table", "graph"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={
                  "px-3 py-1.5 " +
                  (view === v ? "bg-accent text-white" : "bg-white text-slate-700 hover:bg-slate-100")
                }
              >
                {v === "table" ? "📊 Table" : "🕸 Graph"}
              </button>
            ))}
          </div>
          {view === "table" ? (
            <DataTable<Resource> rows={filtered} columns={columns} />
          ) : (
            <KnowledgeGraph<Resource>
              rows={filtered}
              nodeField="Resource Name"
              edgeField="Diseases Included"
            />
          )}
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading resources…</div>
      )}
    </PageShell>
  );
}
