import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { DataError, EmptyState, LoadingState } from "./DataState";
import { ViewerLegend } from "../viewer/ViewerLegend";
import { ApiError } from "@/lib/api/errors";
const render = renderToStaticMarkup;
it("network failure offers worker command, copy and retry", () => {
 const html=render(React.createElement(DataError,{error:new TypeError("fetch failed"),onRetry:()=>{}}));
 for(const text of ["Worker chưa chạy","uvicorn","Sao chép lệnh","Thử lại"]) expect(html).toContain(text);
});
it("502 proxy failure offers worker recovery", () => {
 expect(render(React.createElement(DataError,{error:new ApiError("worker_unavailable","offline",502),onRetry:()=>{}}))).toContain("Worker chưa chạy");
});
it("404 resource offers dashboard without mislabelling worker", () => {
 const html=render(React.createElement(DataError,{error:new ApiError("not_found","missing",404),onRetry:()=>{}}));
 expect(html).toContain('href="/dashboard"'); expect(html).toContain("Không tìm thấy"); expect(html).not.toContain("Worker chưa chạy");
});
it("validation errors keep their message without worker command", () => {
 const html=render(React.createElement(DataError,{error:new ApiError("invalid","Invalid budget",400),onRetry:()=>{}}));
 expect(html).toContain("Invalid budget"); expect(html).not.toContain("uvicorn");
});
it("loading has accessible skeletons", () => {
 const html=render(React.createElement(LoadingState,{label:"Đang tải frame"}));
 expect(html).toContain('role="status"'); expect(html).toContain("animate-pulse"); expect(html).toContain("Đang tải frame");
});
it("empty state offers a dashboard action", () => {
 const html=render(React.createElement(EmptyState,{message:"Không có frame"}));
 expect(html).toContain("Không có frame"); expect(html).toContain('href="/dashboard"');
});
it("viewer legend distinguishes category colours and candidate lines", () => {
 const html=render(React.createElement(ViewerLegend));
 for(const text of ["GT","ứng viên","VRU","#38bdf8","#facc15","#fb923c","nét đứt"]) expect(html).toContain(text);
});
