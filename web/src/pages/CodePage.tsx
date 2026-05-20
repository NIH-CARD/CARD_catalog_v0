import { useEffect, useMemo, useState } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { Chips } from "../components/Chips";
import { DataTable } from "../components/DataTable";
import { FilterRail } from "../components/FilterRail";
import { PageShell } from "../components/PageShell";
import { matchesFacet, matchesQuery } from "../lib/filter";
import { loadCodeRepos } from "../lib/loaders";
import { useFacets } from "../lib/useFacets";
import type { CodeRepo, FacetSpec } from "../types";

const FACETS: readonly FacetSpec<CodeRepo>[] = [
  { field: "Languages", multivalue: true },
  { field: "Diseases Included", multivalue: true },
  { field: "Data Types", multivalue: true },
  { field: "Tooling", multivalue: true },
];

const SEARCH_FIELDS: (keyof CodeRepo & string)[] = [
  "Resource Name",
  "Code Summary",
  "Biomedical Relevance",
  "Owner",
];

const col = createColumnHelper<CodeRepo>();

export function CodePage() {
  const [rows, setRows] = useState<CodeRepo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCodeRepos().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof CodeRepo & string)[]);

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
        header: "Study",
        cell: (info) => <span className="text-slate-700">{info.getValue()}</span>,
      }),
      col.accessor("Repository Link", {
        header: "Repo",
        cell: (info) => {
          const url = info.getValue();
          if (!url) return null;
          // Show "owner/name" if possible
          const shown = url.replace(/^https?:\/\/github\.com\//, "");
          return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline font-mono text-xs"
            >
              {shown || url}
            </a>
          );
        },
      }),
      col.accessor("Languages", {
        header: "Languages",
        cell: (info) => <Chips value={info.getValue()} />,
      }),
      col.accessor("Data Types", {
        header: "Data Types",
        cell: (info) => <Chips value={info.getValue()} />,
      }),
      col.accessor("Biomedical Relevance", {
        header: "Relevance",
        cell: (info) => (
          <span className="text-xs text-slate-600 line-clamp-2 max-w-md">
            {info.getValue()}
          </span>
        ),
      }),
    ],
    [],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Code Repositories"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${rows.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<CodeRepo>
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
        <DataTable<CodeRepo> rows={filtered} columns={columns} />
      ) : (
        <div className="text-sm text-slate-500">Loading code repositories…</div>
      )}
    </PageShell>
  );
}
