"use client";

import { Settings } from "lucide-react";
import type { ParamsSchema, ParamsSchemaOption } from "@/lib/api/types";
import { weightPercents, type AdvancedDraft } from "@/lib/advancedParams";
import { SETTINGS } from "@/lib/glossary";
import { Tooltip } from "@/components/ui/Tooltip";

interface AdvancedParamsPanelProps {
  open: boolean;
  schema?: ParamsSchema | null;
  draft: AdvancedDraft;
  applied: boolean;
  onToggle: () => void;
  onDraftChange: (next: AdvancedDraft) => void;
  onApply: () => void;
  onReset: () => void;
}

function RangeEnds({ min, max }: { min?: string; max?: string }) {
  if (!min && !max) return null;
  return (
    <span className="flex justify-between gap-2 text-[10px] text-slate-400">
      <span>{min}</span>
      <span className="text-right">{max}</span>
    </span>
  );
}

export function AdvancedParamsPanel({
  open,
  schema,
  draft,
  applied,
  onToggle,
  onDraftChange,
  onApply,
  onReset,
}: AdvancedParamsPanelProps) {
  const field = (key: string) => schema?.fields.find((f) => f.key === key);
  const numberField = (key: string, fallback: { min: number; max: number; step: number }) => {
    const f = field(key);
    return {
      min: typeof f?.min === "number" ? f.min : fallback.min,
      max: typeof f?.max === "number" ? f.max : fallback.max,
      step: typeof f?.step === "number" ? f.step : fallback.step,
    };
  };
  const tierAvailable = schema?.tierAvailable ?? [0];
  const set = (patch: Partial<AdvancedDraft>) => onDraftChange({ ...draft, ...patch });
  const k = numberField("k", { min: 3, max: 50, step: 1 });
  const lam = numberField("lam", { min: 0, max: 1, step: 0.05 });
  const maxPerScene = numberField("maxPerScene", numberField("m", { min: 1, max: 50, step: 1 }));
  const weight = {
    alpha: numberField("alpha", { min: 0, max: 1, step: 0.05 }),
    beta: numberField("beta", { min: 0, max: 1, step: 0.05 }),
    gamma: numberField("gamma", { min: 0, max: 1, step: 0.05 }),
  };
  const labelOf = (key: string, fallback: string) => field(key)?.label ?? fallback;
  const helpOf = (key: string, schemaHelp?: string) => [SETTINGS[key]?.tooltip, schemaHelp].filter(Boolean).join("\n\n");
  const tierField = field("tier");
  const tierOptions: ParamsSchemaOption[] = tierField?.options?.length
    ? tierField.options
    : [
        { value: 0, label: "Tầng 0" },
        { value: 1, label: "Tầng 1" },
      ];
  const kField = field("k");
  const lamField = field("lam");
  const maxField = field("maxPerScene") ?? field("m");
  const lamPct = Math.round(draft.lam * 100);
  const lamValue =
    lamField?.minLabel && lamField?.maxLabel
      ? `${lamPct}% ${lamField.maxLabel} · ${100 - lamPct}% ${lamField.minLabel}`
      : draft.lam.toFixed(2);
  const pcts = weightPercents(draft);
  const weightGroup = schema?.groups?.weights;

  return (
    <div className="border-t border-slate-100 pt-3">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls="advanced-settings"
        className="w-full flex items-center justify-between text-xs text-slate-600 font-medium hover:text-slate-900"
      >
        <span className="inline-flex items-center gap-1.5">
          <Settings className="h-3.5 w-3.5" aria-hidden="true" />
          Tham số nâng cao
          {applied && (
            <span className="rounded-full border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-700">
              Tuỳ chỉnh
            </span>
          )}
        </span>
        <span className="font-mono text-slate-400">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div id="advanced-settings" className="mt-3 p-3 bg-slate-50 rounded-lg text-[11px] text-slate-700 space-y-3">
          <div className="flex flex-col gap-1.5">
            <span className="flex flex-wrap items-center font-semibold text-slate-700">
              {labelOf("tier", "Tầng chọn")}
              <Tooltip label={labelOf("tier", "tier")} content={helpOf("tier", tierField?.help)} />
            </span>
            <div className="grid grid-cols-2 p-1 bg-white rounded-lg border border-slate-200 gap-1">
              {tierOptions.map((opt) => {
                const reason = opt.disabledReason || (tierAvailable.includes(opt.value) ? null : "Chưa có model seed");
                const selected = draft.tier === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    disabled={!!reason}
                    title={reason ?? opt.hint ?? opt.label}
                    aria-pressed={selected}
                    onClick={() =>
                      set({
                        tier: opt.value as 0 | 1,
                        beta: opt.value === 0 ? 0 : draft.beta,
                        gamma: opt.value === 0 ? 0 : draft.gamma,
                      })
                    }
                    className={`flex flex-col items-center rounded-md px-2 py-1.5 transition-colors ${
                      selected ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100 disabled:opacity-45 disabled:hover:bg-transparent"
                    }`}
                  >
                    <span className="font-semibold">{opt.label}</span>
                    {opt.hint && <span className={`text-[10px] ${selected ? "text-blue-100" : "text-slate-400"}`}>{opt.hint}</span>}
                    {reason && <span className="text-[10px] text-slate-500">{reason}</span>}
                  </button>
                );
              })}
            </div>
          </div>

          <label className="flex flex-col gap-1">
            <span className="flex flex-wrap items-center justify-between font-semibold">
              <span className="flex flex-wrap items-center">
                {labelOf("k", "Số láng giềng")}
                <Tooltip label={labelOf("k", "k")} content={helpOf("k", kField?.help)} />
              </span>
              <span className="font-mono">{kField?.unit ? `${draft.k} ${kField.unit}` : draft.k}</span>
            </span>
            <input type="range" min={k.min} max={k.max} step={k.step} value={draft.k} onChange={(e) => set({ k: Number(e.target.value) })} className="w-full accent-blue-600" />
            <RangeEnds min={kField?.minLabel} max={kField?.maxLabel} />
          </label>

          <label className="flex flex-col gap-1">
            <span className="flex flex-wrap items-center justify-between font-semibold">
              <span className="flex flex-wrap items-center">
                {labelOf("lam", "Ưu tiên khi chọn")}
                <Tooltip label={labelOf("lam", "lam")} content={helpOf("lam", lamField?.help)} />
              </span>
              <span className="text-right">{lamValue}</span>
            </span>
            <input type="range" min={lam.min} max={lam.max} step={lam.step} value={draft.lam} onChange={(e) => set({ lam: Number(e.target.value) })} className="w-full accent-blue-600" />
            <RangeEnds min={lamField?.minLabel} max={lamField?.maxLabel} />
          </label>

          <div className="flex flex-col gap-1">
            <span className="flex flex-wrap items-center font-semibold">
              {labelOf("maxPerScene", labelOf("m", "Tối đa mỗi cảnh"))}
              <Tooltip label={labelOf("maxPerScene", "maxPerScene")} content={helpOf("maxPerScene", maxField?.help)} />
            </span>
            <div className="grid grid-cols-[1fr_auto] items-center gap-2">
              <span className="flex items-center gap-1.5">
                <input
                  type="number"
                  aria-label={labelOf("maxPerScene", "Tối đa mỗi cảnh")}
                  min={maxPerScene.min}
                  max={maxPerScene.max}
                  step={maxPerScene.step}
                  disabled={draft.quotaOff}
                  value={draft.maxPerScene}
                  onChange={(e) => set({ maxPerScene: Number(e.target.value) })}
                  className="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 font-mono disabled:opacity-45"
                />
                {maxField?.unit && <span className="text-slate-500">{maxField.unit}</span>}
              </span>
              <label className="flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 font-semibold">
                <input type="checkbox" checked={draft.quotaOff} onChange={(e) => set({ quotaOff: e.target.checked })} className="accent-blue-600" />
                <span className="inline-flex max-w-[9rem] items-center gap-1 leading-tight">{labelOf("quotaOff", "Không giới hạn")}<Tooltip label={labelOf("quotaOff", "quotaOff")} content={helpOf("maxPerScene", maxField?.help)} /></span>
              </label>
            </div>
          </div>

          <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-2">
            <span className="flex flex-col">
              <span className="font-semibold text-slate-700">{weightGroup?.label ?? "Mức quan trọng của từng tiêu chí"}</span>
              <span className="text-[10px] text-slate-500">{weightGroup?.help ?? "Tự quy đổi để tổng luôn là 100%."}</span>
            </span>
            {(["alpha", "beta", "gamma"] as const).map((key) => {
              const f = field(key);
              const fallbackLabel = key === "alpha" ? "Hiếm trong dữ liệu" : key === "beta" ? "Lạ với model" : "Model chưa chắc chắn";
              const disabled = draft.tier === 0 && key !== "alpha";
              return (
                <label key={key} className="flex flex-col gap-1">
                  <span className="flex flex-wrap items-center justify-between font-semibold">
                    <span className="flex flex-wrap items-center">
                      {f?.label ?? fallbackLabel}
                      <Tooltip label={f?.label ?? key} content={helpOf(key, f?.help)} />
                    </span>
                    <span className="font-mono">{pcts[key]}%</span>
                  </span>
                  <input
                    type="range"
                    min={weight[key].min}
                    max={weight[key].max}
                    step={weight[key].step}
                    disabled={disabled}
                    value={disabled ? 0 : draft.tier === 0 ? weight[key].max : draft[key]}
                    onChange={(e) => set({ [key]: Number(e.target.value) })}
                    className="w-full accent-blue-600 disabled:opacity-45"
                  />
                </label>
              );
            })}
            {draft.tier === 0 && (
              <span className="text-[10px] text-slate-500">{weightGroup?.basicNote ?? "Chế độ cơ bản chỉ dùng tiêu chí đầu tiên."}</span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 pt-1">
            <button type="button" onClick={onApply} className="min-h-9 rounded-lg bg-blue-600 px-3 text-xs font-semibold text-white hover:bg-blue-700">
              Áp dụng
            </button>
            <button type="button" onClick={onReset} className="min-h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-100">
              Về mặc định
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
