# Workspace instructions — Web Mining 20261

## Scope
- Workspace: `D:/Web_mining_20261/bn` (bản sao làm việc độc lập được clone từ `D:/Web_mining_20261` theo yêu cầu của người dùng; mọi quy tắc giữ nguyên, chỉ thay đổi đường dẫn scope).
- ScholarGraph VN lives in `scholargraph/`. Mọi phiên làm việc trong môi trường này CHỈ hoạt động bên trong `D:/Web_mining_20261/bn`; không đọc/sửa thư mục cha `D:/Web_mining_20261` ngoài `bn/`.
- Toàn bộ công việc thực hiện bên trong `scholargraph/`.
- The user's current request determines scope. A saved plan is context, not permission to execute the entire backlog.
- Respect system/developer instructions and the user's latest corrections.

## Before ScholarGraph work
1. Read `scholargraph/AGENTS.md`.
2. Read `scholargraph/management/state.json` and `scholargraph/management/HANDOFF.md`.
3. Read `scholargraph/management/tasks.json`, relevant task cards in `scholargraph/docs/TASKS.md`, and applicable decisions in `scholargraph/management/DECISIONS.md`.
4. Inspect actual files and running work before resuming. Saved status must be verified against evidence.
5. Follow the checkpoint and closeout workflow in the child instructions.

## General
- Keep user communication and project planning in Vietnamese; code identifiers may be English.
- Do not invent results, completed work, data provenance, commands already run or grading requirements.
- Do not create separate app tasks, spawn subagents, schedule work or publish externally merely because the plan mentions roles or future tasks.
- If work is interrupted, record the next executable step and unfinished work on disk.

## Tiêu chuẩn kỹ thuật bắt buộc & Chống lỗi ngầm (Anti-Silent-Bypass Protocol)
- **Cấm nuốt lỗi và cấm fallback ngầm (No Silent Bypass):** Tuyệt đối không dùng `.get()` mặc định hoặc giá trị giả lập để che giấu việc thiếu tài nguyên, thiếu split, hoặc thiếu trường dữ liệu bắt buộc. Nếu thành phần bắt buộc bị thiếu hoặc lỗi, PHẢI báo FAIL rõ ràng, ghi nhận error, và CLI bắt buộc phải thoát mã lỗi nonzero (1). Tuyệt đối không thay thế phép đo chưa thực hiện bằng 0 hay chuỗi rỗng.
- **Bắt buộc Negative / Adversarial Testing (Kiểm thử phá hủy):** Mọi module dữ liệu/thuật toán/đánh giá trước khi báo hoàn thành BẮT BUỘC phải có test cases phá hủy trong thư mục tạm:
  1. Thiếu tài nguyên bắt buộc (missing files/splits).
  2. Dữ liệu khuyết thiếu/dị dạng (text-only, title-only, format sai, score ngoài biên).
  3. Kiểm tra rò rỉ (leakage across splits/labels).
  4. Chạy trực tiếp CLI qua subprocess kiểm tra exit code = 1 khi dữ liệu có lỗi.
- **Khớp 1:1 giữa Narrative và Dữ liệu:** Mọi câu khẳng định trong báo cáo/Data Card/log phải xuất phát từ logic toán học chặt chẽ trên toàn bộ biến đếm thực tế; không suy đoán một chiều.
- **Tự kiểm adversarial trước khi bàn giao:** Không tự mãn khi chỉ pass "happy path"; tự phản biện xem có kịch bản bất thường nào làm lọt lỗi ngầm không.

