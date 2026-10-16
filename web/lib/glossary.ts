export interface GlossaryItem {
  label: string;
  tooltip: string;
  detail?: string;
  howToRead?: string;
}

export interface HelpItem {
  label: string;
  tooltip: string;
  desc?: string;
}

type PanelHelpKey =
  | "budget"
  | "priority"
  | "formula"
  | "spread"
  | "expert"
  | "engine"
  | "profile"
  | "tierLock"
  | "preset.balanced"
  | "preset.rare_first"
  | "preset.hard_for_model"
  | "preset.safety_scenarios"
  | "w.rare"
  | "w.novel"
  | "w.unsure";

export const PANEL_HELP: Record<PanelHelpKey, HelpItem> = {
  budget: {
    label: "Lấy bao nhiêu frame?",
    tooltip: "Phần trăm frame được chọn ra từ toàn bộ dữ liệu để gửi gán nhãn. Tăng lên thì có nhiều frame hơn nhưng tốn công gán nhãn hơn. Chưa chắc thì để 5%.",
  },
  priority: {
    label: "Ưu tiên tìm gì?",
    tooltip: "Mỗi lựa chọn là một công thức trộn sẵn ba tiêu chí chấm điểm frame. Thanh Công thức bên dưới cho biết tỉ lệ trộn. Chưa chắc thì chọn Cân bằng.",
  },
  "preset.balanced": {
    label: "Cân bằng",
    desc: "Khuyến nghị · trộn cả ba tiêu chí",
    tooltip: "Trộn độ hiếm của dữ liệu với độ khó đối với model. Hợp khi chưa biết model đang yếu ở đâu.",
  },
  "preset.rare_first": {
    label: "Cảnh hiếm",
    desc: "Ưu tiên hình dạng ít gặp",
    tooltip: "Dồn điểm cho frame có hình dạng point cloud ít gặp trong bộ dữ liệu, như vật thể lạ hay bố cục đường bất thường. Hợp khi muốn mở rộng độ phủ dữ liệu.",
  },
  "preset.hard_for_model": {
    label: "Model còn yếu",
    desc: "Ưu tiên frame model chưa chắc",
    tooltip: "Dồn điểm cho frame mà model hiện tại đoán dao động hoặc thiếu tự tin. Gán nhãn nhóm này thường giúp model tiến bộ nhanh nhất. Cần chạy Tầng 1.",
  },
  "preset.safety_scenarios": {
    label: "Kịch bản an toàn",
    desc: "Cảnh hiếm mà model còn lúng túng",
    tooltip: "Dồn điểm cho frame vừa hiếm vừa làm model thiếu tự tin — nhóm dễ gây lỗi nguy hiểm khi xe chạy thật. Cần chạy Tầng 1.",
  },
  formula: {
    label: "Công thức đang dùng",
    tooltip: "Tỉ lệ đóng góp của ba tiêu chí vào điểm cuối của mỗi frame. Chỉ để xem; muốn chỉnh tay hãy mở Chế độ chuyên gia.",
  },
  "w.rare": {
    label: "Hiếm trong dữ liệu",
    tooltip: "Frame có hình dạng ít gặp so với phần còn lại của bộ dữ liệu.",
  },
  "w.novel": {
    label: "Lạ với model",
    tooltip: "Frame khác với những gì model đã được học.",
  },
  "w.unsure": {
    label: "Model chưa chắc chắn",
    tooltip: "Frame mà model đoán dao động hoặc thiếu tự tin.",
  },
  spread: {
    label: "Trải đều nhiều cảnh",
    tooltip: "Bật: mỗi cảnh (một đoạn lái ngắn) góp tối đa 4 frame, tránh chọn nhiều frame gần giống nhau. Tắt: lấy các frame điểm cao nhất, kể cả khi dồn vào vài cảnh.",
  },
  tierLock: {
    label: "Đang ở chế độ Cơ bản",
    tooltip: "Lần chạy này chưa có model (Tầng 1) nên chỉ dùng tiêu chí Hiếm trong dữ liệu. Chạy Tầng 1 để mở các lựa chọn còn lại.",
  },
  expert: {
    label: "Chế độ chuyên gia",
    tooltip: "Dành cho người làm benchmark: chỉnh trực tiếp từng tham số. Thay đổi ở đây ghi đè lựa chọn phía trên và cần bấm Áp dụng.",
  },
  engine: {
    label: "Bộ máy chọn frame",
    tooltip: "C4 hiện tại là bản mặc định đã kiểm chứng. Rare v2.4 là bản thử nghiệm, kết quả có thể khác.",
  },
  profile: {
    label: "Cảm biến dùng để chấm",
    tooltip: "Chỉ áp dụng cho Rare v2.4. Chọn LiDAR + camera khi dữ liệu có đủ ảnh camera; nếu không, giữ Chỉ LiDAR.",
  },
};

interface UploadNotice {
  online: Record<"intro" | "soft" | "middle" | "large" | "localLink" | "warning" | "confirmWarning" | "confirm", string> & { levels: { range: string; label: string }[] };
  checklist: { path: string; label: string; files: string[]; detail: string }[];
  missing: string;
  zip: string;
  title: string;
  exampleLabel: string;
  example: string;
  sampleHelp: string;
  sampleLink: string;
  license: string;
}

export const UPLOAD_HELP: Record<"dropzone" | "limit" | "limitFallback" | "notice", HelpItem> & { notice: HelpItem & UploadNotice } = {
  dropzone: {
    label: "Kéo thả một hoặc nhiều file .zip / .rar / .7z — không giới hạn dung lượng mỗi file",
    tooltip: "",
  },
  limit: {
    label: "Tổng tối đa {max} mỗi lần tải · mất mạng thì tự gửi tiếp",
    tooltip: "File lớn được tự chia nhỏ khi gửi nên bạn không cần nén thành nhiều phần. Giới hạn tổng do người quản trị máy chủ đặt.",
  },
  limitFallback: {
    label: "Tổng dung lượng theo cấu hình máy chủ · mất mạng thì tự gửi tiếp",
    tooltip: "",
  },
  notice: {
    online: {
      levels: [
        { range: "< 1 GB", label: "Phù hợp" },
        { range: "1–5 GB", label: "Chậm, 20–40 phút" },
        { range: "> 5 GB", label: "Nên chạy local" },
      ],
      intro: "Bản online phù hợp dữ liệu",
      soft: "dưới 1 GB",
      middle: ". Từ 1–5 GB vẫn chạy được nhưng upload + giải nén có thể mất 20–40 phút.",
      large: "Trên 5 GB nên chạy bản local",
      localLink: "Hướng dẫn chạy local",
      warning: "Tổng dữ liệu trên 1 GB; upload và giải nén có thể mất 20–40 phút.",
      confirmWarning: "Tổng dữ liệu trên 5 GB. Nên chạy bản local để tránh chờ lâu.",
      confirm: "Vẫn tải lên",
    },
    checklist: [
      { path: "data/v1.0-<tên>/", label: "Bắt buộc", files: ["scene", "sample", "sample_data", "calibrated_sensor", "ego_pose", "sensor"], detail: "Thông tin cảnh, frame, cảm biến" },
      { path: "data/v1.0-<tên>/", label: "Tùy chọn", files: ["category", "instance", "sample_annotation", "visibility", "attribute", "log"], detail: "Nhãn và thông tin bổ sung" },
      { path: "data/samples/LIDAR_TOP/", label: "Bắt buộc", files: ["*.pcd.bin"], detail: "Đám mây điểm LiDAR" },
      { path: "data/sweeps/LIDAR_TOP/", label: "Nên có", files: [], detail: "Giúp Tầng 1 chính xác hơn" },
      { path: "data/samples/CAM_*/", label: "Tùy chọn", files: [], detail: "Ảnh camera, chỉ để xem" },
    ],
    zip: "Nén cả thư mục data/ thành một file .zip là đủ",
    title: "Cấu trúc thư mục cần có trong file nén",
    exampleLabel: "Xem ví dụ thật",
    example: "data/\n├── v1.0-mini/scene.json\n├── samples/LIDAR_TOP/n015-2018-07-24-11-22-45+0800__LIDAR_TOP__1532402927647951.pcd.bin\n├── sweeps/LIDAR_TOP/…\n└── samples/CAM_FRONT/…jpg",
    sampleHelp: "Chưa có dữ liệu? Bấm Chạy thử dữ liệu mẫu ở Bước 2",
    sampleLink: "Tải nuScenes mini (≈ 4 GB, miễn phí, cần đăng ký)",
    license: "nuScenes / Motional · CC BY-NC-SA 4.0",
    missing: "Thiếu file bắt buộc ⇒ bước Chỉ mục LiDAR báo lỗi kèm tên file thiếu.",
    label: "Lưu ý cấu trúc",
    tooltip: "Mỗi file nén phải chứa thư mục data/ ở gốc theo cấu trúc nuScenes (data/v1.0-*/, data/samples/LIDAR_TOP/…). Nén cả thư mục data/ thành một file .zip là đủ; công cụ vcf-pack chỉ cần khi muốn lọc bớt scene hoặc chia nhỏ để lưu trữ.",
  },
};

export const RARITY_CONCEPTS: Record<string, GlossaryItem> = {
  rare_est: {
    label: "Độ hiếm (ước lượng)",
    tooltip: "Model tự đoán frame này lạ đến mức nào chỉ từ hình dạng point cloud, không nhìn nhãn. 100% = lạ nhất trong bộ dữ liệu.",
    detail: "Khoảng cách trung bình từ frame tới k frame giống nó nhất ở các cảnh khác, đổi sang hạng phần trăm. Không đọc nhãn — đây là thứ dùng để CHỌN.",
  },
  "rare (cell)": {
    label: "Hiếm thật (theo nhãn)",
    tooltip: "Frame có ít nhất một vật thể thuộc nhóm rất ít gặp trong bộ dữ liệu (theo nhãn 3D có sẵn). Chỉ dùng để CHẤM xem model chọn đúng không.",
    detail: "Một \"ô\" = loại vật thể × khoảng cách (0–20, 20–40, >40 m) × số điểm LiDAR trên vật (≤5, 6–20, >20). Ô hiếm khi xuất hiện ở dưới ngưỡng τ = 2% số frame. Frame đáng giá (theo nhãn) nếu chứa ≥ 1 ô hiếm. Ngưỡng chốt ở cổng G1.",
  },
};

export const RARITY_COMPARISON = {
  label: "Độ hiếm ước lượng và hiếm thật",
  tooltip: "Model chọn bằng độ hiếm ước lượng; chúng tôi kiểm tra bằng hiếm thật theo nhãn.",
  noLabels: "Không có nhãn nên không chấm được — chỉ có độ hiếm ước lượng.",
};

export const GT_GROUPS: Record<string, GlossaryItem> = {
  "Rare GT A": {
    label: "Môi trường khó",
    tooltip: "Cảnh có mưa hoặc ban đêm (theo mô tả cảnh). LiDAR ít bị ảnh hưởng bởi ánh sáng nên nhóm này thường khó tìm bằng LiDAR.",
  },
  "Rare GT B": {
    label: "Vật thể rất hiếm",
    tooltip: "Có vật thể thuộc nhóm ít gặp nhất: trẻ em, xe đẩy, xe lăn, cảnh sát, công nhân, xe cứu thương/cảnh sát, động vật, vật cản rơi…",
  },
  "Rare GT Bp": {
    label: "Vật thể ít gặp",
    tooltip: "Có xe máy, xe đạp, xe công trình, rơ-moóc hoặc xe buýt — ít hơn ô tô/người đi bộ nhưng không quá hiếm.",
  },
  "Rare GT C": {
    label: "Khó nhìn bằng cảm biến",
    tooltip: "Có vật ở xa (> 40 m) chỉ còn rất ít điểm LiDAR (≤ 5), hoặc bị che khuất nhiều. Lưu ý: hầu hết frame đều có ít nhất một vật như vậy nên nhóm này hiện rất rộng (đang chờ chốt lại).",
  },
  "rare (cell)": {
    label: "Hiếm thật",
    tooltip: "Xem mục 1.",
  },
};

export const FRAME_SCORES: Record<string, Omit<GlossaryItem, "detail">> = {
  S: {
    label: "Điểm tổng",
    tooltip: "Điểm cuối cùng để xếp hạng frame (0–1), gộp từ các tiêu chí theo mức quan trọng bạn đặt.",
  },
  rRar: {
    label: "Hiếm trong dữ liệu",
    tooltip: "Frame khác xa những frame giống nó nhất ở các cảnh khác (xếp hạng phần trăm).",
  },
  rNov: {
    label: "Lạ với model",
    tooltip: "Frame khác với những gì model AI đã học (chỉ có ở chế độ Nâng cao).",
  },
  rUnc: {
    label: "Model chưa chắc chắn",
    tooltip: "Model đoán dao động hoặc thiếu tự tin, ví dụ kết quả thay đổi khi lật ảnh point cloud (chỉ có ở chế độ Nâng cao).",
  },
  reason: {
    label: "Lý do chọn",
    tooltip: "Tiêu chí đóng góp nhiều nhất, ví dụ \"Hiếm trong dữ liệu — top 3%\". (UI dịch \"rarity p97\" thành câu này.)",
  },
  tags: {
    label: "giữ nguyên",
    tooltip: "Gắn khi tiêu chí tương ứng thuộc top 20% bộ dữ liệu. Khó chỉ xuất hiện ở chế độ Nâng cao.",
  },
  duplicate: {
    label: "Gần giống frame #n",
    tooltip: "Frame này gần như giống một frame đã chọn xếp hạng cao hơn.",
  },
};

export const METRICS: Record<string, Omit<GlossaryItem, "detail">> = {
  recall: {
    label: "Tỉ lệ bắt được frame đáng giá",
    tooltip: "Trong tất cả frame đáng giá theo nhãn của bộ dữ liệu, tập 5% đã chọn chứa được bao nhiêu phần trăm.",
    howToRead: "Chọn ngẫu nhiên 5% kỳ vọng ≈ 5%. Cao hơn nhiều là tốt.",
  },
  nRecall: {
    label: "Tỉ lệ bắt được (so với mức tối đa có thể)",
    tooltip: "Như trên nhưng so với số frame tối đa có thể chọn, vì ngân sách 5% có khi nhỏ hơn số frame đáng giá.",
    howToRead: "100% = mọi chỗ trong ngân sách đều là frame đáng giá.",
  },
  uplift: {
    label: "Gấp mấy lần chọn ngẫu nhiên",
    tooltip: "Tập đã chọn bắt frame đáng giá tốt gấp bao nhiêu lần chọn ngẫu nhiên.",
    howToRead: "1× = không hơn ngẫu nhiên.",
  },
  precision: {
    label: "Tỉ lệ frame đã chọn là hiếm thật",
    tooltip: "Trong các frame đã chọn, bao nhiêu phần trăm là hiếm thật.",
    howToRead: "",
  },
  sceneRecall: {
    label: "Số cảnh mưa/đêm được chạm tới",
    tooltip: "Tỉ lệ cảnh mưa hoặc ban đêm có ít nhất một frame được chọn.",
    howToRead: "",
  },
  coverage: {
    label: "Độ phủ các kiểu hiếm",
    tooltip: "Bao nhiêu kiểu vật thể hiếm khác nhau có mặt trong tập đã chọn.",
    howToRead: "",
  },
  coverageGain: {
    label: "Độ phủ hơn ngẫu nhiên",
    tooltip: "Phủ được nhiều kiểu hiếm hơn chọn ngẫu nhiên bao nhiêu điểm phần trăm.",
    howToRead: "",
  },
  redundancy: {
    label: "Mức trùng lặp",
    tooltip: "Tỉ lệ frame đã chọn có một frame khác cùng cảnh cách nhau dưới 2 giây (gần như giống nhau).",
    howToRead: "Thấp là tốt.",
  },
  nBoxes: {
    label: "Số hộp cần gán nhãn",
    tooltip: "Tổng số vật thể trong các frame đã chọn — ước lượng công gán nhãn.",
    howToRead: "",
  },
  random: {
    label: "Chọn ngẫu nhiên (trung bình ± dao động)",
    tooltip: "Kết quả của 10 lần chọn ngẫu nhiên để so sánh.",
    howToRead: "",
  },
  ci95: {
    label: "Khoảng tin cậy 95%",
    tooltip: "Khoảng mà kết quả có thể dao động nếu đổi bộ cảnh — kết luận \"hơn ngẫu nhiên\" chỉ khi mép dưới vẫn cao hơn ngẫu nhiên.",
    howToRead: "",
  },
};

export const SETTINGS: Record<string, Omit<GlossaryItem, "howToRead">> = {
  tier: {
    label: "Cách đánh giá frame",
    tooltip: "Cơ bản: chỉ dùng hình dạng point cloud, nhanh, không cần model. Nâng cao: thêm model AI đã học trên một phần nhỏ dữ liệu có nhãn để tìm frame model còn lạ hoặc chưa chắc. Nâng cao chỉ mở khi dữ liệu đã chạy bước huấn luyện model.",
  },
  k: {
    label: "Số frame giống nhất để so sánh độ hiếm",
    tooltip: "Số nhỏ: nhạy với khác biệt nhỏ, dễ coi nhiễu là hiếm. Số lớn: ổn định hơn nhưng có thể bỏ qua kiểu hiếm chỉ xuất hiện vài lần. Mặc định 10.",
  },
  lam: {
    label: "Ưu tiên khi chọn",
    tooltip: "Hiếm nhất: lấy frame điểm cao nhất kể cả khi giống nhau. Đa dạng nhất: tránh chọn frame na ná nhau. Mặc định 70% hiếm · 30% đa dạng.",
  },
  maxPerScene: {
    label: "Tối đa số frame mỗi cảnh",
    tooltip: "Giữ tập chọn không dồn vào một đoạn đường. Nếu không đủ chỗ để chọn đủ 5%, hệ thống tự nới và báo cảnh báo.",
  },
  alpha: {
    label: "Mức quan trọng: Hiếm trong dữ liệu",
    tooltip: "Tự quy đổi về tổng 100%. Chế độ Cơ bản chỉ dùng \"Hiếm trong dữ liệu\".",
  },
  beta: {
    label: "Mức quan trọng: Lạ với model",
    tooltip: "Tự quy đổi về tổng 100%. Chế độ Cơ bản chỉ dùng \"Hiếm trong dữ liệu\".",
  },
  gamma: {
    label: "Mức quan trọng: Model chưa chắc chắn",
    tooltip: "Tự quy đổi về tổng 100%. Chế độ Cơ bản chỉ dùng \"Hiếm trong dữ liệu\".",
  },
  budget: {
    label: "Ngân sách",
    tooltip: "Phần trăm số frame được chọn để gán nhãn (mặc định 5%).",
  },
};

export function reasonText(reason: string): string {
  if (reason.startsWith("rarity p")) {
    const p = parseInt(reason.replace("rarity p", ""), 10);
    return `Hiếm trong dữ liệu — top ${Math.max(1, 100 - p)}%`;
  }
  if (reason.startsWith("novelty p")) {
    const p = parseInt(reason.replace("novelty p", ""), 10);
    return `Lạ với model — top ${Math.max(1, 100 - p)}%`;
  }
  if (reason.startsWith("uncertainty p")) {
    const p = parseInt(reason.replace("uncertainty p", ""), 10);
    return `Model chưa chắc chắn — top ${Math.max(1, 100 - p)}%`;
  }
  return reason;
}

export function gtTagLabel(tag: string): string {
  return GT_GROUPS[tag]?.label ?? tag;
}

export const PRED_TAG_LABELS: Record<string, string> = { R: "Hiếm", R1: "Hình dạng hiếm", R2: "Lát cắt hiếm", R3: "VRU hiếm", H: "Khó với model", C: "Bối cảnh", I: "Tương tác", O: "Ngoại lệ" };
export const CONTEXT_AXES: Record<string, string> = { illum: "Chiếu sáng", glare: "Chói", lens: "Ống kính", weather: "Thời tiết" };
export const CONTEXT_CLASSES: Record<string, string> = { day: "Ban ngày", lowlight: "Ánh sáng yếu", night: "Ban đêm", none: "Không chói", headlight: "Đèn xe", sun: "Mặt trời", clean: "Sạch", droplets: "Giọt nước", blurred: "Mờ", dry: "Khô", rain: "Mưa", fog: "Sương" };
export const WARNING_LABELS: Record<string, string> = {
 ELIGIBLE_LT_B: "Frame đủ điều kiện ít hơn ngân sách; không trộn ứng viên đáng ngờ.",
 CONTEXT_NOT_FROZEN: "Ngưỡng bối cảnh chưa đóng băng; chưa xác nhận thẻ bối cảnh.",
 STRATEGY_NOT_IMPLEMENTED: "Chiến lược chưa hỗ trợ; engine dùng chiến lược cân bằng.",
};
export const warningLabel = (code: string) => WARNING_LABELS[code] ?? `Cảnh báo chưa có diễn giải: ${code}`;
export const CV_FLAG_LABELS: Record<string, string> = { NIGHT_CV: "Ảnh tối", GLARE_CV: "Vùng chói", BLUR_CV: "Ảnh mờ", VEIL_CV: "Màn sương / loá" };
