import { describe, expect, it } from "vitest";
import { candidateBoxCorners, type CandidateBoxParams } from "./CandidateObjects";

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
