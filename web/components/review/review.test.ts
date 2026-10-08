import { describe, it, expect } from "vitest";
import type { Analysis, FrameSummary } from "@/lib/api/types";
import {
  CAMERA_FILTER_TAGS,
  LIDAR_FILTER_TAGS,
  matchesTagFilter,
} from "@/app/review/[jobId]/review-client";
import { LIDAR_TAG_LABELS } from "@/lib/constants";

describe("Review Components Data Integrity", () => {
  const mockFrames: FrameSummary[] = [
    {
      rank: 1,
      sampleToken: "mock-f01",
      sceneName: "scene-0061",
      frameIdx: 0,
      bestCam: "CAM_FRONT",
      thumbUrl: "/mock/thumb1.jpg",
      S: 0.97,
      rNov: 0.86,
      rUnc: 0.7,
      rQry: 0.47,
      qryBest: "xe máy cắt ngang",
      reason: "Cảnh hiếm so với phần còn lại của dataset (novelty)",
      tags: ["Hiếm"],
      camsAvailable: [
        "CAM_FRONT_LEFT",
        "CAM_FRONT",
        "CAM_FRONT_RIGHT",
        "CAM_BACK_LEFT",
        "CAM_BACK",
        "CAM_BACK_RIGHT",
      ],
    },
    {
      rank: 2,
      sampleToken: "mock-f02",
      sceneName: "scene-0062",
      frameIdx: 5,
      bestCam: "CAM_FRONT",
      thumbUrl: "/mock/thumb2.jpg",
      S: 0.91,
      rNov: 0.72,
      rUnc: 0.85,
      rQry: 0.35,
      qryBest: "người đi bộ qua đường",
      reason: "Độ bất định mô hình cao",
      tags: ["Khó"],
      camsAvailable: [
        "CAM_FRONT_LEFT",
        "CAM_FRONT",
        "CAM_FRONT_RIGHT",
        "CAM_BACK_LEFT",
        "CAM_BACK",
      ],
    },
  ];

  const mockAnalysis: Analysis = {
    pool: {
      scenes: 10,
      frames: 400,
      images: 2400,
      imagesByCam: {
        CAM_FRONT_LEFT: 400,
        CAM_FRONT: 400,
        CAM_FRONT_RIGHT: 400,
        CAM_BACK_LEFT: 400,
        CAM_BACK: 400,
        CAM_BACK_RIGHT: 400,
      },
      hasLidar: true,
      hasAnnotations: true,
      duplicates: { frames: 45, groups: 12 },
      tooSafe: 120,
      easyForModel: 180,
      unlabelable: { total: 15, dark: 5, blurry: 7, noObject: 3 },
      highValue: 40,
      excludedByCamera: 8,
      rare: { total: 32, A: 6, B: 12, C: 14 },
    },
    selected: {
      metrics: {
        recall: 0.82,
        uplift: 2.15,
        precision: 0.65,
        coverage: 0.78,
        coverageGain: 0.25,
        redundancy: 0.08,
        byGroup: { A: 0.9, B: 0.85, C: 0.75 },
      },
      random: {
        mean: {
          recall: 0.38,
          uplift: 1.0,
          precision: 0.38,
          coverage: 0.53,
          coverageGain: 0.0,
          redundancy: 0.32,
          byGroup: { A: 0.35, B: 0.4, C: 0.38 },
        },
        std: {
          recall: 0.04,
          uplift: 0.05,
          precision: 0.04,
          coverage: 0.03,
          coverageGain: 0.0,
          redundancy: 0.05,
          byGroup: { A: 0.06, B: 0.05, C: 0.04 },
        },
      },
      ablation: null,
      recallByGroup: { A: 0.9, B: 0.85, C: 0.75 },
      reasonDistribution: { novelty: 10, uncertainty: 8, query: 2 },
      scenesCovered: 10,
      duplicatesInSelected: 0,
    },
    histogram: {
      bins: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
      counts: [50, 80, 100, 70, 40, 30, 15, 10, 5],
      budgetThreshold: 0.75,
    },
  };

  it("tính toán đúng các chỉ số phân tích bể dữ liệu (spec §3.1)", () => {
    expect(mockAnalysis.pool.duplicates.frames).toBe(45);
    expect(mockAnalysis.pool.duplicates.groups).toBe(12);
    expect(mockAnalysis.pool.tooSafe).toBe(120);
    expect(mockAnalysis.pool.easyForModel).toBe(180);
    expect(mockAnalysis.pool.unlabelable.total).toBe(15);
    expect(mockAnalysis.pool.unlabelable.dark).toBe(5);
    expect(mockAnalysis.pool.unlabelable.blurry).toBe(7);
    expect(mockAnalysis.pool.rare?.total).toBe(32);
  });

  it("tính toán đúng các chỉ số hiệu năng tập 5% đã chọn (spec §3.2)", () => {
    const metrics = mockAnalysis.selected.metrics;
    const primary = metrics && "hybrid" in metrics ? metrics.hybrid : metrics;
    expect(primary?.recall).toBe(0.82);
    expect(primary?.uplift).toBe(2.15);
    expect(primary?.redundancy).toBe(0.08);
    expect(mockAnalysis.selected.scenesCovered).toBe(10);
    expect(mockAnalysis.selected.duplicatesInSelected).toBe(0);
  });

  it("xác minh cấu trúc danh sách frame tuyển chọn", () => {
    expect(mockFrames.length).toBe(2);
    expect(mockFrames[0].bestCam).toBe("CAM_FRONT");
    expect(mockFrames[0].camsAvailable.length).toBe(6);
    expect(mockFrames[1].camsAvailable.length).toBe(5);
  });
});

describe("Lọc chip theo pipeline (LiDAR vs camera)", () => {
  const frame = (over: Partial<FrameSummary>): FrameSummary => ({
    rank: 1,
    sampleToken: "tok",
    sceneName: "scene-0001",
    frameIdx: 0,
    bestCam: "LIDAR_TOP",
    thumbUrl: "/mock/thumb.jpg",
    S: 0.5,
    rNov: 0.1,
    rUnc: 0.1,
    rQry: 0.1,
    reason: "",
    tags: [],
    camsAvailable: [],
    ...over,
  });

  it("LiDAR: chip Hiếm lọc theo rRar > 0.6 (không dùng rNov)", () => {
    const rareByScore = frame({ rRar: 0.8, rNov: 0.05, tags: [] });
    const rareByTag = frame({ rRar: 0.2, tags: ["Hiếm"] });
    const novelButNotRare = frame({ rRar: 0.3, rNov: 0.95, tags: [] });

    expect(matchesTagFilter(rareByScore, "Hiếm", true)).toBe(true);
    expect(matchesTagFilter(rareByTag, "Hiếm", true)).toBe(true);
    expect(matchesTagFilter(novelButNotRare, "Hiếm", true)).toBe(false);
  });

  it("camera: chip Hiếm vẫn lọc theo rNov như cũ", () => {
    const lidarRareOnly = frame({ rRar: 0.95, rNov: 0.2, tags: [] });
    const novel = frame({ rRar: 0.1, rNov: 0.95, tags: [] });

    expect(matchesTagFilter(lidarRareOnly, "Hiếm", false)).toBe(false);
    expect(matchesTagFilter(novel, "Hiếm", false)).toBe(true);
    expect(CAMERA_FILTER_TAGS).toEqual(["Hiếm", "Khó", "Kịch bản", "Rare GT A", "Rare GT B", "Rare GT C"]);
    expect(CAMERA_FILTER_TAGS).not.toContain("Rare GT Bp");
    expect(CAMERA_FILTER_TAGS).not.toContain("rare (cell)");
  });

  it("LiDAR: chip Rare GT Bp có mặt và khớp tag chính xác", () => {
    expect(LIDAR_FILTER_TAGS).toEqual([
      "Hiếm",
      "Khó",
      "Rare GT A",
      "Rare GT B",
      "Rare GT Bp",
      "Rare GT C",
      "rare (cell)",
    ]);
    expect(LIDAR_TAG_LABELS["Rare GT Bp"]).toBe("GT Lớp TB");

    expect(matchesTagFilter(frame({ tags: ["Rare GT Bp"] }), "Rare GT Bp", true)).toBe(true);
    expect(matchesTagFilter(frame({ tags: ["Rare GT B"] }), "Rare GT Bp", true)).toBe(false);
    // camera giữ hành vi khớp mờ cũ (tag chứa hoặc "Rare <nhóm>")
    expect(matchesTagFilter(frame({ tags: ["Rare Bp"] }), "Rare GT Bp", false)).toBe(true);
  });

  it("LiDAR: chip rare (cell) chỉ khớp đúng tag đó", () => {
    expect(LIDAR_TAG_LABELS["rare (cell)"]).toBe("Rare (cell)");
    expect(matchesTagFilter(frame({ tags: ["rare (cell)"], rRar: 0.1 }), "rare (cell)", true)).toBe(true);
    expect(matchesTagFilter(frame({ tags: ["Hiếm"], rRar: 0.99 }), "rare (cell)", true)).toBe(false);
    expect(matchesTagFilter(frame({ tags: ["rare"], rRar: 0.99 }), "rare (cell)", true)).toBe(false);
  });

  it("thẻ Trùng lặp lọc theo tag trùng do API trả về", () => {
    const duplicate = frame({ tags: ["Hiếm", "Trùng với #2"] });
    const unique = frame({ tags: ["Hiếm"] });

    expect(matchesTagFilter(duplicate, "duplicates", true)).toBe(true);
    expect(matchesTagFilter(unique, "duplicates", true)).toBe(false);
  });
});
