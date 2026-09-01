import { describe, expect, it } from "vitest";
import { findColumn, findTable, suggestJoin, TABLE_REGISTRY } from "./tableRegistry";

describe("TABLE_REGISTRY", () => {
  it("has an entry for all ten catalog tables", () => {
    expect(TABLE_REGISTRY).toHaveLength(10);
    expect(TABLE_REGISTRY.map((t) => t.name)).toEqual([
      "Resources",
      "Publications",
      "Code Repositories",
      "Datasets",
      "Supplementary Files",
      "Grants",
      "Software",
      "Models",
      "SciLite Annotations",
      "Human Cellular Models",
    ]);
  });

  it("findTable looks up by exact name", () => {
    expect(findTable("Publications")?.route).toBe("/publications");
    expect(findTable("Nonexistent")).toBeUndefined();
  });

  it("findColumn reports the correct multivalue/delimiter for a known field", () => {
    expect(findColumn("Publications", "Resource Name")).toEqual({
      field: "Resource Name",
      multivalue: true,
      delimiter: ";",
    });
    expect(findColumn("Resources", "Coarse Data Modality")?.delimiter).toBe(",");
  });

  it("no longer lists Resource-derived columns on Publications or Code Repositories (dropped as foreign)", () => {
    expect(findColumn("Publications", "Diseases Included")).toBeUndefined();
    expect(findColumn("Publications", "Coarse Data Modality")).toBeUndefined();
    expect(findColumn("Publications", "Granular Data Modality")).toBeUndefined();
    expect(findColumn("Publications", "Diseases (Annotated)")).toBeUndefined();
    expect(findColumn("Publications", "Genes / Proteins")).toBeUndefined();
    expect(findColumn("Publications", "Chemicals")).toBeUndefined();
    expect(findColumn("Publications", "Cited Datasets")).toBeUndefined();
    expect(findColumn("Code Repositories", "Diseases Included")).toBeUndefined();
  });

  it("defaults unlisted-evidence fields to single-value", () => {
    expect(findColumn("Resources", "Access URL")?.multivalue).toBe(false);
  });
});

describe("suggestJoin", () => {
  it("finds the known-good pairing regardless of argument order", () => {
    const forward = suggestJoin("Datasets", "Publications");
    const backward = suggestJoin("Publications", "Datasets");

    expect(forward).toEqual({
      tableA: "Datasets",
      fieldA: "source_url",
      tableB: "Publications",
      fieldB: "PubMed Central Link",
    });
    expect(backward).toEqual(forward);
  });

  it("suggests Linked Publications (not Gene/dbSNP) for Human Cellular Models to Publications", () => {
    const suggestion = suggestJoin("Human Cellular Models", "Publications");
    expect(suggestion).toEqual({
      tableA: "Human Cellular Models",
      fieldA: "Linked Publications",
      tableB: "Publications",
      fieldB: "PubMed Central Link",
      extract: "pmcid",
    });
  });

  it("returns undefined for Human Cellular Models to SciLite Annotations (needs raw per-row SciLite matching)", () => {
    expect(suggestJoin("Human Cellular Models", "SciLite Annotations")).toBeUndefined();
  });

  it("does not suggest Code Repositories' Source as a Publications join (only ~55% coverage)", () => {
    const suggestion = suggestJoin("Code Repositories", "Publications");
    expect(suggestion).toBeUndefined();
  });

  it("returns undefined for a table pair with no known relationship", () => {
    expect(suggestJoin("Grants", "Human Cellular Models")).toBeUndefined();
  });
});
