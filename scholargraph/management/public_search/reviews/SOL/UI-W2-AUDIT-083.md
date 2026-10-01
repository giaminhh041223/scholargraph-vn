# EXT-05A UI W2 — SOL fresh correctness audit 083

## Phạm vi và snapshot

- Reviewer fresh-context SOL/high, chỉ đọc target: `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph`.
- Snapshot khi chạy: HEAD `7f9b89159b0243b89a9f0536621761f741c20d43` (`feat(public-search): harden W2 UI validation and flows`), target đã clean sau khi author commit R3. Do target có thể tiếp tục đổi, kết luận chỉ áp dụng cho HEAD này.
- Không sửa target/board/contracts/UX/frozen/core; chỉ ghi report này và `reviews/SOL/probes-ui-083/`.

## Verdict

**FAIL — CHANGES_REQUIRED.** Native UI tests hiện còn 1 failure; validator UI có các lỗ hổng strict-schema/calendar và save idempotency làm hỏng contract storage. Vì vậy chưa thể dùng R3 làm PASS/freeze.

## Findings bắt buộc sửa

### P0 — UI gate vẫn FAIL trên chính harness author

- **Repro:** từ target chạy `C:\Program Files\nodejs\node.exe tests/fixtures/public_search/gemini/ui/node_test_runner.js --fixtures tests/fixtures/public_search/gemini/ui/ui_fixtures.json --ux-examples tests/fixtures/public_search/gemini/ux_examples.json`.
- **Actual:** exit 1, Suites 1–6 PASS nhưng Suite 7 fail `Button updated to save_idempotent state` tại `tests/fixtures/public_search/gemini/ui/node_test_runner.js:730`.
- **Cause/evidence:** harness renders `example_06...` hit `doi:10.1000/syn.kg.2025.001` rồi trả `ui_fixtures.fixtures.idempotent_library_save` (`canonical_id=paper_syn_12345`). `savePaperToLibrary` validates response identity and resets button on mismatch (`ui/static/public_search.js:1965–1972`), nên assertion idempotent không bao giờ đạt. Fixture/test phải dùng cùng canonical hit hoặc test phải dựng response đúng hit; không được claim harness PASS.
- `pytest tests/unit/test_public_ui.py -q` từ target: **12 passed, 1 failed, exit 1**. CLI `python -m tests.unit.test_public_ui --check`: exit 0 (chỉ structural, không thay JS gate).

### P1 — `SourceResult` required fields bị UI validator nuốt

- Contract yêu cầu `source_total`, `elapsed_seconds`, `truncated` đều required (nullable), và sai kiểu phải reject. `validateSourceResult` chỉ kiểm `elapsed_seconds`; `source_total`/`truncated` chỉ được đọc trong nhánh `not_requested` (`ui/static/public_search.js:398–445`), không có presence/type guard.
- Repro executable: `probes-ui-083/probe-ui-083.js`.
- Actual Node: `missing_source_total`, `missing_truncated`, `source_total="wrong"`, `truncated="wrong"` đều **ACCEPT**. Python frozen `SearchEnvelope.model_validate` trên cùng payload: cả 4 **REJECT** (probe `probe-python-contract-083.py`, output tương ứng). Đây là silent schema bypass và cho phép metadata thiếu/dị dạng đi vào render.

### P1 — Calendar/tz validator nhận timestamp Python contract loại

- `isIsoTimeWithTz` (`ui/static/public_search.js:83`) kiểm tra day theo tháng và regex nhưng cho phép năm `0000` và offset `+23:59/-23:59`; `new Date()` normalize/accept các giá trị này.
- Repro Node: `0000-01-01T00:00:00Z` và `2026-01-01T00:00:00+23:59` đều **ACCEPT**; Python `SearchEnvelope.model_validate` cùng payload **REJECT**. Probe: `probe-ui-083.js`, đối chiếu `probe-python-contract-083.py`.
- Cần khớp miền `datetime` của frozen contract trước khi cho render; không dùng `Date.parse`/native normalization làm bằng chứng hợp lệ.

### P1 — Idempotent storage entry khác snapshot bị UI báo lỗi

- Store contract cố ý giữ entry cũ theo `canonical_id` khi save lần sau từ snapshot khác (`src/scholargraph/public_search/store.py:493–533`; test `tests/unit/test_public_store.py::test_duplicate_save_and_partial_badge`). Response hợp lệ có `snapshot_id` cũ và provenance ban đầu.
- `savePaperToLibrary` yêu cầu `entry.snapshot_id === targetSnapshotId` (`ui/static/public_search.js:1965`), nên response idempotent hợp lệ bị chuyển thành banner `Lưu bài báo thất bại` và nút không thành `save_idempotent`.
- Repro trong `probe-ui-083.js`: request current snapshot, mock `LibraryEntry` giữ `snapshot_id="snap-original"`; actual 1 POST nhưng banner mismatch. UI phải chấp nhận identity/provenance trả về của store và hiển thị `save_idempotent` (hoặc contract phải đổi đồng bộ; không được coi response hợp lệ là lỗi).

## PASS evidence giới hạn

- Safe URL probes, nested paper/provenance, score/rank/counter, source error deep-equality, required-null `snapshot`, XSS/textContent, stale TTL, pagination request, export missing Blob/createObjectURL đều đã chạy; export negative probe **2/2 PASS** (`probe-export-083-output.txt`).
- Node negative missing-fixture boundary exit **1**.
- Không browser thật/live network/backend W3; không suy ra E2E.

## Artifacts và lệnh tái chạy

- `probes-ui-083/probe-ui-083.js` + `probe-ui-083-output.txt`: 7 lỗi reproduced (4 SourceResult fields, 2 calendar, 1 idempotent snapshot).
- `probes-ui-083/probe-python-contract-083.py` + output: frozen Pydantic đối chiếu, 6/6 payload malformed bị reject.
- `probes-ui-083/probe-schema-types-083.js` và `probe-calendar-083.js`: probes trước đó, cùng kết quả.
- `probes-ui-083/probe-export-083.js` + output: no-silent-success export checks.
- Target runtime: parent `D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe`, Node `C:/Program Files/nodejs/node.exe`, `PYTHONPATH=<target>/src`.

## Bàn giao

Coordinator nên giữ EXT-05A REVIEW, giao author sửa 3 nhóm finding, chạy lại native `pytest tests/unit/test_public_ui.py -q` và Node harness trên HEAD mới, rồi mới fresh-review snapshot mới. Không nhập/freeze HEAD này dựa trên report cũ hoặc structural CLI `--check`.
