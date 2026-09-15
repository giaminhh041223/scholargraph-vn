# Bàn giao ScholarGraph

NEXT_TASK: SG-004

- Phiên hiện tại: SESSION-20260915-007; SG-003 DONE, SG-004 đã mở dependency nhưng chưa bắt đầu.
- Múi giờ: Asia/Saigon, UTC+07:00.
- Giai đoạn: M1 — sẵn sàng nhận SG-004, protocol nghiên cứu v1.

## Bối cảnh đã chốt

ScholarGraph VN có 2 thành viên, dùng agent hỗ trợ triển khai, mục tiêu hoàn thành core trước 2026-10-31 và giữ tháng 11 làm buffer. GPU dùng Kaggle/Colab; chỉ thuê khi pilot của model cuối chứng minh cần thiết. Deadline/rubric chính thức của môn vẫn chưa được cung cấp.

## Trạng thái chính

- SG-000, SG-001, SG-002, SG-003 và SG-005: DONE.
- SG-003: ma trận 12 primary sources và BibTeX đã qua fresh-context artifact review, không có finding P0–P2. Project owner miễn hoạt động hai thành viên đọc sâu ba paper; deviation ghi tại ADR-011. Không ghi rằng hoạt động đọc đã hoàn tất.
- CPU pilot SG-002: 1.000 fixture tổng hợp, MiniLM, batch 8, 21,99 giây, 45,48 docs/s.
- Colab pilot SG-002: Tesla T4 15.360 MiB, batch 32, 0,9385 giây, 1.065,48 docs/s, peak allocated/reserved khoảng 243,6/292 MiB.
- CPU và GPU dùng cùng input hash và model revision. Cả hai file embedding khớp SHA-256 trong report; GPU nhanh hơn khoảng 23,43 lần.
- Đây là compute feasibility, không phải retrieval-quality evidence. Model cuối tại SG-017 phải pilot lại.
- Không có bằng chứng cần thuê GPU ở thời điểm hiện tại.
- Bộ test SG-002 trước đó: 6/6 pass; không chạy lại trong SG-003 vì chỉ sửa tài liệu/điều phối. Kết quả checker SG-003 ghi tại log phiên 006.

## Task tiếp theo

1. SG-004 — Protocol nghiên cứu v1 hiện TODO và đã đủ dependency từ SG-001 + SG-003.
2. Chưa nhận task, chưa gán owner/session/claimed paths và chưa sửa protocol.
3. Khi người dùng giao thực hiện, coordinator nhận SG-004 theo task card rồi mới bắt đầu.

Không có active assignment. Không thay đổi scope/protocol hoặc tuyên bố thuật toán mới/SOTA. TextTAGC chỉ được kiểm tra abstract/metadata, không full text.

## Tệp cần đọc

- [Tổng quan và lịch đọc SG-003](../docs/RELATED_WORK.md)
- [Thư mục trích dẫn](../docs/references.bib)
- [Gói review SG-003 và prompt](reviews/SG-003-REVIEW-PACKET.md)
- [Báo cáo review SG-003](reviews/SG-003-REVIEW-20260915.md)
- [Nhật ký SG-003](logs/SESSION-20260915-006.md)
- [Nhật ký closeout](logs/SESSION-20260915-007.md)
- [Quyết định và deviation](DECISIONS.md)
- [Master plan](../docs/MASTER_PLAN.md)
- [Task cards](../docs/TASKS.md)
- [Research protocol](../docs/RESEARCH_PROTOCOL.md)
- [Model từng ID](../docs/TASK_MODEL_MATRIX.md)
- [Chiến lược chat](../docs/MODEL_AND_CHAT_STRATEGY.md)

## Lưu ý vận hành

- Cache Hugging Face và embedding `.npy` không commit; hai report JSON CPU/GPU được giữ làm bằng chứng.
- Python local có cảnh báo NumPy 2.4.6/SciPy không tương thích; khóa environment trước thí nghiệm khoa học chính thức.
- Không có run/GPU process ScholarGraph đang chạy.
- SG-004 chỉ được mở trên board; chưa có công việc implementation nào được thực hiện.
