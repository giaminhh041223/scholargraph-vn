# EXT-01C Packet W0 R2 (GEMINI)
- Task / Status: EXT-01C (W0 R2) | Trạng thái: REVIEW (chờ coordinator chạy test và MUSE review).
- Sửa validator tests/fixtures/public_search/gemini/validate_fixtures.py: parse wire JSON bằng model_validate_json; leakage check boundary thật bắt buộc fail; 5 negative cases chạy CLI qua subprocess (exit code 1); duyệt dynamic toàn bộ nodes/subcases và báo unrecognized/missing; bỏ hoàn toàn .get() mặc định.
- Files đã sửa: docs/public_search/UX_SPEC.md, tests/fixtures/public_search/gemini/{validate_fixtures.py, ux_examples.sidecar.json}, management/public_search/logs/GEMINI/SESSION-20260930-W0-GEMINI-EXT-01C-R2.md, management/public_search/packets/GEMINI/EXT-01C-R2.md.
- Lệnh kiểm chứng chuyển coordinator (NOT_RUN do headless command denial):
  python tests/fixtures/public_search/gemini/validate_fixtures.py
- Limitation: Không tự claim PASS/COMPLETED do chưa có kết quả chạy thật từ shell; giữ nguyên contract source của SOL; chờ coordinator kiểm chứng.
