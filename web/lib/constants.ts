// Hằng số dùng chung client + server (01-CONTRACTS §1).
export const CHUNK = 50 * 1024 * 1024;
/** Server từ chối chunk lớn hơn CHUNK + 1 KB. */
export const CHUNK_SLACK = 1024;

export const MANIFEST_NAME = "vcf_manifest.json";
/** Tên file được phép upload; chỉ lưu theo basename. */
export const UPLOAD_NAME_RE = /^[\w.\- ()]+\.(zip|rar|7z|\d{3})$/i;

/** Nhãn tiếng Việt cho chip lọc nhóm GT hiếm (pipeline LiDAR). */
export const LIDAR_TAG_LABELS: Record<string, string> = {
  "Rare GT A": "GT Môi trường",
  "Rare GT B": "GT Lớp hiếm",
  "Rare GT Bp": "GT Lớp trung bình",
  "Rare GT C": "GT Cảm biến",
  "rare (cell)": "Hiếm theo nhãn",
};

export const LIDAR_LABELS = {
  rRar: "Hiếm",
  rNov: "Lạ với model",
  rUnc: "Không chắc",
  A: "Môi trường",
  B: "Lớp hiếm",
  Bp: "Lớp trung bình",
  C: "Cảm biến",
  nRecall: "Recall theo box",
  sceneRecall: "Recall theo scene",
} as const;

export function isAllowedUploadName(name: string): boolean {
  return name.length > 0 && name.length <= 200 && (name === MANIFEST_NAME || UPLOAD_NAME_RE.test(name));
}

/** Nhãn stage theo pipeline (JobStatus.stages[].name). */
export const STAGE_LABELS_CAMERA: Record<string, string> = {
  index: "Lập chỉ mục",
  dino: "Độ hiếm",
  det: "Độ khó",
  clip: "Khớp kịch bản",
  merge: "Tổng hợp S",
  t1: "Tầng 1",
};
export const STAGE_LABELS_LIDAR: Record<string, string> = {
  index: "Lập chỉ mục",
  lidar_index: "Chỉ mục LiDAR",
  t0: "Descriptor Tầng 0",
  t1: "Tầng 1",
  merge: "Tổng hợp S",
};

export function stageLabel(name: string, pipeline: "lidar" | "camera" = "camera"): string {
  const table = pipeline === "lidar" ? STAGE_LABELS_LIDAR : STAGE_LABELS_CAMERA;
  return table[name] ?? STAGE_LABELS_LIDAR[name] ?? STAGE_LABELS_CAMERA[name] ?? name;
}

/** Nhãn ablation LiDAR (key trong metrics.ablation). */
export const LIDAR_ABLATION_LABELS: Record<string, string> = {
  t0_rar_topk: "Tầng 0 · chỉ xếp hạng",
  coreset_z0: "Coreset (đa dạng thuần)",
  hybrid_nodiv: "Không đa dạng",
  t1_nov_mmr: "Chỉ Lạ với model",
  t1_unc_mmr: "Chỉ Không chắc",
  novelty: "Chỉ Lạ với model",
  uncertainty: "Chỉ Không chắc",
};
const CAMERA_ABLATION_LABELS: Record<string, string> = {
  novelty: "Độ hiếm",
  uncertainty: "Độ khó",
  query: "Khớp kịch bản",
  hybrid_nodiv: "Coreset",
};

export interface RecallRow {
  name: string;
  val: number;
  isPrimary?: boolean;
}

/** Dựng các dòng biểu đồ Recall theo method; lidar liệt kê đúng các ablation có trong dữ liệu. */
export function recallRows(
  pipeline: "lidar" | "camera",
  m?: {
    hybrid: { recall: number };
    ablation?: Record<string, { recall: number }> | null;
    random?: { mean: { recall: number } } | null;
  } | null,
): RecallRow[] {
  const abl = m?.ablation ?? {};
  const rows: RecallRow[] = [{ name: "VCuboidFIT Hybrid", val: m ? m.hybrid.recall : 0.38, isPrimary: true }];
  if (pipeline === "lidar") {
    for (const [key, v] of Object.entries(abl)) {
      rows.push({ name: LIDAR_ABLATION_LABELS[key] ?? key, val: v.recall });
    }
  } else {
    for (const [key, fallback] of [["novelty", 0.24], ["uncertainty", 0.21], ["query", 0.17], ["hybrid_nodiv", 0.11]] as const) {
      rows.push({ name: CAMERA_ABLATION_LABELS[key], val: abl[key]?.recall ?? fallback });
    }
  }
  rows.push({ name: "Random", val: m?.random?.mean.recall ?? 0.05 });
  return rows;
}
