import React from "react";
import { access } from "node:fs/promises";
import path from "node:path";
import { benchProvenance, loadDemoBench } from "@/lib/server/demoBench";
import { WhyNav } from "@/components/why/WhyNav";
import { WhyHero } from "@/components/why/WhyHero";
import { CostSection } from "@/components/why/CostSection";
import { WhyBenchmark } from "@/components/why/WhyBenchmark";
import { TrustSection } from "@/components/why/TrustSection";
import { BottleneckSection } from "@/components/why/BottleneckSection";
import { CameraSection } from "@/components/why/CameraSection";
import { WhyCta } from "@/components/why/WhyCta";
import { MethodsSection } from "@/components/why/MethodsSection";

export const dynamic = "force-dynamic";

export default async function WhyPage() {
  const { bench, figureUrl } = await loadDemoBench();
  const provenance = bench ? benchProvenance(bench) : null;
  let examples = false;
  if (bench?.figures.includes("fig_examples.png")) {
    try {
      await access(path.join(process.cwd(), "public", "demo", "fig_examples.png"));
      examples = true;
    } catch {
      /* Optional illustration; keep the evidence table. */
    }
  }

  return (
    <div className="vcf-hud relative flex min-h-screen flex-col font-sans [--font-space-grotesk:var(--font-landing-sans)]">
      <div className="hud-ambient" aria-hidden="true" />
      <div className="relative z-10 flex min-h-screen flex-col">
        <WhyNav />
        <WhyHero />
        <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-12 px-4 pb-16 pt-10 sm:gap-16 sm:px-6">
          <CostSection bench={bench} />
          <MethodsSection />
          <WhyBenchmark bench={bench} figureUrl={figureUrl} examples={examples} />
          <TrustSection provenance={provenance} />
          <BottleneckSection benchExists={Boolean(bench)} m2={provenance?.m2 ?? null} />
          <CameraSection />
          <WhyCta />
        </main>
        <footer className="border-t border-slate-200 px-4 py-6 text-center text-xs text-slate-500">
          VCuboidFIT · Dữ liệu nuScenes / Motional · CC BY-NC-SA 4.0 · phi thương mại
        </footer>
      </div>
    </div>
  );
}
