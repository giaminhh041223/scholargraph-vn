# Nhật ký phiên làm việc

Tên file: `SESSION-YYYYMMDD-NNN.md`; một phiên một file.

- Dùng [mẫu SESSION](../templates/SESSION.md).
- Ghi task ID, owner, thời điểm, files, lệnh đã chạy và kết quả thật.
- Checkpoint có thể thêm vào cùng file trong phiên; khi chốt rồi, sửa sai bằng mục correction mới.
- Con trỏ log gần nhất nằm trong [state.json](../state.json).
- Việc tiếp tục nằm trong [HANDOFF](../HANDOFF.md).
- Log không chứa secrets hoặc raw dataset lớn.
- Registry không khóa tiến trình; phối hợp trước khi hai phiên sửa cùng file.
- Dùng thêm [mẫu packet](../templates/CHAT_HANDOFF.md) và [mẫu review](../templates/REVIEW.md) khi chuyển chat. Coordinator cấp tên file riêng để tránh ghi đè.
- Ghi lane, role, model/effort thực tế nếu xác minh được; không chép recommended thành actual. Worker không sửa shared HANDOFF/board.
