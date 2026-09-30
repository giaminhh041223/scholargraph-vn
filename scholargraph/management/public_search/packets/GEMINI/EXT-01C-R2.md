# EXT-01C Packet W0 R2 (GEMINI)
- Task / Status: EXT-01C (W0 R2) | Trạng thái: REVIEW (chờ coordinator chạy test và MUSE review).
- Sửa validator tests/fixtures/public_search/gemini/validate_fixtures.py: 13 typed objects; vá 3 bypasses; khớp 1:1 contract_type/payload; đẳng thức coverage; recursive leakage check + benign text positive; mutate actual RankedHit.score; 16 negative cases CLI qua subprocess (exit code 1); bắt buộc --sidecar.
- Provenance sidecar ux_examples.sidecar.json: checkpoint 2026-09-30T10:05:00+07:00, SOL head cb64c59, commit 774aeef, v1.0.0, không tự tạo hash.
- Files đã sửa: docs/public_search/UX_SPEC.md, tests/fixtures/public_search/gemini/{validate_fixtures.py, ux_examples.sidecar.json, ux_examples.json}, management/public_search/logs/GEMINI/SESSION-20260930-W0-GEMINI-EXT-01C-R2.md, management/public_search/packets/GEMINI/EXT-01C-R2.md. Tệp R1 giữ nguyên.
- Lệnh kiểm chứng chuyển coordinator (NOT_RUN theo chính sách native file tools): python tests/fixtures/public_search/gemini/validate_fixtures.py --sidecar tests/fixtures/public_search/gemini/ux_examples.sidecar.json
- Limitation: Không tự claim PASS/COMPLETED; không chạy shell command; hợp đồng SOL giữ nguyên READ-ONLY.
