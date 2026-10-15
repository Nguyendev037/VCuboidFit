import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { it, expect } from "vitest";
import Providers from "./providers";
import Home from "./page";
import { exportImagesUrl } from "@/lib/api/client";
it("builds encoded ZIP export URL with camera and LiDAR options",()=>{
 const url=exportImagesUrl("job/a","sid b",0.05,{cams:"front",lidar:false});
 expect(url).toContain("job%2Fa/selections/sid%20b/export-images.zip");
 const query=new URL(url,"http://localhost").searchParams;
 expect(Object.fromEntries(query)).toEqual({budget:"0.05",cams:"front",lidar:"false"});
});
it("renders the source hero, three workflow steps, honest sample label and benchmark entry",async()=>{
 const html=renderToStaticMarkup(React.createElement(Providers,null,await Home()));
 expect(html).toContain("Frame đáng giá");expect(html).not.toContain("Frame hiếm");
 for (const step of ["Nạp dữ liệu nuScenes", "Phân tích và chọn lô", "Kiểm tra và xuất ZIP"]) expect(html).toContain(step);
 expect(html).toContain("OpenCLIP + OpenCV");expect(html).toContain('href="/dashboard"');expect(html).toContain("Mở Dashboard");
 expect(html).toContain("Góc nhìn người sử dụng");expect(html).toContain("chưa phải lời chứng thực");expect(html).not.toContain("Số đo trên tập T");
 expect(html).toContain("DỮ LIỆU nuScenes MẪU");
 expect(html).toContain('href="/vi-sao#phuong-phap"');
 expect(html).toContain("Motional");
 expect(html).not.toContain("120 frame");
 expect(html).not.toContain("PCA 64");
});
