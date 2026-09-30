# Log REVIEW EXT-01A R1 - MUSE reviewer

- Task: EXT-01A REVIEW doc lap (REV-W0-01A-R1-MUSE), target SOL head 93f8c75.
- Requested model: opencode/muse-spark-1.3-contributor-free, reasoning xhigh. Actual: unknown (khong bia tu nhan).
- Session: CLI moi, khong resume probe truoc. Checkout MUSE: D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph, branch codex/public-search-muse, head 8cee172edd2b295b95ec06323efbb6b900a11371, base 46328b2.
- SOL snapshot: D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph, review 93f8c75 (code 30434f0 + packet/log), HEAD hien f6582d9 chi them review EXT-01B (diff 93f8c75..HEAD chi 2 files review, khong doi EXT-01A).
- Thoi gian: 2026-09-30T09:30:00+07:00. Khong sua board/state/HANDOFF/routing, khong switch/reset/merge/push, khong doc labels/qrels/held-out, khong goi live them, khong key/token trong log.

## Doc truoc sua

- AGENTS root, management/public_search/tasks.json (EXT-01A REVIEW, owner SOL, reviewer MUSE), docs/PUBLIC_PAPER_SEARCH_TASKS.md muc 4 + EXT-01A.
- Packet SOL EXT-01A-SESSION-20260930-SOL-01.md, CONTRACT.md 1.0.0, configs/public_search.json, contracts.py, transport.py, 2 unit tests (dung snapshot).
- Audit MUSE: SOURCE_AUDIT.md + source_audit.json + data/public_search/muse/source_pilot/MANIFEST.json (hashes e2853e10, 8050e77a, e38e5778); MUSE khong co configs/public_search.json (chua bat verified).

## Lenh da chay (SOL source, PYTHONPATH rieng, import path ghi nhan)

- Import check: scholargraph.__file__ = D:\Web_mining_20261\scholargraph\.worktrees\public-sol\scholargraph\src\scholargraph\__init__.py; contract 1.0.0 schema 1; python 3.12.14 httpx 0.28.1 pydantic 2.13.5 - PASS.
- pytest tests/unit/test_public_contracts.py -q: 84 passed exit 0.
- pytest tests/unit/test_public_transport.py -q: 24 passed exit 0. Tong 108 passed (khop packet).
- Probe A r1_adv_a.py: 12/12 PASS (missing/title-only/bool/NaN/counts/provenance/URL/DOI/digest/dup-json).
- Probe B r1_adv_b.py: 27/27 PASS (truth 6 + edge, priorities, cache, leakage sentinel, CLI 4 cases exit 0/1/1/1, store sigs; 2 OBSERVE lax).
- Probe C r1_adv_c.py: policy/auth/redaction/429/malformed/oversized/deadline/timeout/redirect/cooldown/cross-request/concurrent PASS; arXiv retry waits [1.0,2.0] la dung (bao toan 3s).
- Hashes khop packet: contracts 6a9a..., transport a775..., config 9f20..., CONTRACT b71c... (xem report).
- Config: 1.0.0-unverified, data_root data/public_search/sol, openalex verified=false 1.0s, arxiv verified=false 3.0s.
- NOT_RUN: live, latency/pilot/relevance, offline regression, storage transaction, full leakage audit EXT-06, keyed OpenAlex probe, EXT-01C.

## Findings tom tat

- P0: none.
- P1-1: OpenAlex api_key param bi cam vs docs (transport.py:106-108) - chan EXT-02 neu can key.
- P1-2: Thieu initialize_store/open_existing typed (contracts.py:371-379 vs CONTRACT.md:140-141) - chan W1.
- P2-1: not_requested filter_coverage lax (contracts.py:169-171) - vi pham acceptance, chan freeze.
- P2-2: Thieu canh bao cross-machine rate (arXiv Terms) - P2 policy.
- P3: config_version free, DOI normalize helper (ghi nhan).
- Verdict: CHANGES_REQUIRED (P1+P2 chan freeze). Chi tiet path/line/reproducer/impact trong reviews/MUSE/EXT-01A-R1.md.

## Ghi file va commit

- Da ghi: management/public_search/reviews/MUSE/EXT-01A-R1.md va logs/MUSE/REVIEW-EXT-01A-R1.md (LF, tieng Viet).
- Temp repro: data/public_search/muse/review_r1/r1_adv_*.py, r1_cfg.py, r1_ver.py (git-ignored, khong commit).
- Commit 2 owned files; khong dong vao file khac; bao head/report path + findings cho coordinator.
- Next: SOL sua P1/P2, bump version + delta, chay lai tests/repro, packet/re-review; MUSE re-review snapshot moi; coordinator nhap policy delta truoc freeze.
