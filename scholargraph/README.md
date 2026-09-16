# ScholarGraph VN

Hệ thống tìm kiếm bài báo khoa học và gợi ý tài liệu liên quan, kết hợp truy xuất từ khóa, biểu diễn ngữ nghĩa và thông tin trích dẫn.

**Trạng thái:** đã thiết lập hồ sơ kế hoạch và quy trình tiếp nối. Mã nguồn ứng dụng, dataset, index và benchmark chưa được triển khai trong lần thiết lập này.

## Đọc theo nhu cầu

| Nhu cầu | Tài liệu |
|---|---|
| Hiểu phạm vi, thời gian, yêu cầu | [MASTER_PLAN](docs/MASTER_PLAN.md) |
| Xem scope và yêu cầu chấm đang chờ duyệt | [SCOPE](docs/SCOPE.md), [RUBRIC_MAP](docs/RUBRIC_MAP.md) |
| Làm một task cụ thể | [TASKS](docs/TASKS.md) |
| Chọn model cho từng ID | [Bảng 50 task → model](docs/TASK_MODEL_MATRIX.md), [routing JSON](management/model_routing.json) |
| Chia chat và chuyển context | [Chiến lược model/chat](docs/MODEL_AND_CHAT_STRATEGY.md), [mẫu bắt đầu](management/templates/CHAT_START.md) |
| Biết việc nào đang làm và việc tiếp theo | [state.json](management/state.json), [HANDOFF](management/HANDOFF.md) |
| Tra cứu trạng thái từng task | [tasks.json](management/tasks.json) |
| Quy tắc cộng tác | [AGENTS](AGENTS.md) |
| Đánh giá học thuật | [RESEARCH_PROTOCOL](docs/RESEARCH_PROTOCOL.md) |
| Thiết kế kỹ thuật và dữ liệu | [ARCHITECTURE](docs/ARCHITECTURE.md) |
| Quyết định và lý do | [DECISIONS](management/DECISIONS.md) |
| Nguồn gốc benchmark và tài liệu | [SOURCES](docs/SOURCES.md) |
| Nhật ký từng phiên | [logs/README](management/logs/README.md) |

## Bắt đầu một phiên tiếp nối

Mở đúng workspace và giao một phạm vi cụ thể, ví dụ: “Tiếp tục ScholarGraph từ HANDOFF, thực hiện SG-001.”

Người thực hiện đọc AGENTS, state, HANDOFF, task card; xác minh đầu vào; nhận task; làm việc; kiểm tra; ghi nhật ký và bàn giao. Các file này lưu kiến thức giữa các phiên; chúng không tự khởi chạy công việc nền.

Tra task và model mà không sửa trạng thái: `scripts/get_task_brief.ps1 -TaskId SG-001`. Thường dùng một chat điều phối, một worker và một reviewer khi cần. Routing không tự chọn model/mở chat trong ứng dụng; coordinator là bên duy nhất ghi shared board khi có nhiều phiên.

## Kiểm tra tính nhất quán

Từ thư mục `scholargraph`, chạy trong PowerShell:

```powershell
.\scripts\check_project.ps1
```

Trình kiểm tra chỉ đọc: xác minh ID, dependency, trạng thái, bằng chứng hoàn thành, con trỏ bàn giao, routing đủ 50 task, lane/session và liên kết Markdown nội bộ. Nó không chứng minh mô hình đúng hoặc xác nhận model thực tế trong ứng dụng; kiểm thử thuật toán nằm trong các task triển khai.

## Giới hạn của bản kế hoạch

Thông tin người dùng đã xác nhận: còn khoảng 7 tuần, 2 thành viên, agent hỗ trợ phần lớn triển khai, GPU qua Kaggle/Colab. Kế hoạch dự trù 12–15 giờ/người/tuần để đọc hiểu, điều phối, gán nhãn và kiểm tra; mức thời gian này cần hai bạn cân đối. Chưa có rubric chính thức trong phần tài liệu đã kiểm tra. Mục tiêu A+ phụ thuộc yêu cầu giảng viên và chất lượng thực hiện.

Không có kết quả mô hình nào được công bố ở giai đoạn này.
