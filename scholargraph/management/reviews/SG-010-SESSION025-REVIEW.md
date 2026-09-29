# SG-010 — Review độc lập session025

## Verdict: PASS

- Reviewer `/root/sg008_fresh_review`, lane V; chưa tham gia implementation SG-010. Tên agent được tái sử dụng từ phiên khác, không mở lại SG-008.
- Ngày 2026-09-16, UTC+07:00. actual_model: null; actual_reasoning: null (chưa xác minh runtime).
- Đã đọc AGENTS mới, task card, ADR-013, Protocol A1, packet, auditor, hai bộ tests và DATA_CARD thực tế. Review cả bản dirty hiện tại; không sửa source/shared board.
- Một finding P2 được phát hiện và đã sửa, kiểm lại PASS. Không còn findings mở trong phạm vi này.

## Finding và xử lý

**F1 [P2] — Narrative suy sai kiểu dữ liệu raw khi thiếu key text — RESOLVED.** Trên bản auditor trước correction, tài liệu `{"_id":"d1","title":"Alpha paper","synthetic":true}` được chấp nhận đúng là title-only, nhưng explanation nói `abstract/text is empty string` dù raw không có key text. Probe CLI trả 0, report PASS: [bằng chứng trước sửa](../../artifacts/runs/SG010-REVIEW025-probe1428/missing_text_report.json). Điều này vi phạm narrative 1:1 theo ADR-013. Parent đổi wording thành `abstract/text is missing, null or blank` và thêm bốn regression cases cho key thiếu, null, whitespace và chuỗi rỗng; reviewer chạy lại cả bốn trong suite 74 tests, PASS.

## Bằng chứng reviewer thực thi

Working directory: `D:/Web_mining_20261/scholargraph`.

```powershell
.venv/Scripts/python.exe -B -m pytest tests/unit/test_beir_audit_adversarial.py tests/unit/test_data_integrity.py -q -p no:cacheprovider --basetemp=artifacts/runs/SG010-REVIEW025-142758
```

**74 passed in 60.39s**, exit 0, trên source/tests hashes cuối bên dưới. Tests dùng fixture tạm và subprocess CLI; bao phủ missing/empty/malformed resources, required splits, strict IDs/types/scores, duplicate JSON fields, self positives, ID leakage, title-only/text-only, zero-positive statistics, deterministic all-pair overlap, raw output guard và live audit/Data Card checks.

Probes riêng chạy qua PowerShell here-string vào `.venv/Scripts/python.exe -B -`, dùng import path `src`:

- Thiếu key `text`: tái hiện F1 như trên. Lần thử đầu thiếu import path gây `ModuleNotFoundError` trước tạo fixture; sửa import và chạy lại thành công.
- Wrapper tạm quanh `audit_single_dataset` chèn file **synthetic** giữa hai lần hash: `audit_passed=false`, `unchanged_during_audit=false`, error ghi raw changed. [Report](../../artifacts/runs/SG010-REVIEW025-raw1429/mutated.json).
- Output hardlink tới corpus synthetic: CLI trả **1**, stderr có `aliases a raw benchmark file`, raw bytes không đổi. Không chạm raw benchmark thật trong probes.
- Đọc report chính, kiểm source digest và hash lại **9 raw files**: khớp cả before/after. So JSON với [report live từ reviewer](../../artifacts/runs/SG010-REVIEW025-142758/live_audit0/beir_data_audit.json): **bằng nhau hoàn toàn trừ `audit_timestamp`**. Lần đọc thường không truy cập được thư mục pytest elevated; chạy lại read-only elevated thành công, không coi lỗi quyền là lỗi dữ liệu.

Parent báo full suite cuối **214 passed in 70.31s**, exit 0; đây là bằng chứng coordinator, không phải lệnh reviewer chạy. Reviewer không chạy lại full suite.

## Đánh giá contract

- Missing/parse failure có structured FAIL/error, phép đo và dependency không khả dụng là null. Zero chỉ dùng cho quan sát đã đo, gồm query có toàn nhãn 0.
- Gate tổng hợp kiểm required split, duplicate/orphan/conflict, positive self-qrel, missing cả title/text và loader failure; CLI dữ liệu lỗi trả 1, không silently chuyển thành PASS.
- Overlap phân biệt shared corpus với query leakage; query-ID collision FAIL, normalized text overlap là anomaly có mọi cặp sắp thứ tự cố định. Không suy provenance từ count.
- Số liệu Data Card về corpus/query/qrels, token statistics, hai cặp text overlap và phân rã SCIDOCS 344/115/229 docs, 187/279/466 pairs khớp report/live tests. Các đoạn giới hạn downstream không nhận audit dữ liệu là bằng chứng ranker không leakage hoặc index đã đúng.
- Raw được kiểm hash trước/sau và output không được trỏ vào raw kể cả hardlink. Không lọc benchmark để thay đổi kết quả audit.

## Snapshot cuối đã xác minh SHA-256

| File | SHA-256 |
|---|---|
| `src/scholargraph/ingest/beir_audit.py` | `1c512293fa6670b4451c60c42bec3794320de31ba7863e46ae11fafcd7168c6f` |
| `tests/unit/test_data_integrity.py` | `77b29eb71d9f45edf20e294a7959de89f5c8b0aba33fcd295888c5c6a9257d98` |
| `tests/unit/test_beir_audit_adversarial.py` | `6dceb8057eff2f508a7dee903b18e2f404dc74c843cc855aab7cc84919f0eb30` |
| `docs/DATA_CARD.md` | `0d0f0b11716df06d731f7e29f1e69de3f4c2ff12d451890486c02556f70f147b` |
| `artifacts/reports/beir_data_audit.json` | `d4a94f0a5bd68a65f7be3b353592d826dad96c28470e49679ffb89154a39b8aa` |

Snapshot ban đầu thay đổi có thông báo: trim whitespace, rồi sửa F1 và thêm tests. Verdict chỉ áp dụng snapshot cuối, không nhận hashes cũ là bản được nghiệm thu. Chi tiết bàn giao tại [packet](SG-010-SESSION025-PACKET.md).

## Giới hạn/bàn giao

PASS cho acceptance audit SG-010 và các kịch bản đã kiểm, không bảo đảm mọi lỗi tương lai hoặc hoàn thành split/ranker gates downstream. Review bằng model không phải human approval; routing SG-010 không yêu cầu human gate. Coordinator đồng bộ board/log/HANDOFF và chạy `check_project.ps1` trước closeout.
