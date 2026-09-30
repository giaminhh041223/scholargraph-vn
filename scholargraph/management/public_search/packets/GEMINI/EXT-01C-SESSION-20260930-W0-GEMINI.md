# Packet Bàn giao & Đề nghị Review — `EXT-01C` (`GEMINI`)

```text
Task / author / actual model+effort hoặc unknown / session:
  Task: EXT-01C — Luồng UI và request/response examples (Wave W0)
  Author / Worker: GEMINI (Reviewer dự kiến: MUSE)
  Requested model (theo prompt): gemini 3.8 flash high
  Actual model+effort: unknown (not exposed by Antigravity runtime environment; user-selected high effort; không lấy nhãn prompt làm chứng cứ runtime)
  Coordinator Dispatch ID: DISPATCH-20260930-W0-GEMINI
  Worker Execution Session ID: SESSION-20260930-W0-GEMINI-EXT-01C
  Thread / Conversation ID: 72a7e6b4-27ec-4533-abde-ec22fa00fa48

Checkout / branch / base SHA / head SHA / contract version+hash:
  Checkout: D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/
  Branch: codex/public-search-gemini
  Initial Worktree Base SHA: 46328b2be70d17c644fe3351724a5c9f8702eb35
  Fast-forwarded Dispatch Base SHA: f2ff0901f97c6d72a12a73660086f7010e0bd6b1
  Deliverable Commit SHA: 275820992f9f99fcec1e16067fe485a9875eba86
  Python Executable (read-only): D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe
  Verified Import Path: D:\Web_mining_20261\scholargraph\.worktrees\public-gemini\scholargraph\src\scholargraph\__init__.py (httpx=0.28.1, pytest=9.1.1, pydantic=2.13.5)
  Requirements Lock SHA256: B68FCDC47FDBC67460E8384087E0FDE8D62FC8FE820A6CF9B220283E0298D57D
  Contract Version+Hash: 0.1.0-provisional (provisional_contract=true; chờ đối chiếu và khóa với docs/public_search/CONTRACT.md của SOL tại EXT-01A trước EXT-05A)

Changed paths / input artifacts / outputs+hashes:
  Input artifacts (read-only):
    - docs/PUBLIC_PAPER_SEARCH_PLAN.md
    - docs/PUBLIC_PAPER_SEARCH_TASKS.md
    - docs/agent_packets/public_search/GEMINI.md
    - management/public_search/dispatch/GEMINI-W0.md
    - ui/templates/search.html, ui/static/app.js, ui/static/style.css
  Outputs + SHA256 hashes (owned by GEMINI in W0):
    - docs/public_search/UX_SPEC.md
      SHA256: FD8381206CACF9170DCAC73FF4BCCB2E5A5D4F4B94985ACBD87B9EE91A6FFC72
    - tests/fixtures/public_search/gemini/ux_examples.json
      SHA256: 393F44C681EEE71671F19B7991AC64BEC6C3E641B577352472CB8BF2096B39DE
    - tests/fixtures/public_search/gemini/ux_examples.sidecar.json
      SHA256: A929C4B318C001E948503C0585C913B154E5F88DF616CE502463E68011C65CF1
    - management/public_search/logs/GEMINI/SESSION-20260930-W0-GEMINI-EXT-01C.md
    - management/public_search/packets/GEMINI/EXT-01C-SESSION-20260930-W0-GEMINI.md

Executed commands / exit codes / pass-fail counts / not run:
  1. git -C D:\Web_mining_20261\scholargraph\.worktrees\public-gemini merge --ff-only f2ff090 -> exit 0
  2. Runtime & import path check with PYTHONPATH=...\public-gemini\scholargraph\src -> exit 0 (scholargraph.__file__ resolved inside public-gemini worktree)
  3. Python invariant & counter reconciliation check on ux_examples.json and ux_examples.sidecar.json -> exit 0 (ALL_ASSERTIONS_PASSED=True; 9/9 UI states covered; 7/7 truth-table cases TT-01..TT-07 covered; raw=valid+invalid, valid=eligible+filtered, eligible=unique_groups+duplicate_excess verified across all source_results)
  4. git diff --check -> exit 0
  5. Not run in W0: Live network queries, arXiv adapter unit tests (EXT-03), and browser/DOM UI tests (EXT-05A) — outside W0 scope.

Negative and leakage cases / raw live evidence hoặc synthetic:
  - Evidence type: 100% SYNTHETIC (synthetic=true, provisional_contract=true, not_live_evidence=true, not_for_production_fallback=true in both ux_examples.json and ux_examples.sidecar.json).
  - Negative/Adversarial cases specified in UX_SPEC.md and ux_examples.json:
    * TT-01..TT-07 overall_status truth table (including TT-03 valid records filtered to 0 by year filter, TT-04 empty+failed -> partial_failure HTTP 504 CLI 1, TT-05 success+failed -> partial_failure HTTP 503 CLI 1 with partial hits in JSON body, TT-06 all failed with mixed error precedence 500 > 503 > 504 > 502, TT-07 invalid request HTTP 422 before network).
    * Explicit refresh=true failure (B_refresh_failure_does_not_mask_with_old_cache) preserving old cache pointer without returning stale cache as success.
    * Upstream schema violation (missing required title at offending_index=1 causing entire source to fail without silent drop).
    * Uninitialized SQLite store (HTTP 500 store_not_initialized requiring explicit init-storage).
    * XSS title payload (<img src=x onerror=...>) and unsafe URL schemes (javascript:, embedded user:password@ credentials) blocked by safeUrlOrNull and textContent rendering.
  - Leakage check: Zero reads of core offline splits, qrels, or SG-030/SG-033 label files.

Findings addressed / assumptions / remaining blockers:
  - Addressed all 3 planning review P2 requirements from PLANNING-20260930-SOL.md within UX_SPEC.md and ux_examples.json:
    1. Explicit user refresh=true bypasses TTL cache, updates pointer atomically only on full success, and never masks refresh failure with stale cache.
    2. Complete overall_status truth table (TT-01..TT-07) distinguishing source status from post-filter/fusion overall status.
    3. Explicit SQLite store initialization error handling (HTTP 500 store_not_initialized when open_existing fails).
  - Assumptions / Provisional Notice: Field names in ux_examples.json are provisional for W0 and will be reconciled 1:1 with SOL's frozen docs/public_search/CONTRACT.md (EXT-01A) before EXT-05A.
  - Remaining blockers for W1 (EXT-03) and W2 (EXT-05A): Waiting for MUSE review of EXT-01C, SOL's frozen contract (EXT-01A), and MUSE's source policy audit (EXT-01B).

Review requested / process still running / next executable step:
  - Review requested: Requesting Coordinator to mark EXT-01C as REVIEW and assign reviewer MUSE on snapshot commit of branch codex/public-search-gemini.
  - Process still running: None (0 background tasks).
  - Next executable step: Stop editing EXT-01C owned paths; await MUSE review verdict and W0 contract/source-audit freeze before syncing worktree for EXT-03 (arXiv adapter) and reviewing EXT-04A (MUSE storage).
```
