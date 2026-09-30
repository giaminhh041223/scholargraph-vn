# Dispatch MUSE — EXT-01B

Coordinator cấp quyền bắt đầu **EXT-01B**, dependency không có. Chưa xác minh worker runtime/thread, không nhận là đang chạy.

- Dispatch ID `DISPATCH-20260930-W0-MUSE`; [log cấp quyền](../logs/COORDINATOR/DISPATCH-20260930-W0-MUSE.md).
- Repo `D:/Web_mining_20261/scholargraph/.worktrees/public-muse/`, project **`D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph/`**.
- Branch `codex/public-search-muse`; code base ban đầu `46328b2be70d17c644fe3351724a5c9f8702eb35`, được fast-forward commit chuẩn bị dispatch.
- Authoritative board ở project điều phối gốc; không sửa bản copy worktree.

Đọc [prompt MUSE](../../../docs/agent_packets/public_search/MUSE.md) và card EXT-01B. Ghi ACK/session log namespace MUSE trong checkout riêng rồi audit nguồn. Checkout và dispatch thực tế đã có; không chờ bước tạo nữa.

Quyền ghi W0: `docs/public_search/SOURCE_AUDIT.md`, `artifacts/reports/public_search/muse/source_audit.json`, `data/public_search/muse/source_pilot/`, logs/packets MUSE. Raw payload/generated output không tự add vào Git; ignore local data/public_search trước pilot, không key trong log/raw. Không sửa config SOL, không triển khai store trước EXT-01A DONE.

Python W0 `D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe` read-only, PYTHONPATH trỏ `src` project MUSE; import worktree đã kiểm. API pilot có budget nhỏ theo card; verify Terms/auth/quota thật, lỗi phải ghi BLOCKED/FAIL, không mock thay live. Không cần qrels/benchmark cho source audit.

Packet có raw hash/status/redacted headers/time/request count và facts vs proposal; actual model/session hoặc unknown. Gửi coordinator để SOL review. Task TODO tới khi coordinator nhận ACK; dispatch này cấp quyền ghi ACK và bắt đầu, không cần xin lại quyền.
