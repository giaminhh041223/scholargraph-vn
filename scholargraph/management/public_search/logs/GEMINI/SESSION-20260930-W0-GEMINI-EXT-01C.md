# SESSION-20260930-W0-GEMINI-EXT-01C — ACK Dispatch & Thực thi W0 (`EXT-01C`)

- **Ngày thực hiện:** `2026-09-30T08:20:00+07:00`
- **Task ID:** `EXT-01C` — Luồng UI và request/response examples
- **Worker / Role:** `GEMINI` (Owner `EXT-01C`, Reviewer dự kiến: `MUSE`)
- **Dispatch ID nhận bàn giao:** `DISPATCH-20260930-W0-GEMINI` ([GEMINI-W0.md](../../dispatch/GEMINI-W0.md), [DISPATCH-20260930-W0-GEMINI.md](../COORDINATOR/DISPATCH-20260930-W0-GEMINI.md))
- **Worker Execution Session ID:** `SESSION-20260930-W0-GEMINI-EXT-01C`
- **Thread / Conversation ID:** `72a7e6b4-27ec-4533-abde-ec22fa00fa48`
- **Requested Model (theo packet):** `gemini 3.8 flash high`
- **Actual Model / Effort (xác minh từ runtime):** `unknown (not exposed by Antigravity runtime environment; user-selected high effort)` — Không dùng nhãn prompt làm bằng chứng runtime.
- **Checkout / Project Root:** `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/`
- **Git Branch:** `codex/public-search-gemini`
- **Base Commit SHA:** `f2ff0901f97c6d72a12a73660086f7010e0bd6b1` (fast-forward từ `46328b2be70d17c644fe3351724a5c9f8702eb35` và `14c731cebc26085bc7e1cab693508169f4ec5223`)

---

## 1. Xác nhận ACK & Kiểm tra Môi trường / Phạm vi Ghi

1. **Xác nhận ACK:**
   - Đã đọc đầy đủ [AGENTS.md](../../../../AGENTS.md), [scholargraph/AGENTS.md](../../../../AGENTS.md), [state.json](../../state.json), [HANDOFF.md](../../HANDOFF.md), [tasks.json](../../tasks.json), [PUBLIC_PAPER_SEARCH_PLAN.md](../../../../docs/PUBLIC_PAPER_SEARCH_PLAN.md), [PUBLIC_PAPER_SEARCH_TASKS.md](../../../../docs/PUBLIC_PAPER_SEARCH_TASKS.md), [GEMINI.md](../../../../docs/agent_packets/public_search/GEMINI.md) và [GEMINI-W0.md](../../dispatch/GEMINI-W0.md).
   - Xác nhận chỉ ghi trong các đường dẫn được cấp quyền ở W0 (`docs/public_search/UX_SPEC.md`, `tests/fixtures/public_search/gemini/`, `management/public_search/logs/GEMINI/`, `management/public_search/packets/GEMINI/`).
   - Không chạm vào `management/tasks.json`, `management/public_search/tasks.json` (board snapshot), hay bất kỳ module code nào ngoài phạm vi W0.
2. **Xác minh Python Runtime & Import Path:**
   - Python executable (read-only): `D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe`
   - `PYTHONPATH`: `D:\Web_mining_20261\scholargraph\.worktrees\public-gemini\scholargraph\src`
   - Resolved import path: `D:\Web_mining_20261\scholargraph\.worktrees\public-gemini\scholargraph\src\scholargraph\__init__.py` (`httpx=0.28.1`, `pytest=9.1.1`, `pydantic=2.13.5`)
   - `requirements.lock` SHA256: `B68FCDC47FDBC67460E8384087E0FDE8D62FC8FE820A6CF9B220283E0298D57D`

---

## 2. Công việc đã hoàn thành trong `EXT-01C`

1. **Soạn thảo đặc tả giao diện [`docs/public_search/UX_SPEC.md`](../../../../docs/public_search/UX_SPEC.md):**
   - Đặc tả sự tách biệt hoàn toàn giữa `/public` (Public Paper Search trên OpenAlex + arXiv) và `/` (Offline SciFact Snapshot Search), đảm bảo khởi tạo độc lập không cần index offline.
   - Quy định rõ luồng tìm kiếm thường (`refresh=false`) và nút **`Làm mới từ nguồn` (`refresh=true`)**: bỏ qua cache dù còn TTL, chỉ chuyển con trỏ cache nguyên tử khi toàn bộ request thành công, và giữ nguyên con trỏ cache cũ (không trả cache cũ giả làm thành công) khi làm mới gặp lỗi.
   - Đặc tả đầy đủ 9 trạng thái giao diện bắt buộc (`loading`, `empty`, `missing_fields`, `partial_failure`, `quota_exceeded`, `cached_fresh`, `cached_stale`, `oa_unknown`, `save_idempotent`) cùng câu chữ (wording) và hành động tương ứng.
   - Lập Bảng Chân trị `overall_status` (`TT-01`..`TT-07`), quy tắc ưu tiên mã HTTP khi đa lỗi (`422` trước mạng; server errors: `500 > 503 > 504 > 502`), đối soát bộ đếm (`raw = valid + invalid`, `valid = eligible + filtered`, `eligible = unique_groups + duplicate_excess`), và quy tắc bảo mật chống XSS / lọc URL nguy hiểm (`safeUrlOrNull`) / chống race condition (`AbortController` + `currentRequestSeq`).
   - Ghi rõ giới hạn tiếng Anh, giới hạn không tải PDF offline khi lưu thư viện, và không dùng `citation_count` làm điểm chất lượng.
2. **Tạo bộ ví dụ giả lập [`tests/fixtures/public_search/gemini/ux_examples.json`](../../../../tests/fixtures/public_search/gemini/ux_examples.json) & sidecar [`ux_examples.sidecar.json`](../../../../tests/fixtures/public_search/gemini/ux_examples.sidecar.json):**
   - Bao phủ 11 nhóm kịch bản (gồm toàn bộ 9 UI states và 7 ca chân trị `TT-01`..`TT-07`).
   - Gắn nhãn `"synthetic": true`, `"provisional_contract": true`, `"not_live_evidence": true`, `"not_for_production_fallback": true` ở cả cấp gốc, từng ví dụ và tệp sidecar.

---

## 3. Kiểm chứng & Băm SHA256 (Verification Evidence)

- Lệnh kiểm tra tính nhất quán JSON, cờ `synthetic=true`, `provisional_contract=true` và các đẳng thức bộ đếm (`raw_records`, `valid_records`, `eligible_records`):
  - Exit code: `0` (`ALL_ASSERTIONS_PASSED=True`)
- Băm SHA256 đầu ra:
  - `docs/public_search/UX_SPEC.md`: `FD8381206CACF9170DCAC73FF4BCCB2E5A5D4F4B94985ACBD87B9EE91A6FFC72`
  - `tests/fixtures/public_search/gemini/ux_examples.json`: `393F44C681EEE71671F19B7991AC64BEC6C3E641B577352472CB8BF2096B39DE`
  - `tests/fixtures/public_search/gemini/ux_examples.sidecar.json`: `A929C4B318C001E948503C0585C913B154E5F88DF616CE502463E68011C65CF1`

---

## 4. Bước kế tiếp (Next Executable Step)

- Commit các tệp thuộc quyền sở hữu của `GEMINI` trong `EXT-01C` trên nhánh `codex/public-search-gemini`.
- Xuất packet bàn giao `management/public_search/packets/GEMINI/EXT-01C-SESSION-20260930-W0-GEMINI.md` và dừng sửa vùng snapshot `EXT-01C` để Coordinator chuyển sang `REVIEW` (Reviewer: `MUSE`).
- Chờ `EXT-01A` (`SOL`) và `EXT-01B` (`MUSE`) chốt contract + source policy trước khi đồng bộ worktree sang Wave `W1` (`EXT-03` Adapter arXiv).
