import React from "react";
import { ArrowUpRight, Check, ShieldCheck } from "lucide-react";
import { whyCopy as copy } from "./copy";

const methods = copy.methods;
const splitColors = ["bg-sky-300", "bg-sky-500", "bg-slate-500"] as const;

function JudgeChecks() {
  const labels = methods.validityLabels;
  return (
    <div className="mt-8 rounded-2xl border border-slate-700 p-4 sm:p-6">
      <h4 className="text-xl font-semibold">{methods.validityTitle}</h4>
      <p className="mt-3 leading-7 text-slate-300">{methods.validityIntro}</p>
      <table className="mt-6 hidden w-full table-fixed text-left text-sm leading-6 lg:table">
        <caption className="sr-only">{methods.validityTitle}</caption>
        <thead className="text-sky-300"><tr>
          <th scope="col" className="w-1/5 p-3">{labels.criterion}</th>
          <th scope="col" className="w-1/4 p-3">{labels.question}</th>
          <th scope="col" className="p-3">{labels.calculation}</th>
          <th scope="col" className="w-20 p-3">{labels.ja}</th>
          <th scope="col" className="w-20 p-3">{labels.jb}</th>
        </tr></thead>
        <tbody>{methods.validity.map((row) => (
          <tr key={row.label} className="align-top">
            <th scope="row" className="border-t border-slate-700 p-3 font-semibold">{row.label}<span className="block font-normal text-slate-300">{row.rule}</span></th>
            <td className="border-t border-slate-700 p-3 text-slate-300">{row.question}</td>
            <td className="border-t border-slate-700 p-3 text-slate-300">{row.calculation}</td>
            <td className="border-t border-slate-700 p-3 font-semibold text-sky-300">{row.ja}</td>
            <td className="border-t border-slate-700 p-3 font-semibold text-orange-300">{row.jb}</td>
          </tr>
        ))}</tbody>
      </table>
      <div className="mt-5 grid gap-4 lg:hidden">{methods.validity.map((row) => (
        <article key={row.label} className="rounded-xl bg-slate-900 p-4">
          <h5 className="font-semibold">{row.label}</h5>
          {row.rule && <p className="mt-1 text-sm text-sky-300">{row.rule}</p>}
          <dl className="mt-3 space-y-3 text-sm leading-6">
            <div><dt className="font-semibold text-slate-200">{labels.question}</dt><dd className="text-slate-300">{row.question}</dd></div>
            <div><dt className="font-semibold text-slate-200">{labels.calculation}</dt><dd className="text-slate-300">{row.calculation}</dd></div>
          </dl>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm leading-6">
            <div><dt className="text-slate-300">{labels.ja}</dt><dd className="font-semibold text-sky-300">{row.ja}</dd></div>
            <div><dt className="text-slate-300">{labels.jb}</dt><dd className="font-semibold text-orange-300">{row.jb}</dd></div>
          </dl>
        </article>
      ))}</div>
      <p className="mt-5 leading-7 text-sky-200">{methods.validityConclusion}</p>
      <p className="mt-3 border-l-2 border-amber-300 pl-4 leading-7 text-amber-200">{methods.validityNote}</p>
      <p className="mt-4 break-words text-sm leading-6 text-slate-400">{methods.validitySource}</p>
    </div>
  );
}

function MethodComparison() {
  const labels = methods.baselineLabels;
  return (
    <div className="mt-12">
      <h3 className="text-2xl font-semibold">{methods.baselinesTitle}</h3>
      <table className="mt-6 hidden w-full table-fixed text-left leading-7 md:table">
        <caption className="sr-only">{methods.baselinesTitle}</caption>
        <thead className="text-sm text-sky-300"><tr>
          <th scope="col" className="w-1/5 p-4">{labels.method}</th>
          <th scope="col" className="w-2/5 p-4">{labels.selection}</th>
          <th scope="col" className="p-4">{labels.source}</th>
        </tr></thead>
        <tbody>{methods.baselines.map((method) => (
          <tr key={method.id} className={`align-top ${method.id === "P_our" ? "bg-sky-300/10" : ""}`}>
            <th scope="row" className="border-t border-slate-700 p-4 font-semibold"><span className="block font-mono text-sky-300">{method.id}</span>{method.title}</th>
            <td className="border-t border-slate-700 p-4 text-slate-300">{method.text}</td>
            <td className="border-t border-slate-700 p-4 text-slate-300">{method.source}</td>
          </tr>
        ))}</tbody>
      </table>
      <div className="mt-5 grid gap-4 md:hidden">{methods.baselines.map((method) => (
        <article key={method.id} className={`rounded-xl border p-4 ${method.id === "P_our" ? "border-sky-300 bg-sky-300/10" : "border-slate-700"}`}>
          <h4 className="font-semibold"><span className="font-mono text-sky-300">{method.id}</span> · {method.title}</h4>
          <p className="mt-2 leading-7 text-slate-300">{method.text}</p>
          <p className="mt-3 border-t border-slate-700 pt-3 text-sm leading-6 text-slate-400"><span className="block font-semibold text-slate-300">{labels.source}</span>{method.source}</p>
        </article>
      ))}</div>
      <p className="mt-5 rounded-xl bg-slate-900 p-4 leading-7 text-sky-200">{methods.comparison}</p>
    </div>
  );
}

function ResultsChart() {
  return (
    <figure className="mt-6 rounded-2xl border border-slate-700 p-4 sm:p-6">
      <figcaption className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-200">
        <span className="inline-flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-sky-400" aria-hidden="true" />{methods.chartLabels.ja}</span>
        <span className="inline-flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-orange-400" aria-hidden="true" />{methods.chartLabels.jb}</span>
      </figcaption>
      <div className="mt-6 space-y-4" aria-hidden="true">{methods.results.map((result) => (
        <div key={result.id} className={`grid min-w-0 gap-3 rounded-xl p-3 sm:grid-cols-[15rem_minmax(0,1fr)] sm:items-center ${result.id === "P_our" ? "bg-sky-300/10 ring-1 ring-sky-300" : "bg-slate-900"}`}>
          <p className="text-sm sm:text-right"><span className={`block font-semibold ${result.id === "P_our" ? "text-sky-200" : "text-slate-100"}`}>{result.label}</span><span className="block text-slate-400">{result.hint}</span></p>
          <div className="min-w-0 space-y-2">{(["ja", "jb"] as const).map((judge) => (
            <div key={judge} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
              <div className="h-3 overflow-hidden rounded-full bg-slate-800">
                <div className={`h-full rounded-full ${judge === "ja" ? "bg-sky-400" : "bg-orange-400"}`} style={{ width: `${Number(result[judge].replace(",", ".")) * 100}%` }} />
              </div>
              <span className={`w-28 text-right text-sm ${judge === "ja" ? "text-sky-200" : "text-orange-200"}`}>{result[judge]} · {judge === "ja" ? result.jaObjects : result.jbObjects}</span>
            </div>
          ))}</div>
        </div>
      ))}</div>
      {/* Tables ignore sr-only width, so the wrapper carries it to avoid mobile overflow. */}
      <div className="sr-only"><table>
        <caption>{methods.resultsTitle}</caption>
        <thead><tr><th scope="col">{methods.chartLabels.method}</th><th scope="col">{methods.chartLabels.ja}</th><th scope="col">{methods.chartLabels.jb}</th></tr></thead>
        <tbody>{methods.results.map((result) => (
          <tr key={result.id}><th scope="row">{result.label} ({result.hint})</th><td>{result.ja} · {result.jaObjects} {methods.chartLabels.objects}</td><td>{result.jb} · {result.jbObjects} {methods.chartLabels.objects}</td></tr>
        ))}</tbody>
      </table></div>
      <p className="mt-5 text-sm leading-6 text-slate-400">{methods.resultsNote}</p>
    </figure>
  );
}

export function MethodsSection() {
  return (
    <section id="phuong-phap" aria-labelledby="methods-title" className="scroll-mt-24 min-w-0 overflow-hidden rounded-3xl bg-slate-950 p-5 text-white tabular-nums sm:p-10">
      <div className="max-w-3xl">
        <p className="text-sm font-semibold uppercase tracking-widest text-sky-300">{methods.eyebrow}</p>
        <h2 id="methods-title" className="mt-4 font-[family-name:var(--font-landing-serif)] text-3xl leading-tight sm:text-5xl">{methods.title}</h2>
        <p className="mt-5 text-lg leading-8 text-slate-300">{methods.intro}</p>
        <p className="mt-5 inline-flex rounded-full border border-amber-300/50 px-4 py-2 text-sm font-semibold text-amber-200">{methods.status}</p>
      </div>
      <div className="mt-10">
        <h3 className="text-2xl font-semibold">{methods.protocolTitle}</h3>
        <ol className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{methods.protocol.map((step, index) => (
          <li key={step.title} className="rounded-2xl border border-slate-700 p-5">
            <span className="font-mono text-sm text-sky-300">0{index + 1}</span>
            <h4 className="mt-3 text-lg font-semibold">{step.title}</h4><p className="mt-2 leading-7 text-slate-300">{step.text}</p>
          </li>
        ))}</ol>
      </div>
      <div className="mt-12 border-t border-slate-700 pt-10">
        <h3 className="text-2xl font-semibold">{methods.dataTitle}</h3>
        <p className="mt-4 max-w-3xl leading-7 text-slate-300">{methods.dataIntro}</p>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{methods.dataStats.map((stat) => (
          <div key={stat.label} className="rounded-xl bg-slate-900 p-5"><dt className="text-sm text-slate-300">{stat.label}</dt><dd className="mt-2 text-3xl font-semibold text-sky-300">{stat.value}</dd></div>
        ))}</dl>
        <p className="mt-6 leading-7 text-slate-300">{methods.splitNote}</p>
        <div className="mt-5 flex h-3 overflow-hidden rounded-full" aria-hidden="true">{methods.splits.map((split, index) => (
          <div key={split.id} className={splitColors[index]} style={{ width: `${split.percent}%` }} />
        ))}</div>
        <dl className="mt-4 grid gap-4 md:grid-cols-3">{methods.splits.map((split, index) => (
          <div key={split.id} className="rounded-xl border border-slate-700 p-5">
            <dt className="flex items-center gap-2 font-semibold"><span className={`h-3 w-3 shrink-0 rounded-sm ${splitColors[index]}`} aria-hidden="true" />{split.id} · {split.percent} %</dt>
            <dd className="mt-2 text-2xl font-semibold">{split.count} khung</dd><dd className="mt-3 text-sm font-semibold text-sky-300">{split.title}</dd><dd className="mt-2 leading-7 text-slate-300">{split.text}</dd>
          </div>
        ))}</dl>
      </div>
      <div className="mt-12 rounded-2xl border border-sky-300/60 bg-sky-300/5 p-5 sm:p-7">
        <p className="break-words font-mono text-sm text-sky-300">{methods.modelLabel}</p>
        <h3 className="mt-3 text-2xl font-semibold">{methods.modelTitle}</h3><p className="mt-4 leading-7 text-slate-300">{methods.modelNote}</p>
        <ol className="mt-6 grid gap-5 lg:grid-cols-2">{methods.pipeline.map((step, index) => (
          <li key={step.title} className="min-w-0 border-t border-sky-300/25 pt-5">
            <p className="font-mono text-sm text-sky-300">0{index + 1} · {step.title}</p><h4 className="mt-2 text-lg font-semibold">{step.subtitle}</h4><p className="mt-2 leading-7 text-slate-300">{step.text}</p>
          </li>
        ))}</ol>
      </div>
      <div className="mt-12">
        <h3 className="text-2xl font-semibold">{methods.judgesTitle}</h3>
        <div className="mt-6 grid gap-4 md:grid-cols-2">{methods.judges.map((judge) => (
          <article key={judge.id} className="rounded-2xl bg-slate-900 p-5 sm:p-6">
            <p className={`text-sm font-semibold ${judge.id === "JA" ? "text-sky-300" : "text-orange-300"}`}>{judge.id} · {judge.source}</p><h4 className="mt-3 text-2xl font-semibold">{judge.name}</h4><p className="mt-3 leading-7 text-slate-300">{judge.text}</p>
          </article>
        ))}</div>
        <p className="mt-5 leading-7 text-slate-300">{methods.judgesIntro}</p><JudgeChecks />
      </div>
      <MethodComparison />
      <div className="mt-12">
        <h3 className="text-2xl font-semibold">{methods.dataChecksTitle}</h3><p className="mt-4 leading-7 text-slate-300">{methods.dataChecksIntro}</p>
        <ul className="mt-6 grid gap-4 md:grid-cols-2">{methods.dataChecks.map((check) => (
          <li key={check.value} className="rounded-xl border border-slate-700 p-5"><p className="text-3xl font-semibold text-sky-300">{check.value}</p><p className="mt-3 leading-7 text-slate-300">{check.text}</p><p className="mt-2 font-semibold text-emerald-300">{check.threshold} {check.passed}</p></li>
        ))}</ul>
        <p className="mt-4 text-sm leading-6 text-slate-400">{methods.dataChecksNote}</p>
      </div>
      <div className="mt-12 border-t border-slate-700 pt-10">
        <h3 className="max-w-3xl text-2xl font-semibold leading-snug sm:text-3xl">{methods.resultsTitle}</h3><p className="mt-4 leading-7 text-slate-300">{methods.resultsSubtitle}</p><ResultsChart />
        <h4 className="mt-10 text-xl font-semibold">{methods.qaTitle}</h4>
        <ol className="mt-5 grid gap-4 lg:grid-cols-3">{methods.qa.map((item) => (
          <li key={item.question} className={`min-w-0 rounded-2xl border p-5 ${item.tone === "yes" ? "border-emerald-300/40 bg-emerald-300/5" : "border-amber-300/40 bg-amber-300/5"}`}>
            <span className={`text-sm font-semibold tracking-wide ${item.tone === "yes" ? "text-emerald-300" : "text-amber-200"}`}>{item.badge}</span>
            <h5 className="mt-3 text-lg font-semibold leading-snug">{item.question}</h5>
            <p className="mt-3 leading-7 text-slate-300">{item.answer}</p>
          </li>
        ))}</ol>
        <p className="mt-5 rounded-xl bg-slate-900 p-4 leading-7 text-slate-300">{methods.retryNote}</p>
        <div className="mt-6 rounded-2xl border border-sky-300 bg-sky-100 p-5 text-slate-900 sm:p-7">
          <h4 className="text-sm font-semibold uppercase tracking-wider text-sky-900">{methods.conclusionTitle}</h4>
          <p className="mt-3 text-lg font-semibold leading-8">{methods.conclusionText}</p>
        </div>
        <p className="mt-5 rounded-xl border border-amber-300/50 bg-amber-300/5 p-5 leading-7 text-amber-200">{methods.conclusion}</p>
      </div>
      <div className="mt-12 border-t border-slate-700 pt-10">
        <h3 className="flex items-start gap-3 text-2xl font-semibold"><ShieldCheck className="mt-1 h-6 w-6 shrink-0 text-sky-300" aria-hidden="true" />{methods.locksTitle}</h3>
        <ol className="mt-6 grid gap-4 md:grid-cols-2">{methods.locks.map((lock, index) => (
          <li key={lock.title} className="min-w-0 rounded-xl border border-slate-700 p-5"><p className="font-mono text-sm text-sky-300">0{index + 1}</p><h4 className="mt-2 flex items-start gap-2 text-lg font-semibold"><Check className="mt-1 h-5 w-5 shrink-0 text-sky-300" aria-hidden="true" />{lock.title}</h4><p className="mt-3 break-words leading-7 text-slate-300">{lock.text}</p></li>
        ))}</ol>
        <p className="mt-5 leading-7 text-slate-400">{methods.order}</p>
        <details className="mt-6 rounded-2xl border border-slate-700 p-5 sm:p-6">
          <summary className="cursor-pointer text-lg font-semibold text-sky-300 focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sky-300">{methods.metricsTitle}</summary>
          <dl className="mt-6 grid gap-6 lg:grid-cols-2">{methods.metrics.map((metric) => (
            <div key={metric.title} className="min-w-0 border-t border-slate-700 pt-4"><dt className="font-semibold">{metric.title}</dt><dd className="mt-2 leading-7 text-slate-300">{metric.text}</dd></div>
          ))}</dl>
        </details>
      </div>
      <a href={methods.linkHref} target="_blank" rel="noreferrer" className="mt-8 inline-flex min-h-12 items-center gap-2 text-base font-semibold text-sky-300 underline underline-offset-4 focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-sky-300">{methods.link}<ArrowUpRight className="h-4 w-4 shrink-0" aria-hidden="true" /></a>
    </section>
  );
}
