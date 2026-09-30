# Bàn giao điều phối phần mở rộng public search

Ngày chuẩn bị: 2026-09-30. Nhánh điều phối: `codex/public-paper-search`.

## Trạng thái thật

- Người dùng cung cấp ba worker: gpt 6.1 sol, gemini 3.8 flash high, muse spark 1.3; yêu cầu thiết kế task chi tiết có thể chạy song song, review và sửa.
- Đã soạn [task cards và lịch chạy](../../docs/PUBLIC_PAPER_SEARCH_TASKS.md), [board extension](tasks.json) và prompt từng worker.
- Chưa khởi chạy ba worker implementation; chưa tạo worktree; chưa có code/module/result online được báo hoàn thành. Có reviewer Sol read-only đọc tài liệu, [report](reviews/PLANNING-20260930-SOL.md) đã PASS sau sửa ba P2.
- `proposed_owner`/`proposed_reviewer` là phân công chuẩn bị; model/session thực tế còn null.
- Board extension thuộc phạm vi nhánh này; không thay SG-030/033, không chuyển next_task SG-034 hoặc ghi vào routing main đang dùng catalog cũ.

## Nguồn sự thật của extension

- Phạm vi chức năng: [PUBLIC_PAPER_SEARCH_PLAN.md](../../docs/PUBLIC_PAPER_SEARCH_PLAN.md).
- Task, quyền ghi, gate và review: [PUBLIC_PAPER_SEARCH_TASKS.md](../../docs/PUBLIC_PAPER_SEARCH_TASKS.md).
- Status/session/evidence khi chạy: `tasks.json` trong thư mục này, một coordinator extension ghi.
- Prompts: [SOL](../../docs/agent_packets/public_search/SOL.md), [GEMINI](../../docs/agent_packets/public_search/GEMINI.md), [MUSE](../../docs/agent_packets/public_search/MUSE.md).

Các EXT là task extension trong board riêng, không phải SG đã đăng ký ở board main. Khi tích hợp vào lịch core, coordinator main ánh xạ sang SG IDs và routing được hỗ trợ bằng quyết định có thật. Không tạo SG IDs giả hoặc ép tên model ngoại vào schema main để vượt checker.

## Bước khởi động

1. Kiểm tra Git/worktree/process và scope coordinator main trước sửa phần dùng chung.
2. Chuẩn bị ba checkout riêng theo mục 3 của task cards, cùng một commit kế hoạch đã chốt. Không cho ba worker switch branch trên checkout dùng chung.
3. Mở worker đúng model bằng môi trường thực tế người dùng có. Gemini/Muse chưa có công cụ gọi trực tiếp trong chat lập kế hoạch; dùng prompt trong môi trường của chúng.
4. Coordinator ghi actual model nếu xác minh được, session/log thật, claimed_paths và owner; chỉ lúc worker thực sự nhận việc mới chuyển IN_PROGRESS.
5. Giao đồng thời EXT-01A cho SOL, EXT-01B cho MUSE, EXT-01C cho GEMINI: không có dependency, phạm vi ghi không giao nhau.
6. Review W0, pin contract commit và đồng bộ các checkout trước adapters/storage/UI.

Đầu vào chưa có: arXiv Terms cần kiểm chứng; site HTML B chưa chọn. B vẫn DEFERRED đến khi được giao cụ thể.

## Checkpoint mỗi phiên

Task / role / checkout / branch / base và head commit; model thực tế hoặc unknown; session/log thật; files đã sửa; commands/exit codes/pass-fail thật; evidence/hash; findings; process; việc dở và bước executable kế tiếp.

Không ghi fixture thành kết quả live. Không gửi message sang chat khác nếu chưa có quyền của người dùng; coordinator nhận packet qua file/đầu ra.
