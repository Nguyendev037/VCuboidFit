export interface GlossaryItem {
  label: string;
  tooltip: string;
  detail?: string;
  howToRead?: string;
}

export const RARITY_CONCEPTS: Record<string, GlossaryItem> = {
  rare_est: {
    label: "Độ hiếm (ước lượng)",
    tooltip: "Model tự đoán frame này lạ đến mức nào chỉ từ hình dạng point cloud, không nhìn nhãn. 100% = lạ nhất trong bộ dữ liệu.",
    detail: "Khoảng cách trung bình từ frame tới k frame giống nó nhất ở các cảnh khác, đổi sang hạng phần trăm. Không đọc nhãn — đây là thứ dùng để CHỌN.",
  },
  "rare (cell)": {
    label: "Hiếm thật (theo nhãn)",
    tooltip: "Frame có ít nhất một vật thể thuộc nhóm rất ít gặp trong bộ dữ liệu (theo nhãn 3D có sẵn). Chỉ dùng để CHẤM xem model chọn đúng không.",
    detail: "Một \"ô\" = loại vật thể × khoảng cách (0–20, 20–40, >40 m) × số điểm LiDAR trên vật (≤5, 6–20, >20). Ô hiếm khi xuất hiện ở dưới ngưỡng phần trăm số frame. Frame hiếm thật nếu chứa ≥ 1 ô hiếm. Ngưỡng chốt ở cổng G1.",
  },
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
    label: "Tỉ lệ bắt được frame hiếm",
    tooltip: "Trong tất cả frame hiếm thật của bộ dữ liệu, tập 5% đã chọn chứa được bao nhiêu phần trăm.",
    howToRead: "Chọn ngẫu nhiên 5% kỳ vọng ≈ 5%. Cao hơn nhiều là tốt.",
  },
  nRecall: {
    label: "Tỉ lệ bắt được (so với mức tối đa có thể)",
    tooltip: "Như trên nhưng so với số frame tối đa có thể chọn, vì ngân sách 5% có khi nhỏ hơn số frame hiếm.",
    howToRead: "100% = mọi chỗ trong ngân sách đều là frame hiếm.",
  },
  uplift: {
    label: "Gấp mấy lần chọn ngẫu nhiên",
    tooltip: "Tập đã chọn bắt frame hiếm tốt gấp bao nhiêu lần chọn ngẫu nhiên.",
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
    return `Hiếm trong dữ liệu — top ${100 - p}%`;
  }
  if (reason.startsWith("novelty p")) {
    const p = parseInt(reason.replace("novelty p", ""), 10);
    return `Lạ với model — top ${100 - p}%`;
  }
  if (reason.startsWith("uncertainty p")) {
    const p = parseInt(reason.replace("uncertainty p", ""), 10);
    return `Model chưa chắc chắn — top ${100 - p}%`;
  }
  return reason;
}

export function gtTagLabel(tag: string): string {
  return GT_GROUPS[tag]?.label ?? tag;
}
