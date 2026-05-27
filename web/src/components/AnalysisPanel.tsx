import { useState } from "react";
import { type AnalysisType, useAnalysis } from "../lib/useAnalysis";
import { exportRows } from "../lib/export";

const DESCRIPTIONS: Record<AnalysisType, string[]> = {
  resources: [
    "Analyzes patterns across your selected/filtered resources",
    "Identifies common data modalities, disease focuses, and research trends",
    "Highlights gaps and opportunities in the dataset landscape",
    "Provides actionable recommendations for researchers",
  ],
  publications: [
    "Analyzes major research themes across your selected/filtered publications",
    "Identifies active research areas and collaboration trends",
    "Highlights key findings and emerging directions",
  ],
  code: [
    "Analyzes programming languages, technologies, and research focus across repositories",
    "Identifies code quality patterns and FAIR compliance trends",
    "Highlights collaboration and reusability opportunities",
  ],
  cellular_models: [
    "Disease & Gene Distribution: Compare subset to full catalog",
    "Gene Function Analysis: Insights from gene/variant descriptions",
    "Pathway & Interaction Analysis: Biological pathways and protein interactions",
    "Publications of Interest: Recent relevant research focused on neurodegeneration",
    "Utility for Functional & Precision Medicine: CRISPR models and clinical insights",
  ],
  pub_datasets: [
    "Data Repository Landscape: Most cited repositories and concentration patterns",
    "Dataset Citation Types & Context: Primary vs. secondary use, and how datasets were used",
    "Extraction Quality & Red Flags: Suspect records, garbled fields, and implausible links",
    "Data Reuse & Access Patterns: Cross-study reuse and open vs. controlled access",
  ],
};

interface Props<T extends object> {
  type: AnalysisType;
  filtered: T[];
  total: number;
  prepare: (rows: T[]) => object[];
  maxRows?: number;
}

export function AnalysisPanel<T extends object>({
  type,
  filtered,
  total,
  prepare,
  maxRows = 50,
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const { text, loading, error, analyze } = useAnalysis();

  const handleAnalyze = () => {
    const sample = prepare(filtered.slice(0, maxRows));
    analyze(type, sample, filtered.length, total);
  };

  const handleDownload = () => {
    exportRows([{ analysis: text }], `${type}_analysis`, "json");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${type}_analysis.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="border border-slate-200 rounded bg-white mb-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        <span>🤖 AI Analysis</span>
        <span className="text-slate-400 text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-slate-100">
          <div className="flex flex-wrap items-center gap-2 mt-3 mb-3">
            <button
              onClick={handleAnalyze}
              disabled={loading || filtered.length === 0}
              className="px-3 py-1.5 text-sm rounded bg-accent text-white hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Analyzing…" : "Analyze"}
            </button>
            {text && !loading && (
              <button
                onClick={handleDownload}
                className="px-3 py-1.5 text-sm rounded border border-slate-200 text-slate-600 hover:bg-slate-50"
              >
                ↓ Download .txt
              </button>
            )}
            <span className="text-xs text-slate-400">
              {filtered.length === 0
                ? "No rows to analyze"
                : filtered.length <= maxRows
                  ? `Ready to analyze ${filtered.length.toLocaleString()} rows`
                  : `Ready to analyze top ${maxRows.toLocaleString()} of ${filtered.length.toLocaleString()} filtered rows`}
            </span>
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 mb-2">
              {error}
            </div>
          )}

          {!text && !loading && !error && (
            <div className="text-sm text-slate-600 bg-slate-50 rounded border border-slate-200 p-4">
              <p className="font-medium text-slate-700 mb-2">The analysis includes:</p>
              <ul className="space-y-1">
                {DESCRIPTIONS[type].map((line, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-slate-400 shrink-0">•</span>
                    <span dangerouslySetInnerHTML={{ __html: line.replace(/^([^:]+:)/, "<strong>$1</strong>") }} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(text || loading) && (
            <pre className="whitespace-pre-wrap font-sans text-sm text-slate-700 leading-relaxed bg-slate-50 rounded border border-slate-200 p-4 max-h-[600px] overflow-y-auto">
              {text}
              {loading && <span className="animate-pulse">▌</span>}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
