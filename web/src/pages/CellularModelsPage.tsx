import { useEffect, useMemo, useState } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { DataTable } from "../components/DataTable";
import { FilterRail } from "../components/FilterRail";
import { PageShell } from "../components/PageShell";
import { matchesFacet, matchesQuery } from "../lib/filter";
import { loadCellularModels } from "../lib/loaders";
import { useFacets } from "../lib/useFacets";
import type { CellularModel, FacetSpec } from "../types";

const FACETS: readonly FacetSpec<CellularModel>[] = [
  { field: "Gene", multivalue: false },
  { field: "Condition", multivalue: false },
  { field: "Parental Line", multivalue: false },
  { field: "Genotype", multivalue: false },
];

const SEARCH_FIELDS: (keyof CellularModel & string)[] = [
  "Product Code",
  "Gene",
  "Gene Variant",
  "Condition",
  "Other Names",
  "About this gene",
  "About this variant",
];

const col = createColumnHelper<CellularModel>();

export function CellularModelsPage() {
  const [rows, setRows] = useState<CellularModel[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCellularModels().then(setRows).catch((e: Error) => setError(e.message));
  }, []);

  const fields = useMemo(() => FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof CellularModel & string)[]);

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
      col.accessor("Product Code", {
        header: "Product",
        cell: (info) => {
          const url = info.row.original["Procurement link"];
          const code = info.getValue();
          return url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline font-mono text-xs"
            >
              {code}
            </a>
          ) : (
            <span className="font-mono text-xs">{code}</span>
          );
        },
      }),
      col.accessor("Gene", {
        header: "Gene",
        cell: (info) => (
          <span className="font-mono text-xs text-slate-700">{info.getValue()}</span>
        ),
      }),
      col.accessor("Gene Variant", { header: "Variant" }),
      col.accessor("Condition", {
        header: "Condition",
        cell: (info) => <span className="text-xs">{info.getValue()}</span>,
      }),
      col.accessor("Parental Line", { header: "Parental" }),
      col.accessor("Genotype", { header: "Genotype" }),
    ],
    [],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Human Cellular Models (iNDI)"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${rows.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<CellularModel>
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
        <DataTable<CellularModel> rows={filtered} columns={columns} />
      ) : (
        <div className="text-sm text-slate-500">Loading cellular models…</div>
      )}
    </PageShell>
  );
}
