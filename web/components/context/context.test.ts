import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it, expect } from "vitest";
import { ContextPanel } from "./ContextPanel";
import { CandidateObjects } from "../viewer/CandidateObjects";
import type { RareObject } from "@/lib/api/types";
describe("M7 viewer",()=>{
 it("renders four probability bars for the selected camera",()=>{
  const context={sunElevDeg:null,perCam:{CAM_FRONT:{tags:[],probs:{illum:{day:1},glare:{none:1},lens:{clean:1},weather:{dry:1}},cvFlags:["NIGHT_CV"],review:true,reviewReasons:["illum:DISAGREE"]}}};
  const html=renderToStaticMarkup(React.createElement(ContextPanel,{context,cam:"CAM_FRONT"}));
  expect(html.match(/data-testid="context-axis"/g)).toHaveLength(4);
  expect(html).toContain("Bối cảnh cần xem"); expect(html).toContain("Các tín hiệu không đồng ý");
 });
 it("hides absent context and absent camera",()=>{
  expect(renderToStaticMarkup(React.createElement(ContextPanel,{context:null,cam:"CAM_FRONT"}))).toBe("");
  expect(renderToStaticMarkup(React.createElement(ContextPanel,{context:{sunElevDeg:null,perCam:{}},cam:"CAM_FRONT"}))).toBe("");
 });
 it("marks objects unconfirmed and shows concepts",()=>{
  const object={object_id:"o1",cls_pred:"pedestrian",reasons:"sparse",concept_top:"pedestrian",concept_score:0.7} as RareObject;
  const html=renderToStaticMarkup(React.createElement(CandidateObjects,{objects:[object],predTags:["R3"]}));
  expect(html).toContain("Chưa xác nhận");expect(html).toContain("Khái niệm gần nhất");expect(html).toContain("dự đoán");
 });
});
