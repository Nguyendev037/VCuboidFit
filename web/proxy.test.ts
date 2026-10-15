import { beforeEach, afterEach, describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { proxy } from "./proxy";

const request = (path: string, headers?: HeadersInit, cookies?: string) => {
  const requestHeaders = new Headers(headers);
  if (cookies) requestHeaders.set("cookie", cookies);
  return new NextRequest(`https://vcf.test${path}`, { headers: requestHeaders });
};

describe("proxy authentication and sessions", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_VCF_SESSIONS = "1";
    delete process.env.VCF_DEMO_PASSWORD;
  });

  afterEach(() => {
    delete process.env.NEXT_PUBLIC_VCF_SESSIONS;
    delete process.env.VCF_DEMO_PASSWORD;
  });

  it("allows remote agent traffic without a password or session cookie", () => {
    const response = proxy(request("/api/remote/t1/next"));
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("rejects an incorrect Basic Auth password", () => {
    process.env.VCF_DEMO_PASSWORD = "correct";
    const response = proxy(request("/dashboard", { authorization: "Basic ZGVtbzpub3Q=" }));
    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toContain("Basic realm");
  });

  it("accepts the correct password and creates a session", () => {
    process.env.VCF_DEMO_PASSWORD = "correct";
    const response = proxy(request("/dashboard", {
      authorization: `Basic ${Buffer.from("demo:correct").toString("base64")}`,
    }));
    const sid = response.cookies.get("vcf_sid")?.value;
    expect(response.status).toBe(200);
    expect(sid).toMatch(/^[0-9a-f]{32}$/);
    expect(response.headers.get("x-middleware-request-x-vcf-session")).toBe(sid);
  });

  it("passes through when the demo password is unset", () => {
    const response = proxy(request("/dashboard"));
    expect(response.status).toBe(200);
  });
});
