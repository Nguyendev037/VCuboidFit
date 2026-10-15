import { randomBytes, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

const SID_RE = /^[0-9a-f]{32}$/;

function validBasic(request: NextRequest): boolean {
  const expected = process.env.VCF_DEMO_PASSWORD;
  if (!expected) return true;
  const raw = request.headers.get("authorization") ?? "";
  const token = raw.startsWith("Basic ") ? raw.slice(6) : "";
  let decoded = "";
  try {
    decoded = Buffer.from(token, "base64").toString("utf8");
  } catch {
    decoded = "";
  }
  const supplied = decoded.startsWith("demo:") ? decoded.slice(5) : "";
  const a = Buffer.from(supplied);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export function proxy(request: NextRequest): NextResponse {
  const path = request.nextUrl.pathname;
  if (path.startsWith("/api/remote/")) return NextResponse.next();
  if (!validBasic(request)) {
    return new NextResponse("Authentication required", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="VCuboidFIT", charset="UTF-8"' },
    });
  }
  if (process.env.NEXT_PUBLIC_VCF_SESSIONS !== "1") return NextResponse.next();
  const existing = request.cookies.get("vcf_sid")?.value;
  if (existing && SID_RE.test(existing)) return NextResponse.next();
  const sid = randomBytes(16).toString("hex");
  const headers = new Headers(request.headers);
  headers.set("x-vcf-session", sid);
  const response = NextResponse.next({ request: { headers } });
  response.cookies.set("vcf_sid", sid, {
    httpOnly: true, secure: true, sameSite: "lax", path: "/",
  });
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
