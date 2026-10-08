"use client";

import React, { useState, useRef, useEffect, useSyncExternalStore } from "react";
import Link from "next/link";
import { FolderOpen, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useQuery, useMutation, keepPreviousData } from "@tanstack/react-query";
import {
  createJob,
  getJob,
  getDataset,
  listJobs,
  listSelections,
  getSelection,
  getParamsSchema,
  getT1Remote,
  createT1Remote,
  cancelJob,
  deleteJob,
  deleteAllJobs,
  select,
  exportUrl,
  finalizeUpload,
  getDatasetProgress,
  DEMO_KEY,
} from "@/lib/api/client";
import { checkProgressPct, formatEta, PHASE_LABELS, summarizeUploads, uploadFiles, type UploadItemState } from "@/lib/upload";
import type {
  DatasetProgress,
  DatasetReport,
  Preset,
  SelectParams,
  JobSummary,
  Pipeline,
} from "@/lib/api/types";
import { PRESETS } from "@/lib/api/types";
import { recallRows, stageLabel } from "@/lib/constants";
import { isDatasetUsable, datasetValidationMessage } from "@/lib/datasetValidation";
import { AdvancedParamsPanel } from "@/components/AdvancedParamsPanel";
import { clearRunBookmark, readRunBookmark, saveRunBookmark, recoveryParams, recoveryQueries, inheritedRunParams, paramsEqual } from "@/lib/runRecovery";
import { METRICS, RARITY_COMPARISON, SETTINGS, gtTagLabel, reasonText } from "@/lib/glossary";
import { Tooltip } from "@/components/ui/Tooltip";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  draftFromSchema,
  hasTier1,
  isAdvancedPanelInitiallyOpen,
  normalizeAdvancedParams,
  sanitizeDraft,
  sanitizeSelectParams,
  type AdvancedDraft,
  type AdvancedSubmitParams,
} from "@/lib/advancedParams";

const pct = (x: number) => `${Math.round(x * 100)}%`;
const formatBytes = (bytes: number) => {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
};
const formatDuration = (seconds: number) =>
  `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;

const PRESET_LABELS: Record<Preset, { title: string; desc: string }> = {
  balanced: { title: "Cân bằng", desc: "Cân bằng các tiêu chí" },
  rare_first: { title: "Hiếm trước", desc: "Ưu tiên Hiếm trong dữ liệu" },
  hard_for_model: { title: "Khó với model", desc: "Ưu tiên Model chưa chắc chắn" },
  safety_scenarios: { title: "Kịch bản an toàn", desc: "Ưu tiên Hiếm + Model chưa chắc" },
};

const PRESET_LOCK_TITLE = "Chiến lược chỉ đổi được khi job có Tầng 1 (model seed); job này chưa có nên dùng mặc định Tầng 0.";

const ANALYSIS_STEPS = [
  { stage: "index", name: "Lập chỉ mục", hint: "đọc ảnh & nhãn" },
  { stage: "dino", name: "Độ hiếm", hint: "Novelty" },
  { stage: "det", name: "Độ khó", hint: "Uncertainty" },
  { stage: "clip", name: "Khớp kịch bản", hint: "Query" },
  { stage: "merge", name: "Tổng hợp S", hint: "điểm cuối" },
];
const LIDAR_ANALYSIS_STEPS = [
  { stage: "lidar_index", name: stageLabel("lidar_index", "lidar"), hint: "đọc frame và LiDAR" },
  { stage: "t0", name: stageLabel("t0", "lidar"), hint: "đặc trưng hình học" },
];

// Cờ "dữ liệu mẫu" nằm trong sessionStorage; useSyncExternalStore để badge không lệch khi SSR.
const demoListeners = new Set<() => void>();
const subscribeDemo = (cb: () => void) => {
  demoListeners.add(cb);
  return () => void demoListeners.delete(cb);
};
const getDemo = () => {
  try {
    return window.sessionStorage.getItem(DEMO_KEY) === "1";
  } catch {
    return false;
  }
};
function setDemoFlag(on: boolean) {
  try {
    if (on) window.sessionStorage.setItem(DEMO_KEY, "1");
    else window.sessionStorage.removeItem(DEMO_KEY);
  } catch {
    /* sessionStorage bị chặn: chạy chế độ thật */
  }
  demoListeners.forEach((f) => f());
}

const UPLOAD_COLLAPSED_KEY = "vcf.uploadListCollapsed";
const readUploadCollapsed = (): boolean | null => {
  try {
    const v = window.localStorage.getItem(UPLOAD_COLLAPSED_KEY);
    return v === "1" ? true : v === "0" ? false : null;
  } catch {
    return null;
  }
};

const ADVANCED_PANEL_KEY = "vcf-advanced-open";
const ADVANCED_PANEL_CHANGE = "vcf-advanced-panel-change";
let advancedPanelFallback = false;
const getAdvancedPanelOpen = () => {
  try {
    return isAdvancedPanelInitiallyOpen(window.localStorage);
  } catch {
    return advancedPanelFallback;
  }
};
const subscribeAdvancedPanel = (onChange: () => void) => {
  window.addEventListener("storage", onChange);
  window.addEventListener(ADVANCED_PANEL_CHANGE, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(ADVANCED_PANEL_CHANGE, onChange);
  };
};
function setAdvancedPanelOpen(open: boolean) {
  advancedPanelFallback = open;
  try {
    window.localStorage.setItem(ADVANCED_PANEL_KEY, open ? "1" : "0");
  } catch {
    // Keep the panel state for this tab when storage is unavailable.
  }
  window.dispatchEvent(new Event(ADVANCED_PANEL_CHANGE));
}

const DEFAULT_QUERIES = [
  "người đi bộ cắt ngang",
  "xe đạp ban đêm",
  "mưa lớn",
];

function invalidateRecovery(request: { current: number }) {
  request.current += 1;
}

export default function Home() {
  const [error, setError] = useState("");

  // ---- Bước 1: Nạp dữ liệu ----
  const [items, setItems] = useState<UploadItemState[]>([]);
  const [uploading, setUploading] = useState(false);
  const [collapsedPref, setCollapsedPref] = useState<boolean | null>(() =>
    typeof window === "undefined" ? null : readUploadCollapsed());
  const collapsed = collapsedPref ?? items.length > 3; // C2: > 3 tệp tự rút gọn
  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsedPref(next);
    try {
      window.localStorage.setItem(UPLOAD_COLLAPSED_KEY, next ? "1" : "0");
    } catch {
      // storage không dùng được: giữ trạng thái trong tab
    }
  }
  const [checking, setChecking] = useState(false);
  const [checkProgress, setCheckProgress] = useState<DatasetProgress | null>(null);
  const uploadSummary = summarizeUploads(items);
  const [paused, setPaused] = useState(false);
  const [dataset, setDataset] = useState<DatasetReport | null>(null);
  const [pipeline, setPipeline] = useState<Pipeline>("lidar");
  const uploadIdRef = useRef<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const filesRef = useRef<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const demo = useSyncExternalStore(subscribeDemo, getDemo, () => false);

  /** Chạy thử: dùng dữ liệu mẫu (không cần upload/worker) để xem thẳng Kết quả và Deep Review. */
  async function runDemo() {
    ++recoveryRequest.current;
    setRestoring(false);
    setError("");
    try {
      setDemoFlag(true);
      const report = await finalizeUpload("demo");
      setDataset(report);
      if (!isDatasetUsable(report)) return;
      setPipeline(report.hasLidar ? "lidar" : "camera");
      setRestored(null);
      setAdvancedDraft(null);
      setAdvancedParams(null);
      setJobId((await createJob(report.datasetId, report.hasLidar ? "lidar" : "camera")).jobId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không chạy thử được");
    }
  }

  async function startUpload(files: File[]) {
    ++recoveryRequest.current;
    setRestoring(false);
    setJobId(null);
    setDataset(null);
    setPipeline("lidar");
    setDemoFlag(false); // upload thật: thoát chế độ dữ liệu mẫu
    filesRef.current = files;
    setError("");
    setUploading(true);
    setPaused(false);
    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const uploadRes = await uploadFiles(files, {
        signal: abort.signal,
        uploadId: uploadIdRef.current,
        onUploadId: (id) => {
          uploadIdRef.current = id;
        },
        onProgress: (name, received, total) => {
          setItems((prev) => {
            const next = prev.filter((i) => i.name !== name);
            next.push({ name, received, total });
            return files.map((f) => next.find((i) => i.name === f.name) ?? { name: f.name, received: 0, total: f.size });
          });
        },
      });
      setChecking(true);
      setCheckProgress(null);
      const poll = setInterval(() => {
        void getDatasetProgress(uploadRes.uploadId).then(setCheckProgress);
      }, 1000);
      let report: DatasetReport;
      try {
        report = await finalizeUpload(uploadRes.uploadId);
      } finally {
        clearInterval(poll);
        setChecking(false);
        setCheckProgress(null);
      }
      setDataset(report);
      if (isDatasetUsable(report)) {
        setPipeline(report.hasLidar ? "lidar" : "camera");
      }
      setJobId(null);
      setRestored(null);
      setAdvancedDraft(null);
      setAdvancedParams(null);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        setPaused(true);
      } else {
        setItems((prev) => prev.map((i) => (i.received < i.total ? { ...i, failed: true } : i)));
        setError(e instanceof Error ? e.message : "Lỗi tải tệp lên");
      }
    } finally {
      setUploading(false);
    }
  }

  // ---- Bước 2: Phân tích ----
  const [jobId, setJobId] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [restored, setRestored] = useState<{ id: string; params: SelectParams } | null>(null);
  const [basicOverrides, setBasicOverrides] = useState({ preset: false, diversity: false });
  const recoveryStarted = useRef(false);
  const recoveryRequest = useRef(0);
  const recentJobs = useQuery({
    queryKey: ["recent-jobs", demo],
    queryFn: listJobs,
    refetchOnWindowFocus: true,
  });
  const job = useQuery({
    queryKey: ["job", jobId, demo],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.state ?? "") ? 2000 : false,
  });

  async function startJob() {
    if (!dataset || !isDatasetUsable(dataset)) return;
    ++recoveryRequest.current;
    setRestoring(false);
    setError("");
    try {
      const res = await createJob(dataset.datasetId, dataset.hasLidar ? "lidar" : "camera");
      setRestored(null);
      setPipeline(dataset.hasLidar ? "lidar" : "camera");
      setAdvancedDraft(null);
      setAdvancedParams(null);
      setJobId(res.jobId);
      void recentJobs.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khởi tạo job");
    }
  }

  // ---- Bước 3: Tinh chỉnh & Kết quả ----
  const [budget, setBudget] = useState(0.05);
  const [preset, setPreset] = useState<Preset>("balanced");
  const [diversity, setDiversity] = useState(0.5);
  const [queryTags, setQueryTags] = useState<string[]>(DEFAULT_QUERIES);
  const [newTagInput, setNewTagInput] = useState("");
  const showAdvanced = useSyncExternalStore(subscribeAdvancedPanel, getAdvancedPanelOpen, () => false);
  const [advancedDraft, setAdvancedDraft] = useState<AdvancedDraft | null>(null);
  const [advancedParams, setAdvancedParams] = useState<AdvancedSubmitParams | null>(null);
  const done = job.data?.state === "done";
  const activePipeline = pipeline;
  const analysisSteps = activePipeline === "lidar" ? LIDAR_ANALYSIS_STEPS : ANALYSIS_STEPS;

  const paramsSchema = useQuery({
    queryKey: ["params-schema", jobId, demo],
    queryFn: () => getParamsSchema(jobId!),
    enabled: !!jobId && done && activePipeline === "lidar",
    staleTime: 60_000,
  });
  const currentAdvancedDraft = sanitizeDraft(advancedDraft, paramsSchema.data);
  const noTier1 = !!paramsSchema.data && !hasTier1(paramsSchema.data);

  // A7: Tầng 1 chạy từ xa trên Colab (chỉ hỏi khi job chưa có Tầng 1)
  const t1Remote = useQuery({
    queryKey: ["t1-remote", jobId, demo],
    queryFn: () => getT1Remote(jobId!),
    enabled: !!jobId && done && activePipeline === "lidar" && noTier1 && !demo,
    retry: false,
    refetchInterval: (q) => (["queued", "leased"].includes(q.state.data?.task?.state ?? "") ? 15_000 : false),
  });
  const t1Run = useMutation({
    mutationFn: () => createT1Remote(jobId!),
    onSuccess: () => void t1Remote.refetch(),
    onError: () => void t1Remote.refetch(),
  });
  const t1State = t1Remote.data?.task?.state;
  useEffect(() => {
    if (t1State === "done" && noTier1) void paramsSchema.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t1State, noTier1]);

  const [debounced, setDebounced] = useState<SelectParams>({
    budget,
    pipeline: activePipeline,
    preset,
    diversity,
    queries: activePipeline === "lidar" ? undefined : queryTags,
  });

  async function openRun(summary: JobSummary, sid?: string) {
    const requestId = ++recoveryRequest.current;
    setRestoring(true);
    setError("");
    try {
      const report = await getDataset(summary.datasetId);
      if (requestId !== recoveryRequest.current) return;
      const selections = summary.state === "done" ? await listSelections(summary.jobId) : [];
      if (requestId !== recoveryRequest.current) return;
      const selectionId = sid ?? selections[0]?.selectionId;
      const saved = selectionId ? await getSelection(summary.jobId, selectionId) : null;
      if (requestId !== recoveryRequest.current) return;
      const params = saved ? recoveryParams(saved.params as SelectParams, summary.pipeline) : recoveryParams({ budget: 0.05 }, summary.pipeline);
      if (summary.pipeline === "lidar") delete params.queries;
      else params.queries ??= DEFAULT_QUERIES;
      setBudget(params.budget);
      setPreset(params.preset ?? "balanced");
      setDiversity(params.diversity as number);
      setQueryTags((params.queries ?? DEFAULT_QUERIES).map((q) => typeof q === "string" ? q : q.text));
      setAdvancedParams(null);
      setAdvancedDraft(saved && summary.pipeline === "lidar" ? {
        ...draftFromSchema(), ...params,
        tier: params.tier === 1 ? 1 : 0,
        maxPerScene: params.maxPerScene ?? 4,
      } as AdvancedDraft : null);
      setRestored(saved ? { id: saved.selectionId, params } : null);
      setBasicOverrides({ preset: false, diversity: false });
      setDebounced(params);
      setItems([]);
      setDataset(report);
      setPipeline(summary.pipeline);
      setJobId(summary.jobId);
      let storage: Storage | undefined;
      try { storage = window.localStorage; } catch { /* URL works without storage. */ }
      window.history.replaceState(null, "", saveRunBookmark({ jobId: summary.jobId, datasetId: report.datasetId, selectionId: saved?.selectionId, demo: getDemo() }, new URL(window.location.href), storage));
    } catch (e) {
      if (requestId === recoveryRequest.current) setError(e instanceof Error ? e.message : "Không mở được lần chạy.");
    } finally {
      if (requestId === recoveryRequest.current) setRestoring(false);
    }
  }

  useEffect(() => {
    if (recoveryStarted.current) return;
    recoveryStarted.current = true;
    const bookmark = readRunBookmark(window.location.search);
    if (!bookmark) return;
    const initialRequest = recoveryRequest.current;
    setDemoFlag(bookmark.demo);
    void listJobs().then(async (jobs) => {
      if (initialRequest !== recoveryRequest.current) return;
      let summary = jobs.find((item) => item.jobId === bookmark.jobId);
      if (!summary && bookmark.datasetId) {
        const status = await getJob(bookmark.jobId);
        if (initialRequest !== recoveryRequest.current) return;
        summary = { jobId: bookmark.jobId, datasetId: bookmark.datasetId, pipeline: status.pipeline ?? "camera", state: status.state, createdAt: "", finishedAt: null, scenes: 0, frames: 0, version: "", lastSelectionId: bookmark.selectionId ?? null };
      }
      if (!summary) throw new Error("Không tìm thấy lần chạy đã lưu trong lịch sử.");
      await openRun(summary, bookmark.selectionId);
    }).catch((e) => {
      if (initialRequest === recoveryRequest.current) setError(e instanceof Error ? e.message : "Không tải được lịch sử.");
    });
    // Restore once; subsequent opens are explicit user actions.
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced({
        ...inheritedRunParams(restored?.params, basicOverrides),
        budget,
        pipeline: activePipeline,
        preset,
        diversity,
        queries: activePipeline === "lidar" ? undefined : recoveryQueries(restored?.params, queryTags),
        ...(advancedParams ?? {}),
      });
    }, 300);
    return () => clearTimeout(t);
  }, [budget, preset, diversity, queryTags, activePipeline, advancedParams, restored, basicOverrides]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.altKey && event.shiftKey && event.key.toLowerCase() === "a") {
        event.preventDefault();
        setAdvancedPanelOpen(!getAdvancedPanelOpen());
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const selectParams = activePipeline === "lidar" ? sanitizeSelectParams(debounced, paramsSchema.data) : debounced;
  const selection = useQuery({
    queryKey: ["select", jobId, selectParams, demo],
    queryFn: () => restored && paramsEqual(debounced, restored.params)
      ? getSelection(jobId!, restored.id) : select(jobId!, selectParams),
    enabled: !!jobId && done && !restoring && (activePipeline !== "lidar" || !paramsSchema.isPending),
    placeholderData: (previous, previousQuery) => previousQuery?.queryKey[1] === jobId && previousQuery?.queryKey[3] === demo ? keepPreviousData(previous) : undefined,
  });

  const result = selection.data;
  const m = result?.metrics ?? null;

  useEffect(() => {
    if (!jobId || restoring) return;
    let storage: Storage | undefined;
    try { storage = window.localStorage; } catch { /* URL remains available. */ }
    window.history.replaceState(null, "", saveRunBookmark({ jobId, datasetId: dataset?.datasetId, demo, selectionId: result?.selectionId ?? restored?.id }, new URL(window.location.href), storage));
  }, [jobId, dataset?.datasetId, restoring, demo, result?.selectionId, restored?.id]);

  const handleResetDefaults = () => {
    setRestored(null);
    setBudget(0.05);
    setPreset("balanced");
    setDiversity(0.5);
    setQueryTags(DEFAULT_QUERIES);
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const handleStartNew = () => {
    if (!window.confirm("Nhập dữ liệu mới? Job cũ vẫn còn trong Lần chạy gần đây.")) return;
    resetWorkspace();
  };

  const resetWorkspace = () => {
    invalidateRecovery(recoveryRequest);
    abortRef.current?.abort();
    abortRef.current = null;
    uploadIdRef.current = undefined;
    filesRef.current = [];
    if (fileInputRef.current) fileInputRef.current.value = "";

    let storage: Storage | undefined;
    try { storage = window.localStorage; } catch { /* URL still resets. */ }
    window.history.replaceState(null, "", clearRunBookmark(new URL(window.location.href), storage));

    setDemoFlag(false);
    setError("");
    setItems([]);
    setUploading(false);
    setPaused(false);
    setDataset(null);
    setPipeline("lidar");
    setJobId(null);
    setRestoring(false);
    setRestored(null);
    setBasicOverrides({ preset: false, diversity: false });
    setBudget(0.05);
    setPreset("balanced");
    setDiversity(0.5);
    setQueryTags(DEFAULT_QUERIES);
    setNewTagInput("");
    setAdvancedDraft(null);
    setAdvancedParams(null);
    setDebounced({ budget: 0.05, pipeline: "lidar", preset: "balanced", diversity: 0.5 });
    void recentJobs.refetch();
  };

  // ---- Xoá lịch sử (SPEC-P04) ----
  const [deleteTarget, setDeleteTarget] = useState<{ kind: "one"; jobId: string } | { kind: "all" } | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [historyNote, setHistoryNote] = useState("");

  async function confirmDelete() {
    const target = deleteTarget;
    setDeleteTarget(null);
    if (!target) return;
    setHistoryError("");
    setHistoryNote("");
    try {
      const res = target.kind === "one" ? await deleteJob(target.jobId) : await deleteAllJobs();
      if (res.skipped.length > 0) setHistoryNote(`Bỏ qua ${res.skipped.length} lần chạy đang chạy`);
      if (jobId && res.deleted.includes(jobId)) resetWorkspace();
      await recentJobs.refetch();
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : "Không xoá được lịch sử.");
    }
  }

  const handleApplyAdvanced = () => {
    setAdvancedParams(normalizeAdvancedParams(currentAdvancedDraft));
  };

  const changePreset = (value: Preset) => {
    setPreset(value);
    setBasicOverrides((previous) => ({ ...previous, preset: true }));
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const changeDiversity = (value: number) => {
    setDiversity(value);
    setBasicOverrides((previous) => ({ ...previous, diversity: true }));
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const handleResetAdvanced = () => {
    setRestored(null);
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const handleAddQueryTag = () => {
    const trimmed = newTagInput.trim();
    if (trimmed && !queryTags.includes(trimmed)) {
      setQueryTags([...queryTags, trimmed]);
      setNewTagInput("");
    }
  };

  const handleRemoveQueryTag = (tag: string) => {
    setQueryTags(queryTags.filter((t) => t !== tag));
  };

  return (
    <div className="min-h-screen bg-[#F7F8FA] text-[#0F172A] flex flex-col font-sans">
      {/* 1. Header ứng dụng theo Figma (Screens 01 & 02) */}
      <header className="w-full bg-white border-b border-[#E2E8F0] px-4 sm:px-8 py-3.5 flex flex-wrap items-center justify-between gap-3 shadow-xs sticky top-0 z-40">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5 font-bold text-lg text-slate-900 tracking-tight">
            {/* Cube Logo */}
            <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-xs">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
            </div>
            <span>VCuboidFIT</span>
          </Link>

          <div className="hidden sm:flex flex-col border-l border-slate-200 pl-4">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Dataset</span>
            <span className="text-xs font-semibold text-slate-800">
              {dataset ? dataset.version : "Chưa có dataset"}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-4">
          <Link href="/huong-dan" className="text-xs font-medium text-slate-600 hover:text-blue-700">Hướng dẫn</Link>
          {(jobId || dataset || items.length > 0) && (
            <button type="button" onClick={handleStartNew} className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50">
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Nhập dữ liệu mới
            </button>
          )}
          {demo && (
            <span className="px-2.5 py-0.5 text-[11px] font-semibold rounded-full bg-amber-50 text-amber-700 border border-amber-200">
              Dữ liệu mẫu
            </span>
          )}
          <span className="text-xs text-slate-500 font-mono">
            {jobId ? `Job ${jobId}` : "Chưa có job"}
          </span>
          <span role="status" aria-live="polite">
          {done ? (
            <span className="px-3 py-1 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Hoàn tất
            </span>
          ) : job.data?.state === "running" ? (
            <span className="px-3 py-1 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-1.5 animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              Đang phân tích
            </span>
          ) : (
            <span className="px-3 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-600 border border-slate-200">
              Chờ dữ liệu
            </span>
          )}
          </span>
        </div>
      </header>

      {/* Thông báo lỗi nếu có */}
      {error && (
        <div className="max-w-[1440px] mx-auto px-4 sm:px-8 pt-4 w-full">
          <div role="alert" data-testid="error" className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs font-medium flex items-center justify-between gap-3">
            <span>{error}</span>
            <button type="button" aria-label="Đóng thông báo lỗi" onClick={() => setError("")} className="min-h-9 min-w-9 rounded text-rose-700 hover:bg-rose-100 font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-700">✕</button>
          </div>
        </div>
      )}

      {/* 2. Nội dung 2 cột: Cột trái (Quy trình 3 bước / Kết quả) & Cột phải (Panel Tinh chỉnh) */}
      <main className="max-w-[1440px] mx-auto p-4 sm:p-6 md:p-8 w-full grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 items-start">
        {/* ================= CỘT TRÁI (8 CỘT) ================= */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          <section aria-label="Lần chạy gần đây" className="border-b border-slate-200 pb-4">
            <div className="flex items-center justify-between gap-3 mb-2">
              <h2 className="text-sm font-semibold">Lần chạy gần đây</h2>
              {(recentJobs.data?.length ?? 0) > 0 && <button type="button" onClick={() => setDeleteTarget({ kind: "all" })} className="ml-auto px-2 py-1 text-xs text-rose-700 hover:bg-rose-50 rounded">Xoá tất cả</button>}
              <button type="button" title="Làm mới lịch sử" aria-label="Làm mới lịch sử" onClick={() => void recentJobs.refetch()} className="p-2 hover:bg-slate-200 rounded"><RefreshCw size={16} /></button>
            </div>
            {recentJobs.isPending && <p className="text-xs text-slate-500">Đang tải lịch sử…</p>}
            {recentJobs.error && <p role="alert" className="text-xs text-rose-700">{recentJobs.error.message}</p>}
            {recentJobs.data?.length === 0 && <p className="text-xs text-slate-500">Chưa có lần chạy.</p>}
            <div role="list" className="max-h-48 overflow-auto divide-y divide-slate-200">
              {recentJobs.data?.map((item) => <div role="listitem" key={item.jobId} className="flex items-center justify-between gap-3 py-2 text-xs">
                <div className="min-w-0"><p className="font-medium break-all">{item.version || item.datasetId} · {item.frames} frame · {item.pipeline === "lidar" ? "LiDAR" : "Camera"}{item.createdAt && item.finishedAt ? ` · ${formatDuration(Math.max(0, (new Date(item.finishedAt).getTime() - new Date(item.createdAt).getTime()) / 1000))}` : ""}</p><p className="text-slate-500 break-all">{item.jobId} · {item.state === "done" ? "Hoàn tất" : item.state === "running" ? "Đang chạy" : item.state === "queued" ? "Đang chờ" : item.state === "failed" ? "Lỗi" : "Đã huỷ"}{item.createdAt ? ` · ${new Date(item.createdAt).toLocaleString("vi-VN")}` : ""}</p></div>
                <div className="flex items-center shrink-0">
                <button type="button" disabled={restoring || uploading} onClick={() => void openRun(item)} className="flex items-center gap-1 px-2 py-2 text-blue-700 hover:bg-blue-50 rounded disabled:opacity-50"><FolderOpen size={16} />Mở</button>
                <button type="button" aria-label="Xoá lần chạy" title={item.state === "queued" || item.state === "running" ? "Đang chạy" : "Xoá lần chạy"} disabled={item.state === "queued" || item.state === "running"} onClick={() => setDeleteTarget({ kind: "one", jobId: item.jobId })} className="p-2 text-rose-700 hover:bg-rose-50 rounded disabled:opacity-40"><Trash2 size={16} /></button>
                </div>
              </div>)}
            </div>
            {(recentJobs.data?.length ?? 0) > 4 && <p className="mt-1 text-[11px] text-slate-600">Cuộn trong danh sách để xem đủ {recentJobs.data?.length} lần chạy</p>}
            {restoring && <p role="status" className="text-xs text-slate-500 mt-2">Đang mở lần chạy…</p>}
            {historyError && <p role="alert" className="text-xs text-rose-700 mt-2">{historyError}</p>}
            {historyNote && <p role="status" className="text-xs text-slate-600 mt-2">{historyNote}</p>}
            <ConfirmDialog
              open={deleteTarget !== null}
              title={deleteTarget?.kind === "all" ? "Xoá tất cả lần chạy?" : "Xoá lần chạy này?"}
              message="Xoá kết quả chọn 5% và ảnh xem trước của lần chạy; dữ liệu đã tải lên vẫn giữ."
              confirmLabel="Xoá"
              onConfirm={() => void confirmDelete()}
              onCancel={() => setDeleteTarget(null)}
            />
          </section>
          {!done ? (
            // ============ GIAO DIỆN CHƯA CÓ KẾT QUẢ (FIGMA 01) ============
            <>
              {/* Bước 1: Nạp dữ liệu */}
              <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center">
                      1
                    </div>
                    <h2 className="font-bold text-base text-slate-900">Nạp dữ liệu</h2>
                  </div>
                  <span className="text-xs text-slate-400 font-medium">Bước 1 / 3</span>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed">
                  Tải lên một hoặc nhiều file nén (.zip, .rar, .7z) chứa dataset nuScenes.
                </p>

                {/* Dropzone */}
                <div
                  role="button"
                  tabIndex={uploading ? -1 : 0}
                  aria-label="Chọn hoặc thả tệp dữ liệu"
                  aria-disabled={uploading}
                  onClick={() => !uploading && fileInputRef.current?.click()}
                  onKeyDown={(event) => {
                    if (!uploading && (event.key === "Enter" || event.key === " ")) {
                      event.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                  className="border-2 border-dashed border-blue-200 hover:border-blue-400 bg-blue-50/20 hover:bg-blue-50/40 rounded-xl p-5 sm:p-8 flex flex-col items-center justify-center gap-3 text-center cursor-pointer transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
                >
                  <div className="w-12 h-12 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-semibold text-sm text-slate-800">
                      Kéo thả file .zip / .rar / .7z vào đây
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      Chọn nhiều phần cùng lúc · tải lên theo chunk 50 MB, tiếp tục được khi mất mạng
                    </p>
                  </div>
                  <span className="mt-1 inline-flex min-h-10 items-center rounded-lg bg-blue-600 px-5 py-2 text-xs font-medium text-white shadow-xs">Chọn file</span>
                  <input
                    ref={fileInputRef}
                    data-testid="file-input"
                    type="file"
                    multiple
                    accept=".zip,.rar,.7z,.001,.002,.003,.json"
                    className="hidden"
                    disabled={uploading}
                    onChange={(e) => {
                      const files = Array.from(e.target.files ?? []);
                      if (files.length) {
                        uploadIdRef.current = undefined;
                        setItems([]);
                        setDataset(null);
                        void startUpload(files);
                      }
                    }}
                  />
                </div>

                {/* Điều khiển upload khi đang tiến hành */}
                {uploading && !checking && (
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => abortRef.current?.abort()}
                      className="px-3 py-1.5 bg-amber-100 hover:bg-amber-200 text-amber-800 text-xs font-medium rounded-lg"
                    >
                      Tạm dừng
                    </button>
                  </div>
                )}
                {paused && (
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => void startUpload(filesRef.current)}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg"
                    >
                      Tiếp tục tải lên
                    </button>
                  </div>
                )}

                {/* Danh sách file upload */}
                {items.length > 0 && (
                  <div className="mt-2 flex flex-col gap-2">
                    {items.length >= 2 && (
                      <div className="flex items-center justify-between gap-3 text-xs">
                        <span className="font-semibold text-slate-700">Danh sách tệp</span>
                        <button
                          type="button"
                          aria-expanded={!collapsed}
                          onClick={toggleCollapsed}
                          className="min-h-8 rounded-md border border-slate-300 bg-white px-3 font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          {collapsed ? "Mở rộng" : "Rút gọn"}
                        </button>
                      </div>
                    )}
                    {items.length >= 2 && collapsed ? (
                      <div data-testid="upload-summary" className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium text-slate-700">
                        {uploadSummary.count} tệp · {formatBytes(uploadSummary.totalBytes)} · {uploadSummary.pct}% đã tải
                        {uploadSummary.failed > 0 && <span className="text-rose-700"> · {uploadSummary.failed} tệp lỗi</span>}
                      </div>
                    ) : (
                      <ul className="space-y-2">
                        {items.map((i) => (
                          <li
                            key={i.name}
                            data-testid="upload-item"
                            className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs flex flex-col gap-1.5"
                          >
                            <div className="flex justify-between font-medium text-slate-700">
                              <span>{i.name}</span>
                              <span className="font-mono text-slate-500">
                                {i.received} / {i.total} B ({pct(i.total ? i.received / i.total : 0)})
                              </span>
                            </div>
                            <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-blue-600 rounded-full transition-all duration-200"
                                style={{ width: `${pct(i.total ? i.received / i.total : 0)}` }}
                              />
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {/* Thanh thời gian dự đoán xét tệp (SPEC-P05) */}
                {checking && (
                  <div data-testid="check-eta" className="p-2.5 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-950 flex flex-col gap-1.5">
                    <span className="font-medium">
                      {checkProgress
                        ? `Đang xét tệp đầu vào · ${PHASE_LABELS[checkProgress.phase] ?? checkProgress.phase} · còn khoảng ${formatEta(checkProgress.etaSec)}`
                        : "Đang xét tệp đầu vào…"}
                    </span>
                    {checkProgress ? (
                      <progress aria-label="Tiến độ xét tệp" className="w-full h-2" max={100} value={checkProgressPct(checkProgress)} />
                    ) : (
                      <progress aria-label="Tiến độ xét tệp" className="w-full h-2" />
                    )}
                  </div>
                )}

                {/* Hộp lưu ý data/ nguyên văn spec §5.2 */}
                <div className="p-3.5 bg-blue-50/80 border border-blue-200 text-blue-950 rounded-xl flex items-start gap-2.5 text-xs leading-relaxed">
                  <span className="text-blue-600 font-bold text-sm leading-none mt-0.5">ℹ</span>
                  <p data-testid="data-notice">
                    Mỗi file nén phải chứa thư mục <strong>data/</strong> ở gốc, theo cấu trúc nuScenes (<code>data/v1.0-*/</code>,{" "}
                    <code>data/samples/CAM_*/</code>, <code>data/samples/LIDAR_TOP/</code>). Dataset lớn: dùng <strong>vcf-pack</strong> để chia thành
                    các phần 50 MB rồi chọn tất cả cùng lúc.
                  </p>
                </div>

                {/* Báo cáo dataset nếu đã nạp xong */}
                {dataset && (
                  <div
                    data-testid="dataset-report"
                    role={isDatasetUsable(dataset) ? "status" : "alert"}
                    className={`p-4 rounded-xl text-xs flex flex-col gap-2 ${isDatasetUsable(dataset) ? "bg-emerald-50/50 border border-emerald-200" : "bg-rose-50 border border-rose-300"}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`font-bold ${isDatasetUsable(dataset) ? "text-emerald-900" : "text-rose-900"}`}>Báo cáo Dataset {dataset.version}</span>
                      <span className={`font-mono ${isDatasetUsable(dataset) ? "text-emerald-700" : "text-rose-700"}`}>
                        {dataset.scenes} scene · {dataset.frames} frame
                      </span>
                    </div>
                    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 ${isDatasetUsable(dataset) ? "text-emerald-800" : "text-rose-800"}`}>
                      <span>LiDAR: {dataset.hasLidar ? "✓ Có" : "✗ Không"}</span>
                      <span>Nhãn 3D: {dataset.hasAnnotations ? "✓ Có" : "✗ Không"}</span>
                    </div>
                    {!isDatasetUsable(dataset) && (
                      <p className="font-medium text-rose-800">{datasetValidationMessage(dataset)}</p>
                    )}
                  </div>
                )}
              </div>

              {/* Bước 2: Phân tích */}
              <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full bg-slate-200 text-slate-700 font-bold text-xs flex items-center justify-center">
                      2
                    </div>
                    <h2 className="font-bold text-base text-slate-900">Phân tích</h2>
                  </div>
                  <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:ml-auto">
                  <button
                    type="button"
                    onClick={() => void runDemo()}
                    disabled={!!jobId}
                    className="min-h-10 flex-1 px-3 py-2 bg-white hover:bg-blue-50 disabled:opacity-50 text-blue-800 border border-blue-200 font-medium text-xs rounded-lg transition-colors sm:flex-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
                  >
                    Chạy thử dữ liệu mẫu
                  </button>
                  <button
                    type="button"
                    onClick={() => void startJob()}
                    disabled={!isDatasetUsable(dataset) || !!jobId}
                    className="min-h-10 flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-200 disabled:text-slate-600 text-white font-medium text-xs rounded-lg shadow-xs transition-colors sm:flex-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-800"
                  >
                    Chạy phân tích
                  </button>
                  </div>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed">
                  {activePipeline === "lidar"
                    ? "Đánh giá độ hiếm hình học và tín hiệu LiDAR, rồi gộp thành điểm S. Cần nạp dữ liệu ở Bước 1 trước."
                    : "Đánh giá độ hiếm (Novelty), độ khó (Uncertainty) và mức khớp kịch bản (Query), rồi gộp thành điểm S. Cần nạp dữ liệu ở Bước 1 trước."}
                </p>

                {/* Stepper 5 bước: đường nối đi qua tâm các vòng tròn, nhãn nằm dưới và căn giữa */}
                <ol className={`grid ${activePipeline === "lidar" ? "grid-cols-2" : "grid-cols-5"} py-2`} aria-label="Tiến trình phân tích" aria-busy={job.isFetching || job.data?.state === "running"}>
                  {analysisSteps.map((s, i) => {
                    const st = job.data?.stages?.find((x) => x.name === s.stage)?.state ?? "queued";
                    const finished = st === "done";
                    const active = st === "running";
                    const failed = st === "failed" || st === "cancelled";
                    return (
                      <li key={s.stage} className="relative flex flex-col items-center text-center px-1">
                        {i < analysisSteps.length - 1 && (
                          <span
                            aria-hidden
                            className={`absolute top-3 left-1/2 h-0.5 w-full ${finished ? "bg-blue-600" : "bg-slate-200"}`}
                          />
                        )}
                        <span
                          className={`relative z-10 w-6 h-6 rounded-full border-2 text-[11px] font-bold flex items-center justify-center ${
                            finished
                              ? "bg-blue-600 border-blue-600 text-white"
                              : active
                                ? "bg-white border-blue-600 text-blue-600 animate-pulse"
                                : failed
                                  ? "bg-white border-rose-500 text-rose-600"
                                  : "bg-white border-slate-300 text-slate-500"
                          }`}
                        >
                          {finished ? "✓" : i + 1}
                        </span>
                        <span className="mt-1.5 text-xs font-semibold text-slate-800 leading-tight">{s.name}</span>
                        <span className="text-[10px] leading-tight text-slate-600">{s.hint}</span>
                        <span className={`mt-0.5 text-[10px] ${active ? "text-blue-600" : failed ? "text-rose-600" : "text-slate-400"}`}>
                          {finished ? "xong" : active ? "đang chạy" : failed ? "lỗi" : "chờ"}
                        </span>
                      </li>
                    );
                  })}
                </ol>

                {job.isError && (
                  <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
                    <span>Không tải được trạng thái phân tích: {job.error instanceof Error ? job.error.message : "Lỗi kết nối."}</span>
                    <button type="button" onClick={() => void job.refetch()} className="min-h-9 rounded-md border border-rose-300 bg-white px-3 font-semibold hover:bg-rose-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-700">Thử lại</button>
                  </div>
                )}
                {jobId && job.isPending && (
                  <p role="status" aria-live="polite" className="text-xs text-slate-700">Đang tải trạng thái phân tích...</p>
                )}

                {/* Trạng thái tiến trình */}
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                  <p data-testid="job-state">
                    {job.data
                      ? `${job.data.state} · ${job.data.stage} · ${job.data.done}/${job.data.total}`
                      : 'Chưa chạy — bấm "Chạy phân tích" để bắt đầu.'}
                  </p>
                  {job.data?.state === "running" && (
                    <button
                      onClick={() => void cancelJob(job.data!.jobId).then(() => job.refetch())}
                      className="text-rose-600 hover:text-rose-800 font-medium"
                    >
                      Hủy
                    </button>
                  )}
                </div>
              </div>

              {/* Bước 3: Kết quả placeholder */}
              <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-4 opacity-70">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-slate-200 text-slate-700 font-bold text-xs flex items-center justify-center">
                    3
                  </div>
                  <h2 className="font-bold text-base text-slate-900">Kết quả</h2>
                </div>
                <p className="text-xs text-slate-500">
                  Sau khi phân tích: 4 thẻ số, biểu đồ 6 method, lưới 12 frame đầu và nút Deep Review.
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    "Đã chọn",
                    METRICS.recall.label,
                    activePipeline === "lidar" ? METRICS.nRecall.label : METRICS.uplift.label,
                    activePipeline === "lidar" ? METRICS.sceneRecall.label : METRICS.redundancy.label
                  ].map((label) => (
                    <div key={label} className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-center flex flex-col items-center justify-center">
                      <span className="text-xs text-slate-500 font-medium leading-tight line-clamp-2">{label}</span>
                      <p className="text-xl font-bold text-slate-400 mt-1">—</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            // ============ GIAO DIỆN ĐÃ CÓ KẾT QUẢ (FIGMA 02) ============
            <>
              {/* Tóm tắt Bước 1 & Bước 2 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-white rounded-xl border border-[#E2E8F0] p-4 shadow-xs flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs">
                      ✓
                    </div>
                    <div>
                      <h3 className="font-bold text-xs text-slate-900">Bước 1 · Nạp dữ liệu</h3>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {dataset?.scenes ?? 0} scene · {dataset?.frames ?? 0} frame · {Object.values(dataset?.imagesByCam ?? {}).filter((count) => count > 0).length} camera · LiDAR {dataset?.hasLidar ? "✓" : "—"} · Nhãn {dataset?.hasAnnotations ? "✓" : "—"} · {dataset?.warnings.length ?? 0} cảnh báo
                      </p>
                    </div>
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full border border-emerald-500 text-emerald-700 text-[11px] font-mono font-medium">
                    {items.length > 0
                      ? `${items.length} file · ${formatBytes(items.reduce((sum, item) => sum + item.total, 0))}`
                      : dataset?.version ?? "Dữ liệu mẫu"}
                  </span>
                </div>

                <div className="bg-white rounded-xl border border-[#E2E8F0] p-4 shadow-xs flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs">
                      ✓
                    </div>
                    <div>
                      <h3 className="font-bold text-xs text-slate-900">Bước 2 · Phân tích</h3>
                      <p className="text-[11px] text-slate-500 mt-0.5 font-mono">
                        {(job.data?.stages ?? [])
                          .filter((stage) => stage.state === "done")
                          .map((stage) => `${stageLabel(stage.name, activePipeline)} ${formatDuration(stage.durationSec ?? 0)}`)
                          .join(" · ") || "Chưa có số liệu thời gian"}
                      </p>
                    </div>
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full border border-emerald-500 text-emerald-700 text-[11px] font-mono font-medium">
                    {formatDuration((job.data?.stages ?? [])
                      .filter((stage) => stage.state === "done")
                      .reduce((total, stage) => total + (stage.durationSec ?? 0), 0))}
                  </span>
                </div>
              </div>

              {/* Thẻ Kết quả chính */}
              <div className="bg-white rounded-xl border border-[#E2E8F0] p-6 shadow-xs flex flex-col gap-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center">
                      3
                    </div>
                    <div className="flex items-center gap-2">
                      <h2 className="font-bold text-base text-slate-900">Kết quả</h2>
                      <span className="px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs font-medium border border-blue-200">
                        {PRESET_LABELS[preset]?.title || preset} · ngân sách {pct(budget)}
                      </span>
                      {advancedParams && (
                        <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-semibold border border-slate-200">
                          Tuỳ chỉnh
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5">
                    <button type="button" onClick={handleStartNew} className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                      Nhập dữ liệu mới
                    </button>
                    {result && (
                      <a
                        href={exportUrl(jobId!, result.selectionId, debounced.budget)}
                        className="px-4 py-2 text-xs font-semibold rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 shadow-xs transition-colors flex items-center gap-1.5"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Xuất CSV
                      </a>
                    )}
                    {result && (
                      <Link
                        href={`/review/${jobId}?sel=${result.selectionId}&budget=${debounced.budget}&dataset=${dataset?.datasetId ?? ""}`}
                        className="px-4 py-2 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-xs transition-colors flex items-center gap-1.5"
                      >
                        Deep Review
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                        </svg>
                      </Link>
                    )}
                  </div>
                </div>

                {/* 4 Thẻ số theo Figma 02 */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-200 flex flex-col">
                    <div className="flex items-start gap-1">
                      <span className="text-xs text-slate-700 font-medium leading-tight line-clamp-2">Đã chọn</span>
                      <Tooltip label={SETTINGS.budget.label} content={SETTINGS.budget.tooltip} />
                    </div>
                    <p className="text-2xl font-bold font-mono text-slate-900 mt-1" data-testid="metric-selected">
                      {result ? `${result.budgetB} / ${result.poolSize}` : "21 / 404"}
                    </p>
                    <span className="text-[11px] text-slate-400 mt-1 block">
                      {result ? `${((result.budgetB / result.poolSize) * 100).toFixed(1).replace(".", ",")} % của pool` : "5,2 % của pool"}
                    </span>
                  </div>

                  <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-200 flex flex-col">
                    <div className="flex items-start gap-1">
                      <span className="text-xs text-slate-700 font-medium leading-tight line-clamp-2">{METRICS.recall.label}</span>
                      <Tooltip label={METRICS.recall.label} content={METRICS.recall.tooltip} />
                    </div>
                    <p className="text-2xl font-bold font-mono text-emerald-600 mt-1" data-testid="metric-recall">
                      {m ? pct(m.hybrid.recall) : "38 %"}
                    </p>
                    <span className="text-[11px] text-slate-400 mt-1 block">
                      {m?.random ? `Random ${pct(m.random.mean.recall)} ± ${pct(m.random.std.recall)}` : "Random 5 % ± 2"}
                    </span>
                    <span className="mt-1 flex items-start gap-1 text-[10px] leading-snug text-slate-500">
                      {dataset?.hasAnnotations ? RARITY_COMPARISON.tooltip : RARITY_COMPARISON.noLabels}
                      <Tooltip label={RARITY_COMPARISON.label} content={dataset?.hasAnnotations ? RARITY_COMPARISON.tooltip : RARITY_COMPARISON.noLabels} />
                    </span>
                  </div>

                  <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-200 flex flex-col">
                    <div className="flex items-start gap-1">
                      <span className="text-xs text-slate-700 font-medium leading-tight line-clamp-2">{activePipeline === "lidar" ? METRICS.nRecall.label : METRICS.uplift.label}</span>
                      <Tooltip label={activePipeline === "lidar" ? METRICS.nRecall.label : METRICS.uplift.label} content={activePipeline === "lidar" ? METRICS.nRecall.tooltip : METRICS.uplift.tooltip} />
                    </div>
                    <p className="text-2xl font-bold font-mono text-emerald-600 mt-1" data-testid="metric-uplift">
                      {m ? (activePipeline === "lidar" ? pct(m.hybrid.nRecall ?? m.hybrid.recall) : `${m.hybrid.uplift.toFixed(1)}×`) : "7,6×"}
                    </p>
                    <span className="text-[11px] text-slate-400 mt-1 block">{activePipeline === "lidar" ? "chuẩn hoá theo nhóm" : "so với random"}</span>
                  </div>

                  <div className="p-4 bg-slate-50/70 rounded-xl border border-slate-200 flex flex-col">
                    <div className="flex items-start gap-1">
                      <span className="text-xs text-slate-700 font-medium leading-tight line-clamp-2">{activePipeline === "lidar" ? METRICS.sceneRecall.label : METRICS.redundancy.label}</span>
                      <Tooltip label={activePipeline === "lidar" ? METRICS.sceneRecall.label : METRICS.redundancy.label} content={activePipeline === "lidar" ? METRICS.sceneRecall.tooltip : METRICS.redundancy.tooltip} />
                    </div>
                    <p className="text-2xl font-bold font-mono text-slate-900 mt-1" data-testid="metric-redundancy">
                      {m ? (activePipeline === "lidar" ? pct(m.hybrid.sceneRecall ?? m.hybrid.coverage) : m.hybrid.redundancy.toFixed(2).replace(".", ",")) : "0,12"}
                    </p>
                    <span className="text-[11px] text-slate-400 mt-1 block">{activePipeline === "lidar" ? `${m?.hybrid.nBoxes ?? 0} box` : "thấp hơn là tốt"}</span>
                  </div>
                </div>

                {/* Biểu đồ Recall theo Method (Figma 02) */}
                <div className="p-4 bg-slate-50/50 rounded-xl border border-slate-200 flex flex-col gap-3">
                  {selection.isPending && (
                    <p role="status" aria-live="polite" className="text-xs text-slate-700">Đang tải kết quả chọn frame...</p>
                  )}
                  {selection.isError && (
                    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
                      <span>Không tải được kết quả chọn frame.</span>
                      <button type="button" onClick={() => void selection.refetch()} className="min-h-9 rounded-md border border-rose-300 bg-white px-3 font-semibold hover:bg-rose-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-700">Thử lại</button>
                    </div>
                  )}
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-slate-800">
                    <span className="inline-flex items-center gap-1">Tỉ lệ bắt frame hiếm theo cách chọn <Tooltip label={METRICS.recall.label} content={METRICS.recall.tooltip} /></span>
                    <span className="text-slate-400 font-normal">Random trung bình 5 % ± 2</span>
                  </div>
                  <div className="space-y-2 text-xs">
                    {recallRows(activePipeline, m).map((row) => (
                      <div key={row.name} className="flex items-center gap-3">
                        <span className="w-32 text-slate-600 truncate font-medium text-[11px]">{row.name}</span>
                        <div className="flex-1 h-3 bg-slate-200/80 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${
                              row.isPrimary ? "bg-blue-600" : "bg-slate-400"
                            }`}
                            style={{ width: `${Math.round(row.val * 100)}%` }}
                          />
                        </div>
                        <span className="w-10 text-right font-mono text-slate-700 text-[11px] font-semibold">
                          {Math.round(row.val * 100)} %
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Lưới 12 Thumbnail theo Figma 02 */}
                <div>
                  <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-3">
                    {Math.min(12, result?.preview.length ?? 0)} Frame tiêu biểu đã chọn
                  </h3>
                  {result && result.preview.length === 0 ? (
                    <p role="status" className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center text-sm text-slate-700">Chưa có frame xem trước cho lựa chọn này.</p>
                  ) : <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                    {(result?.preview ?? []).slice(0, 12).map((f) => (
                      <Link
                        key={f.sampleToken}
                        href={`/review/${jobId}?sel=${result?.selectionId}&budget=${debounced.budget}&frame=${f.sampleToken}&dataset=${dataset?.datasetId ?? ""}`}
                        data-testid="thumb"
                        className="group bg-white border border-slate-200 hover:border-blue-500 rounded-xl overflow-hidden shadow-xs hover:shadow-md transition-all flex flex-col"
                      >
                        <div className="aspect-video w-full bg-slate-100 relative overflow-hidden">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={f.thumbUrl}
                            alt={`#${f.rank} ${f.sceneName}`}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                          />
                          <span className="absolute top-1.5 left-1.5 bg-black/75 backdrop-blur-sm text-white font-mono text-[10px] font-bold px-1.5 py-0.5 rounded">
                            #{f.rank}
                          </span>
                        </div>
                        <div className="p-2 flex flex-col gap-1 justify-between flex-1">
                          <p className="text-[11px] font-medium text-slate-800 line-clamp-1">
                            {reasonText(f.reason)}
                          </p>
                          <div className="flex items-center gap-1 flex-wrap">
                            {(activePipeline === "lidar" ? f.tags ?? [] : ["Hiếm", ...((f.tags?.includes("Khó") || (typeof f.rUnc === "number" && f.rUnc >= 0.8)) ? ["Khó"] : [])]).map((tag) => (
                              <span key={tag} className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded font-medium">
                                {activePipeline === "lidar" ? gtTagLabel(tag) : tag}
                              </span>
                            ))}
                          </div>
                        </div>
                      </Link>
                    ))}
                  </div>}
                </div>
              </div>
            </>
          )}
        </div>

        {/* ================= CỘT PHẢI: BẢNG TINH CHỈNH (4 CỘT) ================= */}
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
                  {pct(budget)} · {Math.ceil((result?.poolSize ?? dataset?.frames ?? 0) * budget)} frame
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
                  title={noTier1 ? PRESET_LOCK_TITLE : undefined}
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
                  const isSelected = preset === pKey;
                  const item = PRESET_LABELS[pKey];
                  return (
                    <button
                      key={pKey}
                      type="button"
                      onClick={() => changePreset(pKey)}
                      aria-pressed={isSelected}
                      disabled={noTier1}
                      title={noTier1 ? PRESET_LOCK_TITLE : undefined}
                      className={`p-3 rounded-xl border text-left flex flex-col gap-0.5 transition-all disabled:opacity-60 disabled:cursor-not-allowed ${
                        isSelected
                          ? "border-blue-600 bg-blue-50/60 ring-1 ring-blue-600"
                          : "border-slate-200 hover:border-slate-300 bg-white"
                      }`}
                    >
                      <span className={`text-xs font-bold ${isSelected ? "text-blue-700" : "text-slate-800"}`}>
                        {item.title}
                        {isSelected && advancedParams && (
                          <span className="ml-1 rounded-full border border-blue-200 bg-white px-1 py-0.5 text-[9px] text-blue-700">
                            Tuỳ chỉnh
                          </span>
                        )}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        {activePipeline === "lidar"
                          ? pKey === "rare_first"
                            ? "Ưu tiên Hiếm trong dữ liệu"
                            : pKey === "safety_scenarios"
                            ? "Ưu tiên Hiếm + Model chưa chắc"
                            : item.desc
                          : item.desc}
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
                    aria-pressed={Math.abs(diversity - d.val) < 0.2}
                    className={`py-1.5 rounded-lg transition-all ${
                      Math.abs(diversity - d.val) < 0.2
                        ? "bg-white text-slate-900 font-bold shadow-xs"
                        : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </div>

            <AdvancedParamsPanel
              open={showAdvanced}
              schema={paramsSchema.data}
              draft={currentAdvancedDraft}
              applied={!!advancedParams}
              onToggle={() => setAdvancedPanelOpen(!getAdvancedPanelOpen())}
              onDraftChange={setAdvancedDraft}
              onApply={handleApplyAdvanced}
              onReset={handleResetAdvanced}
              schemaError={paramsSchema.isError ? (paramsSchema.error instanceof Error ? paramsSchema.error.message : "Hãy thử lại.") : null}
              onRetrySchema={() => void paramsSchema.refetch()}
              colab={
                noTier1 && t1Remote.data?.enabled
                  ? {
                      enabled: true,
                      task: t1Remote.data.task,
                      busy: t1Run.isPending,
                      error: t1Run.isError ? (t1Run.error instanceof Error ? t1Run.error.message : "Không tạo được việc trên Colab.") : null,
                      onRun: () => t1Run.mutate(),
                    }
                  : undefined
              }
            />

            {/* Kịch bản quan tâm */}
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

            {/* Cảnh báo hoặc ghi chú chân trang */}
            {result?.warnings && result.warnings.length > 0 ? (
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
            ) : done ? (
              <p className="text-[11px] text-slate-500 text-center">Phân tích hoàn tất.</p>
            ) : (
              <p className="text-[11px] text-slate-400 text-center italic">
                Tinh chỉnh dùng được sau khi phân tích xong.
              </p>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
