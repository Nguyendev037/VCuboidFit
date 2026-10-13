import type { Preset } from "@/lib/api/types";
import { PRESETS } from "@/lib/api/types";
import { AdvancedParamsPanel } from "@/components/AdvancedParamsPanel";
import { PRESET_LABELS, PRESET_LOCK_TITLE, getAdvancedPanelOpen, pct, setAdvancedPanelOpen } from './dashboardState';
import type { DashboardState } from './useDashboard';

export function FilterBar(state: Pick<
  DashboardState,
  "activePipeline"
  |"advancedParams"
  |"budget"
  |"changeDiversity"
  |"changePreset"
  |"currentAdvancedDraft"
  |"dataset"
  |"demo"
  |"diversity"
  |"done"
  |"engineVersion"
  |"handleAddQueryTag"
  |"handleApplyAdvanced"
  |"handleRemoveQueryTag"
  |"handleResetAdvanced"
  |"handleResetDefaults"
  |"job"
  |"jobId"
  |"newTagInput"
  |"noTier1"
  |"paramsSchema"
  |"preset"
  |"profile"
  |"queryTags"
  |"result"
  |"setAdvancedDraft"
  |"setBudget"
  |"setEngineVersion"
  |"setNewTagInput"
  |"setProfile"
  |"setStrategy"
  |"showAdvanced"
  |"strategy"
  |"t1Local"
  |"t1Remote"
  |"t1Run"
  |"uiSchema"
>) {
  const {
    activePipeline,
    advancedParams,
    budget,
    changeDiversity,
    changePreset,
    currentAdvancedDraft,
    dataset,
    demo,
    diversity,
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
    profile,
    queryTags,
    result,
    setAdvancedDraft,
    setBudget,
    setEngineVersion,
    setNewTagInput,
    setProfile,
    setStrategy,
    showAdvanced,
    strategy,
    t1Local,
    t1Remote,
    t1Run,
    uiSchema,
  }=state;
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

        {/* Ngân sách slider */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-slate-700">Ngân sách</span>
            <span className="font-mono font-bold text-blue-600">
              {pct(budget)} · {Math.ceil((result?.poolSize??dataset?.frames??0)*budget)} frame
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

        {/* Chiến lược preset 2x2 grid */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label htmlFor="strategy-select" className="text-xs font-semibold text-slate-700">
              Chiến lược
            </label>
            {/* Select native ẩn/hỗ trợ smoke test */}
            <select
              id="strategy-select"
              aria-label="Chiến lược"
              value={preset}
              disabled={noTier1}
              title={noTier1? PRESET_LOCK_TITLE:undefined}
              onChange={(e) => changePreset(e.target.value as Preset)}
              className="text-xs border border-slate-200 rounded px-1 py-0.5 text-slate-600 bg-white"
            >
              {PRESETS.map((p) => (
                <option key={p} value={p}>
                  {PRESET_LABELS[p].title}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2 mt-1">
            {PRESETS.map((pKey) => {
              const isSelected=preset===pKey;
              const item=PRESET_LABELS[pKey];
              return (
                <button
                  key={pKey}
                  type="button"
                  onClick={() => changePreset(pKey)}
                  aria-pressed={isSelected}
                  disabled={noTier1}
                  title={noTier1? PRESET_LOCK_TITLE:undefined}
                  className={`p-3 rounded-xl border text-left flex flex-col gap-0.5 transition-all disabled:opacity-60 disabled:cursor-not-allowed ${isSelected
                      ? "border-blue-600 bg-blue-50/60 ring-1 ring-blue-600"
                      :"border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                >
                  <span className={`text-xs font-bold ${isSelected? "text-blue-700":"text-slate-800"}`}>
                    {item.title}
                    {isSelected&&advancedParams&&(
                      <span className="ml-1 rounded-full border border-blue-200 bg-white px-1 py-0.5 text-[9px] text-blue-700">
                        Tuỳ chỉnh
                      </span>
                    )}
                  </span>
                  <span className="text-[10px] text-slate-500">
                    {activePipeline==="lidar"
                      ? pKey==="rare_first"
                        ? "Ưu tiên Hiếm trong dữ liệu"
                        :pKey==="safety_scenarios"
                          ? "Ưu tiên Hiếm + Model chưa chắc"
                          :item.desc
                      :item.desc}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Mức đa dạng (Segmented control) */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-semibold text-slate-700">Mức đa dạng</span>
          <div className="grid grid-cols-3 p-1 bg-slate-100 rounded-xl gap-1 text-xs font-medium text-center">
            {[
              { label: "Thấp", val: 0.2 },
              { label: "Vừa", val: 0.5 },
              { label: "Cao", val: 0.8 },
            ].map((d) => (
              <button
                key={d.label}
                type="button"
                onClick={() => changeDiversity(d.val)}
                aria-pressed={Math.abs(diversity-d.val)<0.2}
                className={`py-1.5 rounded-lg transition-all ${Math.abs(diversity-d.val)<0.2
                    ? "bg-white text-slate-900 font-bold shadow-xs"
                    :"text-slate-500 hover:text-slate-800"
                  }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <div data-advanced-params><details className="mb-4 rounded-xl border p-3 text-sm"><summary className="cursor-pointer font-semibold">Chi tiết kỹ thuật</summary><div className="mt-3 flex flex-wrap gap-3">
          <label>Engine <select aria-label="Engine" value={engineVersion} onChange={e => setEngineVersion(e.target.value)}><option value="c4_legacy">C4 hiện tại</option><option value="rare_v24">Rare v2.4</option></select></label>
          <label>Profile <select aria-label="Profile" value={profile} onChange={e => setProfile(e.target.value as "lidar_only"|"multisensor")}><option value="lidar_only">Chỉ LiDAR</option><option value="multisensor">LiDAR + camera</option></select></label>
          {engineVersion==="rare_v24"&&<label>Chiến lược <select value={strategy} onChange={e => setStrategy(e.target.value as typeof strategy)}><option value="balanced">Cân bằng</option><option value="vru_priority">Ưu tiên VRU</option><option value="diversity">Đa dạng</option></select></label>}
        </div></details><AdvancedParamsPanel
            open={showAdvanced}
            schema={uiSchema}
            draft={currentAdvancedDraft}
            applied={!!advancedParams}
            onToggle={() => setAdvancedPanelOpen(!getAdvancedPanelOpen())}
            onDraftChange={setAdvancedDraft}
            onApply={handleApplyAdvanced}
            onReset={handleResetAdvanced}
            schemaError={paramsSchema.isError? (paramsSchema.error instanceof Error? paramsSchema.error.message:"Hãy thử lại."):null}
            onRetrySchema={() => void paramsSchema.refetch()}
            tierStatus={
              !jobId&&paramsSchema.data
                ? {
                  // Chưa có job: Tầng 0 chờ dữ liệu; Tầng 1 theo máy
                  tier0: { state: "queued", nTotal: null, nKeep: null, durationSec: null },
                  tier1: {
                    state: paramsSchema.data.tierAvailable.includes(1)? "ready":"skipped",
                    reason: paramsSchema.data.tier1Reason??null,
                    canRun: false,
                    novSource: null,
                  },
                }
                :job.data?.tier0||job.data?.tier1
                  ? {
                    tier0: job.data.tier0,
                    tier1: job.data.tier1,
                    runBusy: t1Local.isPending,
                    runError: t1Local.isError? (t1Local.error instanceof Error? t1Local.error.message:"Không chạy được Tầng 1."):null,
                    onRunTier1: demo? undefined:() => t1Local.mutate(),
                  }
                  :undefined
            }
            colab={
              noTier1&&t1Remote.data?.enabled&&!["queued", "running"].includes(job.data?.tier1?.state??"")
                ? {
                  enabled: true,
                  task: t1Remote.data.task,
                  busy: t1Run.isPending,
                  error: t1Run.isError? (t1Run.error instanceof Error? t1Run.error.message:"Không tạo được việc trên Colab."):null,
                  onRun: () => t1Run.mutate(),
                }
                :undefined
            }
          /></div>

        {/* Kịch bản quan tâm */}
        {activePipeline==="camera"&&(
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
                  if(e.key==="Enter") {
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

        {/* Cảnh báo hoặc ghi chú chân trang */}
        {result?.warnings&&result.warnings.length>0? (
          <div
            data-testid="warning"
            className="p-3.5 bg-amber-50/90 border border-amber-200 text-amber-900 rounded-xl flex items-start gap-2 text-xs leading-relaxed"
          >
            <span className="text-amber-600 font-bold text-sm leading-none mt-0.5">⚠️</span>
            <div>
              {result.warnings.map((w) => (
                <p key={w}>{w}</p>
              ))}
            </div>
          </div>
        ):done? (
          <p className="text-[11px] text-slate-500 text-center">Phân tích hoàn tất.</p>
        ):(
          <p className="text-[11px] text-slate-400 text-center italic">
            Tinh chỉnh dùng được sau khi phân tích xong.
          </p>
        )}
      </div>
    </aside>
  );
}
