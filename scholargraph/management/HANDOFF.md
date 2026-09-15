# Bàn giao ScholarGraph

NEXT_TASK: SG-008

## Trạng thái — 2026-09-15T22:58:03+07:00

- SG-007 **DONE**: runner, provenance, resume, export và terminal integrity đã nghiệm thu; F1/F2/F3/F4 được reviewer độc lập đóng trên snapshot cuối.
- SG-000 đến SG-007, SG-009, SG-013 DONE. SG-008 vẫn TODO, chưa triển khai evaluator trong phiên này.
- Phiên coordinator SESSION-20260915-019 hoàn tất. Không còn active assignment.
- Tiếp nhận hợp lệ từ task ứng dụng đã idle và worker018 đã bàn giao; không chiếm việc dựa vào tuổi timestamp.
- Các checkpoint sửa SG-007 trước đây được giữ trong logs011/012/015/018 và các review cũ; xem [log closeout](logs/SESSION-20260915-019.md) để có kết quả cuối.

## Bằng chứng SG-007

- [Runner](../src/scholargraph/evaluation/runner.py), [kiểm thử](../tests/unit/test_run_integrity.py), [hướng dẫn](../docs/RUNNER_GUIDE.md).
- [Fresh-context review cuối](reviews/SG-007-CLOSEOUT-REVIEW-20260915.md): PASS ở mục re-review cuối; phần CHANGES_REQUIRED phía trên là lịch sử snapshot cũ.
- [Smoke report](../artifacts/reports/sg007_smoke_20260915.json): 9/9 PASS; hai run COMPLETED/FAILED và exports còn ở artifacts/runs, có manifest SHA-256. Tất cả synthetic, không phải kết quả benchmark.
- Pytest chính thức toàn bộ suite: **78 passed in 21.81s**. Reviewer chạy riêng integrity: **23 passed in 17.77s**, thêm 4 whitespace probes và 4 freeze mutations PASS.
- Correction cuối tiêu thụ whitespace LF/CRLF quanh explicit credential delimiter/value, tránh lưu secret qua command, metadata, log, error và export.
- Môi trường .venv riêng dùng system-site-packages để tái sử dụng runtime; phiên bản kiểm thử ghi trong report/hướng dẫn. Đây chưa phải môi trường tái lập đầy đủ cho toàn ứng dụng.
- Parser không cam kết phát hiện mọi secret tùy ý trong văn xuôi. Code provenance giữ khai báo caller; caller chịu trách nhiệm cung cấp snapshot thật.

## Bảo toàn đầu ra ngoài SG-007

- SG-009 DONE: official archive hashes và loader offline đã được phiên trước kiểm tra; 344 SCIDOCS abstract/text rỗng giữ nguyên để SG-010 audit.
- SG-013 DONE theo review cuối phiên trước; snapshot 2.000 works bất biến. openalex_pilot_correction.json thay riêng số venue sai: 1.627/2.000 (81,35%); không sửa raw snapshot.
- Các implementation/evidence SG-009/013 chưa commit từ phiên trước được giữ nguyên ngoài commit SG-007. Shared board lưu trạng thái hiện có; không suy từ board rằng các file này đã vào Git.
- Protocol v1 đã được người dùng duyệt, không đổi. Official deadline/rubric vẫn ở open questions.

## Bước tiếp theo khi được giao

1. Đọc SG-008 card/routing và protocol phần evaluator/tie handling.
2. Xác minh dependency SG-006/007 DONE và snapshot thật, sau đó claim SG-008 qua coordinator.
3. Kiểm chứng evaluator bằng golden fixtures và đối chiếu công cụ tham chiếu; không dùng smoke metric SG-007 làm chất lượng retrieval.
