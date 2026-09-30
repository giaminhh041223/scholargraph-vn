# SESSION-20260930-078-CODEX — kênh điều phối trực tiếp

## Phạm vi và quyền

- Người dùng yêu cầu thiết lập kênh trực tiếp để không phải chuyển task thủ công;
  xác nhận Gemini qua Antigravity, Muse qua OpenCode và chọn `muse-spark-1.3-free`.
- Coordinator chỉ thiết lập/kiểm tra kênh và reconcile W0 đã có. Không thực hiện
  toàn backlog, không tạo app chat, scheduler, tài khoản hoặc dịch vụ trả phí.
- Đọc child AGENTS, main state/handoff/tasks/routing/registry/strategy/cards/decisions,
  extension board/cards/handoff và actual worker packets trước sửa. Core SG board giữ nguyên.
- Parent bắt đầu f2ff090, branch codex/public-paper-search. Ba worktree có commit mới
  do worker đã thực thi; không reset/sync đè, không gọi lại task implementation.

## Bằng chứng W0 quan sát

| Worker | HEAD checkout sạch | Packet | Trạng thái coordinator |
|---|---|---|---|
| SOL | 93f8c75 | EXT-01A-SESSION-20260930-SOL-01.md | REVIEW |
| GEMINI | 78177a8 | EXT-01C-SESSION-20260930-W0-GEMINI.md | REVIEW |
| MUSE | 8cee172 | EXT-01B-DISPATCH-20260930-W0-MUSE.md | REVIEW |

Packet dưới namespace management/public_search/packets của mỗi project worker.
Đây là worker-delivered outputs, chưa được reviewer độc lập nghiệm thu. Tests/pilot
trong packet là worker-reported; coordinator chưa chạy lại chúng ở phiên này.
Actual model của các implementation W0 còn unknown; probe sau đó không chứng minh
model trước đó. Session log MUSE dùng lại dispatch ID; runtime session cũ unknown.

## Kênh và các lần kiểm tra thật

- SOL: send_message_to_thread vào chat `01a0efcc-2062-7d01-b687-10d249b56cbe`,
  model override người dùng đã chọn `gpt-6.1-sol`; wait_threads lấy reply đúng
  `SCHOLARGRAPH_SOL_CHANNEL_OK`, turn `01a0effa-2c39-7ec2-a111-5fc8574d0376`.
- GEMINI: agy1.2.13 catalog có gemini-3.8-flash-high; plan/json print prompt trả
  đúng nonce, exit0/SUCCESS, conversation b0528373-5710-4bb7-b4e1-859cc58a6423.
  Sau viết runner, smoke lại PASS exit0, conversation ed8034e8-92b5-4900-86e8-2aa4f01734d1,
  evidence data/public_search/control/runs/5e906cef-f0fb-4497-97ac-622da72a53cc/summary.json.
- MUSE CLI1.17.7 lần đầu FAIL exit1; pure retry FAIL exit1, lỗi local SQLite
  `no such column: replacement_seq`. Không gọi đây là model API lỗi.
- Isolate XDG_DATA_HOME/XDG_STATE_HOME dưới data/public_search/control; debug paths
  xác minh config global vẫn hiện có. Meta/muse-spark-1.3 trả HTTP401 invalid_api_key,
  exit1; session ses_f1002c6e5ffeZV7cal0Z06iKqg. Không đổi global key/database.
- Hỏi đúng provider/model; người dùng chọn Muse free. Catalog ID có thật:
  opencode/muse-spark-1.3-contributor-free. CLI1.17.7 trả HTTP426 đòi >=1.18.0,
  runner FAIL exit1 (run c0863b1b-5d3a-40c6-a7f5-a7ed92b02bc4).
- npm view opencode-ai@1.18.0 xác nhận version/integrity; npm install vào thư mục
  data/control/opencode-cli exit0, added3packages; executable --version1.18.0 exit0.
  Không đổi npm global/Desktop. Npm integrity:
  sha512-iPNdDWzzya/IOB2yPEbsoIfowkTU1qV65ejgcYL/zbN+xQ5wlTqZdv0c84VqL4UlsqTIF/kdo/Cepm4tfs8yGQ==.
- MUSE free dùng saved OpenCode auth qua environment process, không copy secret:
  PASS exit0, nonce đúng, final step reason stop, session ses_f0ffc150fffeVVIMDYcrEGTvO3;
  evidence data/public_search/control/runs/445eb7c9-b147-439a-92eb-4d170ff060f4/summary.json.
- Một helper diagnostic parse stdout OpenCode như JSON đơn bị JSONDecodeError exit1;
  đã sửa đọc từng NDJSON event. Không suy shell exit0 là helper PASS.

## Artifact và workflow

- scripts/run_public_worker.py: stdlib subprocess, native argv, bounded timeout,
  fail explicit exit1, response/session/final completion validation, smoke nonce;
  plan/work modes, explicit session resume; local immutable runs. Không scheduler.
- management/public_search/channels.json: channels/ID/model/executable/probe evidence,
  không secrets. MUSE CLI/config credential chỉ process, database riêng.
- CONTROL.md hướng dẫn SOL qua app tool, GEMINI/MUSE qua runner, coordinator giữ
  board/gate. Không blanket skip permissions hoặc claim checkout là security sandbox.
- W0 state/board đồng bộ REVIEW từ packets đã tồn tại; không W1/DONE hoặc merge code.
- main state/tasks/routing/registry/core assets không sửa. Chưa dispatch review;
  probe requests chỉ đòi reply nonce, không thực hiện card mới.

## Kiểm chứng và tiếp tục

- Tests controller lượt đầu: 20 passed exit0; sau thêm incomplete final-step case,
  chạy lại test và project checker ở closeout; kết quả bổ sung bên dưới.
- Positive response parse hai runtime; malformed JSON/missing config/model/executable,
  wrong checkout/mixed session/missing response/zero-exit FAIL event bị từ chối;
  subprocess CLI invalid inputs exit1. Fixtures trong tmp_path, không gọi API trong tests.
- Các test controller kiểm integrity của kênh; không phải chứng nhận dữ liệu/split,
  chưa có thuật toán nghiên cứu hoặc online-search implementation được thay đổi.
- Next executable: tạo review prompts pin heads trong board; SOL review source audit;
  MUSE review contract rồi UX; findings gửi tác giả sửa và re-review trước freeze/W1.
  Channels ready, chưa có chế độ chạy nền khi coordinator/app dừng.

### Closeout đã chạy

- `pytest tests/unit/test_public_worker_control.py -q`: **21 passed in 0.84s**, exit0.
- Replay hai live stdout bằng parser cuối (bao gồm final reason stop): PASS;
  đối chiếu đúng session/nonce với summary đã lưu, không gọi model thêm.
- Đối chiếu board với ba packet/head hiện có: PASS, REVIEW cả ba, actual_model W0
  vẫn null đúng provenance; không có head bị thay giữa checkpoint và kiểm tra cuối.
- Root `scripts/check_project.ps1`: exit0, **53 core tasks / 448 Markdown links /
  53 routes / 7 lanes / 79 registered chats**; warning SG-034 chờ SG-033 giữ nguyên.
- `git diff --check`: exit0. Runtime/package/logs/control runs được local exclude;
  không stage data, credential, worker checkout hoặc core file.
