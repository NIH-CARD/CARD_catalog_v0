import { useEffect, useMemo, useState } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { BrowseCard, BrowseGrid, Field, Section } from "../components/BrowseCard";
import { Chips } from "../components/Chips";
import { DataTable } from "../components/DataTable";
import { ExportButton } from "../components/ExportButton";
import { FilterRail } from "../components/FilterRail";
import { GraphControls, buildEdgeFields } from "../components/GraphControls";
import { InfoList } from "../components/HoverInfo";
import { KnowledgeGraph } from "../components/KnowledgeGraph";
import { PageShell } from "../components/PageShell";
import { matchesFacet, matchesQuery } from "../lib/filter";
import { loadCodeRepos } from "../lib/loaders";
import { useFacets } from "../lib/useFacets";
import type { CodeRepo, FacetSpec } from "../types";

const GRAPH_FIELD_OPTIONS = [
  { field: "Languages" as const, label: "Languages", delimiter: ";" },
  { field: "Data Types" as const, label: "Data Types", delimiter: ";" },
  { field: "Tooling" as const, label: "Tooling", delimiter: ";" },
  { field: "Diseases Included" as const, label: "Diseases", delimiter: ";" },
  { field: "Resource Name" as const, label: "Study" },
];

const FACETS: readonly FacetSpec<CodeRepo>[] = [
  { field: "Resource Name", label: "Study", multivalue: false },
  { field: "Languages", multivalue: true },
  { field: "Diseases Included", multivalue: true },
  { field: "Data Types", multivalue: true },
  { field: "Tooling", multivalue: true },
  { field: "Biomedical Relevance", multivalue: false },
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
  const [view, setView] = useState<"table" | "browse" | "graph">("table");
  const [edgeSelected, setEdgeSelected] = useState<(keyof CodeRepo & string)[]>(["Languages"]);
  const [minShared, setMinShared] = useState(1);
  const [maxNodes, setMaxNodes] = useState(60);
  const [showAll, setShowAll] = useState(false);

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
        size: 320,
        cell: (info) => {
          const url = info.getValue();
          if (!url) return null;
          const shown = url.replace(/^https?:\/\/github\.com\//, "");
          return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline font-mono text-xs break-all"
              title={url}
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
          <span className="text-xs text-slate-600 line-clamp-2 max-w-xs" title={info.getValue()}>
            {info.getValue()}
          </span>
        ),
      }),
      col.accessor("Code Summary", {
        header: "Summary",
        cell: (info) => {
          const text = info.getValue();
          if (!text) return null;
          return (
            <p className="text-xs text-slate-700 line-clamp-3 max-w-sm" title={text}>
              {text}
            </p>
          );
        },
      }),
      col.accessor("Owner", {
        header: "Owner",
        cell: (info) => (
          <span className="text-xs text-slate-500 font-mono truncate block" title={info.getValue()}>
            {info.getValue()}
          </span>
        ),
      }),
      col.accessor("Contributors", {
        header: "Contributors",
        size: 140,
        cell: (info) => (
          <span className="text-xs text-slate-500 line-clamp-2" title={info.getValue()}>
            {info.getValue()}
          </span>
        ),
      }),
      col.accessor("FAIR Score", {
        header: "FAIR Score",
        cell: (info) => {
          const score = Number(info.getValue());
          const color = score >= 8 ? "text-emerald-600" : score >= 5 ? "text-amber-600" : "text-red-500";
          return (
            <span className={`text-xs font-semibold tabular-nums ${color}`}>
              {info.getValue()}/10
            </span>
          );
        },
      }),
      col.accessor("FAIR Issues", {
        header: "FAIR Issues",
        cell: (info) => {
          const text = info.getValue();
          if (!text) return <span className="text-xs text-emerald-600">None</span>;
          return (
            <p className="text-xs text-slate-600 line-clamp-3" title={text}>{text}</p>
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
      title="Code Repositories"
      count={
        rows
          ? `${filtered.length.toLocaleString()} of ${rows.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<CodeRepo>
          specs={FACETS as readonly FacetSpec<CodeRepo>[]}
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
          <AnalysisPanel<CodeRepo>
            type="code"
            filtered={filtered}
            total={rows.length}
            maxRows={20}
            prepare={(rs) => rs.map((r) => ({
              name: r["Resource Name"],
              repo: r["Repository Link"],
              languages: r.Languages,
              dataTypes: r["Data Types"],
              tooling: r.Tooling,
              relevance: r["Biomedical Relevance"],
              fairScore: r["FAIR Score"],
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
            <ExportButton rows={filtered} filename="code_repos" />
          </div>
          {view === "table" ? (
            <DataTable<CodeRepo> rows={filtered} columns={columns} />
          ) : view === "browse" ? (
            <BrowseGrid>
              {filtered.map((r, i) => {
                const repoShort = r["Repository Link"]?.replace(/^https?:\/\/github\.com\//, "") ?? r["Repository Link"];
                return (
                  <BrowseCard
                    key={i}
                    title={
                      r["Repository Link"] ? (
                        <a href={r["Repository Link"]} target="_blank" rel="noreferrer" className="text-accent hover:underline font-mono text-sm">
                          {repoShort}
                        </a>
                      ) : r["Repository Link"]
                    }
                    subtitle={r["Resource Name"]}
                  >
                    <Field label="Languages" value={r.Languages} chips />
                    <Field label="Data Types" value={r["Data Types"]} chips />
                    <Field label="Tooling" value={r.Tooling} chips />
                    <Field label="Biomedical Relevance" value={r["Biomedical Relevance"]} expandable maxChars={160} />
                    {r["Code Summary"] && (
                      <Section title="Summary">
                        <Field label="" value={r["Code Summary"]} expandable maxChars={300} />
                      </Section>
                    )}
                    {r.Contributors && (
                      <Section title="Contributors">
                        <Field label="" value={r.Contributors} />
                      </Section>
                    )}
                  </BrowseCard>
                );
              })}
            </BrowseGrid>
          ) : (
            <>
              <GraphControls<CodeRepo>
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
              <KnowledgeGraph<CodeRepo>
                rows={filtered}
                nodeField="Resource Name"
                edgeFields={buildEdgeFields(GRAPH_FIELD_OPTIONS, edgeSelected)}
                minShared={minShared}
                maxNodes={maxNodes}
                hideDisconnected={!showAll}
                nodeInfo={(r) => (
                  <InfoList
                    rows={[
                      { label: "Study", value: r["Resource Name"] },
                      { label: "Repo", value: r["Repository Link"] },
                      { label: "Languages", value: r.Languages },
                      { label: "Data Types", value: r["Data Types"] },
                      { label: "FAIR Score", value: r["FAIR Score"] },
                    ]}
                  />
                )}
                valueMeta={(_field, value) => (
                  <div className="font-medium">{value}</div>
                )}
              />
            </>
          )}
        </>
      ) : (
        <div className="text-sm text-slate-500">Loading code repositories…</div>
      )}
    </PageShell>
  );
}
