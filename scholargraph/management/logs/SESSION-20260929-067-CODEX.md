# SESSION-20260929-067-CODEX — SG-052 (Vệ sinh test & phủ fallback API) và sửa SG-041

- **Thời gian bắt đầu:** 2026-09-29T12:18:00+07:00
- **Session ID:** `SESSION-20260929-067-CODEX`
- **Lane / Role:** `M` / `P` (`implementation_worker`)
- **Tasks:** `SG-052`, `SG-041`
- **Trạng thái:** `active`

## Phạm vi được giao (Prompt 6.1 — CX-1)
- Phần A (`SG-052`):
  1. Sửa `scripts/build_openalex_text_subset.py` và `tests/unit/test_text_subset.py` để test ghi ra `tmp_path` thay vì ghi đè `data/processed/openalex/works_text.jsonl` và `data/manifests/openalex_core_text.json`.
  2. Rà soát toàn bộ `tests/` tìm test ghi vào `PROJECT_ROOT`.
  3. Bổ sung test cho 2 nhánh fallback còn lại của hybrid API (`lexical-only` và `both-sides-empty`) trong `tests/integration/test_api.py`.
  4. Sửa header bảng A2 trong `scripts/run_ablation.py` và tái sinh riêng `artifacts/reports/ablation.md`.
- Phần B (`SG-041` fixes):
  5. Sửa `run_demo.bat:23` (`>1 phut` $\rightarrow$ `hon 1 phut`) và xóa file rác `scholargraph/1`.
  6. Thêm `--extra-index-url https://download.pytorch.org/whl/cpu` vào `requirements.lock`.
  7. Đổi đường dẫn tuyệt đối `D:\Web_mining_20261\bn\...` trong `docs/REPRODUCE.md` và `docs/DEMO_SCRIPT.md` thành đường dẫn tương đối.
