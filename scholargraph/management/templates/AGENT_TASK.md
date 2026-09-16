# Giao một task có thể tiếp nối

Task: SG-NNN
Owner/coordinator:
Lane; session/log/packet riêng được giao:
Model/effort chính và reviewer: tra model_routing.json, không tự coi là model thực tế.
Phạm vi file được sửa:
Dependency đã hoàn tất:
Input artifacts:
Tài liệu cần đọc: AGENTS.md, state.json, HANDOFF.md, model_routing.json, chat_registry.json, task card, protocol liên quan.
Output và acceptance: theo task card, bổ sung cụ thể nếu cần.

## Cách làm
- Đọc trạng thái/files trước; không suy ra input đã tồn tại từ plan.
- Worker chỉ sửa sau khi coordinator đã ghi owner/session/claimed_paths; thiếu phân công thì chuẩn bị read-only. Không tự sửa shared board.
- Làm module trong phạm vi đã được phân công.
- Nếu nhiều agent cùng làm: coordinator giữ board/state/HANDOFF; agent ghi log riêng và trả summary thay đổi/evidence. Không cùng sửa file hoặc tự nhận task của phiên khác.
- Ghi lệnh kiểm tra đã chạy, kết quả, hạn chế và bước tiếp theo.
- Không claim benchmark tốt nếu chưa đo; không dùng nhãn test làm feature.
- Cuối task giải thích ngắn thuật toán, một ví dụ, một lỗi và nội dung con người cần nắm.

## Bàn giao bắt buộc
Task status đề xuất:
Files/artifacts:
Verification:
Quyết định/assumptions:
Việc còn dở:
Next executable step:
Thông tin cần coordinator cập nhật:
Review/human gate còn thiếu; model/effort thực tế hoặc unknown:

Mẫu này không tự tạo agent/task và không thay thế quyền truy cập công cụ. Dùng khi người dùng giao triển khai hoặc phân công agent.
