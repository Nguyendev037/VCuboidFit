# Colab MCP — vì sao hay kết nối nhầm và cách làm đúng ngay lần đầu

Tài liệu cho developer dùng Claude Code (hoặc agent khác) điều khiển notebook Google Colab qua MCP. Mọi điểm dưới đây đều được **đo trên máy dev ngày 2026-10-17** khi nạp notebook `benchmark_2` cho hồ sơ 21; nguồn được ghi kèm.

## 1. Cơ chế hoạt động (phải hiểu thì mới gỡ được)

```text
Claude Code ──stdio──► colab-mcp.exe (tiến trình trên máy bạn)
                          │  mở websocket localhost:<PORT>, khoá bằng <TOKEN>
                          ▼
             Trình duyệt mở URL:  https://colab.research.google.com/drive/<NOTEBOOK_ID>?authuser=<N>#mcpProxyToken=<TOKEN>&mcpProxyPort=<PORT>
                          │  trang Colab đọc đoạn sau dấu # rồi tự nối ngược về localhost:<PORT>
                          ▼
             Các tool get_cells / add_code_cell / run_code_cell … do CHÍNH TAB ĐÓ cung cấp
```

Hệ quả:
- MCP chỉ điều khiển được **đúng một tab**: tab có đuôi `#mcpProxyToken=…&mcpProxyPort=…` đang mở.
- Tool sửa ô chỉ tồn tại khi tab đó còn nối. Tab bị đóng hoặc chuyển trang thì tool biến mất.
- Không có tool tạo notebook, đổi tên notebook hay chọn tài khoản. Những việc đó người phải làm trên trình duyệt.

## 2. Nguyên nhân mỗi lần đều khó (đo 2026-10-17)

| # | Triệu chứng | Nguyên nhân gốc | Bằng chứng |
|---|---|---|---|
| N1 | Gọi kết nối xong, notebook mở ra **luôn là TrainModel** dù ta muốn notebook khác | Cấu hình `~/.claude.json` của server `colab-mcp` ghim cứng `COLAB_NOTEBOOK_PATH=/drive/1ykAs9e9jmbbry8naXO_vs4NumCz3WgWY` (TrainModel hồ sơ 16/18) và `COLAB_AUTHUSER=2`. Gói đã được **vá tại máy** để đọc biến này | `F:\tools\uv-tools\colab-mcp\Lib\site-packages\colab_mcp\session.py:169-170`, `websocket_server.py:34` (`# local patch`) |
| N2 | Gọi `open_colab_browser_connection` lần nữa vẫn trả `true` nhưng không đổi notebook | Nếu đã có tab nối (`fe_connected`), hàm trả `True` ngay, **không** mở tab mới | `session.py::check_session_proxy_tool_fn` |
| N3 | `Unknown tool: get_cells` | Tab đã bị đóng hoặc chuyển trang nên tool không còn. Hoặc agent chưa nạp lại schema tool sau khi kết nối lại | lỗi trả về 3 lần trong phiên |
| N4 | Link cũ có `mcpProxyToken` không nối được nữa | `TOKEN = secrets.token_urlsafe(16)` và `PORT` ngẫu nhiên, sinh mới **mỗi lần tiến trình server khởi động** (mở lại Claude Code = mã mới) | `websocket_server.py:62`, `port=0` dòng 148 |
| N5 | Có nhiều tiến trình `colab-mcp.exe` cùng lúc | Mỗi phiên Claude Code tự bật một server. Phiên 2026-10-17 đo được **3 tiến trình**; tab có thể nối vào server của phiên khác | `Get-CimInstance Win32_Process` |
| N6 | Thông báo "colab … CONNECTION_CLOSED" mỗi phiên | Còn server thứ hai tên `colab` (`uvx --from git+https://github.com/googlecolab/colab-mcp`) luôn lỗi khi khởi động, gây nhiễu và dễ nhầm là mất kết nối | `~/.claude.json` → `mcpServers.colab` |
| N7 | Mở notebook đúng nhưng Drive/runtime là của tài khoản khác | Trình duyệt đăng nhập nhiều Google account; `authuser=N` trên URL quyết định tài khoản. Chuyển notebook bằng menu Colab làm **mất đoạn `#mcpProxyToken…`** | thao tác thực tế |
| N8 | Không thể "tạo notebook tên benchmark" bằng agent | Bộ tool không có lệnh tạo hay đổi tên | danh sách tool: get/add/update/delete/move/run cell |

## 3. Quy trình chuẩn cho lần sau (≤ 2 phút)

1. **Người:** tạo notebook mới trên Colab, đặt tên, đúng tài khoản (xem `authuser=` trên URL), rồi chép URL. Ví dụ `https://colab.research.google.com/drive/<ID>?authuser=2`.
2. **Người hoặc agent:** trỏ server vào notebook đó *trước khi* mở phiên Claude Code (§4), **hoặc** làm bước 3.
3. **Agent:** gọi `open_colab_browser_connection` **một lần**. Tab vừa mở có URL dạng `…#mcpProxyToken=<TOKEN>&mcpProxyPort=<PORT>`. Nếu tab đó không phải notebook mong muốn: **người** sửa ngay trên thanh địa chỉ của chính tab đó, chỉ thay `<ID>` (giữ nguyên `?authuser=…` và toàn bộ đuôi `#…`), rồi bấm Enter.
4. **Người:** đóng mọi tab Colab khác, nhất là notebook đang train.
5. **Agent:** nạp lại schema tool (`ToolSearch select:mcp__colab-mcp__get_cells,…`), rồi gọi `get_cells`. **Chỉ ghi khi nội dung đúng notebook mong muốn** (notebook mới thì có 1 ô trống).
6. **Agent:** báo ID ô đầu tiên cho người để đối chiếu, rồi mới `add_*_cell`.

Mất mã TOKEN? Cổng xem được bằng lệnh dưới đây; mã thì **chỉ có trên URL của tab** (không ghi log). Cách lấy lại mà không cần người chép URL (đo 2026-10-17): trình duyệt lưu cả đoạn `#…` trong lịch sử ⇒ chép file `History` của Chrome/Edge (`%LOCALAPPDATA%\…\User Data\<profile>\History`) ra thư mục nháp rồi `select url from urls where url like '%mcpProxyPort=<PORT>%' order by last_visit_time desc`, thay ID notebook trong URL đó và gửi người mở. Link người gửi lại mà cổng không khớp tiến trình nào đang nghe ⇒ link cũ (N4), đừng thử nối. Không tìm lại được thì mở lại Claude Code để sinh mã mới, rồi làm lại bước 3.
```powershell
$p = (Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'colab-mcp' }).ProcessId
netstat -ano | Select-String 'LISTENING' | Select-String ($p -join '|')
```

## 4. Sửa cấu hình gốc (làm một lần)

```powershell
# bỏ server thứ hai luôn lỗi (N6)
claude mcp remove colab -s user
# trỏ server vào notebook đang làm việc (N1) — đổi <ID> mỗi khi chuyển notebook chính
claude mcp remove colab-mcp -s user
claude mcp add colab-mcp -s user -e COLAB_NOTEBOOK_PATH=/drive/<ID> -e COLAB_AUTHUSER=2 -- F:\tools\uv-bin\colab-mcp.exe
```
Sau đó mở **phiên Claude Code mới** (cấu hình MCP chỉ được đọc khi khởi động). Lưu ý: bản vá đọc `COLAB_NOTEBOOK_PATH` nằm trong thư mục cài của `uv`. Chạy `uv tool upgrade colab-mcp` sẽ **mất bản vá** và server quay về mở notebook mặc định.

## 5. Luật an toàn khi agent dùng Colab

- Luôn `get_cells` và đối chiếu trước khi ghi. **CẤM** sửa hay chạy ô trong notebook đang train (TrainModel, `vcf_night_pp_trainval`): một ô chạy nhầm có thể giết tiến trình train A100.
- Mỗi lúc chỉ một phiên Claude Code dùng Colab MCP (N5).
- Agent không tự chạy ô tốn GPU khi người chưa bật cờ (`RUN_POOL`, `RUN_TRAIN`).
- Notebook trong repo (`model/notebooks/*.ipynb`) là nguồn chân lý. Bản trên Colab là bản chép; sửa ở repo rồi chép lại, không sửa riêng trên Colab.
