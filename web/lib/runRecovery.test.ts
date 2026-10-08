import { describe, expect, it } from "vitest";
import { readRunBookmark, saveRunBookmark, recoveryParams, recoveryQueries, inheritedRunParams, paramsEqual } from "./runRecovery";

describe("run recovery", () => {
  it("releases explicit restored weights/lambda when basic controls change", () => {
    const saved = { budget: 0.05, k: 5, tier: 1 as const, maxPerScene: 7, alpha: 0.4, beta: 0.3, gamma: 0.3, lam: 0.83 };
    expect(inheritedRunParams(saved, { preset: false, diversity: false })).toEqual(saved);
    const changed = inheritedRunParams(saved, { preset: true, diversity: true });
    expect(changed).toEqual({ budget: 0.05, k: 5, tier: 1, maxPerScene: 7 });
    expect(paramsEqual(changed as never, saved)).toBe(false);
  });
  it("keeps camera query IDs until the user edits their text", () => {
    const queries = [{ id: "original-query", text: "night" }];
    expect(recoveryQueries({ budget: 0.05, queries }, ["night"])).toBe(queries);
    expect(recoveryQueries({ budget: 0.05, queries }, ["rain"])).toEqual(["rain"]);
  });
  it("retains dataset identity for bookmarks older than the recent-50 list", () => {
    const url = saveRunBookmark({ jobId: "old", datasetId: "dataset-old", selectionId: "saved", demo: false }, new URL("https://local/"));
    expect(readRunBookmark(url.split("?")[1])).toEqual({ jobId: "old", datasetId: "dataset-old", selectionId: "saved", demo: false });
  });
  it("URL takes precedence over local demo bookmark", () => {
    expect(readRunBookmark("?job=real&sel=stored", { getItem: () => JSON.stringify({ jobId: "mock-job", demo: true }) })).toEqual({ jobId: "real", selectionId: "stored", demo: false });
  });
  it("survives blocked and malformed storage", () => {
    expect(readRunBookmark("", { getItem: () => { throw new Error(); } })).toBeNull();
    expect(readRunBookmark("", { getItem: () => "{" })).toBeNull();
    expect(saveRunBookmark({ jobId: "real", demo: false }, new URL("https://local/?demo=1&sel=old"), { setItem: () => { throw new Error(); } })).toBe("/?job=real");
  });
  it("preserves selection and unrelated URL fields", () => {
    let value = "";
    const url = saveRunBookmark({ jobId: "j1", selectionId: "s1", demo: true }, new URL("https://local/?other=1"), { setItem: (_key, v) => { value = v; } });
    expect(readRunBookmark(url.split("?")[1])).toEqual({ jobId: "j1", selectionId: "s1", demo: true });
    expect(url).toContain("other=1");
    expect(readRunBookmark("", { getItem: () => value })).toEqual({ jobId: "j1", selectionId: "s1", demo: true });
  });
  it("restores resolved LiDAR quota and explicit weights without changing the score", () => {
    const p = recoveryParams({ budget: 0.08, m: 7, lam: 0.83, tier: 1, alpha: 0.4, beta: 0.3, gamma: 0.3 } as never, "lidar");
    expect(p).toMatchObject({ maxPerScene: 7, lam: 0.83, budget: 0.08, tier: 1, alpha: 0.4, beta: 0.3, gamma: 0.3 });
    expect(p).not.toHaveProperty("m");
    expect(recoveryParams({ budget: 0.05, m: null } as never, "lidar")).toMatchObject({ quotaOff: true, maxPerScene: null });
    expect(paramsEqual(p, { ...p })).toBe(true);
    expect(paramsEqual(p, { ...p, budget: 0.05 })).toBe(false);
  });
});
