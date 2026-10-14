import React from "react";
import { ArrowDown, Check } from "lucide-react";
import { whyCopy as copy } from "./copy";

export function MethodsSection() {
  return (
    <section id="phuong-phap" aria-labelledby="methods-title" className="scroll-mt-24 overflow-hidden rounded-3xl bg-slate-950 p-6 text-white sm:p-10">
      <div className="max-w-3xl">
        <p className="text-sm font-semibold uppercase tracking-widest text-sky-300">{copy.methods.eyebrow}</p>
        <h2 id="methods-title" className="mt-4 font-[family-name:var(--font-landing-serif)] text-4xl leading-tight sm:text-5xl">{copy.methods.title}</h2>
        <p className="mt-5 text-lg leading-8 text-slate-300">{copy.methods.intro}</p>
      </div>
      <div className="mt-9 grid gap-6 lg:grid-cols-2">
        <div className="space-y-6 rounded-2xl border border-slate-700 p-6 sm:p-7">
          <h3 className="text-xl font-semibold">{copy.methods.referenceTitle}</h3>
          {copy.methods.references.map((method) => (
            <article key={method.id}>
              <span className="font-mono text-sm font-semibold text-sky-300">{method.id}</span>
              <h4 className="mt-1 text-xl font-semibold">{method.title}</h4>
              <p className="mt-2 text-base leading-7 text-slate-300">{method.text}</p>
            </article>
          ))}
        </div>
        <div className="rounded-2xl border border-sky-300 bg-sky-100 p-6 text-slate-900 sm:p-7">
          <p className="text-sm font-semibold uppercase tracking-wider text-sky-900">{copy.methods.practicalLabel}</p>
          <h3 className="mt-3 text-2xl font-semibold leading-snug">{copy.methods.practicalTitle}</h3>
          {copy.methods.approaches.map((method) => (
            <article key={method.id} className="mt-6">
              <h4 className="text-lg font-semibold">{method.id} · {method.title}</h4>
              <p className="mt-2 text-base leading-7 text-slate-700">{method.text}</p>
            </article>
          ))}
          <p className="mt-6 flex items-start gap-3 border-t border-sky-300 pt-5 text-base leading-7 text-sky-950"><Check className="mt-1 h-5 w-5 shrink-0" aria-hidden="true" />{copy.methods.practicalReason}</p>
        </div>
      </div>
      <ol className="mt-8 grid gap-6 md:grid-cols-3">
        {copy.methods.proof.map((step, i) => (
          <li key={step.title} className="border-t border-slate-700 pt-5">
            <span className="font-mono text-sm text-sky-300">0{i + 1}</span>
            <h3 className="mt-2 text-xl font-semibold">{step.title}</h3>
            <p className="mt-2 text-base leading-7 text-slate-300">{step.text}</p>
          </li>
        ))}
      </ol>
      <a href="#bang-chung" className="mt-8 inline-flex min-h-12 items-center gap-2 text-base font-semibold text-sky-300 underline underline-offset-4">{copy.methods.link}<ArrowDown className="h-4 w-4" aria-hidden="true" /></a>
    </section>
  );
}
