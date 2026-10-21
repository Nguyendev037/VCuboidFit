import { OnlineTierStatus } from "./OnlineTierStatus";
import type { Tier1State } from "@/lib/api/types";
import { PRESETS } from "@/lib/api/types";
import { AdvancedParamsPanel, ColabBox } from "@/components/AdvancedParamsPanel";
import { TierStatus } from "@/components/TierStatus";
import { Tooltip } from "@/components/ui/Tooltip";
import { PANEL_HELP, WARNING_LABELS, visibleWarnings } from "@/lib/glossary";
import { effectiveWeights as presetWeights, minScenes } from "@/lib/panelParams";
import { effectiveWeights } from "@/lib/advancedParams";
import { RARE_PANELS } from "@/lib/glossary";
import { pct, setAdvancedPanelOpen } from "./dashboardState";
import type { DashboardState } from "./useDashboard";

export function FilterBar(state: Pick<
  DashboardState,
  | "activePipeline"
  | "advancedParams"
  | "budget"
  | "changePreset"
  | "changeSpread"
  | "currentAdvancedDraft"
  | "dataset"
  | "demo"
  | "done"
  | "engineVersion"
  | "handleAddQueryTag"
  | "handleApplyAdvanced"
  | "handleRemoveQueryTag"
  | "handleResetAdvanced"
  | "handleResetDefaults"
  | "job"
  | "jobId"
  | "newTagInput"
  | "noTier1"
  | "paramsSchema"
  | "preset"
  | "queryTags"
  | "result"
  | "setAdvancedDraft"
  | "setBudget"
  | "setNewTagInput"
  | "showAdvanced"
  | "spread"
  | "t1Local"
  | "t1Remote"
  | "t1Run"
  | "uiSchema"
>) {
  const {
    activePipeline,
    advancedParams,
    budget,
    changePreset,
    changeSpread,
    currentAdvancedDraft,
    dataset,
    demo,
    done,
    engineVersion,
    handleAddQueryTag,
    handleApplyAdvanced,
    handleRemoveQueryTag,
    handleResetAdvanced,
    handleResetDefaults,
    job,
    jobId,
    newTagInput,
    noTier1,
    paramsSchema,
    preset,
    queryTags,
    result,
    setAdvancedDraft,
    setBudget,
    setNewTagInput,
    showAdvanced,
    spread,
    t1Local,
    t1Remote,
    t1Run,
    uiSchema,
  } = state;

  const baseWeights = presetWeights({
    preset,
    presets: uiSchema?.presets ?? paramsSchema.data?.presets,
    tier1Available: !noTier1,
    expert: advancedParams ? { alpha: advancedParams.alpha, beta: advancedParams.beta, gamma: advancedParams.gamma } : null,
  });

  const noNovelty = job.data?.tier1?.state === "done" && job.data.tier1.novSource === "none";
  const adjusted = baseWeights && effectiveWeights({ alpha: baseWeights.rare, beta: baseWeights.novel, gamma: baseWeights.unsure }, noNovelty);
  const weights = adjusted && { rare: adjusted.alpha, novel: adjusted.beta, unsure: adjusted.gamma };

  const wRarePct = weights ? Math.round(weights.rare * 100) : 0;
  const wNovelPct = weights ? Math.round(weights.novel * 100) : 0;
  const wUnsurePct = weights ? Math.round(weights.unsure * 100) : 0;

  const isExpertDiversityActive =
    advancedParams != null &&
    (advancedParams.lam !== undefined ||
      advancedParams.maxPerScene !== undefined ||
      advancedParams.quotaOff !== undefined);

  const framesToSelect = Math.ceil((result?.poolSize ?? dataset?.frames ?? 0) * budget);
  const perSceneDefault =
    (uiSchema?.fields.find((f) => f.key === "maxPerScene")?.default as number) ?? 4;
  const perScene = advancedParams?.maxPerScene ?? perSceneDefault;
  const minSceneEstimate = minScenes(framesToSelect, perScene, dataset?.scenes ?? 0) ?? 1;

  const tierStatusProps =
    !jobId && paramsSchema.data
      ? {
          tier0: { state: "queued", nTotal: null, nKeep: null, durationSec: null },
          tier1: {
            state: (paramsSchema.data.tierAvailable.includes(1) ? "ready" : "skipped") as Tier1State,
            reason: paramsSchema.data.tier1Reason ?? null,
            canRun: false,
            novSource: null,
          },
        }
      : job.data?.tier0 || job.data?.tier1
        ? {
            tier0: job.data.tier0,
            tier1: job.data.tier1,
            runBusy: t1Local.isPending,
            runError: t1Local.isError ? (t1Local.error instanceof Error ? t1Local.error.message : "Không chạy được Tầng 1.") : null,
            onRunTier1: demo ? undefined : () => t1Local.mutate(),
          }
        : undefined;

  const colabProps =
    noTier1 && t1Remote.data?.enabled && !["queued", "running"].includes(job.data?.tier1?.state ?? "")
      ? {
          enabled: true,
          task: t1Remote.data.task,
          busy: t1Run.isPending,
          error: t1Run.isError ? (t1Run.error instanceof Error ? t1Run.error.message : "Không tạo được việc trên Colab.") : null,
          onRun: () => t1Run.mutate(),
        }
      : undefined;

  return (
    <aside className="lg:col-span-4 flex flex-col gap-4 sticky top-20">
      <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-5">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <h2 className="font-bold text-base text-slate-900">Tinh chỉnh</h2>
          <button
            type="button"
            onClick={handleResetDefaults}
            aria-label="Đặt lại tùy chỉnh về mặc định"
            className="text-xs font-semibold text-blue-600 hover:text-blue-800 transition-colors"
          >
            Đặt lại mặc định
          </button>
        </div>

        {/* 1. Lấy bao nhiêu frame? */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-slate-700 flex items-center gap-1">
              <span>{PANEL_HELP.budget.label}</span>
              <Tooltip label={PANEL_HELP.budget.label} content={PANEL_HELP.budget.tooltip} />
            </span>
            <span className="font-mono font-bold text-blue-600">
              {pct(budget)} · {framesToSelect} frame
            </span>
          </div>
          <input
            type="range"
            aria-label="Ngân sách chọn frame"
            min={0.01}
            max={0.10}
            step={0.01}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            className="w-full accent-blue-600 h-2 bg-slate-200 rounded-lg cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-slate-400 font-mono">
            <span>1 %</span>
            <span>10 %</span>
          </div>
        </div>

        {/* 2. Ưu tiên tìm gì? */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700 flex items-center gap-1">
              <span>{PANEL_HELP.priority.label}</span>
              <Tooltip label={PANEL_HELP.priority.label} content={PANEL_HELP.priority.tooltip} />
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 mt-1">
            {PRESETS.map((pKey) => {
              const isSelected = preset === pKey;
              const help = PANEL_HELP[`preset.${pKey}`];
              return (
                <div
                  key={pKey}
                  className={`relative p-3 rounded-xl border text-left flex flex-col gap-0.5 transition-all ${
                    isSelected
                      ? "border-blue-600 bg-blue-50/60 ring-1 ring-blue-600"
                      : "border-slate-200 hover:border-slate-300 bg-white"
                  } ${noTier1 ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                  <button
                    type="button"
                    onClick={() => changePreset(pKey)}
                    aria-pressed={isSelected}
                    disabled={noTier1}
                    title={noTier1 ? PANEL_HELP.tierLock.tooltip : undefined}
                    className="w-full text-left flex flex-col gap-0.5 disabled:cursor-not-allowed"
                  >
                    <span className={`text-xs font-bold flex items-center pr-6 ${isSelected ? "text-blue-700" : "text-slate-800"}`}>
                      {help.label}
                      {isSelected && advancedParams && (
                        <span className="ml-1 rounded-full border border-blue-200 bg-white px-1 py-0.5 text-[9px] text-blue-700">
                          Tuỳ chỉnh
                        </span>
                      )}
                    </span>
                    <span className="text-[10px] text-slate-500">{help.desc}</span>
                  </button>
                  <div className="absolute top-2 right-2">
                    <Tooltip label={help.label} content={help.tooltip} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Khung khoá Tầng 1 (chữ thường hiển thị) */}
          {noTier1 && (
            <div className="flex items-start gap-1.5 text-[11px] text-slate-600 mt-1 bg-slate-50 p-2 rounded-lg border border-slate-200">
              <span aria-hidden="true">🔒</span>
              <span>
                <strong className="font-semibold text-slate-700">{PANEL_HELP.tierLock.label}:</strong>{" "}
                {PANEL_HELP.tierLock.tooltip}
              </span>
            </div>
          )}

          {/* TierStatus + ColabBox */}
          {activePipeline === "lidar" && tierStatusProps && (process.env.NEXT_PUBLIC_VCF_SESSIONS === "1" ? <OnlineTierStatus {...tierStatusProps} /> : <TierStatus {...tierStatusProps} />)}
          {activePipeline === "lidar" && colabProps && <ColabBox colab={colabProps} />}

          {/* Thanh Công thức đang dùng */}
          {noNovelty && <p className="text-xs text-slate-500">{RARE_PANELS.noNovelty}</p>}
          {weights && (
            <div className="flex flex-col gap-1.5 mt-2 rounded-lg border border-slate-100 bg-slate-50/80 p-2.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-700 flex items-center gap-1">
                  <span>{PANEL_HELP.formula.label}</span>
                  <Tooltip label={PANEL_HELP.formula.label} content={PANEL_HELP.formula.tooltip} />
                </span>
              </div>
              <div
                role="img"
                aria-label={`Công thức: ${PANEL_HELP["w.rare"].label} ${wRarePct}%, ${PANEL_HELP["w.novel"].label} ${wNovelPct}%, ${PANEL_HELP["w.unsure"].label} ${wUnsurePct}%`}
                className="h-2 w-full rounded-full overflow-hidden flex bg-slate-200"
              >
                {weights.rare > 0 && <div style={{ width: `${weights.rare * 100}%` }} className="bg-blue-600 h-full" />}
                {weights.novel > 0 && <div style={{ width: `${weights.novel * 100}%` }} className="bg-amber-500 h-full" />}
                {weights.unsure > 0 && <div style={{ width: `${weights.unsure * 100}%` }} className="bg-sky-400 h-full" />}
              </div>
              <div className="flex items-center justify-between text-[10px] text-slate-600 font-medium">
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-blue-600" aria-hidden="true" />
                  Hiếm {wRarePct}%
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-amber-500" aria-hidden="true" />
                  Lạ {wNovelPct}%
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-sky-400" aria-hidden="true" />
                  Chưa chắc {wUnsurePct}%
                </span>
              </div>
            </div>
          )}
        </div>

        {/* 3. Trải đều nhiều cảnh */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700 flex items-center gap-1">
              <span>{PANEL_HELP.spread.label}</span>
              <Tooltip label={PANEL_HELP.spread.label} content={PANEL_HELP.spread.tooltip} />
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={spread}
              aria-label="Trải đều nhiều cảnh"
              disabled={isExpertDiversityActive}
              onClick={() => changeSpread(!spread)}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
                spread ? "bg-blue-600" : "bg-slate-200"
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                  spread ? "translate-x-4" : "translate-x-0"
                }`}
              />
            </button>
          </div>
          <div className="text-[11px] text-slate-500">
            {isExpertDiversityActive ? (
              <span className="italic text-slate-500">Đang theo Chế độ chuyên gia</span>
            ) : spread ? (
              <span>
                {dataset?.scenes
                  ? `Ít nhất ~${minSceneEstimate} cảnh trên tổng ${dataset.scenes} cảnh`
                  : `Ít nhất ~${minSceneEstimate} cảnh`}
              </span>
            ) : (
              <span>Có thể dồn vào ít cảnh</span>
            )}
          </div>
        </div>

        {/* Kịch bản quan tâm (chỉ pipeline camera, giữ nguyên) */}
        {activePipeline === "camera" && (
          <div className="flex flex-col gap-2">
            <span className="text-xs font-semibold text-slate-700">Kịch bản quan tâm</span>
            <div className="flex flex-wrap gap-1.5">
              {queryTags.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-200"
                >
                  {t}
                  <button
                    type="button"
                    onClick={() => handleRemoveQueryTag(t)}
                    aria-label={`Xóa kịch bản ${t}`}
                    className="hover:text-blue-900 font-bold text-xs leading-none"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <input
                type="text"
                aria-label="Thêm kịch bản quan tâm"
                placeholder="Thêm kịch bản (vd: công trường ban đêm)"
                value={newTagInput}
                onChange={(e) => setNewTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddQueryTag();
                  }
                }}
                className="flex-1 text-xs px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-600 bg-white"
              />
              <button
                type="button"
                onClick={handleAddQueryTag}
                className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
              >
                Thêm
              </button>
            </div>
          </div>
        )}

        {/* Chế độ chuyên gia */}
        <div data-advanced-params>
          <details
            open={showAdvanced}
            onToggle={(e) => {
              const isOpen = (e.currentTarget as HTMLDetailsElement).open;
              setAdvancedPanelOpen(isOpen);
            }}
            className="rounded-xl border border-slate-200 p-3 text-sm bg-white"
          >
            <summary className="cursor-pointer font-semibold flex items-center justify-between text-xs text-slate-700 select-none">
              <span className="flex items-center gap-1.5">
                <span>{PANEL_HELP.expert.label}</span>
                <Tooltip label={PANEL_HELP.expert.label} content={PANEL_HELP.expert.tooltip} />
                {advancedParams && (
                  <span className="rounded-full border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-700">
                    Tuỳ chỉnh
                  </span>
                )}
              </span>
              <span className="font-mono text-slate-400">{showAdvanced ? "▲" : "▼"}</span>
            </summary>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs border-t border-slate-100 pt-3">
              <span className="font-semibold text-slate-700 flex items-center gap-1">
                <span>{PANEL_HELP.fullConfig.label}</span>
                <Tooltip label={PANEL_HELP.fullConfig.label} content={PANEL_HELP.fullConfig.tooltip} />
              </span>
              <span className="inline-flex flex-wrap items-center gap-1.5 text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs">
                <span className="font-medium text-slate-800">Rare v2.4</span>
                <span className="text-slate-400">·</span>
                <span className="font-medium text-slate-800">LiDAR + camera</span>
                <span className="text-slate-400">·</span>
                <span>PointPillars (Tầng 1) tự dùng khi đã chạy xong</span>
              </span>
            </div>
            <AdvancedParamsPanel
              open={true}
              schema={uiSchema}
              draft={currentAdvancedDraft}
              applied={!!advancedParams}
              onDraftChange={setAdvancedDraft}
              onApply={handleApplyAdvanced}
              onReset={handleResetAdvanced}
              schemaError={paramsSchema.isError ? (paramsSchema.error instanceof Error ? paramsSchema.error.message : "Hãy thử lại.") : null}
              onRetrySchema={() => void paramsSchema.refetch()}
              frozenEngine={engineVersion === "rare_v24"}
            />
          </details>
        </div>

        {/* Cảnh báo hoặc ghi chú chân trang */}
        {result?.warnings && visibleWarnings(result.warnings).length > 0 ? (
          <div
            data-testid="warning"
            className="p-3.5 bg-amber-50/90 border border-amber-200 text-amber-900 rounded-xl flex items-start gap-2 text-xs leading-relaxed"
          >
            <span className="text-amber-600 font-bold text-sm leading-none mt-0.5">⚠️</span>
            <div>
              {visibleWarnings(result.warnings).map((w) => (
                <p key={w}>{WARNING_LABELS[w] ?? w}</p>
              ))}
            </div>
          </div>
        ) : done ? (
          <p className="text-[11px] text-slate-500 text-center">Phân tích hoàn tất.</p>
        ) : (
          <p className="text-[11px] text-slate-400 text-center italic">
            Chỉnh tham số bất kỳ lúc nào; kết quả hiện ở đây sau khi phân tích.
          </p>
        )}
      </div>
    </aside>
  );
}
