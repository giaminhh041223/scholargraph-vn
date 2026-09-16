# SESSION-20260915-012-RUNNER-FIX

- Bắt đầu: 2026-09-15T21:52:00+07:00.
- Worker: `/root/sg007_runner`; lane M.
- Task: SG-007 correction after fresh-context pre-review.
- Phạm vi: `src/scholargraph/evaluation/runner.py`, `tests/unit/test_run_integrity.py`, và log này.
- Must resolve only reproduced findings F1–F4 in `management/reviews/SG-007-009-PRECHECK-20260915.md`; do not modify control files or other modules.

## Correction đã thực hiện

- **F1 — final gate binding:** thay kiểm tra truthy bằng hai JSON evidence artifact có `path` + SHA-256 được xác minh thật. Freeze artifact phải có `status=FROZEN` và khớp track/method/dataset/split, resolved-config/data/split/model hashes, model ID/revision, evaluator revision. Leakage audit phải có `status=PASS` và khớp track/dataset/split/data/split hashes. Resolved config bắt buộc `resolved=true`, có track/dataset/split đúng run và không còn `unresolved_gates` hoặc `runnable=false`. Protocol requirement chưa được runner hỗ trợ bị từ chối.
- **F2 — credential redaction:** che trọn Authorization Bearer, Bearer đứng riêng, CLI `--api-key VALUE`/`--token VALUE`, dạng `key=value` hoặc `key: value`; áp dụng cho command, run log và failed error trước khi ghi/export.
- **F3 — integrity trước completion:** `complete()` gọi full registered-artifact verification trước khi đổi status/seal. Artifact bị sửa hoặc bị xóa giữ run ở `RUNNING`, không sinh seal terminal.
- **F4 — code provenance:** manifest giữ `code_provenance` có toàn bộ commit/dirty/source-reference metadata người gọi cung cấp và `source_digest` khớp `code_hash`; dữ liệu này được export cùng run.

## Regression tests

- Mở rộng `tests/unit/test_run_integrity.py` lên 15 tests; thêm tái hiện trực tiếp cho từng F1–F4:
  - F1: từ chối boolean placeholder, evidence file vắng, SHA-256 lệch, track/dataset/split lệch, unresolved config, audit không PASS; case evidence hợp lệ được nhận.
  - F2: quét mọi file sau failed run + export, xác nhận năm credential synthetic không tồn tại ở manifest/log/error/seal.
  - F3: tamper ranking và xóa per-query trước complete đều bị từ chối, status còn RUNNING và không có seal.
  - F4: commit, dirty flag, source snapshot và source digest còn nguyên sau complete/export.

## Kiểm tra đã chạy

- Bundled Python, `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`: chạy trực tiếp toàn bộ 15 test functions bằng shim tối thiểu chỉ cung cấp `pytest.raises`: **15 passed**, exit code 0. Đây là fallback vì runtime thiếu package pytest, không được ghi như pytest chính thức.
- Reproducer redaction đúng hai chuỗi của pre-review (`Authorization: Bearer ...`, `--api-key ...`): **PASS**, credential synthetic không còn trong output.
- `powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1`: **PASS**, exit code 0; 50 tasks, 198 Markdown links, 50 model routes, 15 sessions; board tại lúc chạy `DONE=8`, `IN_PROGRESS=1`, `REVIEW=1`, `TODO=36`, `DEFERRED=4`.
- Snapshot correction: runner SHA-256 `8641F1466A6779208A3966B5A8923EEDDBB74EDF6F5247235DBE6E627235EFCC`; test SHA-256 `BB2E59DEE0B4F39F23D44C5B0ED8786ED308FF51BEC3ED21C359CAD13D4342D5`.

## Hạn chế và bàn giao

- Pytest chính thức vẫn chưa chạy được trong bundled runtime do `No module named pytest`; coordinator/reviewer cần chạy `pytest tests/unit/test_run_integrity.py -q` trong dev environment có `requirements-dev.txt` trước closeout.
- Chỉ sửa `src/scholargraph/evaluation/runner.py`, `tests/unit/test_run_integrity.py` và log phiên này. Không sửa board/state/HANDOFF/registry hoặc module khác.
- Kết thúc worker lúc `2026-09-15T21:58:04+07:00`; đề xuất fresh-context re-review đúng snapshot hashes trên, không tự chuyển SG-007 sang DONE.
