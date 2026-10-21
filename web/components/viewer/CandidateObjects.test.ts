import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { RareObject } from "@/lib/api/types";
import { CandidateObjects, candidateBoxCorners, type CandidateBoxParams } from "./CandidateObjects";

const object = (id: string, score: number, cls = "other"): RareObject => ({
  sample_token: "frame", object_id: id, cls_pred: cls,
  cx: 0, cy: 0, cz: 0, l: 1, w: 1, h: 1, yaw: 0,
  pts: 12, dist_m: 25.6, track_id: "", speed_mps: null,
  score_shape: 0.91, score_slice: 0, score_vru: 0, score_unc: 0,
  r_sem: null, concept_top: null, concept_score: null,
  s_obj: score, missed_by_model: false, reasons: "shape p91",
});

describe("CandidateObjects · lời thường và xếp hạng", () => {
  it("xếp theo s_obj giảm dần, dịch lớp/lý do/thẻ, giữ dữ liệu đầu vào", () => {
    const objects = [object("low", 0.1), object("high", 0.95, "motorcycle")];
    const html = renderToStaticMarkup(React.createElement(CandidateObjects, { objects, predTags: ["R2", "H", "I"] }));
    expect(html.indexOf("Xe máy")).toBeLessThan(html.indexOf("Vật khác"));
    expect(html).toContain("Hình dạng lạ: 91/100");
    expect(html).not.toContain("shape p91");
    expect(html).toContain("cách 26 m");
    expect(html).toContain("0.95");
    expect(html).toContain("Lát cắt hiếm");
    expect(html).toContain("Khó với model");
    expect(html).toContain("Tương tác");
    expect(html).toContain("Chưa xác nhận");
    expect(html).toContain("(dự đoán)");
    expect(objects.map(o => o.object_id)).toEqual(["low", "high"]);
  });

  it("chỉ hiện sáu vật điểm cao nhất và số vật còn lại", () => {
    const objects = Array.from({ length: 8 }, (_, i) => object(String(i), i / 10));
    const html = renderToStaticMarkup(React.createElement(CandidateObjects, { objects }));
    expect(html.match(/<article/g)).toHaveLength(6);
    expect(html).toContain("Xem thêm (2)");
    expect(html).not.toContain("0.10");
    expect(html).toContain("0.70");
  });

  it("không tạo nút mở rộng khi chỉ có sáu vật và không render dữ liệu rỗng", () => {
    const objects = Array.from({ length: 6 }, (_, i) => object(String(i), 0.5));
    expect(renderToStaticMarkup(React.createElement(CandidateObjects, { objects }))).not.toContain("Xem thêm");
    expect(renderToStaticMarkup(React.createElement(CandidateObjects))).toBe("");
  });
});

/**
 * Bản sao ĐỘC LẬP của `c4/data/geometry.py::box_corners` — nguồn chân lý của box GT mà API trả về
 * (`boxes3d[].corners`): size = (w, l, h); góc 0–3 là mặt trước (+x); quay `yaw` quanh z; hệ EGO nuScenes.
 */
function gtCorners(o: CandidateBoxParams): number[] {
  const signL = [1, 1, 1, 1, -1, -1, -1, -1];
  const signW = [1, -1, -1, 1, 1, -1, -1, 1];
  const signH = [1, 1, -1, -1, 1, 1, -1, -1];
  const cos = Math.cos(o.yaw);
  const sin = Math.sin(o.yaw);
  const out: number[] = [];
  for (let i = 0; i < 8; i++) {
    const x = (o.l / 2) * signL[i];
    const y = (o.w / 2) * signW[i];
    const z = (o.h / 2) * signH[i];
    out.push(o.cx + x * cos - y * sin, o.cy + x * sin + y * cos, o.cz + z);
  }
  return out;
}

describe("Ứng viên LiDAR · quy ước 8 góc box (H25/F2)", () => {
  const cases: CandidateBoxParams[] = [
    { cx: 10, cy: 0, cz: -5, l: 4, w: 2, h: 1.5, yaw: 0 },
    { cx: -3.5, cy: 7.25, cz: 0.4, l: 4, w: 2, h: 1.5, yaw: Math.PI / 2 },
    { cx: 1.234, cy: -8.5, cz: 1.75, l: 2.8, w: 1.5, h: 2, yaw: -1.2 },
    { cx: 0, cy: 0, cz: 0, l: 0.9, w: 0.6, h: 1.7, yaw: Math.PI / 7 },
  ];

  it.each(cases)(
    "8 góc ứng viên trùng 8 góc box GT (thứ tự + toạ độ) · yaw=$yaw",
    (o) => {
      const got = candidateBoxCorners(o);
      const want = gtCorners(o);
      expect(got).toHaveLength(24);
      want.forEach((v, i) => expect(got[i]).toBeCloseTo(v, 12));
    },
  );
});
