/** Node colorings for KnowledgeGraph - the FAIR scales the legacy Streamlit graph used. */

export interface ColorLegend {
  title: string;
  items: { label: string; color: string }[];
}

const UNKNOWN = "#cbd5e1";

// Same Excellent / Strong / Good reading of "FAIR Compliance Notes" as the paper's figure 4.
const FAIR_LEVELS = [
  { label: "Excellent", color: "#166534" },
  { label: "Strong", color: "#22a05a" },
  { label: "Good", color: "#9be3a8" },
];

export const FAIR_LEVEL_LEGEND: ColorLegend = {
  title: "FAIR compliance",
  items: [...FAIR_LEVELS, { label: "Not rated", color: UNKNOWN }],
};

export function fairLevelColor(notes: string | undefined): string {
  const lower = (notes ?? "").toLowerCase();
  return FAIR_LEVELS.find((l) => lower.includes(l.label.toLowerCase()))?.color ?? UNKNOWN;
}

const FAIR_SCORE_BINS = [
  { min: 8, label: "8–10", color: "#166534" },
  { min: 6, label: "6–7", color: "#22a05a" },
  { min: 4, label: "4–5", color: "#e6c84f" },
  { min: 0, label: "0–3", color: "#e8833a" },
];

export const FAIR_SCORE_LEGEND: ColorLegend = {
  title: "FAIR score",
  items: [...FAIR_SCORE_BINS.map(({ label, color }) => ({ label, color })), { label: "No score", color: UNKNOWN }],
};

export function fairScoreColor(score: string | undefined): string {
  const n = Number.parseFloat(score ?? "");
  if (Number.isNaN(n)) return UNKNOWN;
  return FAIR_SCORE_BINS.find((b) => n >= b.min)?.color ?? UNKNOWN;
}
