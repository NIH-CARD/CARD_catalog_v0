import { describe, expect, it } from "vitest";
import { joinRows } from "./joinEngine";

interface Publication {
  "PubMed Central Link": string;
  Title: string;
}
interface Dataset {
  source_url: string;
  dataset_identifier: string;
}
interface CellularModel {
  Gene: string;
  "Product Code": string;
}
interface SciLiteAnnotation {
  "PMC ID": string;
  Exact: string;
  Type: string;
}

describe("joinRows", () => {
  it("connects rows on an exact scalar match (single-value join)", () => {
    const publications: Publication[] = [
      { "PubMed Central Link": "PMC111", Title: "Paper A" },
      { "PubMed Central Link": "PMC222", Title: "Paper B" },
    ];
    const datasets: Dataset[] = [
      { source_url: "PMC111", dataset_identifier: "DS1" },
      { source_url: "PMC999", dataset_identifier: "DS2" },
    ];

    const result = joinRows(
      publications,
      { field: "PubMed Central Link" },
      datasets,
      { field: "source_url" },
    );

    expect(result.matchCount).toBe(1);
    expect(result.matches[0].left.Title).toBe("Paper A");
    expect(result.matches[0].right.dataset_identifier).toBe("DS1");
    expect(result.matches[0].sharedValues).toEqual(["PMC111"]);
  });

  it("splits multi-value fields by delimiter before matching", () => {
    const cellModels: CellularModel[] = [
      { Gene: "APOE;TREM2", "Product Code": "JIPSC001" },
    ];
    const annotations: SciLiteAnnotation[] = [
      { "PMC ID": "PMC111", Exact: "TREM2", Type: "Gene_Proteins" },
      { "PMC ID": "PMC222", Exact: "MAPT", Type: "Gene_Proteins" },
    ];

    const result = joinRows(
      cellModels,
      { field: "Gene", delimiter: ";" },
      annotations,
      { field: "Exact" },
    );

    expect(result.matchCount).toBe(1);
    expect(result.matches[0].right["PMC ID"]).toBe("PMC111");
    expect(result.matches[0].sharedValues).toEqual(["TREM2"]);
  });

  it("matches case-insensitively and trims whitespace", () => {
    const left = [{ Gene: " apoe " }];
    const right = [{ Exact: "APOE" }];

    const result = joinRows(left, { field: "Gene" }, right, { field: "Exact" });

    expect(result.matchCount).toBe(1);
  });

  it("respects a non-default delimiter (e.g. comma for Coarse Data Modality)", () => {
    const left = [{ Modality: "clinical,genetics" }];
    const right = [{ Modality: "genetics" }];

    const result = joinRows(
      left,
      { field: "Modality", delimiter: "," },
      right,
      { field: "Modality" },
    );

    expect(result.matchCount).toBe(1);
  });

  it("returns zero matches when nothing overlaps, without throwing", () => {
    const left = [{ Gene: "APOE" }];
    const right = [{ Exact: "MAPT" }];

    const result = joinRows(left, { field: "Gene" }, right, { field: "Exact" });

    expect(result.matchCount).toBe(0);
    expect(result.matches).toEqual([]);
  });

  it("does not match two rows that both have a blank attribute value", () => {
    const left = [{ Gene: "" }];
    const right = [{ Exact: "" }];

    const result = joinRows(left, { field: "Gene" }, right, { field: "Exact" });

    expect(result.matchCount).toBe(0);
  });

  it("collapses multiple shared values between the same pair into one match", () => {
    const left = [{ Diseases: "Alzheimer's Disease;Dementia" }];
    const right = [{ Diseases: "Dementia;Alzheimer's Disease" }];

    const result = joinRows(
      left,
      { field: "Diseases", delimiter: ";" },
      right,
      { field: "Diseases", delimiter: ";" },
    );

    expect(result.matchCount).toBe(1);
    expect(result.matches[0].sharedValues.sort()).toEqual(
      ["Alzheimer's Disease", "Dementia"].sort(),
    );
  });

  it("produces one match per matching right row when a left row fans out", () => {
    const left = [{ Gene: "APOE" }];
    const right = [
      { Exact: "APOE", "PMC ID": "PMC1" },
      { Exact: "APOE", "PMC ID": "PMC2" },
      { Exact: "APOE", "PMC ID": "PMC3" },
    ];

    const result = joinRows(left, { field: "Gene" }, right, { field: "Exact" });

    expect(result.matchCount).toBe(3);
  });

  it("preserves the right-side row's original casing of the shared value in the output", () => {
    const left = [{ Gene: "Apoe" }];
    const right = [{ Exact: "APOE" }];

    const result = joinRows(left, { field: "Gene" }, right, { field: "Exact" });

    expect(result.matches[0].sharedValues).toEqual(["APOE"]);
  });
});
