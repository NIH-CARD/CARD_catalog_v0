import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { ExportButton } from "../components/ExportButton";
import { BrowseCard, BrowseGrid, Field, Section } from "../components/BrowseCard";
import { createColumnHelper } from "@tanstack/react-table";
import { Chips } from "../components/Chips";
import { DataTable } from "../components/DataTable";
import { FilterRail } from "../components/FilterRail";
import { GraphControls, buildEdgeFields } from "../components/GraphControls";
import { InfoList } from "../components/HoverInfo";
import { KnowledgeGraph } from "../components/KnowledgeGraph";
import { PageShell } from "../components/PageShell";
import { matchesFacet, matchesQuery } from "../lib/filter";
import {
  loadPubDatasets,
  loadPublications,
  loadSciLite,
  loadSupplementary,
} from "../lib/loaders";
import { pmcidFrom } from "../lib/loadPublications";
import {
  applyToPubs,
  PAPER_GRAPH_FIELD_OPTIONS,
  type GraphPublication,
} from "../lib/paperGraph";
import { useFacets } from "../lib/useFacets";
import type {
  FacetSpec,
  PubDataset,
  Publication,
  SciLiteAnnotation,
  Supplementary,
} from "../types";

const SEARCH_FIELDS: (keyof GraphPublication & string)[] = [
  "Title",
  "Abstract",
  "Authors",
  "Keywords",
  "Resource Name",
];

const GRAPH_FIELD_OPTIONS = PAPER_GRAPH_FIELD_OPTIONS;

const col = createColumnHelper<GraphPublication>();

function ResourceLinks({
  pmcid,
  ds,
  sp,
  sc,
}: {
  pmcid: string;
  ds: PubDataset[];
  sp: Supplementary[];
  sc: SciLiteAnnotation[];
}) {
  if (!pmcid || (ds.length === 0 && sp.length === 0 && sc.length === 0))
    return null;
  return (
    <div className="flex flex-wrap gap-2 mt-1">
      {ds.length > 0 && (
        <Link
          to={`/datasets?pmc=${pmcid}`}
          className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100"
        >
          📦 {ds.length} datasets
        </Link>
      )}
      {sp.length > 0 && (
        <Link
          to={`/datasets/supplementary?pmc=${pmcid}`}
          className="text-[10px] px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100"
        >
          📎 {sp.length} supplementary
        </Link>
      )}
      {sc.length > 0 && (
        <Link
          to={`/datasets/scilite?pmc=${pmcid}`}
          className="text-[10px] px-1.5 py-0.5 rounded bg-violet-50 text-violet-700 border border-violet-200 hover:bg-violet-100"
        >
          🏷️ {sc.length} annotations
        </Link>
      )}
    </div>
  );
}

export function PublicationsPage() {
  const [pubs, setPubs] = useState<Publication[] | null>(null);
  const [ds, setDs] = useState<PubDataset[]>([]);
  const [sp, setSp] = useState<Supplementary[]>([]);
  const [sc, setSc] = useState<SciLiteAnnotation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "browse" | "graph">("table");
  const [edgeSelected, setEdgeSelected] = useState<(keyof GraphPublication & string)[]>([
    "Diseases (Annotated)",
  ]);
  const [minShared, setMinShared] = useState(1);
  const [maxNodes, setMaxNodes] = useState(60);
  const [showAll, setShowAll] = useState(false);
  const [hubEnabled, setHubEnabled] = useState(false);
  const [hubThresholdPct, setHubThresholdPct] = useState(30);

  useEffect(() => {
    loadPublications().then(setPubs).catch((e: Error) => setError(e.message));
    loadPubDatasets().then(setDs).catch(() => undefined);
    loadSupplementary().then(setSp).catch(() => undefined);
    loadSciLite().then(setSc).catch(() => undefined);
  }, []);

  // Publications already carry annotation columns from the pipeline (staging/join_annotations.py).
  // Cast to GraphPublication — the type is now identical to Publication.
  const allAugmented = useMemo<GraphPublication[]>(
    () => (pubs as GraphPublication[]) ?? [],
    [pubs],
  );

  // Paper-grounded facets: SciLite types + cited datasets + publication metadata
  const FACETS: readonly FacetSpec<GraphPublication>[] = useMemo(
    () => [
      {
        field: "Resource Name",
        label: "Study",
        multivalue: false,
      },
      {
        field: "Diseases Included",
        label: "Diseases",
        multivalue: true,
        delimiter: ";",
      },
      {
        field: "Coarse Data Modality",
        label: "Coarse Modality",
        multivalue: true,
        delimiter: ";",
      },
      {
        field: "Granular Data Modality",
        label: "Granular Modality",
        multivalue: true,
        delimiter: ";",
      },
      {
        field: "Keywords",
        label: "Keywords",
        multivalue: true,
        delimiter: ";",
      },
      {
        field: "Authors",
        label: "Authors",
        multivalue: true,
        delimiter: ";",
      },
      {
        field: "Diseases (Annotated)",
        label: "Diseases (SciLite)",
        multivalue: true,
        delimiter: ";",
      },
      {
        field: "Genes / Proteins",
        label: "Genes / Proteins (SciLite)",
        multivalue: true,
        delimiter: ";",
      },
      {
        field: "Chemicals",
        label: "Chemicals (SciLite)",
        multivalue: true,
        delimiter: ";",
      },
      {
        field: "Cited Datasets",
        label: "Cited Datasets",
        multivalue: true,
        delimiter: ";",
      },
    ],
    [],
  );

  const fieldNames = useMemo(() => FACETS.map((f) => f.field), [FACETS]);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fieldNames as readonly (keyof GraphPublication & string)[]);

  // Index datasets/supplementary by PMC for the per-row resource chips
  const dsByPmc = useMemo(() => {
    const m = new Map<string, PubDataset[]>();
    for (const r of ds) {
      const k = pmcidFrom(r.source_url);
      if (!k) continue;
      const arr = m.get(k) ?? [];
      arr.push(r);
      m.set(k, arr);
    }
    return m;
  }, [ds]);
  const spByPmc = useMemo(() => {
    const m = new Map<string, Supplementary[]>();
    for (const r of sp) {
      const k = pmcidFrom(r.source_url);
      if (!k) continue;
      const arr = m.get(k) ?? [];
      arr.push(r);
      m.set(k, arr);
    }
    return m;
  }, [sp]);
  const scByPmc = useMemo(() => {
    const m = new Map<string, SciLiteAnnotation[]>();
    for (const r of sc) {
      const k = r["PMC ID"];
      if (!k) continue;
      const arr = m.get(k) ?? [];
      arr.push(r);
      m.set(k, arr);
    }
    return m;
  }, [sc]);

  // Rail filtering operates on augmented rows
  const filtered = useMemo(() => {
    return allAugmented.filter((p) => {
      for (const spec of FACETS) {
        if (!matchesFacet(p, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(p, SEARCH_FIELDS, query);
    });
  }, [allAugmented, FACETS, selections, query]);

  // Re-augment the *filtered* corpus with hub filter for the graph view
  const graphRows = useMemo<GraphPublication[]>(() => {
    const threshold = hubEnabled ? hubThresholdPct / 100 : 1.1;
    return applyToPubs(null, filtered, threshold);
  }, [filtered, hubEnabled, hubThresholdPct]);

  const columns = useMemo(
    () => [
      col.accessor("Title", {
        header: "Title",
        size: 320,
        cell: (info) => {
          const row = info.row.original;
          const pmcLink = row["PubMed Central Link"];
          const pmcid = pmcidFrom(pmcLink);
          return (
            <div>
              {pmcLink ? (
                <a
                  href={pmcLink}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent hover:underline"
                >
                  {info.getValue()}
                </a>
              ) : (
                info.getValue()
              )}
              {pmcid ? (
                <ResourceLinks
                  pmcid={pmcid}
                  ds={dsByPmc.get(pmcid) ?? []}
                  sp={spByPmc.get(pmcid) ?? []}
                  sc={scByPmc.get(pmcid) ?? []}
                />
              ) : (
                <div
                  className="mt-1 text-[10px] inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200"
                  title="No PubMed Central link available — datasets, supplementary files, and SciLite annotations cannot be linked to this publication."
                >
                  ⚠️ No PMC link
                </div>
              )}
            </div>
          );
        },
      }),
      col.accessor("Publication Date", {
        header: "Date",
        size: 30,
        cell: (info) => (
          <span className="text-xs text-slate-500 whitespace-nowrap">{info.getValue()}</span>
        ),
      }),
      col.accessor("Authors", {
        header: "Authors",
        size: 180,
        cell: (info) => (
          <span className="text-xs text-slate-600 line-clamp-4" title={info.getValue()}>{info.getValue()}</span>
        ),
      }),
      col.accessor("Affiliations", {
        header: "Affiliations",
        size: 200,
        cell: (info) => (
          <span className="text-xs text-slate-500 line-clamp-4" title={info.getValue()}>{info.getValue()}</span>
        ),
      }),
      col.accessor("Resource Name", {
        header: "Study",
        size: 160,
        cell: (info) => <span className="text-slate-700">{info.getValue()}</span>,
      }),
      col.accessor("Diseases Included", {
        header: "Diseases",
        size: 160,
        cell: (info) => <Chips value={info.getValue()} max={3} />,
      }),
      col.accessor("Coarse Data Modality", {
        header: "Modality",
        cell: (info) => <Chips value={info.getValue()} delimiter="," max={3} />,
      }),
      col.accessor("Keywords", {
        header: "Keywords",
        size: 160,
        cell: (info) => <Chips value={info.getValue()} delimiter=";" max={4} />,
      }),
      col.accessor("Abstract", {
        header: "Abstract",
        size: 400,
        cell: (info) => {
          const text = info.getValue();
          if (!text) return null;
          return (
            <p className="text-xs text-slate-700 line-clamp-5" title={text}>
              {text}
            </p>
          );
        },
      }),
      col.accessor("Data Completeness", {
        header: "Completeness",
        size: 110,
        cell: (info) => {
          const pct = Number(info.getValue()) || 0;
          const color = pct === 100 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-400" : "bg-red-400";
          return (
            <div className="flex flex-col gap-1" title={`${pct}% complete`}>
              <div className="w-full bg-slate-100 rounded h-1.5 overflow-hidden">
                <div className={`${color} h-full rounded`} style={{ width: `${pct}%` }} />
              </div>
              <span className="text-[10px] text-slate-500 tabular-nums">{pct}%</span>
            </div>
          );
        },
      }),
    ],
    [dsByPmc, spByPmc, scByPmc],
  );

  return (
    <PageShell
      query={query}
      onQueryChange={setQuery}
      title="Publications"
      count={
        pubs
          ? `${filtered.length.toLocaleString()} of ${pubs.length.toLocaleString()}`
          : "Loading…"
      }
      rail={
        <FilterRail<GraphPublication>
          specs={FACETS}
          rows={allAugmented}
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
      {pubs ? (
        <>
          <AnalysisPanel<GraphPublication>
            type="publications"
            filtered={filtered}
            total={pubs.length}
            prepare={(ps) => ps.map((p) => ({
              title: p.Title,
              authors: p.Authors?.split(";").slice(0, 3).join("; "),
              study: p["Resource Name"],
              keywords: p.Keywords,
              abstract: p.Abstract?.slice(0, 200),
              diseases: p["Diseases Included"],
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
            <ExportButton rows={filtered} filename="publications" />
          </div>
          {view === "table" ? (
            <DataTable<GraphPublication> rows={filtered} columns={columns} />
          ) : view === "browse" ? (
            <BrowseGrid>
              {filtered.map((p, i) => {
                const pmcid = pmcidFrom(p["PubMed Central Link"]);
                return (
                  <BrowseCard
                    key={i}
                    title={
                      p["PubMed Central Link"] ? (
                        <a href={p["PubMed Central Link"]} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                          {p.Title}
                        </a>
                      ) : p.Title
                    }
                    subtitle={`${p["Resource Name"]}${p["Publication Date"] ? ` · ${p["Publication Date"]}` : ""}`}
                  >
                    <Field label="Authors" value={p.Authors} expandable maxChars={120} />
                    <Field label="Affiliations" value={p.Affiliations} expandable maxChars={120} />
                    <Field label="Diseases" value={p["Diseases Included"]} chips />
                    <Field label="Modality" value={p["Coarse Data Modality"]} chips delimiter="," />
                    <Field label="Keywords" value={p.Keywords} chips delimiter="," />
                    {p.Abstract && (
                      <Section title="Abstract">
                        <Field label="" value={p.Abstract} expandable maxChars={300} />
                      </Section>
                    )}
                    {pmcid && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {(dsByPmc.get(pmcid) ?? []).length > 0 && (
                          <Link to={`/datasets?pmc=${pmcid}`} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100">
                            📦 {(dsByPmc.get(pmcid) ?? []).length} datasets
                          </Link>
                        )}
                        {(spByPmc.get(pmcid) ?? []).length > 0 && (
                          <Link to={`/datasets/supplementary?pmc=${pmcid}`} className="text-[10px] px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100">
                            📎 {(spByPmc.get(pmcid) ?? []).length} supplementary
                          </Link>
                        )}
                        {(scByPmc.get(pmcid) ?? []).length > 0 && (
                          <Link to={`/datasets/scilite?pmc=${pmcid}`} className="text-[10px] px-1.5 py-0.5 rounded bg-violet-50 text-violet-700 border border-violet-200 hover:bg-violet-100">
                            🏷️ {(scByPmc.get(pmcid) ?? []).length} annotations
                          </Link>
                        )}
                      </div>
                    )}
                  </BrowseCard>
                );
              })}
            </BrowseGrid>
          ) : (
            <>
              <GraphControls<GraphPublication>
                options={GRAPH_FIELD_OPTIONS}
                selected={edgeSelected}
                onSelectedChange={setEdgeSelected}
                minShared={minShared}
                onMinSharedChange={setMinShared}
                maxNodes={maxNodes}
                onMaxNodesChange={setMaxNodes}
                showAll={showAll}
                onShowAllChange={setShowAll}
                hubFilter={{
                  enabled: hubEnabled,
                  onEnabledChange: setHubEnabled,
                  threshold: hubThresholdPct,
                  onThresholdChange: setHubThresholdPct,
                }}
              />
              <KnowledgeGraph<GraphPublication>
                rows={graphRows}
                nodeField="Title"
                edgeFields={buildEdgeFields(GRAPH_FIELD_OPTIONS, edgeSelected)}
                minShared={minShared}
                maxNodes={maxNodes}
                hideDisconnected={!showAll}
                nodeInfo={(p) => (
                  <InfoList
                    rows={[
                      { label: "Title", value: p.Title },
                      { label: "Study", value: p["Resource Name"] },
                      { label: "PMID", value: p.PMID },
                      { label: "Diseases", value: p["Diseases Included"] },
                      { label: "Coarse modality", value: p["Coarse Data Modality"] },
                      { label: "Authors", value: p.Authors },
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
        <div className="text-sm text-slate-500">Loading publications…</div>
      )}
    </PageShell>
  );
}
