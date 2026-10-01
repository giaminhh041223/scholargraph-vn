# EXT-06 W4 — Gate về evidence

Verdict: **PASS_EVIDENCE**, task EXT-06 DONE về kiểm chứng snapshot `5f16994`.

- Fresh SOL R3 [report](../SOL/EXT-06-W4-R3-099.md) xác minh đóng P1 R2; 8 delta tests PASS, hai reproducer collision CLI1 và không đổi input.
- Verifier thực chạy 7 adversarial cases PASS và kiểm 113/113 hashes read-only; operational FAIL nên CLI **1**.
- Evidence pilot: 16 canonical runs, 10 explicit OpenAlex success/cache và 6 two-source partial_failure, arXiv 4 timeout/2 quota, 0 two-source success. Giữ run failure, không silent fallback.
- Regression 523 PASS, helper schema 77 PASS; delta bổ sung 4 omission/collision và 4 hash corruption PASS. 33 primary core freeze files khớp.
- [Decision096](EXT-06-EVIDENCE-DECISION-096.md) quy định tách evidence completeness và operational status. Review xác nhận độ đầy đủ, không chứng nhận hai nguồn hoạt động.

Gate phát hành/merge: **PENDING** do two-source operational FAIL và human demo chưa xác nhận. EXT-07 chỉ audit code/evidence; EXT-08 chỉ chuẩn bị hướng dẫn/checklist. Không giảm scope một nguồn hoặc merge master.

Reconciliation sau gate: kiểm UI entry cho thấy link `/public` mở JSON readiness thay vì template. Giao sửa additive page/link + regression cho SOL helper trước snapshot W5; không đổi kết quả pilot/CLI/freeze đã khóa. Delta cần review W5 trước khi chốt tài liệu/demo.
