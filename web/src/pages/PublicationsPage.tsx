import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { createColumnHelper } from "@tanstack/react-table";
import { Chips } from "../components/Chips";
import { DataTable } from "../components/DataTable";
import { FilterRail } from "../components/FilterRail";
import { GraphControls, buildEdgeFields } from "../components/GraphControls";
import { InfoList } from "../components/HoverInfo";
import { KnowledgeGraph } from "../components/KnowledgeGraph";
import { PageShell } from "../components/PageShell";
import { matchesFacet, matchesQuery } from "../lib/filter";
import { loadPubDatasets, loadPublications, loadSciLite, loadSupplementary } from "../lib/loaders";
import { pmcidFrom } from "../lib/loadPublications";
import {
  buildGraphData,
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

const FACETS: readonly FacetSpec<Publication>[] = [
  { field: "Diseases Included", multivalue: true },
  { field: "Coarse Data Modality", multivalue: true, delimiter: "," },
  { field: "Granular Data Modality", multivalue: true },
  { field: "Resource Name", multivalue: false },
];

const SEARCH_FIELDS: (keyof Publication & string)[] = [
  "Title",
  "Abstract",
  "Authors",
  "Keywords",
  "Resource Name",
];

const GRAPH_FIELD_OPTIONS = PAPER_GRAPH_FIELD_OPTIONS;

const col = createColumnHelper<Publication>();

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
  const [view, setView] = useState<"table" | "graph">("table");
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

  const fields = useMemo(() => FACETS.map((f) => f.field), []);
  const { selections, query, setFacet, setQuery, clearAll, totalSelected } =
    useFacets(fields as readonly (keyof Publication & string)[]);

  // Index datasets/supplementary by PMC for fast per-row counts
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

  const filtered = useMemo(() => {
    if (!pubs) return [];
    return pubs.filter((p) => {
      for (const spec of FACETS) {
        if (!matchesFacet(p, spec, selections[spec.field] ?? new Set())) return false;
      }
      return matchesQuery(p, SEARCH_FIELDS, query);
    });
  }, [pubs, selections, query]);

  // Augment filtered publications with paper-grounded concept fields for the KG.
  // Hub filter applies to the *filtered* corpus so thresholds adapt to slices.
  const graphData = useMemo(() => {
    if (!pubs) return null;
    const threshold = hubEnabled ? hubThresholdPct / 100 : 1.1;
    return buildGraphData(filtered, sc, ds, threshold);
  }, [pubs, filtered, sc, ds, hubEnabled, hubThresholdPct]);

  const columns = useMemo(
    () => [
      col.accessor("PMID", {
        header: "PMID",
        cell: (info) => (
          <span className="font-mono text-xs text-slate-600">{info.getValue()}</span>
        ),
      }),
      col.accessor("Title", {
        header: "Title",
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
              <ResourceLinks
                pmcid={pmcid}
                ds={dsByPmc.get(pmcid) ?? []}
                sp={spByPmc.get(pmcid) ?? []}
                sc={scByPmc.get(pmcid) ?? []}
              />
            </div>
          );
        },
      }),
      col.accessor("Resource Name", {
        header: "Study",
        cell: (info) => <span className="text-slate-700">{info.getValue()}</span>,
      }),
      col.accessor("Diseases Included", {
        header: "Diseases",
        cell: (info) => <Chips value={info.getValue()} />,
      }),
      col.accessor("Coarse Data Modality", {
        header: "Modality",
        cell: (info) => <Chips value={info.getValue()} delimiter="," />,
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
        <FilterRail<Publication>
          specs={FACETS}
          rows={pubs ?? []}
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
            <DataTable<Publication> rows={filtered} columns={columns} />
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
                rows={graphData?.rows ?? []}
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
                valueMeta={(field, value) => {
                  if (field === "Cited Datasets") {
                    const meta = graphData?.datasetMeta.get(value);
                    return (
                      <div>
                        <div className="font-medium">{value}</div>
                        {meta?.repository && (
                          <div className="text-[10px] text-slate-500">
                            {meta.repository}
                          </div>
                        )}
                      </div>
                    );
                  }
                  const meta = graphData?.conceptMeta.get(value);
                  return (
                    <div>
                      <div className="font-medium">
                        {meta?.name || value}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {meta?.type}
                      </div>
                      <div className="text-[10px] text-slate-400 break-all">
                        {value}
                      </div>
                    </div>
                  );
                }}
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
