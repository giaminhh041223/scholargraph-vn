# Bàn giao ScholarGraph

NEXT_TASK: SG-003

- Phiên hiện tại: SESSION-20260915-006; SG-003 REVIEW, worker đã bàn giao artifact.
- Múi giờ: Asia/Saigon, UTC+07:00.
- Giai đoạn: M1 — chờ review riêng và xác nhận đọc paper của SG-003.

## Bối cảnh đã chốt

ScholarGraph VN có 2 thành viên, dùng agent hỗ trợ triển khai, mục tiêu hoàn thành core trước 2026-10-31 và giữ tháng 11 làm buffer. GPU dùng Kaggle/Colab; chỉ thuê khi pilot của model cuối chứng minh cần thiết. Deadline/rubric chính thức của môn vẫn chưa được cung cấp.

## Trạng thái chính

- SG-000, SG-001, SG-002 và SG-005: DONE.
- SG-003: có ma trận 12 primary sources, BibTeX, synthesis/giới hạn novelty, ví dụ RRF/PPR và lịch đọc cho hai người. Chưa có review report riêng; chưa xác nhận hoạt động đọc của hai thành viên.
- CPU pilot SG-002: 1.000 fixture tổng hợp, MiniLM, batch 8, 21,99 giây, 45,48 docs/s.
- Colab pilot SG-002: Tesla T4 15.360 MiB, batch 32, 0,9385 giây, 1.065,48 docs/s, peak allocated/reserved khoảng 243,6/292 MiB.
- CPU và GPU dùng cùng input hash và model revision. Cả hai file embedding khớp SHA-256 trong report; GPU nhanh hơn khoảng 23,43 lần.
- Đây là compute feasibility, không phải retrieval-quality evidence. Model cuối tại SG-017 phải pilot lại.
- Không có bằng chứng cần thuê GPU ở thời điểm hiện tại.
- Bộ test SG-002 trước đó: 6/6 pass; không chạy lại trong SG-003 vì chỉ sửa tài liệu/điều phối. Kết quả checker SG-003 ghi tại log phiên 006.

## Task tiếp theo

1. Review SG-003 ở context riêng theo prompt trong gói review; reviewer chỉ ghi report riêng, không sửa artifact/shared board. Chưa tạo reviewer hoặc phiên app mới.
2. Hai thành viên đọc RRF, SciRepEval và time-balanced centrality theo §7 của RELATED_WORK, bổ sung ghi chú hiểu bài. Không dùng AI review thay bằng chứng con người đọc.
3. Coordinator xử lý findings và cập nhật gate. Chỉ khi acceptance và review đạt mới chuyển SG-003 DONE rồi nhận SG-004 — Research questions/hypotheses. SG-004 hiện vẫn TODO, chưa đủ dependency.

Worker đã nhả claimed paths; không có active assignment. Không thay đổi scope/protocol hoặc tuyên bố thuật toán mới/SOTA. TextTAGC chỉ được kiểm tra abstract/metadata, không full text.

## Tệp cần đọc

- [Tổng quan và lịch đọc SG-003](../docs/RELATED_WORK.md)
- [Thư mục trích dẫn](../docs/references.bib)
- [Gói review SG-003 và prompt](reviews/SG-003-REVIEW-PACKET.md)
- [Nhật ký SG-003](logs/SESSION-20260915-006.md)
- [Master plan](../docs/MASTER_PLAN.md)
- [Task cards](../docs/TASKS.md)
- [Research protocol](../docs/RESEARCH_PROTOCOL.md)
- [Model từng ID](../docs/TASK_MODEL_MATRIX.md)
- [Chiến lược chat](../docs/MODEL_AND_CHAT_STRATEGY.md)

## Lưu ý vận hành

- Cache Hugging Face và embedding `.npy` không commit; hai report JSON CPU/GPU được giữ làm bằng chứng.
- Python local có cảnh báo NumPy 2.4.6/SciPy không tương thích; khóa environment trước thí nghiệm khoa học chính thức.
- Không có run/GPU process ScholarGraph đang chạy.
