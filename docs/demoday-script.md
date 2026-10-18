# Kịch bản thuyết trình Demo Day — 16 slide

Deck: `09-pitch-deck/pitch-deck-demoday.pptx` trên P-007 (bản gốc `H:\tailieu\VCuboidFIT_Slide_DemoDay_16slide.pptx`). Tổng **~13 phút** + hỏi đáp. Mọi số khớp report thật: benchmark T `0df8bd66…`, Argoverse 2 `533d6a16…`.

Quy ước: **[CHỈ]** = chỉ tay vào đâu · **[CHUYỂN]** = câu nối sang slide sau · *nghiêng* = nhấn giọng · **(dừng)** = ngừng 1–2 giây.

## Ba nguyên tắc để thuyết phục

1. **Mở mỗi slide bằng "vì sao cần", rồi mới tới "làm thế nào".** Hội đồng nhớ vấn đề trước, chi tiết sau.
2. **Đổi số thành thứ nhìn thấy được.** Nói "128 so với 120 vật" thay vì "+0,061"; "8 vật trên 42" thay vì "0,114".
3. **Biến sự trung thực thành điểm mạnh.** Nhóm công bố cả chỗ chưa thắng, khoá luật trước khi chấm, để người ngoài chấm. Nói chủ động, không né: hội đồng tin nhóm hơn chính vì điều này.

---

## Slide 1 · Mở đầu (~40 giây)

Em chào thầy cô. (dừng)

Một chiếc xe tự lái chạy một giờ ghi lại hàng chục nghìn khung hình. Muốn AI nhận ra người đi bộ, xe đạp, xe máy tốt hơn, con người phải ngồi khoanh từng vật trên từng khung, và việc đó rất đắt. *Không ai gán nhãn được hết.*

Vậy câu hỏi là: **nếu chỉ đủ tiền gán nhãn 5 %, nên chọn 5 % nào?**

Nhóm em làm VCuboidFIT để trả lời câu hỏi đó: tự động chọn ra những khung hình đáng gán nhãn nhất, ưu tiên người đi đường, phục vụ hệ thống phanh khẩn cấp tự động. Khẩu hiệu của nhóm: *ít gán nhãn hơn, dữ liệu giá trị hơn.*

**[CHUYỂN]** Trước hết, em đi qua toàn bộ quy trình trong một hình.

## Slide 2 · Quy trình 7 bước (~60 giây)

Từ dữ liệu thô đến danh sách cần gán nhãn có 7 bước, đi từ trái sang phải:
1. Nạp điểm laser 3D và ảnh camera của xe.
2. Chia dữ liệu theo từng đoạn đường: phần để chỉnh riêng, phần để chấm riêng.
3. Tìm vật: gom điểm laser thành vật, mô hình PointPillars nhận dạng thêm.
4. Lọc bỏ khung hỏng do cảm biến, *giữ lại tình huống hiếm thật*.
5. Đọc ảnh camera để biết đêm, mưa, chói.
6. Chấm điểm từng khung và chọn đúng 5 %. Thông số chỉnh được, có sẵn 4 hồ sơ.
7. Xem trên web: lý do, vật 3D, ảnh camera; xuất danh sách.

Không có camera thì bỏ bước 5, hệ thống vẫn chạy được chỉ bằng laser.

Và một điều nhóm giữ suốt dự án: **đáp án thật không bao giờ được dùng khi chọn.** Chỉ ở bước kiểm tra cuối mới mở đáp án, để xem cách chọn có hơn chọn ngẫu nhiên hay không. Nếu nhìn đáp án lúc chọn thì kết quả đẹp nhưng vô nghĩa.

**[CHỈ]** bảy ô từ trái sang phải, rồi dòng chữ dưới cùng. **[CHUYỂN]** Bắt đầu từ ảnh camera: một tấm ảnh đi qua hệ thống như thế nào.

## Slide 3 · Ảnh đi qua OpenCV rồi OpenCLIP (~50 giây)

Mỗi khung hình có ảnh từ 6 camera. Ảnh *không quyết định chọn khung nào*; thông tin chính vẫn đến từ laser. Ảnh chỉ giúp hiểu hoàn cảnh.

Ảnh đi qua hai bước bổ sung cho nhau:
- **OpenCV đo bằng công thức:** sáng hay tối, mờ hay chói, cộng vị trí mặt trời theo giờ chụp. Nhanh, chắc, không cần huấn luyện, nhưng không biết trong ảnh có gì.
- **OpenCLIP hiểu bằng ý nghĩa:** ta đưa câu "ban đêm", "mưa lớn", nó cho điểm ảnh khớp câu đó đến đâu. Hiểu nội dung, nhưng điểm không có thang chuẩn.

Ghép lại, ta được nhãn bối cảnh (đêm, mưa, chói) kèm điểm "ảnh này lạ đến mức nào", để người duyệt hiểu vì sao khung được chọn.

**[CHỈ]** bốn ô, dừng ở ô "Vì sao dùng cả hai". **[CHUYỂN]** Đi sâu một chút vào OpenCV.

## Slide 4 · OpenCV: 13 con số cho mỗi ảnh (~50 giây)

OpenCV *không phải AI*. Nó là thư viện xử lý ảnh, chỉ làm phép tính trên từng điểm ảnh. Mỗi ảnh được thu về cùng cỡ để đo công bằng, rồi biến thành **13 con số** trong 4 nhóm:
- **Độ sáng (4 số):** để phát hiện ban đêm.
- **Chói (4 số):** vùng cháy sáng, mảng chói lớn nhất như đèn pha hay mặt trời.
- **Màn mờ (1 số):** chỗ tối nhất cũng bị nâng sáng, tức ảnh bị phủ sương mù hay màng nước.
- **Độ nét (4 số).**

Có một chi tiết nhóm phải xử lý: *ảnh đêm nhiều hạt nhiễu trông như rất nét*. Nên nhóm chia độ sắc cạnh cho mức nhiễu để ra **độ nét thật**.

Bước này chỉ tính số. Ngưỡng bật cờ được học từ dữ liệu chỉnh, không đặt tay, nên tự thích ứng khi đổi sang bộ camera khác.

**[CHỈ]** bốn nhóm, dừng ở ô "Vì sao cần độ nét thật". **[CHUYỂN]** Còn OpenCLIP thì hiểu ảnh bằng cách nào?

## Slide 5 · OpenCLIP (~50 giây)

OpenCLIP có một bộ hiểu ảnh và một bộ hiểu chữ, cùng đặt vào một không gian chung. *Ảnh và câu cùng ý nghĩa sẽ nằm gần nhau*; càng gần thì điểm càng cao. Nó chỉ cho điểm, không tự viết mô tả.

Nhóm dùng nó vào ba việc:
- **Nhãn bối cảnh:** so ảnh với câu như "trẻ em", "xe lăn", "mưa".
- **Độ lạ:** so ảnh với ảnh ở đoạn đường khác; càng khác thường, điểm càng cao.
- **Cắt ảnh quanh từng vật:** chiếu khung 3D lên ảnh rồi cắt riêng, bỏ qua vật bị che gần hết.

Nhóm nói rõ hạn chế: OpenCLIP không hiểu câu phủ định, đếm số lượng còn yếu, và có thể đã từng thấy ảnh giống dữ liệu của ta. **Vì vậy nhóm không dùng OpenCLIP để chấm kết quả chính.** Nó chỉ gợi ý, người duyệt quyết định.

**[CHỈ]** sơ đồ bên trái, ba ô bên phải, rồi dòng hạn chế. **[CHUYỂN]** Từ ảnh, quay về nguồn thông tin chính: điểm laser.

## Slide 6 · PointPillars (~60 giây)

Laser của xe trả về một **đám điểm** quanh xe, mỗi điểm có vị trí 3D và độ phản xạ. Nhưng đám điểm chỉ là hàng chục nghìn chấm, chưa ai biết đâu là người, đâu là xe. PointPillars biến nó thành *khung 3D quanh từng vật*, qua 6 bước:

1. Lấy đám điểm laser.
2. **Nhìn từ trên xuống**, chia mặt đường thành các ô trụ, như chia bàn cờ.
3. Một mạng nhỏ tóm tắt các điểm trong mỗi trụ.
4. Xếp kết quả lại thành *một tấm ảnh phẳng nhìn từ trên xuống*.
5. Dùng mạng xử lý ảnh để nhận ra vật trên tấm ảnh đó. Đây là mẹo của PointPillars: biến bài toán 3D khó thành bài toán ảnh 2D đã có nhiều cách giải tốt.
6. Kết quả: khung 3D có vị trí, kích thước, hướng, loại vật và độ tự tin.

(dừng) Trong VCuboidFIT, PointPillars làm ba việc:
- **Cho vật thể kèm loại:** mỗi khung 3D biết là người, xe đạp hay xe máy. Vật nào PointPillars bỏ sót thì bước gom điểm laser, không cần mô hình, bắt thêm. Hai cách bù cho nhau.
- **Đo độ phân vân:** chạy hai lần, ảnh gốc và ảnh lật trái phải, rồi so. *Hai lần nói khác nhau càng nhiều, mô hình càng chưa chắc*, và khung đó càng đáng gán nhãn.
- **Gộp loại vật** thành 4 nhóm: người đi bộ, xe đạp, xe máy và loại khác.

Phương pháp này là của Lang và cộng sự, công bố ở hội nghị CVPR 2019; nhóm cài bằng thư viện OpenPCDet.

**[CHỈ]** sáu ô từ trái sang phải, dừng ở ô 6 tối màu; rồi ba thẻ bên dưới, nhấn thẻ "Đo độ phân vân". **[CHUYỂN]** Mô hình này nhóm tự huấn luyện, không dùng bản làm sẵn.

## Slide 7 · Huấn luyện PointPillars (~45 giây)

Nhóm **huấn luyện từ đầu** bằng OpenPCDet, cấu hình 20 vòng; một vòng là mô hình xem hết dữ liệu học một lần.

Vì sao không lấy mô hình làm sẵn trên mạng? Vì mô hình làm sẵn có thể *đã thấy trước đáp án* của chính phần dữ liệu mình dùng để kiểm tra. Lấy nó thì kết quả kiểm tra không còn công bằng.

Quy trình: lập danh sách khung để học, loại hẳn phần để dành cho chỉnh và chấm; học từ đầu; chạy kiểm tra hai lượt ảnh gốc và ảnh lật để lưu dấu hiệu "mô hình có chắc không".

Chạy được trên máy RTX 4060 8 GB (2 mẫu mỗi lượt) lẫn A100 (16 mẫu mỗi lượt); sổ tay Colab chạy tiếp được từ điểm dừng. Độ chính xác đo bằng mAP và NDS, sẽ công bố khi huấn luyện xong.

> Chỉ nói nếu bị hỏi: bản đã chấm ở vòng 12 đạt mAP 0,220 và NDS 0,343 trên 602 khung kiểm tra; vòng 20 chưa có số.

**[CHỈ]** số 20 lớn, ba bước, rồi dòng phần cứng. **[CHUYỂN]** Có vật rồi, giờ là phần quan trọng nhất: chấm điểm và chọn.

## Slide 8 · Chấm điểm và chọn lô (~60 giây)

Ba bước, đi từ vật lên khung rồi lên lô:
1. **Điểm của từng vật:** kiểu vật này (loại gì, xa hay gần, bao nhiêu điểm laser) *có thường gặp không*? Ví dụ người đi bộ ở gần thì gặp hoài; một xe đạp ở xa chỉ còn vài điểm laser thì hiếm. Càng ít gặp, điểm càng cao.
2. **Điểm của khung:** 0,70 cho vật nổi bật nhất, 0,15 cho số người đi đường, 0,15 cho bối cảnh đêm hoặc thời tiết xấu.
3. **Chọn lô:** vừa hiếm vừa đa dạng. Khung nào giống khung đã chọn thì bị giảm ưu tiên (phương pháp MMR), mỗi đoạn đường lấy một khung trước. *Không ai muốn trả tiền gán nhãn 10 khung cùng một người đi bộ.*

Các tỉ lệ này là cấu hình mặc định, nhóm không tuyên bố là tối ưu. Người dùng chỉnh được theo nhu cầu; web có sẵn 4 hồ sơ: **Cân bằng, Cảnh hiếm, Mô hình còn yếu, Kịch bản an toàn.**

**[CHỈ]** ba ô, thanh tỉ lệ 0,70 · 0,15 · 0,15, rồi 4 hồ sơ. **[CHUYỂN]** Chọn như vậy có thật sự tốt không? Nhóm đã đo, và công bố đúng như đo được.

## Slide 9 · Đánh giá trên nuScenes (~70 giây)

Đây là phép đo đầu tiên, trên tập kiểm tra của nuScenes: 1 389 khung, 35 đoạn đường, mỗi cách chọn lấy 70 khung. Tập này *chỉ được mở đúng một lần*.

Cả tập có 42 vật hiếm mục tiêu. Điểm trên biểu đồ là số vật hiếm bắt được chia cho 70 khung. Đổi ra số vật cho dễ hình dung:
- chọn ngẫu nhiên (M0): trung bình 5 vật;
- cách cũ của nhóm (M1): 8 vật;
- cách mới chỉ dùng laser (M2): 7 vật;
- cách mới thêm camera (M3): 4 vật.

**Cách mới trừ cách cũ là −0,014, tức kém 1 vật.** Khoảng dao động chứa số 0, nên chưa chứng minh được cách mới tốt hơn. (dừng) *Nhóm công bố đúng như vậy*, không đổi luật, không mở lại tập kiểm tra để chạy lại cho đẹp số.

Quan trọng hơn là **vì sao**: chỉ 14 trên 42 vật mục tiêu có ứng viên nằm trong 1 m. Nghĩa là khó khăn chính không nằm ở cách chấm điểm, mà ở *chưa tìm ra vật*. Đó là lý do nhóm đưa PointPillars vào, và chạy thêm một phép đánh giá độc lập mà mọi người sẽ thấy ở cuối.

**[CHỈ]** bốn cột, ô −0,014, rồi dòng 14/42. **[CHUYỂN]** Trước khi xem phép đánh giá đó, đây là thứ người gán nhãn thực sự dùng.

## Slide 10 · Danh sách khung được chọn (~40 giây)

Đây là ảnh chụp từ bản đang chạy thật tại vcuboidfit.xyz. Ba điều giúp người gán nhãn làm nhanh hơn:
- **Mỗi khung có điểm**: điểm cao, gán trước. Ảnh camera nằm ngay cạnh để nhận ra hoàn cảnh trong một giây.
- **Có lý do bằng chữ**: "hiếm trong dữ liệu", "khó nhìn bằng camera", "vật thể rất hiếm", *không phải một con số khó hiểu*.
- **Lọc nhanh và xuất file**: lọc theo môi trường, loại vật, mức khó; xuất CSV đưa thẳng sang công cụ gán nhãn.

**[CHỈ]** cột điểm, cột lý do, nút lọc và xuất. **[CHUYỂN]** Bấm vào một khung, ta xem nó trong không gian 3D.

## Slide 11 · Xem một khung trong 3D (~40 giây)

Giữa màn hình là đám điểm laser quanh xe; bật tắt được khung đáp án, cụm điểm và khung PointPillars. Dải ảnh phía dưới là cùng một thời điểm nhìn từ 6 hướng. Bên phải là điểm tổng và *vì sao khung này được chọn*.

Người gán nhãn mở ra là biết ngay cần chú ý vật nào, không phải dò cả khung hình.

**[CHỈ]** đám điểm, dải 6 ảnh, ô lý do. **[CHUYỂN]** Giờ là câu hỏi quan trọng nhất: những khung nhóm chọn có thật sự khó không? Nhóm không tự chấm, mà để người ngoài chấm.

## Slide 12 · Đánh giá độc lập 1/3 — cách đo (~60 giây)

Ở slide 9, nhóm đo trên nuScenes. Nhưng nuScenes là dữ liệu nhóm dùng để xây mô hình; chấm trên đó giống *cho thi lại đúng đề đã ôn*. Nên nhóm chấm lại trên **Argoverse 2**: xe khác, cảm biến khác, thành phố khác. Mô hình giữ nguyên, không chỉnh gì.

Bốn bước:
1. **Tập ảnh:** 150 đoạn lái, 4 806 khung, 345 259 khung 3D có đáp án.
2. **Chọn lô:** mô hình của nhóm và 6 cách so sánh, mỗi bên chọn đúng 5 %, tức 132 khung.
3. **Chấm:** hai mô hình phát hiện vật công khai, *không do nhóm huấn luyện*, chấm toàn bộ một lần.
4. **Đếm:** vật có thật mà giám khảo không tìm ra. Lô làm giám khảo bỏ sót nhiều hơn là lô chứa nhiều ca khó hơn, tức càng đáng gán nhãn.

Dữ liệu chia theo đoạn lái thành ba phần tách biệt: phần chỉnh 20 % như bài thi thử, kho ảnh 55 % là bài thi thật, phần để dành 25 % chưa mở.

**[CHỈ]** bốn ô, rồi thanh ba phần. **[CHUYỂN]** Nhưng giám khảo cũng phải được kiểm tra trước khi cho chấm.

## Slide 13 · Đánh giá độc lập 2/3 — giám khảo và đối thủ (~70 giây)

Hai giám khảo thuộc hai kiểu mạng khác nhau: **JA** cổ điển, tìm vùng nghi có vật rồi xem là gì; **JB** hiện đại, nhìn cả ảnh một lần rồi liệt kê vật.

Trên phần chỉnh, cả hai qua kiểm tra:
- Bỏ sót vật khó nhiều gấp **2,5 đến 2,8 lần** vật dễ. Nghĩa là "bị bỏ sót" đúng là dấu hiệu vật khó, không phải giám khảo bỏ sót bừa.
- Hai giám khảo đồng ý với nhau **0,80**, mức khá.

(dừng) *Một điều nhóm nói thẳng:* luật đăng ký trước đòi giám khảo tìm đúng 90 % vật dễ. Trên Argoverse 2, cả hai chỉ đạt **84 %**, vì nhiều người đi bộ bị xe che mất phần dưới. Nhóm hạ ngưỡng sau khi xem phần chỉnh, ghi rõ điều đó trong báo cáo, và gắn **nhãn thăm dò** cho kết quả.

Đối thủ không yếu: chọn ngẫu nhiên lặp 100 lần, chọn ảnh khác nhau nhất, chọn ảnh YOLO phân vân nhất, chọn ảnh đông người. Thêm hai "bẫy": ảnh mờ nhất và ảnh tối nhất.

Và bốn khoá để nhóm không thể tự chấm điểm cho mình: giám khảo dùng nguyên bản; kết luận phải đúng với cả hai; luật kết luận khoá bằng mã băm trước khi mở dữ liệu; chốt danh sách chọn rồi mới chấm.

**[CHỈ]** hai cột JA, JB (dừng ở 0,84), bảng đối thủ, bốn khoá. **[CHUYỂN]** Và đây là kết quả.

## Slide 14 · Đánh giá độc lập 3/3 — kết quả (~70 giây)

Cột càng dài, lô càng làm giám khảo bỏ sót nhiều, tức càng đáng gán nhãn.

- **Lô của nhóm đứng đầu với cả hai giám khảo.** Đổi ra số vật: giám khảo bỏ sót **128 vật** trong lô của nhóm với JA, và **132 vật** với JB. Đối thủ bên ngoài mạnh nhất, chọn ảnh đông người, là 120 và 123. *Nhóm hơn 8 đến 9 vật.*
- **Nhưng nhóm chưa nói là vượt.** Khi rút lại các đoạn lái 2 000 lần, có lúc nhóm hơn tới 35–44 vật, có lúc lại thua 28–34 vật. Khoảng dao động chứa số 0, nên báo cáo ghi đúng câu: *"Chưa chứng minh vượt bên thứ ba ở cỡ mẫu này."*
- **Điều đã chắc chắn:** lô của nhóm hơn ảnh mờ, ảnh tối và cách YOLO phân vân từ khoảng 70 đến hơn 100 vật, với cả hai giám khảo. (dừng) Nghĩa là *độ khó trong lô của nhóm đến từ vật thật khó thấy, không phải từ ảnh xấu.* Đây là điều quan trọng nhất cho người làm dữ liệu: chọn ảnh xấu thì dễ, chọn đúng vật khó mới khó.

**[CHỈ]** cột của nhóm, hai cột sát dưới, ba cột thấp cuối, rồi ô "Chắc chắn" và "Chưa chắc". **[CHUYỂN]** Đằng sau các con số là năm người.

## Slide 15 · Đội ngũ (~30 giây)

Nhóm G01-T007 có năm thành viên, mỗi người một mảng:
- **Nguyên:** phát triển chính: website, máy chủ, mô hình chọn khung, triển khai Azure, đánh giá.
- **Linh:** chủ trì hồ sơ và phê duyệt: tài liệu yêu cầu, kiểm thử người dùng, slide; quy trình xử lý laser, sổ tay Colab.
- **Phú:** quy trình chọn khung phiên bản 2.3 và trang tổng quan phiên bản 2.
- **Hằng và Oanh:** kiểm tra tài liệu, đối chiếu tài liệu với mã nguồn.

Tỉ lệ đóng góp do các thành viên tự đánh giá và cả nhóm thống nhất.

**[CHỈ]** năm thẻ. **[CHUYỂN]** (sang slide cuối)

## Slide 16 · Kết và hỏi đáp (~30 giây)

Tóm lại trong ba câu: (dừng)
1. VCuboidFIT chọn 5 % khung đáng gán nhãn nhất, có lý do và xem được trên 3D, *đang chạy thật* tại vcuboidfit.xyz.
2. Khi để người ngoài chấm trên dữ liệu lạ, lô của nhóm đứng đầu và chắc chắn khó vì vật thật, không vì ảnh xấu.
3. Nhóm công bố cả chỗ chưa thắng, vì một hệ thống chọn dữ liệu chỉ có giá trị khi người khác kiểm lại được.

Em xin cảm ơn thầy cô. Nhóm rất mong nhận câu hỏi, đặc biệt về cách đo và những chỗ kết quả chưa vượt trội.

**[CHỈ]** hai đường link.

---

## Hỏi đáp dự phòng

1. **Vì sao hạ ngưỡng 0,90 xuống 0,84?** Khoảng 95 % vật dễ bị bỏ sót là người đi bộ bị che phần dưới; định nghĩa "vật dễ" chưa tính che khuất. Phép chiếu hộp được kiểm là đúng, nên đây là giới hạn của định nghĩa, không phải lỗi dữ liệu. Lệch được ghi tự động trong báo cáo, kết quả mang nhãn thăm dò. Bản sau sẽ đưa che khuất vào định nghĩa và đăng ký lại trước khi chấm.
2. **M0, M1, M2, M3 là gì?** Bốn cách chọn: ngẫu nhiên; engine cũ chấm theo hình học; engine mới chỉ laser; engine mới thêm camera. Phép so chính là M2 trừ M1.
3. **Vì sao điểm slide 9 thấp (khoảng 0,1)?** Điểm = số vật hiếm bắt được ÷ 70 khung. Cả tập chỉ có 42 vật, nên trần là 0,60. Mới 14/42 vật có ứng viên, nên trần thực tế khoảng 0,20.
4. **Vì sao slide 14 điểm gần 1 còn slide 9 chỉ 0,1?** Hai thước khác nhau: slide 9 đếm 42 vật hiếm theo nhãn; slide 14 đếm vật bị giám khảo bỏ sót, có hàng nghìn vật. Không so trực tiếp được.
5. **Sao không chấm trên nuScenes?** Nhóm đã dùng nuScenes để xây và chỉnh mô hình; chấm trên đó là sân nhà.
6. **Vì sao hơn ngẫu nhiên ít?** Argoverse 2 rất đông người đi đường; khung ngẫu nhiên đã có gần 1 vật khó mỗi khung, khoảng trống để vượt nhỏ.
7. **Lô có bị chọn lại sau khi thấy điểm không?** Không. Danh sách chọn và ngưỡng giám khảo được commit vào git trước khi chấm; mã băm nằm trong báo cáo.
8. **PointPillars chính xác đến đâu?** (chỉ khi được hỏi) Bản vòng 12: mAP 0,220, NDS 0,343 trên 602 khung kiểm tra. Lớp ô tô tốt (0,79), lớp nhỏ như xe đạp còn yếu vì mới tới vòng 12.
9. **Bước tiếp theo?** Định nghĩa vật dễ có tính che khuất và đăng ký lại; thêm dữ liệu để thu hẹp khoảng dao động; huấn luyện lại trên lô đã chọn để đo lợi ích thật cho mô hình phát hiện vật.
