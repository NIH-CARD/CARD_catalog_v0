import { useEffect, useMemo, useState } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { BrowseCard, BrowseGrid, Field, Section } from "../components/BrowseCard";
import { DataTable } from "../components/DataTable";
import { ExportButton } from "../components/ExportButton";
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

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg px-4 py-3 flex flex-col items-center gap-0.5">
      <span className="text-2xl font-bold text-accent">{value.toLocaleString()}</span>
      <span className="text-xs text-slate-500 text-center">{label}</span>
    </div>
  );
}

export function CellularModelsPage() {
  const [rows, setRows] = useState<CellularModel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "browse">("table");

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

  const stats = useMemo(() => ({
    total: filtered.length,
    genes: new Set(filtered.map((r) => r.Gene).filter(Boolean)).size,
    conditions: new Set(
      filtered.map((r) => r.Condition).filter((c) => c && c !== "0")
    ).size,
    parentalLines: new Set(filtered.map((r) => r["Parental Line"]).filter(Boolean)).size,
  }), [filtered]);

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
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <StatCard label="Cell Lines" value={stats.total} />
            <StatCard label="Unique Genes" value={stats.genes} />
            <StatCard label="Unique Conditions" value={stats.conditions} />
            <StatCard label="Parental Lines" value={stats.parentalLines} />
          </div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="inline-flex rounded border border-slate-200 overflow-hidden text-sm">
              {(["table", "browse"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={
                    "px-3 py-1.5 " +
                    (view === v ? "bg-accent text-white" : "bg-white text-slate-700 hover:bg-slate-100")
                  }
                >
                  {v === "table" ? "📊 Table" : "🗂 Browse"}
                </button>
              ))}
            </div>
            <ExportButton rows={filtered} filename="cellular_models" />
          </div>
          {view === "table" ? (
            <DataTable<CellularModel> rows={filtered} columns={columns} />
          ) : (
            <BrowseGrid>
              {filtered.map((r, i) => (
                <BrowseCard
                  key={i}
                  title={
                    r["Procurement link"] ? (
                      <a href={r["Procurement link"]} target="_blank" rel="noreferrer" className="text-accent hover:underline font-mono">
                        {r["Product Code"]}
                      </a>
                    ) : <span className="font-mono">{r["Product Code"]}</span>
                  }
                  subtitle={`${r.Gene}${r["Gene Variant"] ? ` · ${r["Gene Variant"]}` : ""}`}
                  badge={
                    r.Condition && r.Condition !== "0"
                      ? <span className="text-[10px] bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded">{r.Condition}</span>
                      : <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">Control</span>
                  }
                >
                  <Field label="Parental Line" value={r["Parental Line"]} />
                  <Field label="Genotype" value={r.Genotype} />
                  <Field label="dbSNP" value={r.dbSNP} />
                  <Field label="Genome Assembly" value={r["Genome Assembly"]} />
                  {r["Other Names"] && <Field label="Other Names" value={r["Other Names"]} />}
                  {(r["Protospacer Sequence"] || r["Genomic Coordinate"] || r["Genomic Sequence"]) && (
                    <Section title="Genomic Details">
                      <Field label="Protospacer Sequence" value={r["Protospacer Sequence"]} />
                      <Field label="Genomic Coordinate" value={r["Genomic Coordinate"]} />
                      <Field label="Genomic Sequence" value={r["Genomic Sequence"]} expandable maxChars={80} />
                    </Section>
                  )}
                  {r["About this gene"] && (
                    <Section title="About this gene">
                      <Field label="" value={r["About this gene"]} expandable maxChars={280} />
                    </Section>
                  )}
                  {r["About this variant"] && (
                    <Section title="About this variant">
                      <Field label="" value={r["About this variant"]} expandable maxChars={280} />
                    </Section>
                  )}
                </BrowseCard>
              ))}
            </BrowseGrid>
          )}
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading cellular models…</div>
      )}
    </PageShell>
  );
}
