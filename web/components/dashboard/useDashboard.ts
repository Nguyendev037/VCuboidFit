"use client";

import { useState, useRef, useEffect, useSyncExternalStore } from "react";
import { useQuery, useMutation, keepPreviousData } from "@tanstack/react-query";
import { createJob, getJob, getDataset, listJobs, listSelections, getSelection, getParamsSchema, getT1Remote, createT1Remote, runTier1, deleteJob, deleteAllJobs, select, finalizeUpload, getDatasetProgress } from "@/lib/api/client";
import { summarizeUploads, uploadFiles, type UploadItemState } from "@/lib/upload";
import type { DatasetProgress, DatasetReport, Preset, SelectParams, JobSummary, Pipeline } from "@/lib/api/types";
import { isDatasetUsable } from "@/lib/datasetValidation";
import { isAnalysisReady, isT1OnlyRunning } from "@/lib/tierStatus";
import { clearRunBookmark, readRunBookmark, saveRunBookmark, recoveryParams, recoveryQueries, inheritedRunParams, paramsEqual } from "@/lib/runRecovery";
import { draftFromSchema, gateTier1, hasTier1, normalizeAdvancedParams, sanitizeDraft, sanitizeSelectParams, type AdvancedDraft, type AdvancedSubmitParams } from "@/lib/advancedParams";
import { spreadParams, spreadFromParams } from "@/lib/panelParams";
import { ANALYSIS_STEPS, DEFAULT_QUERIES, LIDAR_ANALYSIS_STEPS, UPLOAD_COLLAPSED_KEY, getAdvancedPanelOpen, getDemo, invalidateRecovery, readUploadCollapsed, setAdvancedPanelOpen, setDemoFlag, subscribeAdvancedPanel, subscribeDemo } from './dashboardState';

export function useDashboard() {

  const [error, setError]=useState("");

  // ---- Bước 1: Nạp dữ liệu ----
  const [items, setItems]=useState<UploadItemState[]>([]);
  const [uploading, setUploading]=useState(false);
  const [collapsedPref, setCollapsedPref]=useState<boolean|null>(() =>
    typeof window==="undefined"? null:readUploadCollapsed());
  const collapsed=collapsedPref??items.length>3; // C2: > 3 tệp tự rút gọn
  function toggleCollapsed() {
    const next=!collapsed;
    setCollapsedPref(next);
    try {
      window.localStorage.setItem(UPLOAD_COLLAPSED_KEY, next? "1":"0");
    } catch {
      // storage không dùng được: giữ trạng thái trong tab
    }
  }
  const [checking, setChecking]=useState(false);
  const [checkProgress, setCheckProgress]=useState<DatasetProgress|null>(null);
  const uploadSummary=summarizeUploads(items);
  const [paused, setPaused]=useState(false);
  const [dataset, setDataset]=useState<DatasetReport|null>(null);
  const [pipeline, setPipeline]=useState<Pipeline>("lidar");
  const uploadIdRef=useRef<string|undefined>(undefined);
  const abortRef=useRef<AbortController|null>(null);
  const filesRef=useRef<File[]>([]);
  const fileInputRef=useRef<HTMLInputElement|null>(null);

  const demo=useSyncExternalStore(subscribeDemo, getDemo, () => false);

  /** Chạy thử: dùng dữ liệu mẫu (không cần upload/worker) để xem thẳng Kết quả và Deep Review. */
  async function runDemo() {
    ++recoveryRequest.current;
    setRestoring(false);
    setError("");
    try {
      setDemoFlag(true);
      const report=await finalizeUpload("demo");
      setDataset(report);
      if(!isDatasetUsable(report)) return;
      setPipeline(report.hasLidar? "lidar":"camera");
      setRestored(null);
      setAdvancedDraft(null);
      setAdvancedParams(null);
      setJobId((await createJob(report.datasetId, report.hasLidar? "lidar":"camera")).jobId);
    } catch(e) {
      setError(e instanceof Error? e.message:"Không chạy thử được");
    }
  }

  async function startUpload(files: File[]) {
    ++recoveryRequest.current;
    setRestoring(false);
    setJobId(null);
    setDataset(null);
    setPipeline("lidar");
    setDemoFlag(false); // upload thật: thoát chế độ dữ liệu mẫu
    filesRef.current=files;
    setError("");
    setUploading(true);
    setPaused(false);
    const abort=new AbortController();
    abortRef.current=abort;

    try {
      const uploadRes=await uploadFiles(files, {
        signal: abort.signal,
        uploadId: uploadIdRef.current,
        onUploadId: (id) => {
          uploadIdRef.current=id;
        },
        onProgress: (name, received, total) => {
          setItems((prev) => {
            const next=prev.filter((i) => i.name!==name);
            next.push({ name, received, total });
            return files.map((f) => next.find((i) => i.name===f.name)??{ name: f.name, received: 0, total: f.size });
          });
        },
      });
      setChecking(true);
      setCheckProgress(null);
      const poll=setInterval(() => {
        void getDatasetProgress(uploadRes.uploadId).then(setCheckProgress);
      }, 1000);
      let report: DatasetReport;
      try {
        report=await finalizeUpload(uploadRes.uploadId);
      } finally {
        clearInterval(poll);
        setChecking(false);
        setCheckProgress(null);
      }
      setDataset(report);
      if(isDatasetUsable(report)) {
        setPipeline(report.hasLidar? "lidar":"camera");
      }
      setJobId(null);
      setRestored(null);
      setAdvancedDraft(null);
      setAdvancedParams(null);
    } catch(e) {
      if(e instanceof DOMException&&e.name==="AbortError") {
        setPaused(true);
      } else {
        setItems((prev) => prev.map((i) => (i.received<i.total? { ...i, failed: true }:i)));
        setError(e instanceof Error? e.message:"Lỗi tải tệp lên");
      }
    } finally {
      setUploading(false);
    }
  }

  // ---- Bước 2: Phân tích ----
  const [jobId, setJobId]=useState<string|null>(null);
  const [restoring, setRestoring]=useState(false);
  const [restored, setRestored]=useState<{ id: string; params: SelectParams }|null>(null);
  const [basicOverrides, setBasicOverrides]=useState({ preset: false, diversity: false });
  const recoveryStarted=useRef(false);
  const recoveryRequest=useRef(0);
  const recentJobs=useQuery({
    queryKey: ["recent-jobs", demo],
    queryFn: listJobs,
    refetchOnWindowFocus: true,
  });
  const job=useQuery({
    queryKey: ["job", jobId, demo],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.state??"")? 2000:false,
  });

  async function startJob() {
    if(!dataset||!isDatasetUsable(dataset)) return;
    ++recoveryRequest.current;
    setRestoring(false);
    setError("");
    try {
      const res=await createJob(dataset.datasetId, dataset.hasLidar? "lidar":"camera");
      setRestored(null);
      setPipeline(dataset.hasLidar? "lidar":"camera");
      setAdvancedDraft(null);
      setAdvancedParams(null);
      setJobId(res.jobId);
      void recentJobs.refetch();
    } catch(e) {
      setError(e instanceof Error? e.message:"Lỗi khởi tạo job");
    }
  }

  // ---- Bước 3: Tinh chỉnh & Kết quả ----
  const [engineVersion, setEngineVersion]=useState("c4_legacy");
  const [profile, setProfile]=useState<"lidar_only"|"multisensor">("lidar_only");
  const [strategy, setStrategy]=useState<"balanced"|"vru_priority"|"diversity">("balanced");
  const [budget, setBudget]=useState(0.05);
  const [preset, setPreset]=useState<Preset>("balanced");
  const [diversity, setDiversity]=useState(0.5);
  const [spread, setSpread]=useState(true);
  const [queryTags, setQueryTags]=useState<string[]>(DEFAULT_QUERIES);
  const [newTagInput, setNewTagInput]=useState("");
  const showAdvanced=useSyncExternalStore(subscribeAdvancedPanel, getAdvancedPanelOpen, () => false);
  const [advancedDraft, setAdvancedDraft]=useState<AdvancedDraft|null>(null);
  const [advancedParams, setAdvancedParams]=useState<AdvancedSubmitParams|null>(null);
  // Plan 09 D4: chỉ còn Tầng 1 chạy nền thì kết quả Tầng 0 vẫn xem/chọn được
  const done=isAnalysisReady(job.data);
  const t1Background=isT1OnlyRunning(job.data);
  const activePipeline=pipeline;
  const analysisSteps=activePipeline==="lidar"? LIDAR_ANALYSIS_STEPS:ANALYSIS_STEPS;

  // Chưa có job hoặc job chưa xong ⇒ lược đồ theo máy (biết ngay Tầng 1 có sẵn hay không, plan 09 D1)
  const schemaJobId=jobId&&done&&activePipeline==="lidar"? jobId:null;
  const paramsSchema=useQuery({
    queryKey: ["params-schema", schemaJobId, demo],
    queryFn: () => getParamsSchema(schemaJobId),
    enabled: !jobId||activePipeline==="lidar",
    staleTime: 60_000,
  });
  // Plan 09: máy có model nhưng job chưa có tín hiệu Tầng 1 ⇒ khoá Tầng 1 kèm lý do từ job.tier1
  const uiSchema=gateTier1(paramsSchema.data, job.data?.tier1);
  const currentAdvancedDraft=sanitizeDraft(advancedDraft, uiSchema);
  const noTier1=!!uiSchema&&!hasTier1(uiSchema);

  // A7: Tầng 1 chạy từ xa trên Colab (chỉ hỏi khi job chưa có Tầng 1)
  const t1Remote=useQuery({
    queryKey: ["t1-remote", jobId, demo],
    queryFn: () => getT1Remote(jobId!),
    enabled: !!jobId&&done&&activePipeline==="lidar"&&noTier1&&!demo,
    retry: false,
    refetchInterval: (q) => (["queued", "leased"].includes(q.state.data?.task?.state??"")? 15_000:false),
  });
  const t1Run=useMutation({
    mutationFn: () => createT1Remote(jobId!),
    onSuccess: () => void t1Remote.refetch(),
    onError: () => void t1Remote.refetch(),
  });
  // Chạy Tầng 1 ngay trên máy worker (Docker + GPU), rồi poll job tới khi tier1 đổi trạng thái
  const t1Local=useMutation({
    mutationFn: () => runTier1(jobId!),
    onSettled: () => void job.refetch(),
  });
  const tier1JobState=job.data?.tier1?.state;
  useEffect(() => {
    if(tier1JobState==="done") void paramsSchema.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tier1JobState]);
  const t1State=t1Remote.data?.task?.state;
  useEffect(() => {
    if(t1State==="done"&&noTier1) {
      void paramsSchema.refetch();
      void job.refetch(); // tier1.state của job đổi sang done khi có tín hiệu
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t1State, noTier1]);

  const [debounced, setDebounced]=useState<SelectParams>({
    budget,
    pipeline: activePipeline,
    preset,
    diversity,
    queries: activePipeline==="lidar"? undefined:queryTags,
  });

  async function openRun(summary: JobSummary, sid?: string) {
    const requestId=++recoveryRequest.current;
    setRestoring(true);
    setError("");
    try {
      const report=await getDataset(summary.datasetId);
      if(requestId!==recoveryRequest.current) return;
      const selections=summary.state==="done"? await listSelections(summary.jobId):[];
      if(requestId!==recoveryRequest.current) return;
      const selectionId=sid??selections[0]?.selectionId;
      const saved=selectionId? await getSelection(summary.jobId, selectionId):null;
      if(requestId!==recoveryRequest.current) return;
      const params=saved? recoveryParams(saved.params as SelectParams, summary.pipeline):recoveryParams({ budget: 0.05 }, summary.pipeline);
      if(summary.pipeline==="lidar") delete params.queries;
      else params.queries??=DEFAULT_QUERIES;
      setEngineVersion(params.engineVersion??"c4_legacy");
      setProfile(params.profile??"lidar_only");
      setStrategy(params.strategy??"balanced");
      setBudget(params.budget);
      setPreset(params.preset??"balanced");
      setDiversity(params.diversity as number);
      setSpread(spreadFromParams(params));
      setQueryTags((params.queries??DEFAULT_QUERIES).map((q) => typeof q==="string"? q:q.text));
      setAdvancedParams(null);
      setAdvancedDraft(saved&&summary.pipeline==="lidar"? {
        ...draftFromSchema(), ...params,
        tier: params.tier===1? 1:0,
        maxPerScene: params.maxPerScene??4,
      } as AdvancedDraft:null);
      setRestored(saved? { id: saved.selectionId, params }:null);
      setBasicOverrides({ preset: false, diversity: false });
      setDebounced(params);
      setItems([]);
      setDataset(report);
      setPipeline(summary.pipeline);
      setJobId(summary.jobId);
      let storage: Storage|undefined;
      try { storage=window.localStorage; } catch { /* URL works without storage. */ }
      window.history.replaceState(null, "", saveRunBookmark({ jobId: summary.jobId, datasetId: report.datasetId, selectionId: saved?.selectionId, demo: getDemo() }, new URL(window.location.href), storage));
    } catch(e) {
      if(requestId===recoveryRequest.current) setError(e instanceof Error? e.message:"Không mở được lần chạy.");
    } finally {
      if(requestId===recoveryRequest.current) setRestoring(false);
    }
  }

  useEffect(() => {
    if(recoveryStarted.current) return;
    recoveryStarted.current=true;
    const bookmark=readRunBookmark(window.location.search);
    if(!bookmark) return;
    const initialRequest=recoveryRequest.current;
    setDemoFlag(bookmark.demo);
    void listJobs().then(async (jobs) => {
      if(initialRequest!==recoveryRequest.current) return;
      let summary=jobs.find((item) => item.jobId===bookmark.jobId);
      if(!summary&&bookmark.datasetId) {
        const status=await getJob(bookmark.jobId);
        if(initialRequest!==recoveryRequest.current) return;
        summary={ jobId: bookmark.jobId, datasetId: bookmark.datasetId, pipeline: status.pipeline??"camera", state: status.state, createdAt: "", finishedAt: null, scenes: 0, frames: 0, version: "", lastSelectionId: bookmark.selectionId??null };
      }
      if(!summary) throw new Error("Không tìm thấy lần chạy đã lưu trong lịch sử.");
      await openRun(summary, bookmark.selectionId);
    }).catch((e) => {
      if(initialRequest===recoveryRequest.current) setError(e instanceof Error? e.message:"Không tải được lịch sử.");
    });
    // Restore once; subsequent opens are explicit user actions.
  }, []);

  useEffect(() => {
    const t=setTimeout(() => {
      const sp=spreadParams(spread);
      setDebounced({
        ...inheritedRunParams(restored?.params, basicOverrides),
        budget,
        pipeline: activePipeline,
        preset,
        ...sp,
        queries: activePipeline==="lidar"? undefined:recoveryQueries(restored?.params, queryTags),
        ...(advancedParams??{}),
        engineVersion, profile, strategy,
      });
    }, 300);
    return () => clearTimeout(t);
  }, [budget, preset, spread, queryTags, activePipeline, advancedParams, restored, basicOverrides, engineVersion, profile, strategy]);

  useEffect(() => {
    const onKeyDown=(event: KeyboardEvent) => {
      const target=event.target as HTMLElement|null;
      if(target&&["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if(event.altKey&&event.shiftKey&&event.key.toLowerCase()==="a") {
        event.preventDefault();
        setAdvancedPanelOpen(!getAdvancedPanelOpen());
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const selectParams=activePipeline==="lidar"? sanitizeSelectParams(debounced, uiSchema):debounced;
  const selection=useQuery({
    queryKey: ["select", jobId, selectParams, demo],
    queryFn: () => restored&&paramsEqual(debounced, restored.params)
      ? getSelection(jobId!, restored.id):select(jobId!, selectParams),
    enabled: !!jobId&&done&&!restoring&&(activePipeline!=="lidar"||!paramsSchema.isPending),
    placeholderData: (previous, previousQuery) => previousQuery?.queryKey[1]===jobId&&previousQuery?.queryKey[3]===demo? keepPreviousData(previous):undefined,
  });

  const result=selection.data;
  const m=result?.evaluationAvailable===false? null:result?.metrics??null;

  useEffect(() => {
    if(!jobId||restoring) return;
    let storage: Storage|undefined;
    try { storage=window.localStorage; } catch { /* URL remains available. */ }
    window.history.replaceState(null, "", saveRunBookmark({ jobId, datasetId: dataset?.datasetId, demo, selectionId: result?.selectionId??restored?.id }, new URL(window.location.href), storage));
  }, [jobId, dataset?.datasetId, restoring, demo, result?.selectionId, restored?.id]);

  const handleResetDefaults=() => {
    setRestored(null);
    setBudget(0.05);
    setPreset("balanced");
    setDiversity(0.5);
    setSpread(true);
    setQueryTags(DEFAULT_QUERIES);
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const handleStartNew=() => {
    if(!window.confirm("Nhập dữ liệu mới? Job cũ vẫn còn trong Lần chạy gần đây.")) return;
    resetWorkspace();
  };

  const resetWorkspace=() => {
    invalidateRecovery(recoveryRequest);
    abortRef.current?.abort();
    abortRef.current=null;
    uploadIdRef.current=undefined;
    filesRef.current=[];
    if(fileInputRef.current) fileInputRef.current.value="";

    let storage: Storage|undefined;
    try { storage=window.localStorage; } catch { /* URL still resets. */ }
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
    setSpread(true);
    setQueryTags(DEFAULT_QUERIES);
    setNewTagInput("");
    setAdvancedDraft(null);
    setAdvancedParams(null);
    setDebounced({ budget: 0.05, pipeline: "lidar", preset: "balanced", diversity: 0.5 });
    void recentJobs.refetch();
  };

  // ---- Xoá lịch sử (SPEC-P04) ----
  const [deleteTarget, setDeleteTarget]=useState<{ kind: "one"; jobId: string }|{ kind: "all" }|null>(null);
  const [historyError, setHistoryError]=useState("");
  const [historyNote, setHistoryNote]=useState("");

  async function confirmDelete() {
    const target=deleteTarget;
    setDeleteTarget(null);
    if(!target) return;
    setHistoryError("");
    setHistoryNote("");
    try {
      const res=target.kind==="one"? await deleteJob(target.jobId):await deleteAllJobs();
      if(res.skipped.length>0) setHistoryNote(`Bỏ qua ${res.skipped.length} lần chạy đang chạy`);
      if(jobId&&res.deleted.includes(jobId)) resetWorkspace();
      await recentJobs.refetch();
    } catch(e) {
      setHistoryError(e instanceof Error? e.message:"Không xoá được lịch sử.");
    }
  }

  const handleApplyAdvanced=() => {
    setAdvancedParams(normalizeAdvancedParams(currentAdvancedDraft));
  };

  const changePreset=(value: Preset) => {
    setPreset(value);
    setBasicOverrides((previous) => ({ ...previous, preset: true }));
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const changeDiversity=(value: number) => {
    setDiversity(value);
    setSpread(value > 0.35);
    setBasicOverrides((previous) => ({ ...previous, diversity: true }));
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const changeSpread=(value: boolean) => {
    setSpread(value);
    setDiversity(spreadParams(value).diversity as number);
    setBasicOverrides((previous) => ({ ...previous, diversity: true }));
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const handleResetAdvanced=() => {
    setRestored(null);
    setAdvancedParams(null);
    setAdvancedDraft(null);
  };

  const handleAddQueryTag=() => {
    const trimmed=newTagInput.trim();
    if(trimmed&&!queryTags.includes(trimmed)) {
      setQueryTags([...queryTags, trimmed]);
      setNewTagInput("");
    }
  };

  const handleRemoveQueryTag=(tag: string) => {
    setQueryTags(queryTags.filter((t) => t!==tag));
  };

  return {
    abortRef,
    activePipeline,
    advancedParams,
    analysisSteps,
    budget,
    changeDiversity,
    changePreset,
    changeSpread,
    checkProgress,
    checking,
    collapsed,
    confirmDelete,
    currentAdvancedDraft,
    dataset,
    debounced,
    deleteTarget,
    demo,
    diversity,
    done,
    engineVersion,
    error,
    fileInputRef,
    filesRef,
    handleAddQueryTag,
    handleApplyAdvanced,
    handleRemoveQueryTag,
    handleResetAdvanced,
    handleResetDefaults,
    handleStartNew,
    historyError,
    historyNote,
    items,
    job,
    jobId,
    m,
    newTagInput,
    noTier1,
    openRun,
    paramsSchema,
    paused,
    preset,
    profile,
    queryTags,
    recentJobs,
    restoring,
    result,
    runDemo,
    selection,
    setAdvancedDraft,
    setBudget,
    setDataset,
    setDeleteTarget,
    setEngineVersion,
    setError,
    setItems,
    setNewTagInput,
    setProfile,
    setSpread,
    setStrategy,
    showAdvanced,
    spread,
    startJob,
    startUpload,
    strategy,
    t1Background,
    t1Local,
    t1Remote,
    t1Run,
    toggleCollapsed,
    uiSchema,
    uploadIdRef,
    uploadSummary,
    uploading
  };
}

export type DashboardState=ReturnType<typeof useDashboard>;
