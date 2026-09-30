# Bàn giao điều phối phần mở rộng public search

Ngày chuẩn bị: 2026-09-30. Nhánh điều phối: `codex/public-paper-search`.

## Trạng thái thật

- Người dùng cung cấp ba worker: gpt 6.1 sol, gemini 3.8 flash high, muse spark 1.3; yêu cầu thiết kế task chi tiết có thể chạy song song, review và sửa.
- Đã soạn [task cards và lịch chạy](../../docs/PUBLIC_PAPER_SEARCH_TASKS.md), [board extension](tasks.json) và prompt từng worker.
- Đã tạo ba checkout/branches, xác minh Git/runtime import, cấp quyền W0. Chưa xác nhận ba worker chạy implementation hoặc kết quả online. Reviewer tài liệu [report](reviews/PLANNING-20260930-SOL.md) PASS là review thiết kế.
- Owner/dispatch/session cấp quyền có thật được đăng ký; worker execution session/model runtime chưa xác minh vẫn null. SOL có chat thật, Gemini/Muse chưa xác minh thread.
- Board extension thuộc phạm vi nhánh này; không thay SG-030/033, không chuyển next_task SG-034 hoặc ghi vào routing main đang dùng catalog cũ.

## Nguồn sự thật của extension

- Phạm vi chức năng: [PUBLIC_PAPER_SEARCH_PLAN.md](../../docs/PUBLIC_PAPER_SEARCH_PLAN.md).
- Task, quyền ghi, gate và review: [PUBLIC_PAPER_SEARCH_TASKS.md](../../docs/PUBLIC_PAPER_SEARCH_TASKS.md).
- Status/session/evidence khi chạy: `tasks.json` trong thư mục này, một coordinator extension ghi.
- Con trỏ startup/progress: [state extension](state.json); `session_id` W0 là session cấp quyền coordinator có log thật, `session_kind=coordinator_issued_dispatch`; `worker_execution_session_id` vẫn null trước ACK. Không nhầm dispatch session với worker đã chạy.
- Prompts: [SOL](../../docs/agent_packets/public_search/SOL.md), [GEMINI](../../docs/agent_packets/public_search/GEMINI.md), [MUSE](../../docs/agent_packets/public_search/MUSE.md).

Các EXT là task extension trong board riêng, không phải SG đã đăng ký ở board main. Khi tích hợp vào lịch core, coordinator main ánh xạ sang SG IDs và routing được hỗ trợ bằng quyết định có thật. Không tạo SG IDs giả hoặc ép tên model ngoại vào schema main để vượt checker.

## Bước khởi động

**Setup đã hoàn tất:** worker đọc [dispatch SOL](dispatch/SOL-W0.md), [GEMINI](dispatch/GEMINI-W0.md), [MUSE](dispatch/MUSE-W0.md), ACK/log rồi bắt đầu card W0 được cấp. Không chờ bước tạo worktree nữa. Python W0 dùng runtime root read-only với PYTHONPATH source riêng, đã kiểm cả ba.

`active_assignments` của extension ghi quyền ghi đã cấp với state authorized_awaiting_ack; status task chưa chuyển IN_PROGRESS khi chưa có ACK. Đây không phải nhận xét worker đang chạy; dispatch cho phép worker bắt đầu và coordinator cập nhật khi nhận ACK. Bản board trong checkout worker là snapshot; luôn đọc root board authoritative.

1. Kiểm tra Git/worktree/process và scope coordinator main trước sửa phần dùng chung.
2. Ba checkout riêng đã có theo mục 3 của task cards, cùng commit dispatch. Không cho workers switch branch trên checkout dùng chung.
3. Mở worker đúng model bằng môi trường thực tế người dùng có. Gemini/Muse chưa có công cụ gọi trực tiếp trong chat lập kế hoạch; dùng prompt trong môi trường của chúng.
4. Coordinator ghi actual model nếu xác minh được, session/log thật, claimed_paths và owner; chỉ lúc worker thực sự nhận việc mới chuyển IN_PROGRESS.
5. Giao đồng thời EXT-01A cho SOL, EXT-01B cho MUSE, EXT-01C cho GEMINI: không có dependency, phạm vi ghi không giao nhau.
6. Review W0, pin contract commit và đồng bộ các checkout trước adapters/storage/UI.

Đầu vào chưa có: arXiv Terms cần kiểm chứng; site HTML B chưa chọn. B vẫn DEFERRED đến khi được giao cụ thể.

## Checkpoint mỗi phiên

Task / role / checkout / branch / base và head commit; model thực tế hoặc unknown; session/log thật; files đã sửa; commands/exit codes/pass-fail thật; evidence/hash; findings; process; việc dở và bước executable kế tiếp.

Không ghi fixture thành kết quả live. Không gửi message sang chat khác nếu chưa có quyền của người dùng; coordinator nhận packet qua file/đầu ra.
