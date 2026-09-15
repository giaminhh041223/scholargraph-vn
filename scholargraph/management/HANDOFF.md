# Bàn giao ScholarGraph

NEXT_TASK: SG-006

- Phiên: SESSION-20260915-008; múi giờ Asia/Saigon (UTC+07:00).
- SG-004: **DONE**. Project owner đã xác nhận “Duyệt protocol v1”, ghi nhận lúc 2026-09-15T17:40:52.6906333+07:00; hai artifact giữ đúng SHA-256 đã review PASS.
- SG-000/001/002/003/004/005: DONE. SG-006 đủ dependencies và đang TODO, chưa owner/session/claimed paths, chưa bắt đầu.
- Phiên coordinator C, support Sol High và reviewer Astra High đã hoàn tất; không còn active assignment hoặc file đang có worker sửa.

## Đầu ra và bằng chứng SG-004

- [Protocol v1](../docs/RESEARCH_PROTOCOL.md) và [JSON contract](../configs/protocol_v1.json): đủ RQ→data/labels/method/metric, split/candidates, primary comparisons/ablations, graph gate và pending freeze.
- A: BEIR text riêng; SciFact official train mang role internal dev, SCIDOCS dùng transfer config khóa trước test.
- B: warm-start citation holdout, mask dev/test và reverse trước features, cutoff graph theo năm; rerank cùng C100. Graph gate/years/data/model còn chờ downstream.
- C: một cấu hình dịch/encoder pin trước pool; chấm dev trước, giữ ba fixed methods, freeze trước test annotation. 30 query; upper bound 300 dev + 600 test = 900 cặp, khoảng 600 là dự trù chưa đo.
- JSON runnable=false: đây là design contract, không phải final run config hoặc bằng chứng SG-027 đã freeze.
- [Source audit dossier](reviews/SG-004-SOURCE-AUDIT.md): bản pre hữu ích để dựng khung; cần sửa linear nDCG, MRR/ties, temporal attribution, masking và pooling/statistics. Không có phép đo phần trăm thời gian tiết kiệm.
- [Review packet và hashes](reviews/SG-004-REVIEW-PACKET.md), [review cuối](reviews/SG-004-REVIEW-20260915.md): Astra High fresh-context review; vòng 1 có một P2 về C dev pool/tuning; đã sửa và re-review PASS, không còn P0–P2.
- [ADR-012](DECISIONS.md) đã accepted theo xác nhận project owner; [log phiên](logs/SESSION-20260915-008.md) ghi checks, lịch sử sửa và bằng chứng human approval.

## Kiểm tra đã chạy

- JSON parse/contract spot checks PASS; C pool bound khớp 300+600=900; 49 task records khác giữ nguyên.
- git diff --check exit 0; chỉ cảnh báo line endings.
- scripts/check_project.ps1 sau closeout: exit 0, 50 tasks/routes, 188 local links, 7 lanes, 7 registered sessions. Board: DONE=6, TODO=40, DEFERRED=4; next SG-006. Các kết quả REVIEW/193 links trước đó là checkpoint cũ có thật.
- Không chạy dataset, benchmark, evaluator parity hoặc graph pilot trong SG-004; các gate đã chỉ rõ task chịu trách nhiệm. Không có retrieval metric mới.

## Bước tiếp tục chính xác

1. SG-004 đã hoàn tất; không còn bước phê duyệt protocol đang chờ.
2. Task tiếp theo là SG-006 — Schema và interface. Khi được giao, đọc task card, protocol v1/JSON và kiểm tra file thực tế trước nhận owner/claimed paths.
3. Giữ final-run gates của SG-008/014/017/027/034; protocol design được duyệt không có nghĩa data/model/final test đã được freeze.
4. Chưa thực thi SG-006 hoặc backlog downstream trong phiên này.

## Bối cảnh còn hiệu lực

2 thành viên; target core 2026-10-31, tháng11 buffer; deadline/rubric/chính sách môn còn Q-001 chưa có nguồn. SG-003 DONE theo board và ADR-011 (hoạt động đọc sâu được owner miễn, không ghi là đã đọc); một số mô tả trạng thái trong artifact lịch sử SG-003 là tại thời điểm soạn.

CPU/Colab-T4 compute pilot SG-002 là feasibility trên fixture tổng hợp, không chứng minh retrieval quality hoặc chọn model cuối; xem log SESSION-20260915-005 và COMPUTE_PLAN. Cảnh báo NumPy/SciPy cần xử lý trước main experiments. Không có Python/GPU process ScholarGraph được quan sát đầu phiên; không khởi chạy run dài phiên này.

Tài liệu bài giảng untracked tại workspace root ngoài scope được giữ nguyên. Các thay đổi SG-004 chỉ nằm trong scholargraph/.
