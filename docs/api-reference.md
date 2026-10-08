# API reference — Worker, proxy và media

API worker dùng JSON camelCase ở lớp HTTP (Pydantic alias), còn file trên đĩa
dùng cấu trúc workspace. Mọi lỗi worker có dạng:

```json
{"error":{"code":"not_found","message":"Không tìm thấy tài nguyên."}}
```

Các URL dưới đây là URL worker trực tiếp, ví dụ `http://localhost:8008`. Web
Next.js chuyển tiếp worker qua `/api/...`; upload và media có route riêng.

## 1. Health và dataset

| Method | Path | Body/query | Response thành công | Lỗi chính |
|---|---|---|---|---|
| GET | `/health` | Không | Trạng thái service | 500 nếu service không sẵn sàng |
| POST | `/datasets` | `{ "uploadId": "..." }` | `DatasetReport` | 404 phiên upload; report có `ok=false` nếu dữ liệu sai |
| GET | `/datasets/{datasetId}` | Không | `DatasetReport` | `404 not_found` |

`DatasetReport` gồm `datasetId`, `ok`, `scenes`, `frames`, `imagesByCam`,
`hasLidar`, `hasAnnotations`, `version`, `errors`, `warnings`.

```bash
curl -X POST http://localhost:8008/datasets \
  -H "content-type: application/json" \
  -d '{"uploadId":"upload-id"}'
curl http://localhost:8008/datasets/dataset-id
```

## 2. Jobs

| Method | Path | Body/query | Response |
|---|---|---|---|
| POST | `/jobs` | `{ "datasetId": "...", "pipeline": "lidar" }` | `{ "jobId": "..." }` |
| GET | `/jobs` | Không | `{ "items": [JobSummary] }` |
| GET | `/jobs/{jobId}` | Không | `JobStatus` |
| POST | `/jobs/{jobId}/cancel` | Không | `JobStatus` |

`pipeline` nhận `lidar` hoặc `camera`; nếu bỏ trống, worker chọn LiDAR khi
dataset có `hasLidar`, nếu không thì camera. `JobStatus.state` là
`queued|running|done|failed|cancelled`; stage LiDAR là `lidar_index`, `t0`,
`t1`, còn camera là `index`, `dino`, `det`, `clip`, `merge`.

```bash
curl -X POST http://localhost:8008/jobs \
  -H "content-type: application/json" \
  -d '{"datasetId":"dataset-id","pipeline":"lidar"}'
curl http://localhost:8008/jobs/job-id
curl -X POST http://localhost:8008/jobs/job-id/cancel
```

## 3. Selection và tham số nâng cao

### 3.1. Chọn frame

`POST /jobs/{jobId}/select` yêu cầu job đã `done`. Body dùng các trường sau:

| Trường | Kiểu/miền | Mặc định hoặc ý nghĩa |
|---|---|---|
| `budget` | số `0.01..0.10` | `0.05`, ngân sách chọn |
| `preset` | `balanced`, `rare_first`, `hard_for_model`, `safety_scenarios` | chiến lược trọng số |
| `diversity` | `low`, `medium`, `high` | mức đa dạng MMR |
| `tier` | `0` hoặc `1` | Tầng đánh giá LiDAR |
| `k` | số nguyên `3..50` | số láng giềng so hiếm |
| `lam` | số `0..1` | cân bằng điểm và đa dạng |
| `maxPerScene` | số nguyên `1..50` | quota mỗi scene |
| `quotaOff` | boolean | tắt quota nếu `true` |
| `alpha`, `beta`, `gamma` | số `0..1` | trọng số; tự chuẩn hóa |
| `queries` | 1–12 chuỗi, mỗi chuỗi 1–200 ký tự | pipeline camera |
| `cameras` | danh sách camera hợp lệ | pipeline camera |
| `minLuma`, `minBlurVar` | số | lọc chất lượng camera |
| `minGap` | số nguyên `1..20` | pipeline camera |

Ví dụ LiDAR:

```bash
curl -X POST http://localhost:8008/jobs/job-id/select \
  -H "content-type: application/json" \
  -d '{"budget":0.05,"preset":"balanced","diversity":"medium","tier":0,"k":10,"lam":0.7}'
```

Response `SelectionResult` gồm `selectionId`, `params`, `poolSize`, `budgetB`,
`warnings`, `metrics`, `preview`, `pipeline`, `tierAvailable`. Với LiDAR,
`tierAvailable=[0]` khi chưa có `t1/signals.parquet`, và `[0,1]` khi đã có.

| Lỗi | HTTP | Khi nào |
|---|---:|---|
| `busy` | 409 | Job chưa `done` |
| `tier_unavailable` | 422 | Chọn Tầng 1 nhưng thiếu model seed |
| `bad_params` | 422 | preset, diversity, k, λ hoặc weights sai |
| `bad_request` | 400 | Tham số camera sai |
| `missing_input` | 500 | Thiếu file job |
| `contract` | 500 | File job vi phạm contract |

### 3.2. Lược đồ và lịch sử selection

| Method | Path | Response/lỗi |
|---|---|---|
| GET | `/jobs/{jobId}/params-schema` | schema panel nâng cao; 404 `not_lidar` nếu job camera |
| GET | `/jobs/{jobId}/selections` | `{ "items": [SelectionInfo] }` |
| GET | `/jobs/{jobId}/selections/{sid}` | `SelectionResult` |

```bash
curl http://localhost:8008/jobs/job-id/params-schema
curl http://localhost:8008/jobs/job-id/selections
curl http://localhost:8008/jobs/job-id/selections/selection-id
```

Web không hard-code miền giá trị panel; `params-schema` trả `key`, `type`,
`min`, `max`, `step`, `default`, `label`, `help`, `options`, `tierAvailable`.

## 4. Frame, analysis và export

| Method | Path | Query/body | Response |
|---|---|---|---|
| GET | `/jobs/{jobId}/selections/{sid}/frames` | `budget`, `sort=rank|score`, `tag`, `page`, `pageSize=1..200` | `FramesPage` |
| GET | `/jobs/{jobId}/frames/{token}` | bắt buộc query `sid` | `FrameDetail` |
| GET | `/jobs/{jobId}/selections/{sid}/analysis` | Không | `Analysis` |
| GET | `/jobs/{jobId}/selections/{sid}/export.csv` | tùy chọn `budget` | CSV UTF-8, `Content-Disposition` |

`FramesPage` có `items`, `total`, `budgetB`; `FrameSummary` có `S`, `rRar`,
`rNov`, `rUnc`, `reason`, `tags`, thumbnail và BEV. Theo glossary, UI phải
hiển thị `S` là **Điểm tổng**, `rRar` là **Độ hiếm (ước lượng)**, không gọi đó
là Hiếm thật.

`FrameDetail` thêm camera, `boxes3d`, `camPoses`, timestamp và:

```json
{"lidar":{"url":"/api/media/job-id/lidar/token.f16",
          "numPoints":12345,"format":"f16-xyzi"}}
```

```bash
curl 'http://localhost:8008/jobs/job-id/selections/sid/frames?sort=score&page=1&pageSize=60'
curl 'http://localhost:8008/jobs/job-id/frames/sample-token?sid=sid'
curl http://localhost:8008/jobs/job-id/selections/sid/analysis
curl -OJ 'http://localhost:8008/jobs/job-id/selections/sid/export.csv?budget=0.05'
```

Budget ngoài `1%..10%` trả `400 bad_request`; frame/index thiếu trả `404
not_found`.

## 5. Proxy API của Next.js

File [`web/app/api/[...path]/route.ts`](../../../../vcuboidfit-ui/web/app/api/%5B...path%5D/route.ts)
chuyển tiếp mọi method `GET|POST|PUT|PATCH|DELETE` nhưng chỉ cho hai prefix
`datasets` và `jobs`:

| URL web | Worker đích | Quy tắc |
|---|---|---|
| `/api/datasets...` | `/datasets...` | encode từng segment, giữ query |
| `/api/jobs...` | `/jobs...` | forward body và content type |
| prefix khác | Không forward | `404 not_found` |
| segment rỗng, `.`, `..`, slash, backslash, NUL | Không forward | `400 bad_path` |

Proxy chỉ forward `content-type`, `content-disposition`, `cache-control`,
`etag`, `last-modified`; không forward cookie/hop-by-hop. Upload không đi qua
catch-all này.

## 6. Upload chunk và finalize

| Method | Path | Hợp đồng |
|---|---|---|
| POST | `/api/uploads` | Tạo phiên, trả `{uploadId}` |
| GET | `/api/uploads/{id}` | Trả `{files:[{name,size,received}]}` |
| PUT | `/api/uploads/{id}/files/{name}` | `Content-Range: bytes start-end/total`, mỗi chunk tối đa 50 MB |
| POST | `/api/uploads/{id}/finalize` | Đủ byte mới gọi worker `POST /datasets` |

Tên file chỉ nhận archive được phép và `vcf_manifest.json`. Chunk được ghi vào
`.part`, kiểm tra độ dài rồi nối; gửi sai offset trả `409 offset_mismatch` kèm
`received`, chunk quá lớn trả `413 chunk_too_large`. Finalize trả `409
no_files` hoặc `upload_incomplete` nếu chưa đủ.

```bash
UPLOAD=$(curl -s -X POST http://localhost:3000/api/uploads)
# client đọc uploadId từ JSON rồi gửi từng chunk:
curl -X PUT 'http://localhost:3000/api/uploads/ID/files/vcf_manifest.json' \
  -H 'Content-Range: bytes 0-123/124' -H 'X-File-Size: 124' --data-binary @vcf_manifest.json
curl -X POST http://localhost:3000/api/uploads/ID/finalize
```

## 7. Media route và lý do dùng `.f16`

`GET /api/media/{jobId}/{kind}/{path...}` do
[`web/app/api/media/[jobId]/[...path]/route.ts`](../../../../vcuboidfit-ui/web/app/api/media/%5BjobId%5D/%5B...path%5D/route.ts)
phục vụ:

| `kind` | Đuôi hợp lệ | Nguồn |
|---|---|---|
| `thumbs` | `.webp`, `.jpg`, `.jpeg`, `.png` | `jobs/{id}/media/thumbs` |
| `bev` | ảnh như trên | `jobs/{id}/media/bev` |
| `lidar` | `.f16` hoặc `.bin` | `jobs/{id}/media/lidar` |
| `images` | ảnh như trên | dataset gắn với job |

Route kiểm tra job ID, segment nguy hiểm, extension, `realpath` chống symlink
escape, MIME, `Content-Length`, cache immutable và byte range. Range hợp lệ trả
`206`; range sai trả `416 range_not_satisfiable`.

File thật trên đĩa vẫn là `<token>.bin`, format `float16 x,y,z,intensity`
(`f16-xyzi`). URL public dùng `<token>.f16` vì IDM và trình quản lý tải thường
coi `.bin` hoặc `application/octet-stream` là file tải xuống. Route map `.f16`
về `.bin` nhưng trả MIME `application/x-vcf-lidar-f16`; vì vậy viewer có thể
stream dữ liệu mà không biến một endpoint xem LiDAR thành download bắt buộc.
