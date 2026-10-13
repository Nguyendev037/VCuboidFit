import { expect, it, vi, afterEach } from "vitest";
import { fetchExport } from "./exportDownload";
afterEach(()=>vi.unstubAllGlobals());
it("rejects ZIP failures with HTTP code instead of downloading error JSON",async()=>{
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({error:{code:"not_found",message:"Missing selection"}}),{status:404})));
 await expect(fetchExport("/api/export.zip")).rejects.toMatchObject({status:404,code:"not_found"});
});
it("wraps ZIP connection failures so callers can retry with a readable code",async()=>{
 vi.stubGlobal("fetch",vi.fn().mockRejectedValue(new TypeError("fetch failed")));
 await expect(fetchExport("/api/export.zip")).rejects.toMatchObject({status:0,code:"network"});
});
