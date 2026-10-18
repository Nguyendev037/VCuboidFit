# Kịch bản thuyết trình Demo Day — slide 9 đến 14

Deck: `H:\VCuboidFIT_Slide_DemoDay_15slide.pptx` (bản AutoRecovered). Phần này khoảng **5 phút 30 giây** + hỏi đáp.
Số trên slide 11–13 khớp report benchmark Argoverse 2 `533d6a16…` (nhãn thăm dò); chi tiết ở [judge-bench.md](judge-bench.md).

Quy ước: **[CHỈ]** = chỉ tay vào đâu · **[CHUYỂN]** = câu nối sang slide sau · *nghiêng* = chỗ nhấn giọng.

---

## Slide 9 · Danh sách khung hình được chọn (~45 giây)

Vừa rồi là cách hệ thống chọn. Còn đây là thứ người gán nhãn thực sự nhìn thấy, trên bản đang chạy trực tuyến tại vcuboidfit.xyz.

Mỗi dòng là một khung hình được chọn. Có ba điều:
- **Có điểm.** Điểm càng cao, khung càng đáng gán nhãn trước. Ảnh camera nằm ngay cạnh để nhận ra hoàn cảnh trong một giây.
- **Có lý do bằng chữ.** Không phải một con số khó hiểu, mà là câu như *"hiếm trong dữ liệu"*, *"khó nhìn bằng camera"*, *"vật thể rất hiếm"*.
- **Lọc nhanh và xuất file.** Lọc theo môi trường, loại vật hiếm, mức khó; xuất ra CSV để đưa thẳng sang công cụ gán nhãn.

Ảnh này dùng dữ liệu mẫu nuScenes mini.

**[CHỈ]** cột điểm → cột lý do → nút lọc và xuất. **[CHUYỂN]** Bấm vào một khung hình, ta xem được nó trong không gian 3D.

## Slide 10 · Xem một khung hình trong 3D (~45 giây)

Đây là trình xem 3D của một khung hình.
- **Giữa màn hình:** đám điểm laser quanh xe. Có thể bật tắt từng lớp: khung đáp án, cụm điểm nhóm gom được, và khung do PointPillars tìm ra.
- **Dải ảnh phía dưới:** cùng một thời điểm nhìn từ 6 camera, có đánh dấu vật thể.
- **Bên phải:** điểm tổng và *vì sao khung này được chọn*.

Nhờ vậy người gán nhãn biết ngay cần chú ý vật nào, không phải tự dò cả khung hình.

**[CHỈ]** đám điểm → dải 6 ảnh → khung lý do bên phải. **[CHUYỂN]** Câu hỏi quan trọng nhất: những khung được chọn có thật sự khó không? Nhóm không tự chấm, mà để mô hình bên ngoài chấm.

## Slide 11 · Đánh giá độc lập 1/3 — cách đo (~60 giây)

Ở slide 8 nhóm đã đo trên nuScenes, nhưng nuScenes là dữ liệu nhóm dùng để xây mô hình. Chấm trên đó giống *cho thi lại đúng đề đã ôn*. Vì vậy nhóm chấm lại trên **Argoverse 2**: xe khác, cảm biến khác, thành phố khác. Mô hình của nhóm giữ nguyên, không chỉnh gì.

Cách đo có bốn bước:
1. **Tập ảnh:** 150 đoạn lái, 4 806 khung hình, 345 259 khung 3D có đáp án.
2. **Chọn lô:** mô hình của nhóm và 6 cách so sánh, mỗi bên chọn đúng 5 %, tức 132 khung.
3. **Chấm:** hai mô hình phát hiện vật công khai, không do nhóm huấn luyện, chấm toàn bộ kho ảnh một lần.
4. **Đếm:** vật có thật mà giám khảo không tìm ra. Lô nào làm giám khảo bỏ sót nhiều hơn là lô chứa nhiều ca khó hơn.

Dữ liệu được chia theo đoạn lái thành ba phần tách biệt, trước khi nhìn nội dung:
- **Phần chỉnh, 20 %:** giống bài thi thử, chỉ để đặt ngưỡng và kiểm tra giám khảo;
- **Kho ảnh, 55 %:** bài thi thật, mọi con số kết quả đến từ đây;
- **Phần để dành, 25 %:** chưa mở.

**[CHỈ]** bốn ô từ trái sang phải, rồi thanh ba phần bên dưới. **[CHUYỂN]** Nhưng trước khi tin giám khảo, chính giám khảo cũng phải được kiểm tra.

## Slide 12 · Đánh giá độc lập 2/3 — giám khảo và đối thủ (~60 giây)

Hai giám khảo thuộc hai loại mạng khác nhau. **JA, Faster R-CNN v2**, là mạng cổ điển: tìm vùng nghi có vật rồi xem là vật gì. **JB, RT-DETR**, là mạng hiện đại: nhìn cả ảnh một lần rồi liệt kê vật.

Trên phần chỉnh, cả hai qua kiểm tra:
- bỏ sót vật khó nhiều gấp **2,5 đến 2,8 lần** vật dễ, tức là "bị bỏ sót" đúng là dấu hiệu ca khó;
- hai giám khảo đồng ý với nhau **0,80**, mức khá.

*Một điều nhóm nói thẳng:* luật đăng ký trước đòi giám khảo tìm đúng 90 % vật dễ. Trên Argoverse 2 cả hai chỉ đạt **0,84**, vì nhiều người đi bộ bị che phần dưới. Nhóm hạ ngưỡng sau khi xem phần chỉnh, nên kết quả được gắn **nhãn thăm dò**.

Đối thủ không yếu: chọn ngẫu nhiên lặp 100 lần, chọn ảnh khác nhau nhất, chọn ảnh YOLO phân vân nhất, chọn ảnh đông người. Thêm hai cách "bẫy" chỉ lấy ảnh mờ nhất và tối nhất.

Và bốn khoá để nhóm không tự chấm cho mình: giám khảo dùng nguyên bản; kết luận phải đúng với cả hai; luật kết luận khoá bằng mã băm trước khi mở dữ liệu; chốt danh sách chọn rồi mới chấm.

**[CHỈ]** hai cột JA, JB (dừng ở 0,84) → bảng 6 cách so sánh → bốn khoá cuối slide. **[CHUYỂN]** Và đây là kết quả.

## Slide 13 · Đánh giá độc lập 3/3 — kết quả (~60 giây)

Biểu đồ là số vật bị bỏ sót trên mỗi khung, cột càng dài thì lô càng khó.

- **Lô của nhóm đứng đầu với cả hai giám khảo:** 0,970 với JA và 1,000 với JB. Ngay sau là chọn ngẫu nhiên, khoảng 0,92–0,94, và chọn ảnh đông người, khoảng 0,91–0,93.
- **So với đối thủ ngoài mạnh nhất:** hơn +0,061 và +0,068. Nhưng khoảng dao động 95 % vẫn chứa số 0, nên nhóm *chưa* nói là vượt.
- **Điều đã chắc chắn:** lô của nhóm hơn rõ rệt cách chọn ảnh mờ, ảnh tối và cách YOLO phân vân, với cả hai giám khảo. Ảnh mờ, ảnh tối chỉ được 0,2–0,3. Nghĩa là *độ khó trong lô của nhóm đến từ vật thật, không phải từ ảnh xấu*.
- **Điều chưa chắc:** hơn chọn ngẫu nhiên +0,05 và hơn cách ảnh khác nhau nhất, chưa đủ căn cứ thống kê. Argoverse 2 rất đông người đi đường, nên khung ngẫu nhiên đã có gần 1 vật khó mỗi khung; khoảng trống để vượt nhỏ.

Báo cáo ghi đúng câu: *"Chưa chứng minh vượt bên thứ ba ở cỡ mẫu này."*

**[CHỈ]** cột OURS → hai cột sát dưới → ba cột thấp cuối → ô "Chắc chắn" và "Chưa chắc". **[CHUYỂN]** Đó là toàn bộ phần trình bày của nhóm.

## Slide 14 · Hỏi đáp (~15 giây)

Em xin cảm ơn thầy cô đã lắng nghe. Bản trực tuyến ở vcuboidfit.xyz, mã nguồn ở GitHub. Nhóm rất mong nhận câu hỏi, đặc biệt về cách đo và những chỗ kết quả chưa vượt trội một cách chắc chắn.

**[CHỈ]** hai đường link.

---

## Hỏi đáp dự phòng

1. **Vì sao hạ ngưỡng 0,90 xuống 0,84?** Khoảng 95 % vật dễ bị bỏ sót là người đi bộ bị che phần dưới; định nghĩa "vật dễ" chưa tính che khuất. Nhóm kiểm thấy phép chiếu hộp đúng, nên đây là giới hạn của định nghĩa, không phải lỗi dữ liệu. Lệch được ghi tự động trong báo cáo, kết quả mang nhãn thăm dò. Bản sau sẽ đưa che khuất vào định nghĩa và đăng ký lại trước khi chấm.
2. **Sao không chấm trên nuScenes?** Nhóm đã dùng nuScenes để xây và chỉnh mô hình; chấm trên đó là sân nhà. Argoverse 2 là xe khác, cảm biến khác, mô hình giữ nguyên cấu hình.
3. **Vì sao hơn ngẫu nhiên ít?** Argoverse 2 đông người đi đường, khung ngẫu nhiên đã có ~0,92 vật khó mỗi khung.
4. **Vì sao tin được giám khảo?** Trọng số công khai, không do nhóm huấn luyện; hai loại mạng khác nhau đồng ý 0,80; kết luận phải đúng với cả hai.
5. **Lô có bị chọn lại sau khi thấy điểm không?** Không. Danh sách chọn và ngưỡng giám khảo được commit vào git trước khi chấm kho ảnh; mã băm nằm trong báo cáo.
6. **Ảnh xấu có ăn gian được không?** Không. Ảnh mờ 0,21 và ảnh tối 0,28 vật mỗi khung, thấp hơn lô của nhóm rất xa.
7. **Bước tiếp theo?** Định nghĩa vật dễ có tính che khuất và đăng ký lại; thêm dữ liệu để thu hẹp khoảng dao động; huấn luyện lại trên lô đã chọn để đo lợi ích thật cho mô hình phát hiện vật.
