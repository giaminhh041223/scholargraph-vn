# Dispatch SOL — EXT-01A

Coordinator đã cấp quyền bắt đầu **EXT-01A**. Dependency không có; không cần xin lại quyền hoặc chờ worktree được tạo.

- Dispatch ID: `DISPATCH-20260930-W0-SOL`; log coordinator [ở đây](../logs/COORDINATOR/DISPATCH-20260930-W0-SOL.md).
- Chat đã xác minh: `01a0efcc-2062-7d01-b687-10d249b56cbe`, tên “Chuẩn bị worker SOL ScholarGraph”. Model runtime chưa xác minh.
- Repo checkout: `D:/Web_mining_20261/scholargraph/.worktrees/public-sol/`.
- **Project làm việc:** `D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph/`.
- Branch: `codex/public-search-sol`. Code base ban đầu: `46328b2be70d17c644fe3351724a5c9f8702eb35`; commit chuẩn bị dispatch được nhập fast-forward sau đó.
- Coordinator board authoritative: `D:/Web_mining_20261/scholargraph/management/public_search/tasks.json`; bản trong worktree chỉ là snapshot, không sửa.

## Bắt đầu ngay trong checkout riêng

1. Kiểm Git branch/HEAD và đọc card EXT-01A, plan, AGENTS và [prompt SOL](../../../docs/agent_packets/public_search/SOL.md). Nếu thấy văn bản lịch sử “chưa tạo”, dispatch này và filesystem/Git hiện tại là bằng chứng mới hơn.
2. Ghi ACK/log session của bạn dưới `management/public_search/logs/SOL/` trong project SOL: dispatch ID, actual model nếu xác minh được, HEAD, paths sẽ ghi. Đây là quyền được coordinator cấp để nhận task và triển khai, không chỉ read-only preparation.
3. Chỉ làm EXT-01A: contract/schema/transport/config và tests. Gửi packet REVIEW cho coordinator; chưa tự chuyển EXT-02 hoặc sửa shared board.

Quyền ghi: `docs/public_search/CONTRACT.md`, `src/scholargraph/public_search/__init__.py`, `contracts.py`, `transport.py`, `configs/public_search.json`, `tests/unit/test_public_contracts.py`, `test_public_transport.py`, log/packet namespace SOL. Không sửa module arXiv/UI/storage/core.

## Python W0 đã kiểm chứng

```powershell
Set-Location -LiteralPath 'D:\Web_mining_20261\scholargraph\.worktrees\public-sol\scholargraph'
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
& 'D:\Web_mining_20261\scholargraph\.venv\Scripts\python.exe' -m pytest tests/unit/test_public_contracts.py tests/unit/test_public_transport.py -q
```

Lệnh pytest trên dùng khi tests đã được tạo, chưa phải test đã chạy. Runtime ScholarGraph hiện có dùng read-only cho W0; không pip install vào environment chung. Import source worktree đã kiểm đúng; httpx 0.28.1, pytest 9.1.1, pydantic 2.13.5. Nếu cần dependency mới gửi coordinator, không fallback hoặc sửa runtime chung.

Raw/data/index nghiên cứu không tự có trong checkout; W0 dùng fixture tạm, không cần corpus thật. Missing required fixture/config phải FAIL, không đọc data core để che thiếu input. Khi bàn giao commit owned paths và packet, report actual tests/exit codes và next step.
