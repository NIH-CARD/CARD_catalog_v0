import * as XLSX from "xlsx";

function downloadFile(content: BlobPart, filename: string, mimeType: string) {
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

function toXLSXBuffer(rows: Record<string, unknown>[]): ArrayBuffer {
  const sheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, "Data");
  return XLSX.write(workbook, { bookType: "xlsx", type: "array" });
}

export function exportRows(
  rows: object[],
  filename: string,
  format: "csv" | "tsv" | "json" | "xlsx",
) {
  const cast = rows as Record<string, unknown>[];
  if (format === "json") {
    downloadFile(JSON.stringify(cast, null, 2), `${filename}.json`, "application/json");
  } else if (format === "csv") {
    downloadFile(toCSV(cast), `${filename}.csv`, "text/csv");
  } else if (format === "xlsx") {
    downloadFile(
      toXLSXBuffer(cast),
      `${filename}.xlsx`,
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
  } else {
    downloadFile(toTSV(cast), `${filename}.tsv`, "text/tab-separated-values");
  }
}
