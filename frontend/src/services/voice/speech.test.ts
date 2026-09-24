import { describe, expect, it } from "vitest";
import { speakable } from "./speech";

describe("speakable", () => {
  it("strips markdown so it isn't read aloud", () => {
    const md = "## Weather\n- **Tomorrow**: rain [source](https://x.y)\n\n```py\nprint(1)\n```\n> ⚠️ **Verification:** note";
    const out = speakable(md);
    expect(out).not.toMatch(/[#*`>[\]]/);
    expect(out).toContain("Tomorrow: rain source");
    expect(out).toContain("(code omitted)");
  });
});
