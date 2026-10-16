export type GpuStatus = { state: "ready" | "starting" | "idle" | "disabled" | "error"; reason: string | null; since: string | null };
export type GpuSnapshot = { overlay: boolean; status: GpuStatus };

/** Per dashboard mount; reused across React StrictMode effect replay. */
export class GpuWarmupController {
  snapshot: GpuSnapshot = { overlay: true, status: { state: "starting", reason: null, since: null } };
  private warm?: Promise<void>;
  private startedAt?: number;
  private settled = false;
  private skipped = false;
  private listener?: (snapshot: GpuSnapshot) => void;
  private minTimer?: ReturnType<typeof setTimeout>;
  private maxTimer?: ReturnType<typeof setTimeout>;
  private pollTimer?: ReturnType<typeof setInterval>;
  private stopped = true;
  constructor(private request: typeof fetch, private visible: () => boolean) {}
  private emit() { this.listener?.({ ...this.snapshot }); }
  private closeIfAllowed() {
    if (Date.now() - this.startedAt! >= 4000 && (this.settled || this.skipped)) {
      this.snapshot = { ...this.snapshot, overlay: false };
      this.emit();
    }
  }
  private async read(url: string, method: string) {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 8000);
    try {
      const response = await this.request(url, { method, signal: abort.signal, cache: "no-store" });
      if (!response.ok) throw new Error("gpu-unreachable");
      const status = await response.json() as GpuStatus;
      if (!["ready", "starting", "idle", "disabled", "error"].includes(status.state)) throw new Error("gpu-unreachable");
      this.snapshot = { ...this.snapshot, status };
    } catch {
      this.snapshot = { ...this.snapshot, status: { state: "error", reason: "gpu-unreachable", since: null } };
    } finally { clearTimeout(timeout); }
    if (!this.stopped) this.emit();
  }
  start(listener: (snapshot: GpuSnapshot) => void) {
    this.listener = listener;
    this.stopped = false;
    this.startedAt ??= Date.now();
    if (!this.warm) {
      this.warm = this.read("/api/gpu/warm", "POST").finally(() => {
        this.settled = true;
        if (!this.stopped) this.closeIfAllowed();
      });
    }
    const elapsed = Date.now() - this.startedAt;
    this.minTimer = setTimeout(() => this.closeIfAllowed(), Math.max(0, 4000 - elapsed));
    this.maxTimer = setTimeout(() => {
      this.snapshot = { ...this.snapshot, overlay: false };
      this.emit();
    }, Math.max(0, 8000 - elapsed));
    this.pollTimer = setInterval(() => { if (this.visible()) void this.read("/api/gpu/status", "GET"); }, 30000);
    this.emit();
    return () => this.stop();
  }
  skip() { this.skipped = true; this.closeIfAllowed(); }
  stop() {
    this.stopped = true;
    this.listener = undefined;
    clearTimeout(this.minTimer);
    clearTimeout(this.maxTimer);
    clearInterval(this.pollTimer);
  }
}
