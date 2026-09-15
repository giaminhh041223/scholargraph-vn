# SESSION-20260915-015-RUNNER-SECRET-FIX

- Bắt đầu: 2026-09-15T22:05:41+07:00.
- Worker: `/root/sg007_runner`; lane M.
- Task: SG-007 narrow correction after re-review.
- Phạm vi: `src/scholargraph/evaluation/runner.py`, `tests/unit/test_run_integrity.py`, và log này.
- Must resolve only remaining P1 F2 secret sanitization and regression coverage; do not change control files or behavior already passing F1/F3/F4.

## Sửa P1 F2

- Thay sanitizer regex bằng ba lớp có ranh giới key rõ ràng và không phân biệt hoa/thường:
  - Authorization dùng dấu `:` hoặc `=`, hỗ trợ `Basic`/`Bearer` và giá trị quoted/unquoted; che toàn bộ scheme + credential.
  - CLI nhạy cảm (`--password`, `--api-key`, `--token`, `--access-token`, `--secret` và dạng một dấu gạch) hỗ trợ `OPTION VALUE`, `OPTION=value`, cùng giá trị nằm trong nháy đơn/đôi có khoảng trắng.
  - Key/value diagnostic hỗ trợ key có hoặc không có nháy trong dict repr/JSON và giá trị quoted/unquoted.
- Giữ exact-key boundary để không che nhầm metadata khoa học như `token_count`, `tokenizer`, `passwordless_method`, cụm “authorization model”, “bearer plants” hay “API key effects”.
- Không thay đổi logic final gate, artifact verification/completion hoặc code provenance đã PASS ở re-review.

## Regression và kiểm tra

- Thêm regression trực tiếp và persistence cho đúng bốn reproducer còn lỗi:
  - `Authorization=Bearer REVIEW_SECRET_EQUALS`
  - `Authorization: Basic REVIEW_SECRET_BASIC`
  - `--password="prefix REVIEW_SECRET_QUOTED"`
  - `{'api_key': 'REVIEW_SECRET_DICT'}`
- Mỗi case được đưa qua command, `append_log`, `fail`, `export`; test quét toàn bộ file export và xác nhận credential synthetic không còn trong manifest/run.log/error/seal.
- Thêm negative over-redaction test cho metadata khoa học thông thường.
- Bundled Python với `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`: chạy trực tiếp 17 test functions bằng shim tối thiểu chỉ cung cấp `pytest.raises`: **17 passed**, exit code 0. Đây là fallback do runtime thiếu pytest, không phải lượt pytest chính thức.
- Direct sanitizer reproducer cho cả bốn dạng trên, thêm lowercase Authorization và JSON double-quoted key: **PASS**; ordinary scientific metadata giữ nguyên.
- `powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1`: **PASS**, exit code 0; 50 tasks, 198 links, 50 model routes, 18 sessions; board lúc chạy `DONE=8`, `IN_PROGRESS=2`, `TODO=36`, `DEFERRED=4`.
- Snapshot mới: runner SHA-256 `96D902B08CF7877D3869DA49BD8F14631C69FBA372FB832F9056758116623EC9`; test SHA-256 `2B9DB25A1F1A2A666659C410185A02FA1DF34024F8AAF5BC5D835AA6DB051B02`.

## Bàn giao

- Pytest chính thức vẫn chưa chạy được trong bundled runtime vì package `pytest` không có; reviewer/coordinator cần chạy lại trong dev environment trước closeout.
- Chỉ sửa `src/scholargraph/evaluation/runner.py`, `tests/unit/test_run_integrity.py` và log này; không sửa shared board/state/HANDOFF/registry.
- Kết thúc worker lúc `2026-09-15T22:10:37+07:00`; đề xuất re-review đúng snapshot hashes trên và không tự chuyển task DONE.
