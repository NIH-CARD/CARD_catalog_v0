function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function toCSV(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const escape = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return [
    headers.map(escape).join(","),
    ...rows.map((r) => headers.map((h) => escape(r[h])).join(",")),
  ].join("\n");
}

function toTSV(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  return [
    headers.join("\t"),
    ...rows.map((r) => headers.map((h) => String(r[h] ?? "")).join("\t")),
  ].join("\n");
}

export function exportRows(
  rows: object[],
  filename: string,
  format: "csv" | "tsv" | "json",
) {
  const cast = rows as Record<string, unknown>[];
  if (format === "json") {
    downloadFile(JSON.stringify(cast, null, 2), `${filename}.json`, "application/json");
  } else if (format === "csv") {
    downloadFile(toCSV(cast), `${filename}.csv`, "text/csv");
  } else {
    downloadFile(toTSV(cast), `${filename}.tsv`, "text/tab-separated-values");
  }
}
