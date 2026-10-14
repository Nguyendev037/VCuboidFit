import React from "react";
import Link from "next/link";
import { access } from "node:fs/promises";
import path from "node:path";
import { Benchmark } from "@/components/home/Benchmark";
import { EmptyState } from "@/components/ui/DataState";
import { whyCopy as copy } from "@/components/why/copy";
import { benchProvenance, loadDemoBench } from "@/lib/server/demoBench";

export const dynamic = "force-dynamic";

export default async function WhyPage() {
  const { bench, figureUrl } = await loadDemoBench();
  const provenance = bench ? benchProvenance(bench) : null;
  let examples = false;
  if (bench?.figures.includes("fig_examples.png")) {
    try { await access(path.join(process.cwd(), "public", "demo", "fig_examples.png")); examples = true; }
    catch { /* Optional illustration; keep the evidence table. */ }
  }
  const section = "rounded-vcf-card border border-vcf-border bg-vcf-surface p-6 sm:p-8";
  const heading = "mb-4 text-2xl font-bold sm:text-3xl";
  return <main className="min-h-screen bg-vcf-bg text-vcf-text">
    <nav aria-label={copy.home} className="mx-auto max-w-6xl px-6 py-5"><Link href="/" className="font-semibold text-vcf-accent-ink">VCuboidFIT · {copy.home}</Link></nav>
    <div className="mx-auto max-w-6xl space-y-8 px-6 pb-16 text-lg leading-relaxed">
      <header className="py-10 sm:py-16">
        <p className="font-semibold text-vcf-accent-ink">{copy.eyebrow}</p>
        <h1 className="mt-4 max-w-4xl text-4xl font-bold leading-tight sm:text-6xl">{copy.title}</h1>
        <p className="mt-6 max-w-3xl text-xl text-vcf-muted">{copy.subtitle}</p>
      </header>
      <section className={section} aria-labelledby="cost-title">
        <h2 id="cost-title" className={heading}>{copy.costTitle}</h2>
        {bench ? <p className="mb-4 text-2xl font-semibold tabular-nums">{copy.annotate} {bench.budget_B} {copy.instead} {bench.pool} {copy.frames} · {bench.pool > 0 ? (bench.budget_B / bench.pool * 100).toFixed(1) : "—"} % {copy.budget}</p> : <EmptyState message={copy.missing} />}
        <p className="text-vcf-muted">{copy.cost}</p>
      </section>
      <section aria-labelledby="evidence-title">
        <h2 id="evidence-title" className={heading}>{copy.evidenceTitle}</h2>
        {bench ? <>
          <p className={`rounded-vcf-control p-4 font-semibold ${bench.primary.conclusion === "shown" ? "bg-vcf-good-soft text-vcf-good" : "bg-vcf-warn-soft text-vcf-warn"}`}>{bench.primary.conclusion === "shown" ? copy.variants.shown : copy.variants.unproven}</p>
          <Benchmark bench={bench} figureUrl={figureUrl} />
          {examples && <figure className="mt-6">{/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/demo/fig_examples.png" alt={copy.examples} className="h-auto w-full rounded-vcf-card" /><figcaption className="mt-2 text-vcf-muted">{copy.examples} · {bench.label}</figcaption>
          </figure>}
        </> : <EmptyState message={copy.missing} />}
      </section>
      <section className={section} aria-labelledby="trust-title">
        <h2 id="trust-title" className={heading}>{copy.trustTitle}</h2><p>{copy.trust}</p>
        <dl className="mt-4 space-y-3 break-all text-base text-vcf-muted"><div><dt>{copy.prereg}</dt><dd className="font-mono">{provenance?.prereg?.slice(0, 12) || copy.unavailable}</dd></div><div><dt>{copy.report}</dt><dd className="font-mono">{provenance?.report || copy.unavailable}</dd></div></dl>
      </section>
      <section className={section} aria-labelledby="bottleneck-title">
        <h2 id="bottleneck-title" className={heading}>{copy.bottleneckTitle}</h2>
        {provenance?.m2 ? <p className="mb-4 text-2xl font-semibold tabular-nums">{copy.reachLabel}: {provenance.m2.n_reachable}/{provenance.m2.n_targets}</p> : <EmptyState message={bench ? copy.unavailable : copy.missing} />}
        <p className="text-vcf-muted">{copy.bottleneck}</p>
      </section>
      <section className={section} aria-labelledby="camera-title"><h2 id="camera-title" className={heading}>{copy.cameraTitle}</h2><p className="text-vcf-muted">{copy.camera}</p></section>
      <section className="py-8" aria-labelledby="cta-title"><h2 id="cta-title" className={heading}>{copy.ctaTitle}</h2><div className="flex flex-wrap gap-4"><Link href="/dashboard" className="rounded-vcf-control bg-vcf-accent px-6 py-3 font-semibold text-vcf-on-accent hover:bg-vcf-accent-ink">{copy.demo}</Link><Link href="/huong-dan" className="rounded-vcf-control border border-vcf-border bg-vcf-surface px-6 py-3 font-semibold text-vcf-accent-ink">{copy.guide}</Link></div></section>
    </div>
  </main>;
}
