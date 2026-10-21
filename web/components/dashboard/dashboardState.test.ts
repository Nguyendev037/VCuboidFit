import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { formatBytes } from "./dashboardState";

describe("formatBytes", () => {
  it("shows upload sizes in KB/MB/GB instead of raw bytes", () => {
    expect(formatBytes(2306867200)).toBe("2.1 GB");
    expect(formatBytes(10770344825)).toBe("10.0 GB");
    expect(formatBytes(194352619)).toBe("185 MB");
    expect(formatBytes(4096)).toBe("4 KB");
  });

  it("the per-file upload progress no longer prints raw bytes", () => {
    const src = readFileSync(new URL("./UploadPanel.tsx", import.meta.url), "utf-8");
    expect(src).not.toMatch(/\{i\.total\} B/);
    expect(src).toContain("{formatBytes(i.received)} / {formatBytes(i.total)}");
  });
});
