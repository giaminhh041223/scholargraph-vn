# Điều phối trực tiếp ba worker

Thiết lập ngày 2026-09-30 theo yêu cầu người dùng: Gemini qua Antigravity,
Muse qua OpenCode; Muse được người dùng xác nhận dùng bản miễn phí.
Coordinator ở chat hiện tại giữ gate và board extension.

## Kênh đã kiểm tra bằng lời gọi thật

| Worker | Kênh | Model ID chọn khi gọi | Kết quả |
|---|---|---|---|
| SOL | Chat Codex có sẵn `01a0efcc-2062-7d01-b687-10d249b56cbe` | `gpt-6.1-sol` | Trả nonce kiểm tra đúng |
| GEMINI | Antigravity CLI 1.2.13 | `gemini-3.8-flash-high` | SUCCESS, trả nonce đúng |
| MUSE | OpenCode CLI 1.18.0 riêng của coordinator | `opencode/muse-spark-1.3-contributor-free` | CLI0, trả nonce đúng |

[Cấu hình](channels.json) lưu endpoint cục bộ, executable/model/session và trạng thái
probe. Model ID được gửi vào runtime; không dùng kết quả probe để khẳng định model
đã viết implementation W0 trước đó. Provenance W0 còn unknown khi packet không
có bằng chứng runtime.

## Cách giao việc và nhận kết quả

SOL: coordinator gọi `send_message_to_thread` với thread/host/model trong cấu hình;
theo dõi bằng `wait_threads` và lấy packet ở worktree SOL. Dùng chat đã có, không
tạo chat khác. Người dùng đã yêu cầu kênh giao việc trực tiếp nên không cần chuyển
prompt thủ công giữa các ứng dụng.

GEMINI/MUSE: dùng [CLI runner](../../scripts/run_public_worker.py) từ project gốc:

```powershell
& .venv/Scripts/python.exe scripts/run_public_worker.py --worker GEMINI --smoke
& .venv/Scripts/python.exe scripts/run_public_worker.py --worker MUSE --smoke

# Prompt do coordinator chuẩn bị: task/head/input/owned paths/acceptance/packet.
& .venv/Scripts/python.exe scripts/run_public_worker.py --worker GEMINI --prompt-file management/public_search/dispatch/review-gemini.txt --mode plan --timeout 1800
& .venv/Scripts/python.exe scripts/run_public_worker.py --worker MUSE --prompt-file management/public_search/dispatch/review-muse.txt --mode plan --timeout 1800
```

Hai file `review-*.txt` ở ví dụ là đầu vào cần tạo khi giao review; chưa được tạo hay
dispatch. `--mode work` cho phép dùng accept-edits/build khi task ghi đã được cấp
quyền. `--session ID` tiếp tục một phiên CLI đã xác minh đúng scope; không dùng
`--continue` để vô tình nối nhầm phiên. Mỗi process chỉ một turn; không tự chọn task.

Runner ghi summary và diagnostics dưới `data/public_search/control/runs/<UUID>/`,
không ghi đè run cũ. Có timeout, model/session rõ, FAIL và exit1 nếu thiếu input,
lỗi subprocess/provider, JSON thiếu trường, thiếu response/completion hoặc probe
nonce không đúng. Bằng chứng PASS không chỉ dựa vào process exit0.
Runner không sửa board, tự merge hoặc tự chuyển task DONE. Cấu hình không chứa key.

OpenCode giữ config tài khoản hiện có. Credential được đọc từ auth.json sẵn có và
truyền trong môi trường process, không sao chép vào repo. CLI dùng kho SQLite/state
riêng trong `data/public_search/control/` và chạy `--pure`; không chạy plugin ngoài
trong kênh này. Không tự tắt kiểm tra quyền. Prompt phải giới hạn đúng vùng file;
checkout riêng không phải sandbox bảo mật. Khi runtime cần quyền bổ sung, coordinator
xử lý yêu cầu cụ thể hoặc báo block, không giả định turn hoàn thành.

## Lỗi đã gặp và cách xử lý

1. OpenCode 1.17.7 dùng kho phiên mặc định: FAIL SQLite `no such column: replacement_seq`.
   Dùng kho CLI riêng, không sửa/migrate database của desktop để vượt lỗi.
2. `meta/muse-spark-1.3`: HTTP401 `invalid_api_key`. Giữ lại lỗi trong checkpoint.
3. Người dùng chọn Muse miễn phí; catalog máy ánh xạ sang
   `opencode/muse-spark-1.3-contributor-free`. CLI1.17.7 bị HTTP426, yêu cầu >=1.18.0.
4. Cài `opencode-ai@1.18.0` riêng tại `data/public_search/control/opencode-cli/`;
   không cập nhật global CLI/desktop. Probe đúng model miễn phí PASS sau đó.

## Gate và bước tiếp theo

Vòng làm việc: kiểm dependencies/phiên đang chạy → giao task vào checkout riêng →
thu packet/commit/test → giao reviewer độc lập → trả findings cho tác giả sửa →
re-review → coordinator kiểm và tích hợp. Board chỉ có một coordinator ghi.

Ba packet W0 đã có và task EXT-01A/B/C ở REVIEW. Chưa dispatch review trong phiên
thiết lập kênh; chưa freeze contract hoặc bắt đầu W1. Không suy W0 DONE từ lời
worker báo tests pass. Bước tiếp: giao SOL review audit MUSE; MUSE review contract
SOL và UX GEMINI lần lượt, trên commit đã pin trong board. Xử lý findings và policy
delta trước W1. Lời gọi kiểm tra kênh chỉ yêu cầu trả nonce.

Công cụ này dùng khi coordinator đang chạy. `scheduler_enabled=false`; chưa có
vòng chạy nền khi chat/app đã dừng.

Nguồn hướng dẫn CLI: [Antigravity headless](https://antigravity.google/docs/cli/headless/),
[OpenCode CLI](https://opencode.ai/docs/cli/),
[OpenCode providers](https://opencode.ai/docs/providers/).
