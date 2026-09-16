# Mẫu bắt đầu một phiên chat

Điền task, role và phạm vi trước khi gửi. Người dùng chọn model/effort theo routing trong ứng dụng; prompt không tự đổi model. Phiên làm độc lập có thể kiêm coordinator + worker, nhưng phải ghi rõ và chắc chắn không có coordinator khác.

```text
Làm ScholarGraph VN trong D:/Web_mining_20261/scholargraph.
Task được giao: SG-NNN. Lane: C/R/D/M/P/W. Vai trò: coordinator / worker / coordinator+worker.
Model/effort khuyến nghị: tra management/model_routing.json cho đúng ID.
Phạm vi file được sửa: <đường dẫn cụ thể>; ngoài phạm vi này chỉ đọc.
Input/handoff: <đường dẫn log/artifact đã tồn tại>.

Đọc AGENTS.md, management/state.json, HANDOFF.md, tasks.json, model_routing.json,
chat_registry.json, task card tương ứng trong docs/TASKS.md và protocol/decision liên quan.
Xác minh dependencies và file thật trước khi làm. Không tự mở task/agent khác.
Nếu chưa được coordinator ghi owner/session/claimed_paths thì worker chỉ chuẩn bị
read-only và trả yêu cầu nhận task; không tự sửa shared board.

Thực hiện đúng acceptance của task. Không thay split/metric/phạm vi từ kết quả test.
Chạy kiểm tra phù hợp; ghi lệnh, kết quả thật, artifact và hạn chế.
Lưu log/packet vào đường dẫn riêng do coordinator giao. Nếu là coordinator+worker,
cập nhật registry/state/HANDOFF và chạy scripts/check_project.ps1 khi chốt phiên.
Nếu là worker, trả status đề xuất để coordinator cập nhật. Không tự claim DONE
khi còn review riêng hoặc human approval bắt buộc.

Cuối phiên giải thích cho hai người: thuật toán, một ví dụ, bằng chứng đúng,
một hạn chế và câu hỏi bảo vệ. Nêu bước tiếp theo có thể thực hiện.
Nếu không xác minh được model/effort thực tế, ghi unknown; không chép recommended
thành actual. Không tự thuê GPU, upload/public dataset hay nộp bài.
```

Để bắt đầu ngay với scope: điền SG-001, lane C, vai trò coordinator+worker, model GPT-5.6 Sol / High. Chỉ bắt đầu khi người dùng thực sự giao SG-001; mẫu này không tự khởi chạy task.
