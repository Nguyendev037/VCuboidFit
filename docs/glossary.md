# Bảng thuật ngữ: "hiếm", điểm số và chỉ số đánh giá

Nguồn chân lý cho mọi tooltip, nhãn UI và tài liệu. Mỗi mục có **Tên hiển thị** (dùng trên UI),
**Tooltip** (≤ 2 câu, lời thường, không ký hiệu toán) và **Chi tiết** (cho tài liệu). Khoá kỹ thuật
(`rRar`, `nRecall`, …) chỉ để lập trình viên tra; KHÔNG hiện cho người dùng.

## 1. Hai loại "hiếm" — đừng nhầm

| Khái niệm | Tên hiển thị | Tooltip | Chi tiết |
|---|---|---|---|
| Hiếm do model ước lượng (`rRar`, `S`) | **Độ hiếm (ước lượng)** | Model tự đoán frame này lạ đến mức nào chỉ từ hình dạng point cloud, không nhìn nhãn. 100% = lạ nhất trong bộ dữ liệu. | Khoảng cách trung bình từ frame tới k frame giống nó nhất ở *các cảnh khác*, đổi sang hạng phần trăm. Không đọc nhãn — đây là thứ dùng để CHỌN. |
| Hiếm theo nhãn (`is_rare`, tag `rare (cell)`) | **Hiếm thật (theo nhãn)** | Frame có ít nhất một vật thể thuộc nhóm rất ít gặp trong bộ dữ liệu (theo nhãn 3D có sẵn). Chỉ dùng để CHẤM xem model chọn đúng không. | Một "ô" = loại vật thể × khoảng cách (0–20, 20–40, >40 m) × số điểm LiDAR trên vật (≤5, 6–20, >20). Ô hiếm khi xuất hiện ở dưới τ = 2% số frame. Frame hiếm thật nếu chứa ≥ 1 ô hiếm. Ngưỡng τ chốt ở cổng G1. |

Thông điệp cho người dùng: **model chọn bằng "độ hiếm ước lượng"; chúng tôi kiểm tra bằng "hiếm thật theo nhãn".**
Dataset không có nhãn ⇒ chỉ có độ hiếm ước lượng, các chỉ số Recall bị ẩn.

## 2. Nhóm hiếm theo nhãn (tag `Rare GT …`)

| Tag kỹ thuật | Tên hiển thị | Tooltip |
|---|---|---|
| `Rare GT A` | **Môi trường khó** | Cảnh có mưa hoặc ban đêm (theo mô tả cảnh). LiDAR ít bị ảnh hưởng bởi ánh sáng nên nhóm này thường khó tìm bằng LiDAR. |
| `Rare GT B` | **Vật thể rất hiếm** | Có vật thể thuộc nhóm ít gặp nhất: trẻ em, xe đẩy, xe lăn, cảnh sát, công nhân, xe cứu thương/cảnh sát, động vật, vật cản rơi… |
| `Rare GT Bp` | **Vật thể ít gặp** | Có xe máy, xe đạp, xe công trình, rơ-moóc hoặc xe buýt — ít hơn ô tô/người đi bộ nhưng không quá hiếm. |
| `Rare GT C` | **Khó nhìn bằng cảm biến** | Có vật ở xa (> 40 m) chỉ còn rất ít điểm LiDAR (≤ 5), hoặc bị che khuất nhiều. Lưu ý: hầu hết frame đều có ít nhất một vật như vậy nên nhóm này hiện rất rộng (đang chờ chốt lại). |
| `rare (cell)` | **Hiếm thật** | Xem mục 1. |

## 3. Điểm của từng frame

| Khoá | Tên hiển thị | Tooltip |
|---|---|---|
| `S` | **Điểm tổng** | Điểm cuối cùng để xếp hạng frame (0–1), gộp từ các tiêu chí theo mức quan trọng bạn đặt. |
| `rRar` | **Hiếm trong dữ liệu** | Frame khác xa những frame giống nó nhất ở các cảnh khác (xếp hạng phần trăm). |
| `rNov` | **Lạ với model** | Frame khác với những gì model AI đã học (chỉ có ở chế độ Nâng cao). |
| `rUnc` | **Model chưa chắc chắn** | Model đoán dao động hoặc thiếu tự tin, ví dụ kết quả thay đổi khi lật ảnh point cloud (chỉ có ở chế độ Nâng cao). |
| `reason` | **Lý do chọn** | Tiêu chí đóng góp nhiều nhất, ví dụ "Hiếm trong dữ liệu — top 3%". (UI dịch "rarity p97" thành câu này.) |
| tag `Hiếm` / `Lạ với model` / `Khó` | giữ nguyên | Gắn khi tiêu chí tương ứng thuộc top 20% bộ dữ liệu. `Khó` chỉ xuất hiện ở chế độ Nâng cao. |
| `Trùng với #n` | **Gần giống frame #n** | Frame này gần như giống một frame đã chọn xếp hạng cao hơn. |

## 4. Chỉ số đánh giá tập đã chọn (cần nhãn)

| Khoá | Tên hiển thị | Tooltip | Cách đọc |
|---|---|---|---|
| `recall` | **Tỉ lệ bắt được frame hiếm** | Trong tất cả frame hiếm thật của bộ dữ liệu, tập 5% đã chọn chứa được bao nhiêu phần trăm. | Chọn ngẫu nhiên 5% kỳ vọng ≈ 5%. Cao hơn nhiều là tốt. |
| `nRecall` | **Tỉ lệ bắt được (so với mức tối đa có thể)** | Như trên nhưng so với số frame tối đa có thể chọn, vì ngân sách 5% có khi nhỏ hơn số frame hiếm. | 100% = mọi chỗ trong ngân sách đều là frame hiếm. |
| `uplift` | **Gấp mấy lần chọn ngẫu nhiên** | Tập đã chọn bắt frame hiếm tốt gấp bao nhiêu lần chọn ngẫu nhiên. | 1× = không hơn ngẫu nhiên. |
| `precision` | **Tỉ lệ frame đã chọn là hiếm thật** | Trong các frame đã chọn, bao nhiêu phần trăm là hiếm thật. | |
| `sceneRecall` | **Số cảnh mưa/đêm được chạm tới** | Tỉ lệ cảnh mưa hoặc ban đêm có ít nhất một frame được chọn. | |
| `coverage` | **Độ phủ các kiểu hiếm** | Bao nhiêu kiểu vật thể hiếm khác nhau có mặt trong tập đã chọn. | |
| `coverageGain` | **Độ phủ hơn ngẫu nhiên** | Phủ được nhiều kiểu hiếm hơn chọn ngẫu nhiên bao nhiêu điểm phần trăm. | |
| `redundancy` | **Mức trùng lặp** | Tỉ lệ frame đã chọn có một frame khác cùng cảnh cách nhau dưới 2 giây (gần như giống nhau). | Thấp là tốt. |
| `nBoxes` | **Số hộp cần gán nhãn** | Tổng số vật thể trong các frame đã chọn — ước lượng công gán nhãn. | |
| `random mean ± std` | **Chọn ngẫu nhiên (trung bình ± dao động)** | Kết quả của 10 lần chọn ngẫu nhiên để so sánh. | |
| `ci95` | **Khoảng tin cậy 95%** | Khoảng mà kết quả có thể dao động nếu đổi bộ cảnh — kết luận "hơn ngẫu nhiên" chỉ khi mép dưới vẫn cao hơn ngẫu nhiên. | |

## 5. Tham số người dùng chỉnh (panel "Tham số nâng cao")

Nhãn/tooltip lấy từ API `GET /jobs/{id}/params-schema` (`label`, `help`) — sửa ở `worker/c4/lidar/params.py`.

| Khoá | Tên hiển thị | Tooltip mở rộng (dùng cho tooltip chi tiết) |
|---|---|---|
| `tier` | Cách đánh giá frame | **Cơ bản**: chỉ dùng hình dạng point cloud, nhanh, không cần model. **Nâng cao**: thêm model AI đã học trên một phần nhỏ dữ liệu có nhãn để tìm frame model còn lạ hoặc chưa chắc. Nâng cao chỉ mở khi dữ liệu đã chạy bước huấn luyện model. |
| `k` | Số frame giống nhất để so sánh độ hiếm | Số nhỏ: nhạy với khác biệt nhỏ, dễ coi nhiễu là hiếm. Số lớn: ổn định hơn nhưng có thể bỏ qua kiểu hiếm chỉ xuất hiện vài lần. Mặc định 10. |
| `lam` | Ưu tiên khi chọn | Hiếm nhất: lấy frame điểm cao nhất kể cả khi giống nhau. Đa dạng nhất: tránh chọn frame na ná nhau. Mặc định 70% hiếm · 30% đa dạng. |
| `maxPerScene` / `quotaOff` | Tối đa số frame mỗi cảnh | Giữ tập chọn không dồn vào một đoạn đường. Nếu không đủ chỗ để chọn đủ 5%, hệ thống tự nới và báo cảnh báo. |
| `alpha` / `beta` / `gamma` | Mức quan trọng: Hiếm trong dữ liệu / Lạ với model / Model chưa chắc chắn | Tự quy đổi về tổng 100%. Chế độ Cơ bản chỉ dùng "Hiếm trong dữ liệu". |
| `budget` | Ngân sách | Phần trăm số frame được chọn để gán nhãn (mặc định 5%). |
