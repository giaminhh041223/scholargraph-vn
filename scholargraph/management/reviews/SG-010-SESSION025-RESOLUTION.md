# SG-010 — Kết quả review và sửa session025

## Kết luận kỹ thuật

Implementation, live audit và toàn bộ kiểm thử bản cuối **PASS**. Reviewer context riêng đã thông báo **PASS**, không còn finding mở; kết luận chi tiết nằm trong `SG-010-SESSION025-REVIEW.md`. Không thay đổi raw benchmark hoặc mở lại SG-008/SG-011.

## Các lỗi đã xử lý

| Mức | Phát hiện | Sửa và bằng chứng |
|---|---|---|
| P1 | File/split thiếu hoặc parse lỗi vẫn sinh số 0 và nhóm rỗng như đã đo; phép đo phụ thuộc có thể báo orphan dựa trên universe chưa đọc được | Schema2 dùng FAIL/error và `null`; required split luôn có entry. Các ca missing/malformed CLI kiểm tra exit1, JSON FAIL và measurements null |
| P1 | Positive self-qrel và ID whitespace có thể đi qua CLI với exit0 | Gate positive self, parser ID strict không trim/coercion; subprocess hồi quy đã tái hiện và sau sửa đều exit1 |
| P2 | Sai kiểu title/text có thể bị coi là missing; raw qrel audit chưa tự chặn score ngoài biên | Validation ngay raw parser; chặn score ngoài0/1/2, invalid JSON types, duplicate JSON key và NaN; title-only/text-only hợp lệ vẫn giữ |
| P2 | Thống kê positive-per-query bỏ query toàn nhãn0 | Tập thống kê gồm mọi query có qrels trong split; fixture `[2,0]` có count2, mean1, std1 |
| P2 | Narrative suy provenance từ corpus counts, nhận đã kiểm chứng indexing; chi tiết text overlap có thể mất các cặp cùng nội dung và thứ tự không ổn định | Không suy official provenance từ số liệu, Data Card nêu giới hạn; overlap chuẩn hóa strip/casefold, enumerate mọi cặp và sắp ổn định |
| P1 | Output tùy chọn chưa bảo vệ raw khỏi bị ghi đè | Từ chối path trong raw và hardlink alias; giữ bytes cũ, CLI1. Hash before/after và file inventory phát hiện raw đổi trong audit |
| P2 | Reviewer phát hiện narrative gọi abstract “empty string” khi key thiếu/null | Sửa “missing, null or blank”; thêm4 CLI cases missing/null/whitespace/empty, review lại PASS |

Các phép đo không có dữ liệu trả null; query đã đo có0 positive vẫn là quan sát thật. Counter `.get(q, 0)` chỉ áp dụng cho tập qrels đã parse/kiểm tra, không che file/split bắt buộc bị thiếu. Không có metric retrieval hoặc benchmark mới được đo trong phiên này.

## Lệnh kiểm chứng bản cuối

Từ ScholarGraph, môi trường `.venv`:

```powershell
.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp=artifacts/runs/SG010-FINAL-025
$env:PYTHONPATH='src'
.venv/Scripts/python.exe -B -m scholargraph.ingest.beir_audit data/raw/beir artifacts/reports/beir_data_audit.json
```

- Full suite: **214 passed in 70.31s**, exit0.
- Reviewer targeted: **74 passed in 60.39s**, được reviewer báo; parent không nhận đây là command parent đã chạy.
- Parent adversarial bản cuối: **49 passed in 23.03s**, exit0.
- Live CLI: **PASS**, exit0; 5.183 SciFact docs, 25.657 SCIDOCS docs,344 SCIDOCS missing abstracts,115 có positive qrel. 9 file raw trước/sau có SHA256 giống nhau.
- Final auditor SHA256: `1c512293fa6670b4451c60c42bec3794320de31ba7863e46ae11fafcd7168c6f`.
- Final report SHA256: `d4a94f0a5bd68a65f7be3b353592d826dad96c28470e49679ffb89154a39b8aa`.
- [Báo cáo máy đọc](../../artifacts/reports/beir_data_audit.json), [Data Card](../../docs/DATA_CARD.md), [packet snapshot](SG-010-SESSION025-PACKET.md), [log](../logs/SESSION-20260916-025.md).
- Bản báo cáo trước sửa được lưu tại `artifacts/reports/sg010_pre_session025.json`; lịch sử findings cũ không bị viết lại.

## Giới hạn

PASS xác nhận phạm vi data audit SG-010 và các tests đã chạy, không chứng minh toàn bộ pipeline không có leakage. Text overlap trong dữ liệu nguồn được báo để split policy xử lý trước tuning; shared relevant document giữa splits không phải query leakage. Report version2 yêu cầu caller đọc status trước measurements. Không sửa implementation của loader SG-009 hoặc evaluator SG-008 trong phiên này.
