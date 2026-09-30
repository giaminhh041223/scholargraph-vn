# Log review độc lập EXT-05A W2 082 — MUSE

- **Task:** EXT-05A UI public search/library
- **Role:** reviewer độc lập (không phải author), fresh context
- **Reviewer actual:** `opencode/muse-spark-1.3-contributor-free`, effort `xhigh`
- **Thời điểm:** 2026-09-30T23:00:00+07:00 (giờ Việt Nam, ISO 8601)
- **Reviewer cwd:** `D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph`
- **Target (READ ONLY):** `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph` @ `68b24163e9affbbd7e7d25735c0d4c2ac1076500`
- **Parent authoritative:** `D:/Web_mining_20261/scholargraph` (board/tasks.json EXT-05A REVIEW, log `data/public_search/control/w2-082/ui-r1-tests.log`)
- **Quyền ghi:** chỉ `management/public_search/reviews/MUSE/EXT-05A-W2-082.md`, `management/public_search/reviews/MUSE/probes-ui-082/`, file log này. Không sửa target/board/state/HANDOFF/shared modules. Không commit/push/install/live network/labels/keys.
- **Verdict:** FAIL (CHANGES_REQUIRED) — chi tiết tại report reviewer. Task giữ REVIEW.

## 1. Đọc trước khi kiểm

1. `AGENTS.md` (root + worktree muse) — phạm vi, vòng đời REVIEW, quyền ghi coordinator/worker/reviewer, anti-silent-bypass, negative/adversarial, 1:1 narrative-data.
2. `management/state.json`, `management/HANDOFF.md` (muse worktree; ghi nhận W1 DONE, W2 chưa dispatch trong snapshot muse — parent mới có W2).
3. `management/public_search/tasks.json` parent — EXT-05A REVIEW, owner GEMINI, `delivered_head 68b2416`, `verification.ui_r1 11/1/exit1`.
4. `docs/PUBLIC_PAPER_SEARCH_TASKS.md` §EXT-05A — acceptance UI (search/filter/paging/detail/save/export/refresh/partial/non-2xx/cached/stale/OA/language/keyboard/race/XSS/URL, truth table, no offline graph, synthetic fixture).
5. `docs/public_search/CONTRACT.md` v1.0.0 + `src/.../contracts.py` target (436 dòng) — SearchEnvelope truth table/failed-null, SourceResult/RankedHit/display/LibraryEntry/export/URL invariants, extra-forbid, CLI boundaries.
6. Toàn bộ `docs/public_search/UX_SPEC.md` (202 dòng) — 9 states, TT-01..TT-07, HTTP/CLI mapping, safe_url, Abort+seq, a11y.
7. Dispatch `management/public_search/dispatch/GEMINI-W2-082.txt` parent — owned 10 files, synthetic, native tools, Node `C:/Program Files/nodejs/node.exe`, real JS execution.
8. Target 10 owned files + GEMINI log/packet + `ux_examples.json` (136KB, 11 examples) + freezes `W0/W1-FREEZE-081.json`.

## 2. Xác minh HEAD/scope/frozen (lệnh thật)

- `git -C public-gemini rev-parse HEAD` → `68b24163e9affbbd7e7d25735c0d4c2ac1076500`; `log -1` khớp message/date; `diff 51cdef5..HEAD --stat` 10 files owned.
- SHA-256 45/45 frozen OK trên cả parent và target (W0 14 + W1 31), script reviewer bằng parent `.venv/Scripts/python.exe`.
- `search.html` chỉ thêm nav `/public` (giữ `app.js`/offline); 9 files còn lại đúng owned.

## 3. Chạy kiểm thử thật

- **R1 reproduce (target, parent venv, PYTHONPATH target src):** `pytest tests/unit/test_public_ui.py -v --tb=short -p no:cacheprovider` → `1 failed, 11 passed in 2.00s`, exit 1. Failure `test_node_dom_test_runner_all_tests` do `node_test_runner.js:263` locator `tests/ui/static/...`. Khớp parent log R1 từng chữ. Không claim PASS.
- **Diagnostic cô lập (tmp-diag, patched locator, nhãn temporary):** `node node_test_runner_patched.js --fixtures ... --ux-examples ...` → Suite1+2+TT01/02 PASS, **TT-03 FAIL** (`excluded_by_year 0` nhưng assert filter wording) rồi abort; Suite 4–7 chưa từng PASS. Node v24.14.1.
- **Probes DOM thực tế (Mock + isolated JS, synthetic):**
  - `probe-ui-behavior-082.js` → 63 checks (pagination missing, refresh params đúng, stale false-claim, partial-save sai snapshot, XSS/URL/OA đúng, wire shallow, detail/a11y/race gaps, harness gaps).
  - `probe-wire-082.py` (PYTHONPATH target src) → 35 checks (7 truth envelopes via `model_validate_json` PASS, extra/splits/source/rank/URL/CLI boundaries đúng; `pytest.skip` gap; UI CLI + node missing/malformed + contracts duplicate/nonfinite/extra/missing exit 1).
  - `probe-ui-extra-082.js` → 21 checks (form 8/8, cached/export/race/detail-crash/placeholder/overall-mask/offline).
  - `probe-tt-082.js` → 21 checks (TT-01/02/04/05 + quota + non-2xx body đúng; TT-06 lộ che schema error khi kèm quota).
  - Outputs `.txt` lưu nguyên văn trong `probes-ui-082/`. Hand-counters `example_01` khớp đẳng thức (raw 3/valid 3/invalid 0/excluded 0/eligible 3/groups 2/dup 1/returned 2).
- **Grep xác minh:** không `innerHTML` cho dữ liệu; không `/paper/|/recommend/`; không `GET /public/results/`; chỉ search có Abort/seq; 5 `pytest.skip`; CSS/HTML live regions như report.

## 4. Findings và verdict

- Blocker P0-1..P0-10 + P1-1..P1-7 như report (locator+TT03, pagination, wire shallow/leakage, stale giả, partial-save, mock/harness, skip-gate, mixed-error che, crash/placeholder/masking, race thiếu). P2 là điểm tốt đã xác minh.
- **FAIL — CHANGES_REQUIRED.** Không nhập `68b2416` vào parent, không mở DONE/W3 từ commit này.
- Đã ghi report `reviews/MUSE/EXT-05A-W2-082.md` + probes `reviews/MUSE/probes-ui-082/` + log này. Không sửa target/board/shared.
- Hạn chế review: không browser thật, không backend W3, không live/TTL thật, không đo deadline/đa luồng thật (đã ghi trong report §4).

## 5. Bước executable kế tiếp (cho coordinator)

1. Giao GEMINI sửa P0/P1 đúng owned paths, không chạm frozen/shared.
2. Chạy lại focused pytest + node harness trên HEAD mới, log `data/public_search/control/w2-082/ui-r2-*.log` (expect 12/12 exit 0 + `ALL TESTS PASSED`).
3. Giao MUSE re-review fresh context trên snapshot mới trước nhập parent hay W3.

## 6. Reconciliation closeout R1 (không đổi verdict)

- Controller run `569bbe8f` FAIL/exit 1 do bash tạo/copy `C:/Users/ADMIN/AppData/Local/Temp/opencode/ext05a-diag-082` bị `external_directory` deny. Giữ nguyên lịch sử lỗi, không mở quyền, không lặp lệnh `C:/Temp`.
- Reviewer đã dùng owned `probes-ui-082/tmp-diag/` cho diagnostic nên không cần `C:/Temp`. Probes/report/log thực có thật, verdict product vẫn **FAIL**. Đây là completion review artifact, không phải product PASS hay đổi status.
