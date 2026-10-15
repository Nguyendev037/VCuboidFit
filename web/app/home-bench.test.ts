import { renderToStaticMarkup } from "react-dom/server";
import { readFile, access } from "node:fs/promises";
import { beforeEach, expect, it, vi } from "vitest";
import React from "react";
import { Benchmark } from "@/components/home/Benchmark";
import { loadDemoBench } from "@/lib/server/demoBench";

// Assert the benchmark contract independently of the landing hero and sample media.
async function Home() {
  const { bench, figureUrl } = await loadDemoBench();
  return React.createElement("section", null, "Số đo", React.createElement(Benchmark, { bench, figureUrl }));
}

vi.mock("node:fs/promises", () => ({ readFile: vi.fn(), access: vi.fn() }));

const fixture = {
  schema: "vcf-demo-bench-v1",
  source: { run_id: "fixture-T", repo_sha: "fixture", code_sha: "fixture", prereg_sha256: "fixture", final_config_sha256: "fixture", report_sha256: "fixture" },
  label: "T pool", pool: 1389, scenes: 10, capture_primary: "rare_form", budget_B: 21,
  methods: {
    M0: { name: "Random", iy: 0.1, ci_lo: 0.05, ci_hi: 0.15, status: "ok" },
    M1: { name: "M1", iy: 0.2, ci_lo: 0.1, ci_hi: 0.3, status: "ok" },
    M2: { name: "M2", iy: 0.25, ci_lo: 0.12, ci_hi: 0.4, status: "ok" },
    M3: { name: "M3", iy: 0.3, ci_lo: 0.14, ci_hi: 0.45, status: "ok" },
  },
  primary: { pair: "M3-M0", delta: 0.2, ci_lo: -0.01, ci_hi: 0.4, conclusion: "not shown / underpowered" },
  reachability: { radius_m: 1, n_targets: 0, methods: {} },
  figures: ["fig_iy_budget.png"],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(access).mockResolvedValue(undefined);
});

it("formats every IY and CI to three decimals without changing the source", async () => {
  const data = structuredClone(fixture);
  data.methods.M0.iy = 0.08666666666666666;
  data.primary.delta = -0.0004;
  const source = JSON.stringify(data);
  vi.mocked(readFile).mockResolvedValue(source);
  const html = renderToStaticMarkup(await Home());
  for (const value of ["0.087", "0.050", "0.150", "0.120", "0.400"]) expect(html).toContain(value);
  expect(html).not.toContain("0.08666666666666666");
  expect(JSON.stringify(data)).toBe(source);
});

it("renders T benchmark: all M0–M3, IY with CI95 and source, without a primary-comparison verdict", async () => {
  vi.mocked(readFile).mockResolvedValue(JSON.stringify(fixture));
  const html = renderToStaticMarkup(await Home());
  for (const method of ["M0", "M1", "M2", "M3", "Random"]) expect(html).toContain(method);
  for (const number of ["0.05", "0.15", "0.12", "0.4"]) expect(html).toContain(number);
  expect(html).toContain("CI95");
  expect(html).toContain("T pool");
  expect(html).toContain("fixture-T");
  expect(html).not.toContain(fixture.primary.conclusion);
  expect(html).not.toContain("ΔIY");
  expect(html).toContain('/demo/fig_iy_budget.png');
  expect(html).not.toContain("minh hoạ");
});

it("labels mini benchmark as minh hoạ alongside its original source label", async () => {
  vi.mocked(readFile).mockResolvedValue(JSON.stringify({ ...fixture, label: "mini", pool: 404 }));
  const html = renderToStaticMarkup(await Home());
  expect(html).toContain("mini · minh hoạ");
  expect(html).not.toContain("T pool");
  vi.mocked(readFile).mockResolvedValue(JSON.stringify({ ...fixture, label: "mini · minh hoạ · in-sample", pool: 404 }));
  const exportedHtml = renderToStaticMarkup(await Home());
  expect(exportedHtml).toContain("mini · minh hoạ · in-sample");
  expect(exportedHtml).not.toContain("in-sample · minh hoạ");
});

it("keeps Số đo visible with Chưa có kết quả T when bench_pitch.json is missing", async () => {
  vi.mocked(readFile).mockRejectedValue(Object.assign(new Error("missing"), { code: "ENOENT" }));
  const html = renderToStaticMarkup(await Home());
  expect(html).toContain("Số đo");
  expect(html).toContain("Chưa có kết quả T");
  expect(html).not.toContain("<table");
});

it("keeps unmeasured methods visible without presenting zero as a measurement", async () => {
  vi.mocked(readFile).mockResolvedValue(JSON.stringify({ ...fixture, methods: { M0: fixture.methods.M0 } }));
  vi.mocked(access).mockRejectedValue(new Error("missing image"));
  const html = renderToStaticMarkup(await Home());
  expect(html.match(/Chưa đo/g)).toHaveLength(3);
  expect(html).toContain("M3");
  expect(html).not.toContain("<img");
});

it("shows missing-results state for invalid benchmark JSON instead of crashing", async () => {
  vi.mocked(readFile).mockResolvedValue("{invalid");
  expect(renderToStaticMarkup(await Home())).toContain("Chưa có kết quả T");
});
