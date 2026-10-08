import { afterEach, describe, expect, it } from "vitest";
import { workerUrl } from "./worker";

const saved = { w: process.env.WORKER_URL, p: process.env.VCF_PORT };
afterEach(() => {
  if (saved.w === undefined) delete process.env.WORKER_URL; else process.env.WORKER_URL = saved.w;
  if (saved.p === undefined) delete process.env.VCF_PORT; else process.env.VCF_PORT = saved.p;
});

describe("workerUrl", () => {
  it("suy URL từ VCF_PORT khi WORKER_URL vắng", () => {
    delete process.env.WORKER_URL;
    process.env.VCF_PORT = "8011";
    expect(workerUrl()).toBe("http://127.0.0.1:8011");
  });
  it("mặc định 8001 khi cả hai vắng", () => {
    delete process.env.WORKER_URL;
    delete process.env.VCF_PORT;
    expect(workerUrl()).toBe("http://127.0.0.1:8001");
  });
  it("WORKER_URL thắng và cắt dấu / cuối", () => {
    process.env.WORKER_URL = "https://x.trycloudflare.com/";
    process.env.VCF_PORT = "8011";
    expect(workerUrl()).toBe("https://x.trycloudflare.com");
  });
});
