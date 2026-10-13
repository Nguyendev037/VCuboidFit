import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { it, expect } from "vitest";
import Home from "./page";
import { exportImagesUrl } from "@/lib/api/client";
it("builds encoded ZIP export URL with camera and LiDAR options",()=>{
 const url=exportImagesUrl("job/a","sid b",0.05,{cams:"front",lidar:false});
 expect(url).toContain("job%2Fa/selections/sid%20b/export-images.zip");
 const query=new URL(url,"http://localhost").searchParams;
 expect(Object.fromEntries(query)).toEqual({budget:"0.05",cams:"front",lidar:"false"});
});
it("renders the hero, three v2 steps and dashboard entry",()=>{
 const html=renderToStaticMarkup(React.createElement(Home));
 expect(html).toContain("Tìm tình huống VRU hiếm");
 expect(html.match(/<article/g)).toHaveLength(3);
 expect(html).toContain("OpenCLIP + OpenCV");expect(html).toContain('href="/dashboard"');expect(html).toContain("Vào dashboard");expect(html).toContain("Đang đo");
});
