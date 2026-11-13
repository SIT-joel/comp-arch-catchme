import { describe, expect, it } from "vitest";
import { buildSegments, levelForXp } from "./graph";

describe("buildSegments — honesty of the live graph", () => {
  it("connects consecutive valid readings into one segment", () => {
    const segments = buildSegments([
      { t: 0, bpm: 70, valid: true, status: "valid" },
      { t: 2, bpm: 72, valid: true, status: "valid" },
      { t: 4, bpm: 74, valid: true, status: "valid" },
    ]);
    expect(segments).toHaveLength(1);
    expect(segments[0].points).toHaveLength(3);
  });

  it("breaks the line at an invalid reading instead of interpolating", () => {
    const segments = buildSegments([
      { t: 0, bpm: 70, valid: true, status: "valid" },
      { t: 2, bpm: 0, valid: false, status: "no_contact" },
      { t: 4, bpm: 74, valid: true, status: "valid" },
    ]);
    expect(segments).toHaveLength(2);
    expect(segments[0].points).toHaveLength(1);
    expect(segments[1].points).toHaveLength(1);
  });

  it("breaks the line when readings stop for more than 4 seconds", () => {
    const segments = buildSegments([
      { t: 0, bpm: 70, valid: true, status: "valid" },
      { t: 8, bpm: 74, valid: true, status: "valid" },
    ]);
    expect(segments).toHaveLength(2);
  });

  it("returns no segments when nothing valid exists", () => {
    expect(buildSegments([{ t: 0, bpm: 0, valid: false, status: "invalid_signal" }])).toHaveLength(0);
  });
});

describe("levelForXp", () => {
  it("follows 1 + floor(xp/100)", () => {
    expect(levelForXp(0)).toBe(1);
    expect(levelForXp(99)).toBe(1);
    expect(levelForXp(100)).toBe(2);
    expect(levelForXp(250)).toBe(3);
  });
});
