import { useEffect, useMemo, useState } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { BrowseCard, BrowseGrid, Field, Section } from "../components/BrowseCard";
import { Chips } from "../components/Chips";
import { DataTable } from "../components/DataTable";
import { FilterRail } from "../components/FilterRail";
import { GraphControls, buildEdgeFields } from "../components/GraphControls";
import { InfoList } from "../components/HoverInfo";
import { KnowledgeGraph } from "../components/KnowledgeGraph";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { ExportButton } from "../components/ExportButton";
import { PageShell } from "../components/PageShell";
import { matchesFacet, matchesQuery } from "../lib/filter";
import { loadResources } from "../lib/loaders";
import { useFacets } from "../lib/useFacets";
import type { FacetSpec, Resource } from "../types";

const GRAPH_FIELD_OPTIONS: readonly { field: keyof Resource & string; label?: string; delimiter?: string }[] = [
  { field: "Diseases Included", delimiter: ";" },
  { field: "Coarse Data Modality", delimiter: "," },
  { field: "Granular Data Modality", delimiter: ";" },
  { field: "Resource Type", delimiter: "," },
];

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
  const [view, setView] = useState<"table" | "browse" | "graph">("table");
  const [edgeSelected, setEdgeSelected] = useState<(keyof Resource & string)[]>([
    "Diseases Included",
  ]);
  const [minShared, setMinShared] = useState(1);
  const [maxNodes, setMaxNodes] = useState(60);
  const [showAll, setShowAll] = useState(false);

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
        header: "Resource",        size: 280,
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
        header: "Abbrev.",
        size: 90,
        cell: (info) => (
          <span className="font-mono text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      col.accessor("Resource Type", {
        header: "Type",
        size: 130,
        cell: (info) => <Chips value={info.getValue()} max={2} delimiter="," />,
      }),
      col.accessor("Diseases Included", {
        header: "Diseases",
        size: 220,
        cell: (info) => <Chips value={info.getValue()} />,
      }),
      col.accessor("Coarse Data Modality", {
        header: "Modality",
        cell: (info) => <Chips value={info.getValue()} delimiter="," />,
      }),
      col.accessor("Sample Size", {
        header: "Sample Size",
        cell: (info) => (
          <span className="text-xs tabular-nums text-slate-700">{info.getValue()}</span>
        ),
      }),
      col.accessor("FAIR Compliance Notes", {
        header: "FAIR Notes",
        cell: (info) => {
          const text = info.getValue();
          if (!text) return null;
          return (
            <p className="text-xs text-slate-600 line-clamp-3 max-w-sm" title={text}>
              {text}
            </p>
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
          <AnalysisPanel<Resource>
            type="resources"
            filtered={filtered}
            total={rows.length}
            prepare={(rs) => rs.map((r) => ({
              name: r["Resource Name"],
              abbreviation: r["Abbreviation"],
              diseases: r["Diseases Included"],
              modality: r["Coarse Data Modality"],
              sampleSize: r["Sample Size"],
              type: r["Resource Type"],
            }))}
          />
          <div className="mb-3 flex items-center justify-between gap-3">
          <div className="inline-flex rounded border border-slate-200 overflow-hidden text-sm">
            {(["table", "browse", "graph"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={
                  "px-3 py-1.5 " +
                  (view === v ? "bg-accent text-white" : "bg-white text-slate-700 hover:bg-slate-100")
                }
              >
                {v === "table" ? "📊 Table" : v === "browse" ? "🗂 Browse" : "🕸 Graph"}
              </button>
            ))}
          </div>
            <ExportButton rows={filtered} filename="resources" />
          </div>
          {view === "table" ? (
            <DataTable<Resource> rows={filtered} columns={columns} />
          ) : view === "browse" ? (
            <BrowseGrid>
              {filtered.map((r, i) => (
                <BrowseCard
                  key={i}
                  title={
                    r["Access URL"] ? (
                      <a href={r["Access URL"]} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                        {r["Resource Name"]}
                      </a>
                    ) : r["Resource Name"]
                  }
                  subtitle={r.Abbreviation}
                  badge={r["Sample Size"] ? <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">{r["Sample Size"]}</span> : undefined}
                >
                  <Field label="Type" value={r["Resource Type"]} chips delimiter="," />
                  <Field label="Diseases" value={r["Diseases Included"]} chips />
                  <Field label="Coarse Modality" value={r["Coarse Data Modality"]} chips delimiter="," />
                  <Field label="Granular Modality" value={r["Granular Data Modality"]} chips />
                  {r["FAIR Compliance Notes"] && (
                    <Section title="FAIR Compliance Notes">
                      <Field label="" value={r["FAIR Compliance Notes"]} expandable />
                    </Section>
                  )}
                  {r.Notes && (
                    <Section title="Notes">
                      <Field label="" value={r.Notes} expandable />
                    </Section>
                  )}
                  {r["Date added to catalog"] && (
                    <Field label="Added" value={r["Date added to catalog"]} />
                  )}
                </BrowseCard>
              ))}
            </BrowseGrid>
          ) : (
            <>
              <GraphControls<Resource>
                options={GRAPH_FIELD_OPTIONS}
                selected={edgeSelected}
                onSelectedChange={setEdgeSelected}
                minShared={minShared}
                onMinSharedChange={setMinShared}
                maxNodes={maxNodes}
                onMaxNodesChange={setMaxNodes}
                showAll={showAll}
                onShowAllChange={setShowAll}
              />
              <KnowledgeGraph<Resource>
                rows={filtered}
                nodeField="Resource Name"
                edgeFields={buildEdgeFields(GRAPH_FIELD_OPTIONS, edgeSelected)}
                minShared={minShared}
                maxNodes={maxNodes}
                hideDisconnected={!showAll}
                nodeInfo={(r) => (
                  <InfoList
                    rows={[
                      { label: "Resource", value: r["Resource Name"] },
                      { label: "Abbrev", value: r.Abbreviation },
                      { label: "Type", value: r["Resource Type"] },
                      { label: "Diseases", value: r["Diseases Included"] },
                      { label: "Coarse modality", value: r["Coarse Data Modality"] },
                      { label: "Granular modality", value: r["Granular Data Modality"] },
                      { label: "Sample size", value: r["Sample Size"] },
                      { label: "FAIR notes", value: r["FAIR Compliance Notes"] },
                    ]}
                  />
                )}
              />
            </>
          )}
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading resources…</div>
      )}
    </PageShell>
  );
}
