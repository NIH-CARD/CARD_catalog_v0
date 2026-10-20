import { describe, expect, it } from "vitest";
import { fairLevel, fairLevelColor } from "./graphColors";

describe("fairLevel", () => {
  it("reads the level from the start of the FAIR notes", () => {
    expect(fairLevel("Excellent FAIR compliance: open data")).toBe("Excellent");
    expect(fairLevel("  strong compliance with ...")).toBe("Strong");
    expect(fairLevel("Good: basic access")).toBe("Good");
  });

  it("ignores a level mentioned later in the note", () => {
    expect(fairLevel("Strong overall, though not excellent metadata")).toBe("Strong");
  });

  it("returns Not rated for empty or unrecognised notes", () => {
    expect(fairLevel("")).toBe("Not rated");
    expect(fairLevel(undefined)).toBe("Not rated");
    expect(fairLevel("Pending review")).toBe("Not rated");
  });

  it("colours graph nodes from the same level", () => {
    expect(fairLevelColor("Strong overall, though not excellent")).toBe(fairLevelColor("Strong"));
  });
});
