# SG-004 — gói review artifact v1

- Coordinator/session: SESSION-20260915-008; task SG-004, lane C/R.
- Snapshot: danh sách file + SHA-256 dưới đây; worker ngừng sửa các file này trong lượt review.
- Acceptance nguyên gốc: mỗi RQ có data/labels/method/metric; ranh giới dev/test rõ. Phải có A/B/C, split/candidates/primary comparisons/ablations, graph gate và phần chờ freeze.
- Đầu ra chính: docs/RESEARCH_PROTOCOL.md và configs/protocol_v1.json.
- Source audit chỉ kiểm chứng dossier, không thay final artifact review.

## Snapshot đầu vào

| File | SHA-256 |
|---|---|
| docs/RESEARCH_PROTOCOL.md | 337EC1560E2C71CB945966D17942461EE0F5A0B406598FA72BDFBE3107451A7D |
| configs/protocol_v1.json | B846901DF6E65EB76B2DA9B25DA2EAAA71AEC9B652972497D6FD36BF7F29976F |

## Phạm vi reviewer

Đọc AGENTS, task card SG-004, scope, ADR-012 và artifact thật; kiểm tra doc/JSON khớp, thiết kế metric/split/graph leakage/label access, freeze/tuning và feasibility. Tìm lỗi có tác động thay vì yêu cầu triển khai task downstream ngay. Không chỉnh implementation hoặc shared board. Output duy nhất: management/reviews/SG-004-REVIEW-20260915.md.

Review_mode=fresh_context_required, review profile A_H (Astra High). Nêu model/effort được công cụ lựa chọn và giới hạn introspection; không suy model từ persona. Verdict PASS/CHANGES_REQUIRED/INSUFFICIENT_EVIDENCE; mỗi finding có severity, vị trí và cách sửa. PASS không thay human approval.

## Tự kiểm của worker

- PowerShell ConvertFrom-Json nạp thành công; đã kiểm runnable=false, 5 primary comparisons, linear gain và upper bound pool 900.
- git diff --check: exit 0, chỉ cảnh báo chuyển line endings.
- scripts/check_project.ps1: exit 0; 50 tasks/routes, 193 local links, 7 lanes, 6 sessions; SG-004 IN_PROGRESS tại thời điểm kiểm tra.
- Chưa chạy dataset/benchmark hoặc executable evaluator parity; các phần đó thuộc SG-008 trở đi và được đánh dấu pending rõ.

## Gate sau review

Sau sửa findings: kiểm lại snapshot ảnh hưởng. Project owner còn phải xác nhận protocol cụ thể theo AGENTS §3 vòng đời task và model_routing SG-004 human_approval_required=true. Chỉ khi có xác nhận thật mới DONE; chưa bắt đầu SG-006.

## Snapshot sửa P2 để re-review

Vòng 1 CHANGES_REQUIRED với một P2 về C dev pooling/tuning. Đã sửa theo phương án giữ ngân sách: một translation/encoder config trước pooling, chấm dev trước test, chọn default trong ba fixed methods và giữ primary comparison. Upper bound tách 300 dev + 600 test = 900; mở grid cần ADR/ngân sách riêng. Chỉ thêm đổi URL trec_eval master→main (cùng nguồn redirect).

| File | SHA-256 mới |
|---|---|
| docs/RESEARCH_PROTOCOL.md | 90E6B80F5C54B8A4BC445FAFFAACA9D7174F9024CB551FEB9CC86E489B093351 |
| configs/protocol_v1.json | 8B9BE0EA50C79462B6736DB5C392EAD093A4F7F78732914902E1EE81D9B02306 |

Giữ snapshot này trong lượt re-review. Các hash lượt 1 giữ ở trên để truy lịch sử; verdict mới phải chỉ rõ snapshot mới.
