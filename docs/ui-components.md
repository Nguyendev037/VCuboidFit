# UI/UX components — VCuboidFIT Web

Tài liệu này mô tả **code đang chạy thực tế** trong
[`vcuboidfit-ui/web`](../../../../vcuboidfit-ui/web). Tên hiển thị và ý nghĩa chỉ số
theo [glossary](glossary.md); kiểu dữ liệu theo
[`web/lib/api/types.ts`](../../../../vcuboidfit-ui/web/lib/api/types.ts). Đây là
as-built guide, không phải bản thiết kế thay thế code.

## 0. Sơ đồ component và luồng dữ liệu

```text
app/layout.tsx
└── Providers (React Query)
    ├── /  — Home
    │   ├── Lần chạy gần đây
    │   ├── Bước 1: upload → DatasetReport
    │   ├── Bước 2: JobStatus → stepper → SelectionResult
    │   ├── Bước 3: Kết quả
    │   │   ├── metrics / recallRows
    │   │   ├── preview thumbnails
    │   │   └── Deep Review → /review/[jobId]
    │   └── Tinh chỉnh
    │       └── AdvancedParamsPanel → ParamsSchema → SelectParams
    ├── /review/[jobId] — ReviewClient
    │   ├── listFrames → FrameGrid (grid/list + filter)
    │   ├── getAnalysis → AnalysisPanel (pool + metrics + histogram)
    │   └── ?frame=token → FrameViewer
    │       ├── getFrame → FrameDetail
    │       ├── CameraImage × 6
    │       └── LidarScene (point cloud + boxes + frustum + minimap)
    └── /frame/[token] — FrameClient → FrameViewer

UI → lib/api/client.ts → /api/*
                       ├── /api/[...path] → worker (datasets, jobs)
                       ├── /api/uploads/* → upload/workspace
                       └── /api/media/[jobId]/* → file trong workspace
```

| Luồng | Đầu vào | API/client | Đầu ra chính |
|---|---|---|---|
| Nạp dataset | File `.zip`, `.rar`, `.7z`, phần `.001`… | `uploadFiles` → `createUpload`, `uploadStatus`, `finalizeUpload` | `DatasetReport` |
| Chạy phân tích | `datasetId`, `pipeline` | `createJob`, `getJob` | `JobStatus` và các `StageInfo` |
| Chọn frame | `SelectParams` | `getParamsSchema`, `select`, `getSelection` | `SelectionResult` |
| Xem Deep Review | `jobId`, `selectionId`, filter/query | `listFrames`, `getAnalysis` | `FrameSummary[]`, `Analysis` |
| Xem một frame | `jobId`, `sampleToken`, `sid` | `getFrame` | `FrameDetail` |
| Media | URL `thumbUrl`, `imageUrl`, `bevUrl`, `lidar.url` | route media nội bộ | ảnh hoặc binary LiDAR |
| Dữ liệu mẫu | `sessionStorage["vcf-demo"] = "1"` hoặc nút chạy thử | cùng các hàm client, chuyển sang `mockApi` | dữ liệu `web/mocks/*.json` |

**Quy tắc dữ liệu:** UI không gọi worker trực tiếp. Mọi request đi qua
`lib/api/client.ts`; khi `NEXT_PUBLIC_MOCK=1` hoặc session flag demo bật,
client dùng `lib/api/mock.ts` thay cho network.

## 1. Bảng route, màn hình và trạng thái chung

| Route/component | Mục đích | Màn hình | Dữ liệu vào | Test liên quan | Ảnh |
|---|---|---|---|---|---|
| `app/page.tsx` — `Home` | Điều phối upload, job, chọn frame và hiển thị kết quả | Trang chủ | `DatasetReport`, `JobStatus`, `SelectionResult`, `JobSummary[]`, `ParamsSchema` | `lib/api/client.test.ts`, `lib/upload.test.ts`, `lib/datasetValidation.test.ts`, `lib/advancedParams.test.ts`, `lib/runRecovery.test.ts` | [01 trống](../../../screenshots/01-home-empty-1440x900.png), [04 kết quả](../../../screenshots/04-home-result-1440x900.png) |
| `app/review/[jobId]/review-client.tsx` — `ReviewClient` | Lọc, sắp xếp, chuyển grid/list và mở viewer | Deep Review | `jobId`, query `sel`, `budget`, `frame`; `FrameSummary[]`, `Analysis` | `components/review/review.test.ts`, `lib/api/client.test.ts` | [11 grid](../../../screenshots/11-review-grid-1440x900.png), [13 filter](../../../screenshots/13-review-filter-rare-gt-1440x900.png) |
| `components/viewer/FrameViewer.tsx` — `FrameViewer` | Overlay xem chi tiết một frame | Frame Viewer | `FrameDetail` | `components/viewer/viewer.test.ts`, `lib/api/client.test.ts` | [14 surround](../../../screenshots/14-viewer-surround-1440x900.png), [18 focus cam](../../../screenshots/18-viewer-focus-cam-front-1440x900.png) |
| `app/frame/[token]/frame-client.tsx` | Entry point trực tiếp cho một frame | Frame Viewer độc lập | `token`, route params; truyền tiếp `FrameViewer` | dùng chung viewer tests | [19 BEV](../../../screenshots/19-viewer-focus-bev-1440x900.png) |
| `app/dev/viewer/page.tsx` | Màn hình dev cho viewer | Dev viewer | UI fixture/dev route | không có test route riêng | [14 surround](../../../screenshots/14-viewer-surround-1440x900.png) |

### Trạng thái bắt buộc của các màn hình

| Component | Rỗng | Đang tải | Lỗi | Xong |
|---|---|---|---|---|
| `Home` | Chưa có dataset/job; hiển thị “Chờ dữ liệu” và placeholder Kết quả | Upload có progress; job có stepper và `role=status`; selection có dòng đang tải | `role=alert`, thông báo đóng được, nút thử lại ở job/selection | Dataset report, stage đã xong, metrics, preview và link Deep Review |
| `ReviewClient` | Thiếu `sel` hoặc lọc không còn frame | Skeleton grid; AnalysisPanel có spinner | Hai vùng lỗi độc lập cho frames và analysis, đều có “Thử lại” | Grid/list và panel phân tích |
| `FrameViewer` | Frame chưa có LiDAR/camera thì hiện placeholder tương ứng | Spinner “Đang nạp dữ liệu frame…” | `role=alert`, “Thử lại” hoặc “Quay lại” | Surround/focus, chỉ số, camera, LiDAR |
| `LidarScene` | Không có `lidarUrl` → “Frame này chưa có dữ liệu LiDAR” | `Đang nạp LiDAR…` và số điểm sau khi decode | `Không tải được LiDAR: …` + “Thử lại LiDAR” | Three.js scene, boxes, frustum và minimap |

## 2. Trang chủ `/` — `Home`

### 2.1 Bước 1 — Nạp dữ liệu

| Thành phần | Mục đích và hành vi |
|---|---|
| Dropzone trong `Home` | `role="button"`, `tabIndex=0`, click hoặc `Enter`/Space mở input file. Nhận nhiều file; input chấp nhận `.zip`, `.rar`, `.7z`, `.001`… |
| Progress list | Mỗi file có `name`, `received`, `total`; hiển thị byte và phần trăm. Upload chunk mặc định 50 MB trong `lib/constants.ts`. |
| Tạm dừng / tiếp tục | `AbortController` dừng request; gọi lại `startUpload` với cùng `uploadId` để tiếp tục. |
| Dataset report | Dữ liệu `DatasetReport`: `scenes`, `frames`, `imagesByCam`, `hasLidar`, `hasAnnotations`, `version`, `warnings`, `errors`. Report hợp lệ là `role=status`; không hợp lệ là `role=alert`. |
| Thông báo lỗi | `error` là câu tiếng Việt; nút đóng có `aria-label="Đóng thông báo lỗi"`. |

**API và kiểu:** `uploadFiles` gọi `createUpload(): Promise<{uploadId}>`,
`uploadStatus(id): Promise<UploadStatus>`, rồi `finalizeUpload(id):
Promise<DatasetReport>`. Sau report hợp lệ, `pipeline` chọn `"lidar"` nếu
`hasLidar`, ngược lại `"camera"`.

**Ảnh:** [02 đang upload](../../../screenshots/02-home-uploading-1440x900.png),
[27 upload lỗi định dạng](../../../screenshots/27-home-upload-bad-format-error-1440x900.png).

**Test:** `lib/upload.test.ts` kiểm tra tạo phiên, resume, chunk, pause và
retry; `lib/datasetValidation.test.ts` kiểm tra dataset có dùng được không.

### 2.2 Bước 2 — Phân tích và stepper

| Pipeline | Bước thật trong code | Nhãn hiển thị | Dữ liệu |
|---|---|---|---|
| Camera | `index`, `dino`, `det`, `clip`, `merge` | Lập chỉ mục, Độ hiếm, Độ khó, Khớp kịch bản, Tổng hợp S | `JobStatus.stages` |
| LiDAR | `lidar_index`, `t0` | nhãn qua `stageLabel`, lần lượt đọc frame/LiDAR và đặc trưng hình học | `JobStatus.stages` |

`JobStatus` có `state` (`queued`, `running`, `done`, `failed`, `cancelled`),
`stage`, `done`, `total`, `etaSec`, `stages` và lỗi tùy chọn. Mỗi stage có
`state`, `durationSec`, `peakVramMb`. Nút “Hủy” gọi `cancelJob` khi job đang
chạy; lỗi trạng thái có nút “Thử lại”.

**Tương tác và truy cập:** stepper là `<ol aria-label="Tiến trình phân
tích">`; trạng thái động dùng `aria-busy` và `role=status aria-live=polite`.
Nút “Chạy phân tích” bị khóa khi dataset không hợp lệ hoặc đã có job.

**API:** `createJob(datasetId, pipeline?)`, `getJob(jobId)`,
`cancelJob(jobId)`. **Test:** `lib/api/client.test.ts` kiểm tra URL/method,
`lib/labels.test.ts` kiểm tra nhãn stage.

**Ảnh:** [03 job đang chạy](../../../screenshots/03-home-running-mocked-1440x900.png).

### 2.3 Kết quả

| Khu vực | Mục đích | Kiểu dữ liệu / API |
|---|---|---|
| Tóm tắt Bước 1 | Nhắc số scene/frame/camera, LiDAR, nhãn và cảnh báo | `DatasetReport` |
| Tóm tắt Bước 2 | Tổng thời gian các stage đã done | `JobStatus.stages` |
| Thẻ “Đã chọn” | Số frame trong ngân sách trên pool | `SelectionResult.budgetB`, `.poolSize` |
| Thẻ `Recall@budget` | Tỉ lệ bắt được frame hiếm thật | `Metrics.recall`; glossary gọi là “Tỉ lệ bắt được frame hiếm” |
| Thẻ LiDAR `nRecall` / camera `Uplift` | LiDAR dùng nRecall chuẩn hóa; camera dùng số lần hơn random | `Metrics.nRecall` hoặc `.uplift` |
| Thẻ LiDAR `Scene-Recall` / camera `Redundancy` | LiDAR dùng cảnh đã chạm; camera dùng mức trùng lặp | `Metrics.sceneRecall` hoặc `.redundancy` |
| Recall theo method | Thanh so sánh từ `recallRows(activePipeline, metrics)` | `MetricsBlock.hybrid`, `.random`, `.ablation` |
| Preview | Tối đa 12 `FrameSummary`, link tới Deep Review với `frame` | `SelectionResult.preview` |
| Xuất CSV | Link tải theo ngân sách hiện tại | `exportUrl(jobId, selectionId, budget)` |
| Deep Review | Mở `/review/{jobId}?sel={selectionId}&budget={budget}` | route review |

`FrameSummary` gồm `rank`, `sampleToken`, `sceneName`, `frameIdx`, `bestCam`,
`thumbUrl`, `S`, `rNov`, `rUnc`, `rQry`, `reason`, `tags`, `camsAvailable`;
LiDAR có thêm `rRar` và `bevUrl`. Ý nghĩa hiển thị: `S` = **Điểm tổng**,
`rRar` = **Độ hiếm (ước lượng)**, `rNov` = **Lạ với model**, `rUnc` =
**Model chưa chắc chắn**, `reason` = **Lý do chọn**.

**Trạng thái:** khi selection pending có `role=status`; lỗi có `role=alert` và
thử lại; kết quả rỗng preview có thông báo rõ. **Test:** `components/review/review.test.ts`
kiểm tra shape và chỉ số; `lib/api/mocks.test.ts` kiểm tra mock contract.

**Ảnh:** [04 kết quả](../../../screenshots/04-home-result-1440x900.png),
[05 kết quả đầy đủ](../../../screenshots/05-home-result-full-1440x900.png).

### 2.4 Lần chạy gần đây

`Home` dùng `listJobs(): Promise<JobSummary[]>`. Mỗi dòng hiển thị dataset/version,
số frame, pipeline, job id, state tiếng Việt và thời gian `createdAt`; nút
“Mở” gọi `openRun` để khôi phục job/selection, bị khóa khi đang upload hoặc
đang restore. Nút refresh có `aria-label="Làm mới lịch sử"`.

| Trạng thái | Hiển thị |
|---|---|
| Đang tải | “Đang tải lịch sử…” |
| Lỗi | câu lỗi từ API |
| Rỗng | “Chưa có lần chạy.” |
| Có dữ liệu | danh sách cuộn tối đa `max-h-48` |

Bookmark run được lưu qua `lib/runRecovery.ts`; URL có ưu tiên hơn bookmark
session. **Test:** `lib/runRecovery.test.ts` và `lib/api/client.test.ts`.

**Ảnh:** [09 lịch sử](../../../screenshots/09-recent-runs-section-1440x900.png),
[10 mở lại sau reload](../../../screenshots/10-recent-runs-reopened-after-reload-1440x900.png).

### 2.5 Panel Tinh chỉnh

| Điều khiển | Props/state | Giá trị gửi |
|---|---|---|
| Ngân sách | state `budget`, slider 0.01–0.10 | `SelectParams.budget` |
| Chiến lược | `preset: Preset`, 4 nút và native select | `balanced`, `rare_first`, `hard_for_model`, `safety_scenarios` |
| Mức đa dạng | state `diversity` với Thấp/Vừa/Cao | số 0.2/0.5/0.8, client đổi thành `low/medium/high` khi POST |
| Kịch bản quan tâm | state `queries: string[]`, thêm/xóa chip | `SelectParams.queries` |
| Đặt lại mặc định | `handleResetDefaults` | reset budget/preset/diversity/query và advanced |
| Tham số nâng cao | `AdvancedParamsPanel` | `AdvancedSubmitParams` hợp nhất vào select |

Các nút preset dùng `aria-pressed`; slider có `aria-label="Ngân sách chọn
frame"`; nút reset có `aria-label="Đặt lại tùy chỉnh về mặc định"`. **Ảnh:**
[06 đóng](../../../screenshots/06-params-advanced-closed-1440x900.png),
[07 mở](../../../screenshots/07-params-advanced-open-1440x900.png),
[08 trợ giúp](../../../screenshots/08-params-advanced-help-1440x900.png).

**Test:** `lib/advancedParams.test.ts` kiểm tra draft, normalize, phần trăm
trọng số và ngôn ngữ thường; `lib/api/client.test.ts` kiểm tra payload select.

#### `AdvancedParamsPanel`

| Mục | Chi tiết |
|---|---|
| Props | `open: boolean`, `schema?: ParamsSchema | null`, `draft: AdvancedDraft`, `applied: boolean`, `onToggle`, `onDraftChange(next)`, `onApply`, `onReset` |
| Dữ liệu vào | `ParamsSchema.fields[]`: `key`, `label`, `type`, `min/max/step`, `help`, `options`, `unit`; `tierAvailable` và `groups` |
| Điều khiển | Tầng 0/1, `k`, `lam`, `maxPerScene`, `quotaOff`, `alpha/beta/gamma`; Tầng 0 khóa beta/gamma |
| API | Parent gọi `getParamsSchema(jobId)` và `select`; component không gọi API trực tiếp |
| Nhãn glossary | Cách đánh giá frame, Số frame giống nhất, Ưu tiên khi chọn, Tối đa số frame mỗi cảnh, mức Hiếm/Lạ/Không chắc |
| Trạng thái | Đóng/mở; option Tầng 1 disabled nếu thiếu seed; applied hiện badge “Tuỳ chỉnh” |
| Accessibility | Nút toggle có `aria-expanded`, `aria-controls`; help có `aria-label="Giải thích"` và `aria-expanded`; slider/number có label |
| Phím | Không có handler bàn phím riêng; native button, range, checkbox và input dùng phím mặc định |

## 3. Deep Review — `/review/[jobId]`

### 3.1 `ReviewClient`

| Mục | Chi tiết |
|---|---|
| Props | `jobId: string` |
| Query URL | `sel` chọn selection, `budget` mặc định `0.05`, `frame` mở viewer |
| API | `listFrames(jobId, sel, {budget, sort, page:1, pageSize:200})`; `getAnalysis(jobId, sel)` |
| Lọc | tìm theo `sceneName`, `sampleToken`, `reason`; chip theo pipeline; LiDAR dùng `rRar` cho Hiếm, `rUnc` cho Khó và tag `Rare GT`/`rare (cell)` |
| Sắp xếp | `rank` hoặc `score`; đổi query key để tải lại |
| Chế độ | `grid`/`list`, nút có `aria-pressed` |
| Rỗng/lỗi | Thiếu `sel` → alert + về trang chủ; không có frame → hướng dẫn xóa lọc; lỗi frames/analysis độc lập có retry |
| Phím | Khi viewer mở: `←/→` chuyển frame, `Esc` đóng; bỏ qua input/textarea/select và phím có modifier |

**Ảnh:** [11 grid](../../../screenshots/11-review-grid-1440x900.png),
[12 list](../../../screenshots/12-review-list-1440x900.png),
[13 filter](../../../screenshots/13-review-filter-rare-gt-1440x900.png),
[25 mobile](../../../screenshots/25-review-grid-390x844.png).

### 3.2 `FrameGrid`

| Mục | Chi tiết |
|---|---|
| Props | `frames: FrameSummary[]`, `selectedToken?`, `onSelectFrame?`, `onOpenViewer?`, `viewMode?`, `pipeline?`, `className?` |
| Grid | Card ảnh `thumbUrl`, rank, `S`, scene/frame, `reason`, tags và sáu đèn camera |
| List | Bảng Rank, Scene, Frame, S; LiDAR đổi cột thành Hiếm/Lạ với model/Không chắc |
| Virtualization | Khi hơn 200 frame, `@tanstack/react-virtual` chia hàng 3 cột, overscan 3 |
| Tương tác | Click chọn + mở; double click mở; Enter/Space trên card mở; grid/list dùng mũi tên và Enter |
| Accessibility | Card `role=button`, `tabIndex=0`, `aria-label` có rank/scene/frame, `aria-pressed`; thumbnail `alt=sceneName`; toggle view có label |
| Test | `components/review/review.test.ts` kiểm tra data/filter; `FrameGrid` không có test render riêng |

### 3.3 `AnalysisPanel`

| Mục | Chi tiết |
|---|---|
| Props | `analysis: Analysis`, `selectedFilter?`, `onFilterChange?`, `pipeline?`, `className?` |
| Pool cards | Trùng lặp, Quá an toàn, Dễ với model, Không gán nhãn, Loại bởi camera, Giá trị cao, Hiếm (GT) |
| Dữ liệu pool | `PoolAnalysis`: `scenes`, `frames`, `duplicates`, `tooSafe`, `easyForModel/easy`, `unlabelable`, `highValue`, `excludedByCamera`, `rare/rareGt` |
| Histogram | `bins`, `counts`, `budgetThreshold`; phần vượt ngưỡng tô xanh và tooltip chỉ số S |
| Metrics | `selected.metrics` lấy `hybrid` nếu là `MetricsBlock`; hiển thị Uplift, Recall, Precision, Coverage, Redundancy, nRecall/sceneRecall/nBoxes tùy payload |
| Tương tác | Bấm card gọi `onFilterChange(card.id)`; card active đổi nền/viền |
| Accessibility | Mỗi card là button; `data-testid="metric-card-*"`; wrapper `data-testid="analysis"` |
| Test | `components/review/review.test.ts` kiểm tra pool, metrics, recall và shape |

**Thuật ngữ:** “Hiếm (GT)” là **Hiếm thật (theo nhãn)**, chỉ dùng để chấm;
“Độ hiếm (ước lượng)” là tín hiệu model dùng để chọn. `recall` là tỉ lệ bắt
frame hiếm, `nRecall` là tỉ lệ so với ngân sách tối đa, `uplift` là số lần
hơn random, `redundancy` thấp là tốt.

## 4. Frame Viewer

### 4.1 `FrameViewer`

| Mục | Chi tiết |
|---|---|
| Props | `jobId: string`, `token: string`, `sid?`, `onPrev?`, `onNext?`, `onClose` |
| API | `getFrame(jobId, token, sid)` → `FrameDetail` |
| `FrameDetail` | Kế thừa `FrameSummary`, thêm `timestamp`, `cams: CamDetail[]`, `lidar`, `boxes3d`, `camPoses` |
| Surround | Ba camera trước, `LidarScene`, ba camera sau; camera thiếu tự ẩn |
| Focus | Camera, LiDAR 3D hoặc BEV; dải thumbnail cho các nguồn |
| Panel thông tin | S, rRar/rNov, rUnc, rQry, reason, chất lượng từng camera, số điểm LiDAR, số 3D boxes |
| Loading/error | Spinner `role=status`; lỗi `role=alert`, retry tăng `retryVersion`, hoặc đóng viewer |
| Sample mode | `useSyncExternalStore` đọc `sessionStorage["vcf-demo"]`; header/footer hiện “Dữ liệu mẫu” |
| Accessibility | Toggle dùng `aria-pressed`; nút prev/next/close có label; footer `aria-label="Phím tắt Frame Viewer"` |

### 4.2 Phím tắt viewer

| Phím | Hành động | Nơi xử lý |
|---|---|---|
| `←` / `→` | Frame trước/kế | `ReviewClient` và `viewerUtils` |
| `Esc` | Đóng viewer | `viewerUtils` |
| `0` | Surround | `viewerUtils` |
| `1`–`6` | Focus sáu camera theo `CAMS` | `viewerUtils` |
| `7` hoặc `L` | Focus LiDAR | `viewerUtils` |
| `B` | Bật/tắt hộp 3D | `viewerUtils` |
| `P` | Bật/tắt lớp LiDAR giả lập trên ảnh | `viewerUtils` |
| `I` | Bật/tắt panel thông tin | `viewerUtils` |
| `R` | Reset góc nhìn 3D | `viewerUtils` |

Các phím bị bỏ qua khi con trỏ đang ở `input` hoặc `textarea`; modifier
Ctrl/Alt/Meta cũng không chiếm.

**Ảnh:** [14 surround](../../../screenshots/14-viewer-surround-1440x900.png),
[15 top](../../../screenshots/15-viewer-surround-top-1440x900.png),
[16 rear](../../../screenshots/16-viewer-surround-rear-1440x900.png),
[17 panel thông tin](../../../screenshots/17-viewer-info-panel-1440x900.png),
[18 focus camera](../../../screenshots/18-viewer-focus-cam-front-1440x900.png),
[19 BEV](../../../screenshots/19-viewer-focus-bev-1440x900.png),
[26 mobile](../../../screenshots/26-viewer-surround-390x844.png).

### 4.3 `CameraImage`

| Mục | Chi tiết |
|---|---|
| Props | `camDetail: CamDetail`, `showBoxes?`, `showLidarOverlay?`, `isFocus?`, `onClick?`, `className?` |
| Dữ liệu | `CamDetail`: `cam`, `imageUrl`, `width/height`, `boxes: Box2D[]`, `score {nov, unc, qry, s}`, `qOk` |
| Hiển thị | Ảnh `object-contain`, SVG box 2D từ 16 tọa độ, màu theo `getCategoryColor`, nhãn category |
| Chất lượng | `qOk` → “✓ Đạt” hoặc “✗ Kém”; score hiện `S: 0.00` và có aria-label |
| Focus tương tác | Wheel zoom 1–5×; kéo ảnh khi zoom; nút `-`, `+`, “Đặt lại” |
| Overlay | `showLidarOverlay` chỉ là lớp hiển thị “LiDAR overlay (P)” |
| Accessibility | `img alt={camDetail.cam}`; trạng thái qOk có aria-label; nút zoom có label thu nhỏ/phóng to/reset |
| Test | `components/viewer/viewer.test.ts`: tên camera friendly/compact; box/frustum dùng decoder tests |

### 4.4 `LidarScene` và các component Three.js

| Component | Mục đích / input |
|---|---|
| `LidarScene` | Props `lidarUrl?`, `boxes3d?`, `camPoses?`, `showBoxes?`, `onSelectCam?`, `resetTrigger?`, `className?`; fetch binary rồi `decodeFloat16Lidar` |
| `PointCloudMesh` | `LidarPointCloud`, màu `Float32Array`, cỡ và opacity; dựng `BufferGeometry` |
| `Boxes3DMesh` / `Cuboid` | Đổi 8 góc thành cuboid, màu category, hover hiện tên object |
| `EgoVehicle` | Wireframe xe ego và hướng trước |
| `CameraFrustums` / `CameraFrustum` | Dùng `camPoses` và `getCameraFrustumLines`; click sphere chọn camera |
| `CameraController` | OrbitControls; góc Tự do/Trên/Sau và reset |
| `SceneContents` | Canvas chính và ba minimap `Trên/Bên/Trước` |

| Điều khiển | Trạng thái/ARIA |
|---|---|
| Góc | `Tự do`, `Trên`, `Sau`; button `aria-pressed`; reset có `aria-label="Đặt lại góc nhìn LiDAR"` |
| Màu | `Độ cao` hoặc `Intensity`; button `aria-pressed` |
| Cỡ điểm | range `aria-label="Kích thước điểm LiDAR"`, output một chữ số |
| Mobile | nút “Điều khiển” mở/ẩn toolbar với `aria-expanded` |
| LiDAR state | vùng status hiện “Đang nạp LiDAR…”, số điểm, hoặc “Không có LiDAR”; lỗi có alert/retry |

**Phép đổi hệ:** point cloud và scene dùng Three.js `(x, z, -y)`. Frustum
nhận quaternion camera theo thứ tự `[w,x,y,z]`, chuẩn hóa quaternion và xoay
trục camera bằng `getCameraFrustumLines`. `boxes3d` là góc 8×xyz trong hệ ego.

**Test:** `components/viewer/viewer.test.ts` kiểm tra float16, màu intensity/
height, cuboid, frustum identity và sáu pose nuScenes thật, quaternion không
đơn vị/hỏng, layout camera thiếu và shortcut.

## 5. Proxy API và media route

### 5.1 `/api/[...path]` — worker proxy

| Thuộc tính | Hành vi |
|---|---|
| Prefix được phép | Chỉ `datasets` và `jobs`; mọi prefix khác trả `404 not_found` |
| Method | GET, POST, PUT, PATCH, DELETE |
| Path safety | Chặn segment rỗng, `.`, `..`, slash, backslash và NUL bằng `400 bad_path` |
| Forward | Mã trạng thái, body và các header `content-type`, `content-disposition`, `cache-control`, `etag`, `last-modified` |
| Body | Method không GET/HEAD đọc text và chuyển `content-type` |
| Worker lỗi | `workerFetch` chuyển thành envelope lỗi chuẩn `{error:{code,message}}` |

**API client dùng qua route này:** `/api/datasets/{id}`, `/api/jobs`,
`/api/jobs/{id}`, `/select`, `/selections`, `/frames`, `/analysis`,
`/params-schema`, `/export.csv`, `/cancel`.

**Test:** `app/api/proxy.test.ts` kiểm tra forward query/body/status, DELETE,
worker down `503`, prefix/path traversal và không rò header hop-by-hop/cookie.

### 5.2 `/api/media/[jobId]/[...path]` — media route

| URL kind | Đuôi cho phép | Nguồn |
|---|---|---|
| `thumbs/<file>` | `.webp`, `.jpg`, `.jpeg`, `.png` | `jobs/{jobId}/media/thumbs` |
| `bev/<file>` | ảnh | `jobs/{jobId}/media/bev` |
| `lidar/<file>` | `.f16`, `.bin` | `jobs/{jobId}/media/lidar`; `.f16` ánh xạ file `.bin` |
| `images/<path>` | ảnh | dataset `data/` của job |

Route kiểm tra `jobId`, segment unsafe, extension, `realpath` chống symlink/
path traversal, file phải tồn tại và là file. Có `cache-control` immutable,
`accept-ranges`, `content-length`; hỗ trợ range 206 và trả 416 khi range sai.

**Test:** `app/api/media.test.ts` kiểm tra MIME, ảnh/LiDAR/BEV, range, file
không được phép, traversal, symlink-prefix, job/file không tồn tại và không
phục vụ JSON/secret.

## 6. Chế độ dữ liệu mẫu

| Cách bật | Cơ chế |
|---|---|
| Nút “Chạy thử dữ liệu mẫu” | `Home.runDemo()` bật `sessionStorage["vcf-demo"]="1"`, gọi `finalizeUpload("demo")`, tạo job mock |
| Biến môi trường | `NEXT_PUBLIC_MOCK=1` khiến `lib/api/client.ts` dùng `mockApi` |
| Trạng thái badge | `Home` và `FrameViewer` đọc cùng `DEMO_KEY`; header Home/Viewer hiện “Dữ liệu mẫu” |
| Dữ liệu | `web/mocks/*.json`, được `lib/api/mocks.test.ts` kiểm tra shape |
| Khôi phục | `runRecovery` lưu job/selection/dataset/demo; URL hiện tại ưu tiên bookmark local |

`mockApi` vẫn giữ contract của `api/types.ts`: job, selection, frame list,
analysis, params schema, upload status và frame detail. Vì vậy Deep Review và
Frame Viewer có cùng trạng thái rỗng/đang tải/lỗi/xong như chế độ thật.

**Ảnh:** [20 kết quả mẫu](../../../screenshots/20-demo-home-result-1440x900.png),
[21 Deep Review mẫu](../../../screenshots/21-demo-review-grid-1440x900.png).

## 7. Quy ước accessibility và test map

| Nhóm | Quy ước đang có trong code |
|---|---|
| Trạng thái động | `role=status`, `aria-live="polite"`, spinner có `aria-hidden` |
| Lỗi | `role=alert`, thông báo tiếng Việt, retry/close rõ hành động |
| Toggle | `aria-pressed` cho preset, view, góc, màu, boxes, info |
| Disclosure | `aria-expanded` + `aria-controls` cho advanced/mobile controls |
| Card tương tác | `role=button`, `tabIndex`, `aria-label`, Enter/Space |
| Ảnh | `alt` theo scene/camera/rank; media binary không hiển thị như ảnh nếu không phù hợp |
| Focus | `focus-visible:outline` trên control chính; native input/select giữ hành vi bàn phím |

| Khu vực | Test chính |
|---|---|
| API client/mock | `lib/api/client.test.ts`, `lib/api/mocks.test.ts` |
| Upload/dataset/recovery | `lib/upload.test.ts`, `lib/datasetValidation.test.ts`, `lib/runRecovery.test.ts` |
| Advanced params/labels | `lib/advancedParams.test.ts`, `lib/labels.test.ts` |
| Deep Review | `components/review/review.test.ts` |
| Viewer/decoder/frustum | `components/viewer/viewer.test.ts` |
| Worker proxy/media/upload routes | `app/api/proxy.test.ts`, `app/api/media.test.ts`, `app/api/uploads/uploads.test.ts` |
