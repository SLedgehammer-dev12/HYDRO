import { describe, expect, it } from "vitest";
import { downsampleLttb } from "./downsample";

describe("downsampleLttb", () => {
  it("returns original points when length <= threshold or threshold < 3", () => {
    const small = [
      { x: 0, y: 1 },
      { x: 1, y: 5 },
      { x: 2, y: 2 },
    ];
    expect(downsampleLttb(small, 10, (p) => p.x, (p) => p.y)).toEqual(small);
    expect(downsampleLttb(small, 2, (p) => p.x, (p) => p.y)).toEqual(small);
  });

  it("reduces 5000 points to threshold while preserving endpoints and global spike", () => {
    const data = Array.from({ length: 5000 }, (_, i) => ({
      x: i,
      y: Math.sin(i / 50) * 10 + (i === 2345 ? 250 : 0),
    }));

    const out = downsampleLttb(data, 500, (p) => p.x, (p) => p.y);
    expect(out).toHaveLength(500);
    expect(out[0]).toEqual(data[0]);
    expect(out[out.length - 1]).toEqual(data[data.length - 1]);
    expect(out.some((p) => p.x === 2345 && p.y > 200)).toBe(true);
  });
});
