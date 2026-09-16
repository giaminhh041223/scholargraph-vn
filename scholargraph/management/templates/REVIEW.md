# Mẫu giao review trong context mới

```text
Review ScholarGraph task SG-NNN ở D:/Web_mining_20261/scholargraph.
Lane V; vai trò reviewer. Model/effort: review_profile trong model_routing.json.
Artifact snapshot: <commit hoặc file list/hash>; worker đã ngừng sửa vùng review.
Đầu vào: task card, protocol/ADR, artifact/run thật và packet tại <đường dẫn>.
Output duy nhất được ghi: <review report riêng do coordinator giao>.

Không sửa implementation, shared board hoặc dữ liệu test. Không chỉ tin summary
của worker. Đọc acceptance rồi kiểm tra bằng chứng, công thức, split/leakage,
ID alignment, failure paths và reproducibility trong phạm vi task.
Có thể chạy kiểm tra không phá dữ liệu; chạy dài/compute phát sinh cần đúng scope.
Ghi test đã chạy, chưa chạy và giới hạn; findings phải có vị trí/reproducer/bằng chứng.
Đưa verdict PASS / CHANGES_REQUIRED / INSUFFICIENT_EVIDENCE.
PASS không thay thế human approval hoặc xác nhận nhãn người.
Nếu không có finding, nêu còn rủi ro gì; không tuyên bố bảo đảm đúng tuyệt đối.
```

## Report

- Review/session ID; reviewer và model/effort thực tế hoặc unknown:
- Task ID; snapshot/version được review:
- Acceptance và protocol đã đối chiếu:
- Kiểm tra đã chạy, kết quả và phần chưa kiểm:
- Findings: mức ảnh hưởng, artifact/vị trí, bằng chứng, sửa đề xuất:
- Verdict và hạn chế:
- Human approval còn cần:
- Re-review sau sửa: snapshot mới, vùng kiểm lại, kết quả:

Fresh-context AI review không phải nhãn người độc lập. Chỉ coi review xong khi có report thật; việc điền review_profile vào routing chưa phải đã review.
