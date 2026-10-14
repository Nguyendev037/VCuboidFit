import { readFileSync } from "node:fs";
import { readFile, access } from "node:fs/promises";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import WhyPage from "./page";
import { whyCopy } from "@/components/why/copy";
import { benchProvenance, type DemoBench } from "@/lib/server/demoBench";

vi.mock("node:fs/promises", () => ({ readFile: vi.fn(), access: vi.fn() }));

// Deliberately different from the shipped pool and budget: detect hardcoded copy.
const fixture = {
  schema: "vcf-demo-bench-v1", source: { run_id: "fixture-T-why", prereg_sha256: "abcdefghijklmnopqrstuv", report_sha256: "report-fixture-sha" },
  label: "T pool", pool: 1200, scenes: 20, capture_primary: "rare_form", budget_B: 60,
  methods: {
    M0: { name: "Random", iy: 0.1234, ci_lo: 0.0111, ci_hi: 0.2345, status: "ok" },
    M1: { name: "Baseline fixture", iy: 0.2345, ci_lo: 0.0222, ci_hi: 0.3456, status: "ok" },
    M2: { name: "lidar_only", iy: 0.2222, ci_lo: 0.0333, ci_hi: 0.4567, status: "ok" },
    M3: { name: "multisensor", iy: 0.1111, ci_lo: 0.0444, ci_hi: 0.5678, status: "ok" },
  },
  primary: { pair: "M2-M1", delta: -0.0123, ci_lo: -0.1234, ci_hi: 0.0567, conclusion: "not shown / underpowered" },
  reachability: { radius_m: 1, n_targets: 33, methods: { M2: { n_reachable: 11, n_targets: 33 } } },
  figures: ["fig_iy_budget.png", "fig_examples.png"],
} satisfies DemoBench;

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(readFile).mockResolvedValue(JSON.stringify(fixture));
  vi.mocked(access).mockResolvedValue(undefined);
});

it("SPEC7(a): renders source pool and budget, every IY with adjacent CI and verbatim primary conclusion", async () => {
  const html = renderToStaticMarkup(await WhyPage());
  expect(html).toContain("Gán nhãn 60 thay vì 1200 frame · 5.0 % ngân sách");
  for (const [id, method] of Object.entries(fixture.methods)) {
    expect(html).toContain(`${id} · ${method.name}`);
    expect(html).toMatch(new RegExp(`${method.iy.toFixed(3)}[\\s\\S]*?\\[${method.ci_lo.toFixed(3)}, ${method.ci_hi.toFixed(3)}\\]`));
  }
  expect(html).toContain("M2-M1: ΔIY = -0.012 · CI95 [-0.123, 0.057]");
  expect(html).toContain(fixture.primary.conclusion);
  expect(html).toContain(whyCopy.variants.unproven);
  for (const value of ["T pool", "fixture-T-why", "abcdefghijkl", "report-fixture-sha", "11/33", "/demo/fig_examples.png"]) expect(html).toContain(value);
});

it("SPEC7(b): missing or corrupt JSON renders DataState for all three numeric blocks and retains copy", async () => {
  for (const missing of [true, false]) {
    if (missing) vi.mocked(readFile).mockRejectedValue(new Error("ENOENT"));
    else vi.mocked(readFile).mockResolvedValue("{broken");
    const html = renderToStaticMarkup(await WhyPage());
    expect(html.match(/Chưa có kết quả T/g)).toHaveLength(3);
    expect(html.match(/role="status"/g)).toHaveLength(3);
    expect(html).toContain(whyCopy.title);
    expect(html).toContain(whyCopy.camera);
    expect(html).not.toContain("<table");
    expect(html).not.toContain("11/33");
  }
});

it("SPEC7(c): rendered HTML and copy source contain no prohibited marketing claims", async () => {
  const html = renderToStaticMarkup(await WhyPage());
  const source = readFileSync(new URL("../../components/why/copy.ts", import.meta.url), "utf8");
  // Assemble claims so the repository source scan does not flag its own detector.
  const claims = [
    ["vượt", "trội"].join(" "), ["tốt", "nhất"].join(" "),
    ["hàng", "đầu"].join(" "), ["đánh", "bại"].join(" "),
    ["out", "perform"].join(""), ["state", "of", "the", "art"].join("-"),
    ["so", "ta"].join(""), ["#", "1"].join(""),
    "tăng\\s+\\S+\\s*%", "chính xác\\s+9\\S*\\s*%",
  ];
  const banned = new RegExp(claims.join("|"), "i");
  expect(html).not.toMatch(banned);
  expect(source).not.toMatch(banned);
  vi.mocked(readFile).mockResolvedValue(JSON.stringify({ ...fixture, primary: { ...fixture.primary, conclusion: "shown" } }));
  expect(renderToStaticMarkup(await WhyPage())).not.toMatch(banned);
});

it("SPEC7(d): shown export switches copy and conclusion tone automatically", async () => {
  const before = renderToStaticMarkup(await WhyPage());
  vi.mocked(readFile).mockResolvedValue(JSON.stringify({ ...fixture, primary: { ...fixture.primary, conclusion: "shown" } }));
  const after = renderToStaticMarkup(await WhyPage());
  expect(before).toContain(whyCopy.variants.unproven);
  expect(after).toContain(whyCopy.variants.shown);
  expect(after).not.toContain(whyCopy.variants.unproven);
  expect(after).toContain('>shown</p>');
  expect(after).toContain("bg-vcf-good-soft text-vcf-good");
  expect(after).not.toContain("bg-vcf-warn-soft text-vcf-warn");
});

it("keeps optional provenance safe without rejecting old exports or requiring figures", async () => {
  const old = { ...fixture, source: { run_id: "old-export" }, reachability: undefined, figures: [] };
  vi.mocked(readFile).mockResolvedValue(JSON.stringify(old));
  const html = renderToStaticMarkup(await WhyPage());
  expect(html).toContain("old-export");
  expect(html).toContain("<table");
  expect(html).not.toContain("<img");
  expect(benchProvenance({ ...fixture, source: { run_id: "bad", prereg_sha256: 42 }, reachability: { methods: { M2: { n_targets: -1 } } } } as unknown as DemoBench)).toEqual({ prereg: null, report: null, m2: null });
});
