import { describe, expect, it } from "vitest";

import { cn, formatCurrency, formatDelta, initials, timeAgo } from "@/lib/utils";

describe("utils", () => {
  it("formats currency without decimals", () => {
    expect(formatCurrency(47328)).toBe("$47,328");
  });

  it("formats currency compactly", () => {
    expect(formatCurrency(156400, { compact: true })).toMatch(/\$1(56)?/);
  });

  it("formats deltas with sign", () => {
    expect(formatDelta(12.4)).toBe("+12.4%");
    expect(formatDelta(-3.1)).toBe("-3.1%");
  });

  it("computes initials", () => {
    expect(initials("Aziz Ben Amor")).toBe("AB");
    expect(initials("demo")).toBe("D");
  });

  it("merges classes without conflicts", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("handles null timestamps", () => {
    expect(timeAgo(null)).toBe("never");
  });
});
