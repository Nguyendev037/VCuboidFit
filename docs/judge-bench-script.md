# Kịch bản thuyết trình — Benchmark model giám khảo VCuboidFIT

Deck: https://claude.ai/artifact/G9wVTB5bF6wXUYfXCRZSwU (14 slide, ~11,5 phút). Số liệu lấy từ report thật
AV2 `533d6a16…`. Chỉ dùng tài liệu nội bộ, không đẩy lên git.

Quy ước: **[CHỈ]** = chỉ tay vào đâu trên slide · **[CHUYỂN]** = câu nối sang slide sau.

---

## 1 · cover (~30 giây)

Thưa hội đồng, nhóm em xây một model chọn ra 5 % khung dữ liệu khó nhất để gán nhãn cho hệ phanh khẩn cấp AEB. Câu hỏi đặt ra: làm sao biết lô ảnh đó thật sự khó, khi người chấm lại chính là nhóm? Câu trả lời của nhóm: để hai model giám khảo bên ngoài, không do nhóm huấn luyện, chấm lô ảnh, trên dữ liệu của hãng khác. Luật kết luận được đăng ký và khoá bằng mã băm trước khi mở dữ liệu chấm.

**[CHỈ]** câu hỏi lớn giữa slide. **[CHUYỂN]** Trước hết, em xin trình bày cách nhóm đo.

## 2 · method (~55 giây)

Cách đo gồm bốn bước. Một: lấy một tập ảnh có nhãn 3D gốc, gọi là POOL; trên Argoverse 2 là 2 630 khung. Hai: model của nhóm và 6 cách chọn đối chứng cùng chọn đúng 5 % số khung, tức 132 khung. Ba: hai model giám khảo công khai chấm toàn bộ POOL một lần, mọi lô lấy điểm từ cùng một bảng chấm. Bốn: so với nhãn gốc, đếm số vật có thật mà model giám khảo không tìm ra.

Lô nào làm model giám khảo bỏ sót nhiều vật thật hơn là lô chứa nhiều ca khó hơn. Model của nhóm không đọc nhãn POOL khi chọn.

**[CHỈ]** bốn ô từ trái sang phải, dừng ở ô 4. **[CHUYỂN]** Vậy ảnh dùng để chấm lấy từ đâu?

## 3 · imageset (~45 giây)

Ảnh dùng để chấm **không phải nuScenes**. nuScenes là dữ liệu nhóm dùng để xây và chỉnh model; chấm trên đó giống cho thi lại đúng đề đã ôn.

Nhóm chấm trên **Argoverse 2 Sensor, tập VAL**: dữ liệu của Argo AI, xe khác, cảm biến khác, đường phố Mỹ. 150 log (đoạn lái), 4 806 khung, 28 831 ảnh camera, 345 259 hộp 3D nhãn gốc.
- Xe có 7 camera vòng; chọn 6 hướng giống bố cục nuScenes theo quy tắc cố định, bỏ 1 camera sau.
- Cắt khung 16:9, đưa về 1600×900.
- Giám khảo và mọi cách chọn nhìn đúng cùng một file ảnh, có mã băm từng ảnh.

Model của nhóm giữ nguyên cấu hình làm trên nuScenes, không chỉnh gì trên Argoverse 2. Không dùng Waymo vì giấy phép cấm đánh giá xe thật.

**[CHỈ]** hai thẻ, rồi dải bốn bước. **[CHUYỂN]** Giới thiệu nhanh về bộ dữ liệu Argoverse 2.

## 4 · av2intro (~40 giây)

Argoverse 2 là bộ dữ liệu lái xe tự hành công khai do Argo AI thu thập và gán nhãn, công bố ở NeurIPS 2021: xe thật chạy trên đường phố, ghi đồng thời camera, LiDAR và vị trí xe.
- **1 000 đoạn lái**, mỗi đoạn ~15 giây: 700 train, 150 val, 150 test.
- **6 thành phố Mỹ:** Austin, Detroit, Miami, Pittsburgh, Palo Alto, Washington DC.
- **7 camera vòng + 2 LiDAR** trên nóc xe.
- **26 loại vật** có hộp 3D do người gán.

Nhóm dùng toàn bộ 150 đoạn tập val: 4 806 khung, 28 831 ảnh, 345 259 hộp 3D. Tập test không dùng được vì nhãn không công khai.

**[CHỈ]** câu giới thiệu, bốn con số, băng "Phần nhóm dùng". **[CHUYỂN]** Bộ ảnh này được chia làm ba phần, mỗi phần một việc.

## 5 · splits (~45 giây)

Dữ liệu Argoverse 2 (150 log, 4 806 khung) được chia thành ba phần rời nhau theo tên log, trước khi nhìn nội dung; một log chỉ nằm trong một phần:
- **CAL (~20 %, 960 khung) — bài thi thử:** đặt ngưỡng và kiểm hợp lệ hai giám khảo; model của nhóm lấy thống kê tham chiếu, không đọc nhãn. Không ra kết quả.
- **POOL (~55 %, 2 630 khung) — bài thi thật:** mọi cách chọn lấy 5 % (132 khung) từ đây, giám khảo chấm một lần. Mọi con số kết quả đến từ đây.
- **EVAL (~25 %, 1 216 khung) — để dành:** chưa ai mở, dùng cho Pha 4 khi huấn luyện lại trên lô đã chọn.

Tách như vậy để nhóm không vừa ra đề vừa chấm: chỉnh trên CAL, khóa lại, rồi mới mở POOL.

**[CHỈ]** thanh ba màu, ba thẻ, rồi câu cuối. **[CHUYỂN]** Vậy model của nhóm chọn 5 % khung đó như thế nào?

## 6 · ours (~65 giây)

Đây là model mới nhất của nhóm, rare_v24 đa cảm biến, gồm sáu bước:
1. Từ đám điểm LiDAR, bỏ mặt đất, gom điểm thành vật, dựng hộp 3D.
2. Nối cùng một vật qua các khung, ước vận tốc, loại khung lỗi.
3. Vật càng ít gặp so với thống kê tham chiếu thì điểm hiếm càng cao.
4. Camera bổ sung bối cảnh đêm, mưa, chói, và đo độ lạ từng vật bằng OpenCLIP.
5. Gộp thành điểm khung: 0,70 cho vật đáng chú ý nhất, 0,15 cho mức đông người đi đường, 0,15 cho đêm hoặc thời tiết xấu.
6. MMR cân bằng điểm cao với đa dạng, rồi lấy đủ 5 %.

**[CHỈ]** dừng lâu ở ô 5 và ô 6. **[CHUYỂN]** Chọn xong lô, nhóm cần một thước đo chuẩn.

## 7 · metrics (~60 giây)

Nhóm không tự đặt thước mới. Chỉ số chính là **số vật thật bị model giám khảo bỏ sót trên mỗi khung**. Một vật được tính là "thấy" theo đúng tiêu chí của recall: có hộp dự đoán cùng nhóm lớp, đủ IoU và đủ độ tin cậy. Càng cao thì lô càng chứa nhiều ca detector còn yếu.

Phần thống kê dùng toàn công cụ chuẩn: kappa của Cohen đo hai giám khảo có đồng thuận không; khoảng tin cậy 95 % lấy mẫu lại theo scene 2 000 lần; Holm hiệu chỉnh khi so nhiều cặp cùng lúc.

**[CHỈ]** hàng tô màu đầu bảng. **[CHUYỂN]** Vậy ai là người chấm?

## 8 · judgeintro (~35 giây)

Trước khi nói con số, em giới thiệu hai người chấm:
- **JA · Faster R-CNN v2** (torchvision), họ CNN kinh điển: khoanh vùng có thể có vật, rồi xem từng vùng là gì.
- **JB · RT-DETR** (Hugging Face), họ transformer: nhìn cả ảnh một lượt, đưa thẳng ra danh sách vật.

Cả hai huấn luyện sẵn trên COCO, nhóm không huấn luyện, không chỉnh, chưa từng thấy dữ liệu dự án. Công dụng giống hai giáo viên chấm chéo: vật có thật trong nhãn gốc mà giám khảo không nhận ra là một ca khó; lô nào chứa nhiều ca khó hơn thì đáng gán nhãn hơn. Hai họ kiến trúc khác nhau để kết quả không phụ thuộc điểm yếu riêng của một model; kết luận phải đúng với cả hai.

**[CHỈ]** hai thẻ JA, JB rồi băng "Công dụng". **[CHUYỂN]** Nhưng chính hai giám khảo cũng phải được kiểm tra trước khi chấm.

## 9 · judges (~55 giây)

JA là Faster R-CNN v2, JB là RT-DETR, hai họ kiến trúc khác nhau, trọng số công khai. Nhóm đặt trước ba phép kiểm trên tập hiệu chỉnh CAL của Argoverse 2, 9 307 đối tượng:
- Recall vật dễ: luật đặt trước là 0,90; cả hai chỉ đạt khoảng 0,84 vì nhiều người đi bộ bị che phần dưới. Nhóm hạ ngưỡng xuống 0,84 và gắn nhãn thăm dò cho kết quả.
- Bỏ sót vật khó nhiều hơn vật dễ: 2,77 lần với JA và 2,54 lần với JB (cần ít nhất 2 lần).
- Kappa đồng thuận: 0,80, mức khá.

Model giám khảo trượt kiểm thì bị loại. Nhóm không được chọn lại model giám khảo sau khi xem kết quả.

**[CHỈ]** cột ngưỡng so với hai cột số đo. **[CHUYỂN]** Câu hỏi tiếp theo: nhóm so với ai?

## 10 · rivals (~55 giây)

Nhóm không chọn đối thủ yếu:
- **X0:** bốc ngẫu nhiên, làm 100 lần rồi lấy trung bình.
- **X1:** chọn ảnh khác nhau nhất bằng DINOv2, phương pháp core-set đã công bố.
- **X2:** chọn ảnh mà YOLO11m phân vân nhất, cách phổ biến nhất của active learning.
- **X3:** chọn ảnh đông người, xe đạp, xe máy nhất.
- **N1, N2:** chọn ảnh mờ nhất, tối nhất. Đây là phép kiểm bẫy: nếu ảnh xấu cũng làm giám khảo bỏ sót nhiều như lô của nhóm, thì "khó" chỉ là do ảnh xấu.

Phép so chính là lô của nhóm trừ đối thủ mạnh nhất trong X1, X2, X3, tính lại trong từng lượt lấy mẫu.

**[CHỈ]** X0 → X1–X3 → N1, N2 → công thức D. **[CHUYỂN]** Trước khi xem kết quả, đây là dữ liệu dùng để chấm.

## 11 · data (~55 giây)

Vai trò hai bộ ghi trong đăng ký từ trước:
- **PandaSet:** sơ bộ, chưa có dữ liệu.
- **Argoverse 2:** bộ kết luận, gồm 150 log, 4 806 keyframe, 345 259 hộp 3D, của hãng khác, thành phố khác, cảm biến khác. Config model giữ nguyên.

Trước khi chấm, nhóm kiểm chuyển đổi dữ liệu, vì hộp lệch thì giám khảo bị chấm oan: 96,8 % hộp đạt kiểm phép chiếu, 99,99 % xe dài hơn rộng, 92,5 % hộp thẳng trục với đám điểm LiDAR.

**[CHỈ]** hai nhãn rồi bốn con số. **[CHUYỂN]** Ngoài kiểm dữ liệu, nhóm đặt bốn khoá để không thể tự chấm điểm cho mình.

## 12 · guards (~50 giây)

Bốn khoá:
1. Model giám khảo zero-shot, không fine-tune trên dữ liệu dự án.
2. Kết luận phải đúng với cả hai giám khảo.
3. Luật kết luận băm sha256 trước khi có dữ liệu; config model đóng băng.
4. Lô đã chọn được commit vào git trước khi chấm. Trên Argoverse 2, lô commit lúc 13:24, ngưỡng giám khảo lúc 13:30, sau đó mới mở POOL.

**[CHỈ]** ô 03 và ô 04. **[CHUYỂN]** Và đây là kết quả trên Argoverse 2.

## 13 · av2chart (~40 giây)

Biểu đồ này là toàn bộ kết quả trên một hình: mỗi cách chọn lấy 132 khung, thanh xanh là JA, thanh cam là JB, càng dài thì lô càng làm giám khảo bỏ sót nhiều vật thật.
- Lô của nhóm dài nhất với cả hai: 0,970 và 1,000.
- Ngay sau là bốc ngẫu nhiên và chọn ảnh đông người, khoảng 0,91–0,94: khoảng cách nhỏ.
- Ba hàng cuối (YOLO phân vân, ảnh tối, ảnh mờ) chỉ 0,2–0,5: ảnh xấu không tự thành ca khó.

**[CHỈ]** hàng OURS tô màu, hai hàng ngay dưới, rồi ba hàng cuối. **[CHUYỂN]** Vậy khoảng cách ở trên có chắc không?

## 14 · av2 (~60 giây)

- **Lô của nhóm cao nhất trong các cách chọn bên ngoài, với cả hai giám khảo:** 0,970 và 1,000 vật bị bỏ sót mỗi khung. Đối thủ mạnh nhất là chọn ảnh đông người, 0,909 và 0,932; bốc ngẫu nhiên 0,921 và 0,943.
- **Điều đã chắc chắn:** lô của nhóm vượt rõ ảnh mờ, ảnh tối và cách chọn theo độ phân vân của YOLO, p sau Holm dưới 0,01 với cả hai giám khảo. Nghĩa là độ khó trong lô đến từ vật thật, không phải từ ảnh xấu.
- **Điều chưa chắc:** chênh lệch với đối thủ mạnh nhất là +0,061 và +0,068, dương với cả hai giám khảo, nhưng khoảng tin cậy 95 % vẫn chứa 0. Báo cáo ghi đúng câu: "Chưa chứng minh vượt bên thứ 3 ở cỡ mẫu này".
- **Một điều nhóm nói rõ:** luật đăng ký yêu cầu giám khảo nhận ra 90 % vật dễ. Trên Argoverse 2 cả hai chỉ đạt khoảng 85 %, vì nhiều người đi bộ bị che phần dưới. Nhóm hạ ngưỡng xuống 0,84 sau khi xem tập hiệu chỉnh, nên kết quả mang nhãn thăm dò. Bản tiếp theo sẽ đưa che khuất vào định nghĩa vật dễ và đăng ký lại trước khi chấm.

**[CHỈ]** hai số lớn, rồi dòng "Chắc chắn" và "Chưa chắc". **[KẾT]** Em xin cảm ơn hội đồng, nhóm sẵn sàng nhận câu hỏi.

---

## Hỏi đáp dự phòng

1. **Vì sao hạ ngưỡng 0,90 xuống 0,84?** Trên Argoverse 2, khoảng 95 % vật dễ bị bỏ sót là người đi bộ bị che phần dưới; định nghĩa "vật dễ" chưa tính che khuất. Nhóm kiểm thấy phép chiếu hộp đúng (tâm lệch gần 0), nên đây là giới hạn của định nghĩa, không phải lỗi dữ liệu. Lệch này được ghi tự động trong báo cáo, kết quả mang nhãn thăm dò.
2. **Vì sao hơn ngẫu nhiên ít vậy?** Argoverse 2 rất đông người đi đường, khung ngẫu nhiên đã có khoảng 0,92 vật khó mỗi khung, nên khoảng trống để vượt nhỏ.
3. **Vì sao không dùng mAP?** Câu hỏi là lô chứa bao nhiêu vật thật bị bỏ sót, nên chỉ cần biết từng vật có được thấy hay không; không cần ghép một-một như mAP.
4. **Vì sao tin được model giám khảo?** Trọng số công khai, không do nhóm huấn luyện; hai họ kiến trúc khác nhau đồng thuận kappa 0,80 trên Argoverse 2; luật đòi đúng với cả hai.
5. **Lô có bị chọn lại sau khi thấy điểm không?** Không. Lô và ngưỡng được commit vào git trước khi chấm POOL; mã băm của lô nằm trong báo cáo.
6. **Chọn ảnh xấu có ăn gian được không?** Không. Ảnh mờ chỉ được 0,21 và ảnh tối 0,28 vật/khung, thấp hơn lô của nhóm rất xa.
7. **Bước tiếp theo?** Định nghĩa vật dễ có tính che khuất, đăng ký lại; thêm log để thu hẹp khoảng tin cậy; Pha 4 huấn luyện lại trên lô đã chọn để đo lợi ích thật cho detector.
