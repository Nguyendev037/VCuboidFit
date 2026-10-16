import { afterEach, describe, expect, it, vi } from "vitest";
import { GpuWarmupController } from "./gpuWarmup";

const response = () => new Response(JSON.stringify({ state: "starting", reason: null, since: null }));
afterEach(() => { vi.useRealTimers(); });

describe("A14 dashboard GPU warmup", () => {
  it("sends warm once across StrictMode replay and keeps the overlay for 4000 ms", async () => {
    vi.useFakeTimers();
    const request = vi.fn<typeof fetch>().mockResolvedValue(response());
    const controller = new GpuWarmupController(request, () => true);
    const listener = vi.fn();
    const cleanup = controller.start(listener);
    cleanup();
    controller.start(listener);
    await vi.advanceTimersByTimeAsync(3999);
    expect(controller.snapshot.overlay).toBe(true);
    expect(request).toHaveBeenCalledTimes(1);
    expect(request.mock.calls[0][0]).toBe("/api/gpu/warm");
    expect(request.mock.calls[0][1].method).toBe("POST");
    await vi.advanceTimersByTimeAsync(1);
    expect(controller.snapshot.overlay).toBe(false);
    controller.stop();
  });
  it("closes by 8000 ms even if warm never responds", async () => {
    vi.useFakeTimers();
    const controller = new GpuWarmupController(vi.fn<typeof fetch>(() => new Promise<Response>(() => {})), () => true);
    controller.start(vi.fn());
    await vi.advanceTimersByTimeAsync(7999);
    expect(controller.snapshot.overlay).toBe(true);
    await vi.advanceTimersByTimeAsync(1);
    expect(controller.snapshot.overlay).toBe(false);
    controller.stop();
  });
  it("skip preserves warm and the minimum duration", async () => {
    vi.useFakeTimers();
    const request = vi.fn<typeof fetch>(() => new Promise<Response>(() => {}));
    const controller = new GpuWarmupController(request, () => true);
    controller.start(vi.fn());
    controller.skip();
    await vi.advanceTimersByTimeAsync(3999);
    expect(controller.snapshot.overlay).toBe(true);
    await vi.advanceTimersByTimeAsync(1);
    expect(controller.snapshot.overlay).toBe(false);
    expect(request).toHaveBeenCalledTimes(1);
    controller.stop();
  });
  it("polls every 30 s while visible and stops on unmount", async () => {
    vi.useFakeTimers();
    let visible = false;
    const request = vi.fn<typeof fetch>().mockImplementation(async () => response());
    const controller = new GpuWarmupController(request, () => visible);
    controller.start(vi.fn());
    await vi.advanceTimersByTimeAsync(30000);
    expect(request).toHaveBeenCalledTimes(1);
    visible = true;
    await vi.advanceTimersByTimeAsync(30000);
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls[1][0]).toBe("/api/gpu/status");
    controller.stop();
    await vi.advanceTimersByTimeAsync(30000);
    expect(request).toHaveBeenCalledTimes(2);
  });
});
