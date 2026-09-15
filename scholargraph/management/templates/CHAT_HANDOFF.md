# Packet bàn giao giữa hai phiên

- Session ID / lane / task IDs:
- Vai trò và owner; coordinator nhận:
- Model/effort khuyến nghị:
- Model/effort thực tế và cách xác minh (unknown nếu không biết):
- Thời điểm checkpoint, timezone:
- Trạng thái đề xuất: checkpoint / REVIEW / DONE / BLOCKED:
- Phạm vi được giao và phạm vi đã làm:

## Đầu vào đã xác minh

- Task dependencies thực sự DONE:
- Code version / commit hoặc file hash quan trọng:
- Dataset/config/model revision/run ID:
- Protocol/ADR áp dụng:

## Đầu ra và kiểm tra

| Artifact hoặc thay đổi | Đường dẫn | Lệnh/kiểm tra thật | Kết quả/exit code |
|---|---|---|---|

## Chưa xong

- Failure/reproducer cụ thể:
- Giả thuyết đã thử và kết quả:
- Việc chưa kiểm tra/chưa đo:
- Review report và findings còn mở:
- Human gate: cần ai duyệt; xác nhận thật đã có hay chưa:

## Tiếp tục

- Bước tiếp theo chính xác (không chỉ “làm tiếp”):
- File cần đọc, không dán toàn bộ log/dataset:
- Process/notebook còn chạy: run ID, nơi checkpoint, ai quản lý; none nếu không có:
- File còn đang được sửa; ai được tiếp nhận:
- Đề nghị coordinator cập nhật board/state/assignment:

## Gói hiểu bài

- Thuật toán bằng lời thường và một ví dụ:
- Bằng chứng đáng tin nhất:
- Một hạn chế và một câu hỏi bảo vệ:

Mục tiêu khoảng 400–800 từ nếu đủ; log dài dẫn bằng đường dẫn. Worker lưu packet riêng, không ghi đè management/HANDOFF.md của coordinator.
