# SESSION-20260915-011-RUNNER

- Bắt đầu: 2026-09-15T21:22:46+07:00.
- Worker: `/root/sg007_runner`; lane M.
- Task: SG-007 — Runner và run manifest.
- Phạm vi được giao: `src/scholargraph/evaluation/runner.py` và `tests/unit/test_run_integrity.py`.
- Không sửa shared board/state/handoff/chat registry. Chưa có kết quả kiểm tra tại thời điểm nhận việc.

## Kết quả triển khai

- Hoàn tất `src/scholargraph/evaluation/runner.py`:
  - Sinh run ID có timestamp + timezone context và suffix chống va chạm.
  - Manifest lưu resolved config, config/protocol/data/split/code/model SHA-256, model revision, hardware, environment lock, seed và command đã che tham số nhạy cảm.
  - Lưu ranking JSONL còn raw score, per-query metrics và aggregate metrics; mọi artifact có checksum.
  - State machine giữ `RUNNING → COMPLETED|FAILED`; completed/failed được seal, không resume hay sửa qua API. Failed run lưu loại lỗi và thông báo đã lọc secret.
  - Resume chỉ cho run chưa kết thúc, xác minh provenance tùy chọn và checksum artifact; retry run terminal phải tạo ID mới.
  - Export sang đường dẫn mới và từ chối ghi đè; integrity check phát hiện sửa artifact/manifest ngoài luồng.
  - Final test thật (`split=test`, không synthetic) tự động yêu cầu resolved config và đầy đủ freeze evidence của protocol; không thể né gate bằng cách bỏ cờ `final_test`.
- Hoàn tất `tests/unit/test_run_integrity.py` với 10 test: smoke provenance, raw ranking/per-query, terminal immutability, export collision, failed status/error redaction, run-ID collision, resume hash, artifact/manifest tampering, final freeze gate, deterministic tree hash và duplicate output.
- Không sửa `evaluation/__init__.py`, fixtures hay file điều phối dùng chung.

## Kiểm tra đã chạy

- `pytest tests/unit/test_run_integrity.py -q`: không chạy được; `pytest` không có trong PATH.
- Bundled Python `-m pytest tests/unit/test_run_integrity.py -q`: không chạy được; runtime báo `No module named pytest`.
- Bundled Python với `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`: compile/import runner và test module **PASS**.
- Chạy trực tiếp toàn bộ 10 hàm test bằng shim tối thiểu chỉ thay `pytest.raises`: **10 passed**, exit code 0. Đây là kiểm tra fallback do thiếu pytest, không được ghi như một lượt pytest chính thức.
- Manual smoke riêng cho create/ranking/per-query/complete/integrity/export/collision/resume/fail/final gate: **PASS**, exit code 0.
- `powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1`: **PASS**, exit code 0; 50 tasks, 198 Markdown links, 50 model routes, 12 sessions; board `DONE=7`, `IN_PROGRESS=3`, `TODO=36`, `DEFERRED=4`.

## Hạn chế và bàn giao

- Chưa chạy được pytest chính thức vì runtime hiện tại thiếu package `pytest`; coordinator nên chạy lại `pytest tests/unit/test_run_integrity.py -q` trong môi trường dev đã cài `requirements-dev.txt` trước khi chốt DONE.
- Runner không được re-export qua `evaluation/__init__.py` vì file đó ngoài phạm vi ghi đã giao; caller hiện import trực tiếp từ `scholargraph.evaluation.runner`.
- Kết thúc worker lúc `2026-09-15T21:34:28+07:00`; đề xuất coordinator kiểm tra diff/acceptance, chạy pytest chính thức và cập nhật board/state/HANDOFF nếu đạt.
