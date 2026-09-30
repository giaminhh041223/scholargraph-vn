# Dispatch GEMINI — EXT-01C

Coordinator cấp quyền bắt đầu **EXT-01C**, dependency không có. Chưa xác minh worker runtime/thread, không nhận là đang chạy.

- Dispatch ID `DISPATCH-20260930-W0-GEMINI`; [log cấp quyền](../logs/COORDINATOR/DISPATCH-20260930-W0-GEMINI.md).
- Repo `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/`, project **`D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/`**.
- Branch `codex/public-search-gemini`; code base ban đầu `46328b2be70d17c644fe3351724a5c9f8702eb35`, được fast-forward commit chuẩn bị dispatch.
- Authoritative board ở project điều phối gốc, worktree copy là snapshot không được sửa.

Đọc [prompt GEMINI](../../../docs/agent_packets/public_search/GEMINI.md) và card EXT-01C. Ghi ACK/session log thực tế namespace GEMINI trong checkout riêng, rồi làm UX spec/examples. Không tiếp tục bị chặn bởi văn bản lịch sử “chưa tạo”; checkout và dispatch đã có. Nếu thiếu nguồn/runtime thật báo rõ, không đổi model.

Quyền ghi W0: `docs/public_search/UX_SPEC.md`, `tests/fixtures/public_search/gemini/` (synthetic sidecar), logs/packets GEMINI. Chưa code arxiv/UI hoặc sửa contract SOL. Fields contract chưa khóa là provisional; review MUSE trước DONE.

Python W0: `D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe`, dùng read-only, đặt PYTHONPATH bằng `src` của project GEMINI. Import source checkout đã kiểm. Không install vào runtime chung. Raw/corpus core không tự có, UX W0 không cần dữ liệu benchmark thật.

Bàn giao packet đúng card: branch/base/head, actual model/session hoặc unknown, examples synthetic, states/assumptions/next step. Board task TODO cho đến coordinator nhận ACK; dispatch này cấp quyền ghi ACK và bắt đầu task đã phân công, không yêu cầu chờ thêm lần phê duyệt.
