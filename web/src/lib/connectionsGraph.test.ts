import { describe, expect, it } from "vitest";
import {
  tablesInDomain,
  validDomainsFor,
  facetColumnsFor,
  nativeColumnsFor,
  mergedFieldKey,
  buildJoinIndex,
  joinedValue,
  buildWideRows,
  generateSql,
  toFacetFilters,
  dropHubValues,
  buildValueCountsReport,
  buildAbstractSample,
  type DagEdge,
} from "./connectionsGraph";

describe("tablesInDomain / validDomainsFor", () => {
  it("lists exactly the tables that carry a Publication lineage", () => {
    expect(tablesInDomain("publication")).toEqual([
      "Publications",
      "Datasets",
      "Supplementary Files",
      "Grants",
      "Software",
      "Models",
      "SciLite Annotations",
      "Human Cellular Models",
    ]);
  });

  it("lists exactly the tables that carry a Resource Name lineage, including Human Cellular Models via Linked Studies", () => {
    expect(tablesInDomain("resource")).toEqual([
      "Resources",
      "Code Repositories",
      "Publications",
      "Human Cellular Models",
    ]);
  });

  it("lists exactly Human Cellular Models and SciLite Annotations for concept", () => {
    expect(tablesInDomain("concept")).toEqual(["Human Cellular Models", "SciLite Annotations"]);
  });

  it("Datasets can only join Publications via the publication domain", () => {
    expect(validDomainsFor("Publications", "Datasets")).toEqual(["publication"]);
  });

  it("Human Cellular Models can join Publications via publication or resource, not concept", () => {
    expect(validDomainsFor("Publications", "Human Cellular Models")).toEqual(["publication", "resource"]);
  });

  it("returns no valid domain for a pair that shares none", () => {
    expect(validDomainsFor("Resources", "Grants")).toEqual([]);
  });
});

describe("facetColumnsFor", () => {
  it("matches Publications' own page facets exactly - not every column", () => {
    expect(facetColumnsFor("Publications").map((c) => c.field)).toEqual([
      "Resource Name",
      "Keywords",
      "Authors",
      "Publication Year",
    ]);
  });

  it("excludes raw Publication Date - that page only ever facets on the aggregated Publication Year", () => {
    expect(facetColumnsFor("Publications").map((c) => c.field)).not.toContain("Publication Date");
  });
});

describe("nativeColumnsFor", () => {
  it("keeps an external resource's own identifier even though it's unique per row", () => {
    expect(nativeColumnsFor("Datasets").map((c) => c.field)).toContain("dataset_identifier");
    expect(nativeColumnsFor("Software").map((c) => c.field)).toContain("url");
  });

  it("excludes domain fields and catalog-internal identifiers", () => {
    expect(nativeColumnsFor("Publications").map((c) => c.field)).not.toContain("Resource Name");
    expect(nativeColumnsFor("Human Cellular Models").map((c) => c.field)).not.toContain("Product Code");
  });
});

describe("mergedFieldKey", () => {
  it("namespaces a merged column by its source table", () => {
    expect(mergedFieldKey("Datasets", "dataset_identifier")).toBe("Datasets: dataset_identifier");
  });
});

describe("buildJoinIndex / joinedValue", () => {
  it("indexes a merge-source table by its domain key and looks values up by a base row's own key", () => {
    const index = buildJoinIndex("Grants", "funder_name", "publication", [
      { funder_name: "NIH", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/" },
    ]);
    expect(joinedValue("PMC1234567", index)).toBe("NIH");
  });

  it("aggregates multiple matches with '; ' (STRING_AGG semantics)", () => {
    const index = buildJoinIndex("Grants", "funder_name", "publication", [
      { funder_name: "NIH", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" },
      { funder_name: "NIA", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" },
    ]);
    expect(joinedValue("PMC1", index)).toBe("NIH; NIA");
  });

  it("returns empty when nothing matches", () => {
    const index = buildJoinIndex("Grants", "funder_name", "publication", [
      { funder_name: "NIH", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9999999/" },
    ]);
    expect(joinedValue("PMC1234567", index)).toBe("");
  });
});

describe("buildWideRows", () => {
  it("merges one edge's table into a surviving Publication's row, preserving its own columns", () => {
    const pubRows = [
      { PMID: "1", Title: "Paper A", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", DOI: "" },
      { PMID: "2", Title: "Paper B", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2/", DOI: "" },
    ];
    const edges: DagEdge[] = [{ table: "Grants", domain: "publication", columns: ["funder_name"] }];
    const rawByTable = {
      Grants: [
        { funder_name: "NIH", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" },
        { funder_name: "NIA", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" },
      ],
    };
    const wide = buildWideRows(pubRows, edges, rawByTable);
    // PMC2 has no matching grant - dropped by the default zero-hit filter (see below).
    expect(wide).toHaveLength(1);
    expect(wide[0]["Grants: funder_name"]).toBe("NIH; NIA");
    expect(wide[0].Title).toBe("Paper A"); // original Publications columns preserved
  });

  it("merges multiple edges independently onto the same rows", () => {
    const pubRows = [
      { PMID: "1", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", DOI: "" },
    ];
    const edges: DagEdge[] = [
      { table: "Grants", domain: "publication", columns: ["funder_name"] },
      { table: "Software", domain: "publication", columns: ["software_name"] },
    ];
    const rawByTable = {
      Grants: [{ funder_name: "NIH", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" }],
      Software: [{ software_name: "PLINK", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" }],
    };
    const wide = buildWideRows(pubRows, edges, rawByTable);
    expect(wide[0]["Grants: funder_name"]).toBe("NIH");
    expect(wide[0]["Software: software_name"]).toBe("PLINK");
  });

  it("returns rows unchanged (just Publications' own fields) with no edges", () => {
    const pubRows = [{ PMID: "1", Title: "Paper A" }];
    expect(buildWideRows(pubRows, [], {})).toEqual(pubRows);
  });

  it("drops a Publication with zero hits across all edges, by default - no toggle needed", () => {
    const pubRows = [
      { PMID: "1", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", DOI: "" },
      { PMID: "2", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2/", DOI: "" },
    ];
    const edges: DagEdge[] = [{ table: "Grants", domain: "publication", columns: ["funder_name"] }];
    const rawByTable = {
      Grants: [{ funder_name: "NIH", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" }],
    };
    const wide = buildWideRows(pubRows, edges, rawByTable);
    expect(wide).toHaveLength(1);
    expect(wide[0].PMID).toBe("1");
  });

  it("chains edges - a Publication is dropped if ANY edge has no hit, not just if all edges miss", () => {
    const pubRows = [{ PMID: "1", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", DOI: "" }];
    const edges: DagEdge[] = [
      { table: "Grants", domain: "publication", columns: ["funder_name"] },
      { table: "Software", domain: "publication", columns: ["software_name"] },
    ];
    const rawByTable = {
      Grants: [{ funder_name: "NIH", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" }],
      Software: [], // no software data - this edge alone contributes nothing
    };
    expect(buildWideRows(pubRows, edges, rawByTable)).toHaveLength(0);
  });

  it("keeps a Publication that has a hit on every edge in the chain", () => {
    const pubRows = [{ PMID: "1", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", DOI: "" }];
    const edges: DagEdge[] = [
      { table: "Grants", domain: "publication", columns: ["funder_name"] },
      { table: "Software", domain: "publication", columns: ["software_name"] },
    ];
    const rawByTable = {
      Grants: [{ funder_name: "NIH", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" }],
      Software: [{ software_name: "PLINK", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" }],
    };
    const wide = buildWideRows(pubRows, edges, rawByTable);
    expect(wide).toHaveLength(1);
    expect(wide[0]["Grants: funder_name"]).toBe("NIH");
    expect(wide[0]["Software: software_name"]).toBe("PLINK");
  });

  it("a hit in any ONE column of an edge is enough to count as a hit", () => {
    const pubRows = [{ PMID: "1", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", DOI: "" }];
    const edges: DagEdge[] = [{ table: "Grants", domain: "publication", columns: ["funder_name", "grant_number"] }];
    const rawByTable = {
      // grant_number is blank on this row, but funder_name matches - should still count as a hit.
      Grants: [{ funder_name: "NIH", grant_number: "", source_url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/" }],
    };
    expect(buildWideRows(pubRows, edges, rawByTable)).toHaveLength(1);
  });

  it("drops every Publication when no edge matches anything at all", () => {
    const pubRows = [
      { PMID: "1", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", DOI: "" },
      { PMID: "2", "PubMed Central Link": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2/", DOI: "" },
    ];
    const edges: DagEdge[] = [{ table: "Grants", domain: "publication", columns: ["funder_name"] }];
    expect(buildWideRows(pubRows, edges, { Grants: [] })).toHaveLength(0);
  });
});

describe("generateSql", () => {
  it("renders a plain SELECT p.* with no edges", () => {
    const sql = generateSql([]);
    expect(sql).toContain("SELECT");
    expect(sql).toContain("p.*");
    expect(sql).toContain("FROM Publications p");
    expect(sql).not.toContain("LEFT JOIN");
  });

  it("renders one INNER JOIN and one STRING_AGG column per edge", () => {
    const edges: DagEdge[] = [{ table: "Datasets", domain: "publication", columns: ["dataset_identifier"] }];
    const sql = generateSql(edges);
    expect(sql).toContain('INNER JOIN "Datasets"');
    expect(sql).toContain("STRING_AGG");
    expect(sql).toContain('"Datasets: dataset_identifier"');
    expect(sql).toContain("GROUP BY");
  });

  it("chains a second edge's INNER JOIN after the first - narrowing, not a separate HAVING", () => {
    const edges: DagEdge[] = [
      { table: "Grants", domain: "publication", columns: ["funder_name"] },
      { table: "Software", domain: "publication", columns: ["software_name"] },
    ];
    const sql = generateSql(edges);
    expect(sql).toContain('INNER JOIN "Grants" t1');
    expect(sql).toContain('INNER JOIN "Software" t2');
    expect(sql).not.toContain("HAVING");
  });

  it("renders Publications' own filters as a WHERE clause on p", () => {
    const sql = generateSql([], [{ field: "Publication Year", values: ["2024"] }]);
    expect(sql).toContain(`WHERE p."Publication Year" IN ('2024')`);
  });

  it("renders a merge-source table's filters as a pre-join subquery, not a WHERE after the JOIN", () => {
    const edges: DagEdge[] = [{ table: "Grants", domain: "publication", columns: ["funder_name"] }];
    const sql = generateSql(edges, [], { Grants: [{ field: "funder_name", values: ["NIH"] }] });
    expect(sql).toContain(`SELECT * FROM "Grants" WHERE t1."funder_name" IN ('NIH')`);
    expect(sql).toContain("INNER JOIN (");
    // the filter appears exactly once, inside the subquery - not duplicated as a post-join WHERE
    expect(sql.match(/WHERE t1\."funder_name"/g)).toHaveLength(1);
  });

  it("combines Publications' own WHERE with edge subqueries and multiple selected values", () => {
    const edges: DagEdge[] = [{ table: "Grants", domain: "publication", columns: ["funder_name"] }];
    const sql = generateSql(
      edges,
      [{ field: "Publication Year", values: ["2023", "2024"] }],
      { Grants: [{ field: "funder_name", values: ["NIH"] }] },
    );
    expect(sql).toContain(`WHERE p."Publication Year" IN ('2023', '2024')`);
    expect(sql).toContain(`WHERE t1."funder_name" IN ('NIH')`);
  });

  it("escapes a single quote in a filter value", () => {
    const sql = generateSql([], [{ field: "Keywords", values: ["Alzheimer's disease"] }]);
    expect(sql).toContain(`'Alzheimer''s disease'`);
  });
});

describe("toFacetFilters", () => {
  it("drops a facet with nothing selected", () => {
    expect(toFacetFilters({ Keywords: new Set(), Authors: new Set(["Smith J"]) })).toEqual([
      { field: "Authors", values: ["Smith J"] },
    ]);
  });

  it("returns an empty array for undefined selections", () => {
    expect(toFacetFilters(undefined)).toEqual([]);
  });
});

describe("dropHubValues", () => {
  it("is a no-op when threshold >= 1", () => {
    const rows = [{ Concept: "APOE" }, { Concept: "APOE" }];
    expect(dropHubValues(rows, 1, ["Concept"])).toEqual(rows);
  });

  it("is a no-op when no fields are given", () => {
    const rows = [{ Concept: "APOE" }];
    expect(dropHubValues(rows, 0.3, [])).toEqual(rows);
  });

  it("strips a value present in more than the threshold fraction of rows", () => {
    const rows = [{ Concept: "APOE" }, { Concept: "APOE" }, { Concept: "APOE" }, { Concept: "TREM2" }];
    const result = dropHubValues(rows, 0.5, ["Concept"]); // APOE is in 75% of rows
    expect(result.map((r) => r.Concept)).toEqual(["", "", "", "TREM2"]);
  });

  it("keeps a value at or under the threshold", () => {
    const rows = [{ Concept: "APOE" }, { Concept: "TREM2" }, { Concept: "GRN" }, { Concept: "SORL1" }];
    const result = dropHubValues(rows, 0.5, ["Concept"]); // every value appears in only 25% of rows
    expect(result.map((r) => r.Concept)).toEqual(["APOE", "TREM2", "GRN", "SORL1"]);
  });

  it("only strips the hub value, keeping other values in the same multivalue field", () => {
    const rows = [{ Concept: "APOE;TREM2" }, { Concept: "APOE" }, { Concept: "APOE" }, { Concept: "GRN" }];
    const result = dropHubValues(rows, 0.5, ["Concept"]); // APOE in 75%
    expect(result.map((r) => r.Concept)).toEqual(["TREM2", "", "", "GRN"]);
  });
});

describe("buildValueCountsReport", () => {
  it("counts a multivalue field's distinct values across all rows, sorted descending", () => {
    const rows = [{ "Resource Name": "AMP-PD" }, { "Resource Name": "AMP-PD" }, { "Resource Name": "ADNI" }];
    const report = buildValueCountsReport(rows, [{ field: "Resource Name" }], ["Grants"]);
    expect(report).toContain("## Resource Name");
    expect(report).toContain("- AMP-PD: 2");
    expect(report).toContain("- ADNI: 1");
    // AMP-PD (2) should be listed before ADNI (1) - sorted descending
    expect(report.indexOf("AMP-PD: 2")).toBeLessThan(report.indexOf("ADNI: 1"));
  });

  it("skips a column marked skip (free text)", () => {
    const rows = [{ Title: "A unique paper title" }];
    const report = buildValueCountsReport(rows, [{ field: "Title", skip: true }], []);
    expect(report).not.toContain("## Title");
  });

  it("splits a semicolon-delimited multivalue field before counting", () => {
    const rows = [{ Authors: "Smith J;Doe J" }, { Authors: "Smith J" }];
    const report = buildValueCountsReport(rows, [{ field: "Authors", delimiter: ";" }], []);
    expect(report).toContain("- Smith J: 2");
    expect(report).toContain("- Doe J: 1");
  });

  it("caps at topN and notes how many more distinct values exist", () => {
    const rows = Array.from({ length: 20 }, (_, i) => ({ Field: `v${i}` }));
    const report = buildValueCountsReport(rows, [{ field: "Field" }], [], 5);
    expect(report).toContain("...and 15 more distinct value(s)");
  });

  it("lists the merged tables and total row count in the header", () => {
    const report = buildValueCountsReport([{}, {}], [], ["Grants", "Datasets"]);
    expect(report).toContain("**2 Publications** merged with: Grants, Datasets");
  });

  it("notes no merges when the table list is empty", () => {
    const report = buildValueCountsReport([], [], []);
    expect(report).toContain("merged with: (none)");
  });
});

describe("buildAbstractSample", () => {
  it("includes full title and abstract text for genuine comparative reading", () => {
    const rows = [{ Title: "ROSMAP study", "Resource Name": "ROSMAP", Abstract: "We profiled microglia in..." }];
    const sample = buildAbstractSample(rows);
    expect(sample).toContain("### ROSMAP study");
    expect(sample).toContain("Resource: ROSMAP");
    expect(sample).toContain("We profiled microglia in...");
  });

  it("skips a row with no abstract", () => {
    const rows = [{ Title: "No abstract here" }];
    expect(buildAbstractSample(rows)).toBe("");
  });

  it("caps at maxRows and discloses that it's a partial sample", () => {
    const rows = Array.from({ length: 10 }, (_, i) => ({ Title: `Paper ${i}`, Abstract: `Abstract ${i}` }));
    const sample = buildAbstractSample(rows, 3);
    expect(sample).toContain("Paper 0");
    expect(sample).toContain("Paper 2");
    expect(sample).not.toContain("Paper 3");
    expect(sample).toContain("Showing the first 3 of 10 rows");
  });

  it("doesn't disclose a partial sample when every row fits under maxRows", () => {
    const rows = [{ Title: "Paper 0", Abstract: "Abstract 0" }];
    expect(buildAbstractSample(rows, 3)).not.toContain("Showing the first");
  });

  it("returns empty string when nothing has an abstract", () => {
    expect(buildAbstractSample([{ Title: "A" }, { Title: "B" }])).toBe("");
  });
});
