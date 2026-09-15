# Bàn giao ScholarGraph

NEXT_TASK: SG-002

- Phiên gần nhất: SESSION-20260915-004.
- Múi giờ làm việc: Asia/Saigon, UTC+07:00.
- Giai đoạn: M1 — SG-001 DONE; SG-005 DONE; package Python và Git repository đã sẵn sàng. Task tiếp theo SG-002.

## Bối cảnh đã chốt
Người dùng chọn ScholarGraph, yêu cầu plan từng task và rules/log để tiếp nối. Sau đó xác nhận còn khoảng 7 tuần, 2 người, phần triển khai nhờ agent; GPU qua Kaggle/Colab, có thể cân nhắc thuê nếu cần.

Ngày 2026-09-15, project owner xác nhận SG-001 hoàn tất. Tiếp đó SG-005 đã triển khai thành công: cấu trúc package Python, file cấu hình, tài liệu môi trường, unit test và Git local repository tại thư mục gốc.

## Đã tạo
- Root AGENTS, SCHOLARGRAPH entry point và root `.gitignore`.
- ScholarGraph AGENTS, master plan 7 tuần, 50 task (46 core gồm setup, 4 stretch).
- Protocol riêng cho BEIR text, OpenAlex graph, query Việt; graph leakage gate.
- Registry, state, decision log, templates và checker chỉ đọc.
- Bổ sung routing model/reviewer đủ 50 ID, bảng tra cứu, 7 lane chat logic.
- SG-001 tạo/duyệt SCOPE và RUBRIC_MAP.
- SG-005 tạo `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, cấu trúc module `src/scholargraph/`, tests `conftest.py`, `test_package.py`, tài liệu `docs/ENVIRONMENT.md`, `scholargraph/.gitignore` và khởi tạo local Git repository tại thư mục gốc workspace.

## Kết quả kiểm tra và trạng thái
- SG-000 DONE: có file kế hoạch/rules/log và checker đã chạy thành công.
- SG-001 DONE: problem, 4 RQ, core/non-core, mapping chất lượng và deadline nội bộ đã chốt.
- SG-005 DONE: package import được, pytest pass 2/2 tests, git repository hoạt động với trạng thái sạch (loại trừ các file nhị phân lớn của E-COMASPECT).
- 43 task core triển khai ở TODO; 4 stretch DEFERRED; không có task IN_PROGRESS sau bàn giao.
- Kiểm tra tự động bằng `scripts/check_project.ps1` exit code 0.

## Bước tiếp theo
SG-002 — khảo sát local và GPU pilot.
1. Nhận task/session mới, lane D; model đề xuất Sol High, self-check allowed.
2. Xác minh runtime/RAM/disk local và khả năng dùng Kaggle/Colab; không suy quota từ kế hoạch.
3. Tạo COMPUTE_PLAN, notebook encode 1.000 mẫu và compute_pilot report theo card.
4. SG-003 (Related work) cũng đã mở dependency và có thể làm song song nếu phân công phù hợp.

## Tệp cần đọc
- [Master plan](../docs/MASTER_PLAN.md)
- [Task cards](../docs/TASKS.md)
- [Protocol](../docs/RESEARCH_PROTOCOL.md)
- [Decisions](DECISIONS.md)
- [Model từng ID](../docs/TASK_MODEL_MATRIX.md)
- [Chiến lược chat](../docs/MODEL_AND_CHAT_STRATEGY.md)
- [Scope đang review](../docs/SCOPE.md)
- [Rubric map](../docs/RUBRIC_MAP.md)
- [Hướng dẫn môi trường](../docs/ENVIRONMENT.md)
- [Nhật ký gần nhất](logs/SESSION-20260915-004.md)

## Môi trường và lưu ý
- Git repository đã được khởi tạo tại workspace root; commit lịch sử theo từng task.
- Runtime Python 3.13.0 và Git 2.40+ đã xác minh hoạt động tốt trên hệ thống.
- Cấu hình `.gitignore` đảm bảo không trộn lẫn và không làm ảnh hưởng đến mã nguồn/dữ liệu cũ của E-COMASPECT.
- Không có run/GPU process của ScholarGraph đang chạy.

