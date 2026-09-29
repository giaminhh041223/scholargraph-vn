# SG-010 — Review bản sửa session025

- Snapshot: 2026-09-16T14:23:56+07:00; user giao review và sửa ngay nếu lỗi.
- Auditor/tests frozen; parent chỉ đang chạy full suite, tạo report chính mới và cập nhật management. Không sửa implementation trong review.
- Task card SG-010 và ADR013/AGENTS mới là tiêu chuẩn. Đọc DATA_CARD §6.1 contract schema2.
- Targeted:70 tests PASS in47.61s. Live/full suite đang chạy, parent sẽ gửi kết quả.
- Lỗi đã sửa: missing/malformed null; strict types/IDs/scores và duplicate JSON keys; self positive; statistics include zero positives; overlap every pair/deterministic; provenance không dựa count; raw output protection và before/after hashes.
- Không sửa raw/SG009 loader/SG008/SG011. Preexisting SG010 dirty được giữ làm baseline và sửa tiếp.

| File | SHA256 |
|---|---|
| `src/scholargraph/ingest/beir_audit.py` | `1c512293fa6670b4451c60c42bec3794320de31ba7863e46ae11fafcd7168c6f` |
| `tests/unit/test_data_integrity.py` | `77b29eb71d9f45edf20e294a7959de89f5c8b0aba33fcd295888c5c6a9257d98` |
| `tests/unit/test_beir_audit_adversarial.py` | `6dceb8057eff2f508a7dee903b18e2f404dc74c843cc855aab7cc84919f0eb30` |
| `docs/DATA_CARD.md` | `0d0f0b11716df06d731f7e29f1e69de3f4c2ff12d451890486c02556f70f147b` |

## Nhiệm vụ reviewer
- Kiểm tra snapshot implementation và adversarial/API/CLI contract, tìm bypass cụ thể; chạy targeted/probes nếu cần. Không sửa source hoặc report chính.
- Chỉ ghi management/reviews/SG-010-SESSION025-REVIEW.md và management/logs/SESSION-20260916-025-REVIEW.md; ghi verdict, findings, hashes, commands/results thực tế.
- Phép đo lỗi phải null; count0 hợp lệ chỉ là quan sát đã đo. Text-only/title-only không bị loại nếu field còn lại thật. Upstream text overlap được ghi nhận, không tự fail thay policy SG011; ID overlap phải fail.

## Kiểm chứng hoàn tất — 2026-09-16T14:25:59+07:00
- Full suite:210 passed in76.89s; live audit PASS,9 raw files không đổi hashes before/after.
- Chỉ trim trailing whitespace auditor/tests sau kiểm tra; không đổi thuật toán. Hashes ở bảng đã cập nhật, báo cáo live được tái sinh để pin đúng code hash.

## Sửa finding reviewer P2
- Narrative title-only đổi thành missing/null/blank, không suy raw text là chuỗi rỗng. Thêm4 CLI cases: thiếu field/null/whitespace/empty. Bảng hashes đã cập nhật.
