# Re-review doc lap EXT-01A R2 - Contract/transport (SOL fix 774aeef)

- Task: EXT-01A, owner SOL, reviewer MUSE (REV-W0-01A-R2-MUSE).
- Requested model: muse spark 1.3. Actual model/effort: unknown (khong suy tu nhan).
- Reviewer checkout: D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph, branch codex/public-search-muse, head 9f70669.
- SOL checkout: D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph, branch codex/public-search-sol.
- SOL target: fix 774aeef0bfc42c636779f739c3fb4fbb8e9e37c4, HEAD cb64c59a714085f1c453284fdfba76de3efb086e (HEAD chi them packet/log R2, code giong 774aeef). Base R1 93f8c75.
- Ngay: 2026-09-30. Pham vi ghi: chi hai report R2 + mot log MUSE. Khong sua implementation/fixtures/board/raw. Khong live request, khong doc qrels/labels/env.

## Inputs da doc

- management/public_search/packets/SOL/EXT-01A-R2-774aeef.md (scope: hai finding accepted, contract 1.0.0 giu nguyen).
- management/public_search/logs/SOL/SESSION-20260930-SOL-01.md (muc R2: 111 passed, diff check exit 0).
- src/scholargraph/public_search/contracts.py (SourceResult.coherent:169-173), transport.py (RateState:28-32, secret params:106-108, bearer:112-118).
- configs/public_search.json (1.0.0-unverified, verified=false ca hai), docs/public_search/CONTRACT.md (not_requested:48, rate process-local:115-116, store MUSE:140-141).
- tests/unit/test_public_contracts.py (test_not_requested 107-119), tests/unit/test_public_transport.py.
- R1 cua chinh MUSE: reviews/MUSE/EXT-01A-R1.md (P1-1/P1-2/P2-1/P2-2) de doi chieu.

## Phuong phap (read-only)

- Runtime: D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe, Python 3.12.14. PYTHONPATH rieng SOL src moi shell, PYTHONDONTWRITEBYTECODE=1, pytest -p no:cacheprovider.
- Import check: scholargraph tu SOL src, CONTRACT_VERSION 1.0.0, SCHEMA_VERSION 1.
- Diff: git diff 93f8c75..cb64c59; git diff --check. Grep .get va initialize_store/open_existing trong SOL src. Rerun pytest doc lap.

## Evidence that

- `git diff 93f8c75..cb64c59` chi 3 file code/docs + packet/log review: contracts.py +2 dong invariant, CONTRACT.md 2 doan wording (not_requested + rate gap), test_public_contracts.py +14 dong (2 tests moi). Khong doi transport.py, config, wire/schema/version.
- SHA256 bytes: contracts.py 5d752064888f0558f121407bfa3bbc2d2c1a921f7991a39d5716ced79a553908 (R1 6a9a...); transport.py a775b1e99c2dc64d4b6f523567a6543d1b536deed35c255a1b66c894e3607baf (khong doi); config 9f2069f22cdfffa6021cb480a756b994663636820579cf31cbe02672ea4e5ce2 (khong doi); CONTRACT.md 5040dee0e05685625ccb7a1cfc61b26e1f1350d4c564d0a4d2b82e91fd4b657a (R1 b71c...); test_contracts d84aca1f66024f4b9387450d11a94bfcfa1001bba442c28896b8f22da1326938 (R1 a8fc...); test_transport c8688c1edfb4eb34b94352931a8d4145506c2f04dcaa8f02aaac8834fd020317 (khong doi).
- `pytest test_public_contracts.py test_public_transport.py -q`: 111 passed, exit 0 (R1 108; +3 dung bang so test moi). Khop claim SOL 111.
- `pytest test_public_contracts.py -k not_requested`: 3 passed (server reject, bounded_pool reject, none valid).
- `pytest test_public_transport.py -q`: 24 passed, exit 0 (khong regression transport).
- `git diff --check 93f8c75 cb64c59 -- src/tests/docs/configs`: exit 0.
- Grep `\.get\(` trong SOL src: khong co (khong silent fallback qua default). Boundary fail-loud giu nguyen.
- Invariant code contracts.py:170-171 `if filter_coverage != "none": raise "not_requested requires filter_coverage=none"`; CONTRACT.md:48 ghi `server`/`bounded_pool` la loi schema. Khop R1 P2-1 expected.
- Politeness: transport.py RateState van process-local (locks/next_times xuyen request cung process); CONTRACT.md:115-116 ghi ro process-local, chua co distributed lock/shared quota/cross-machine guarantee, gap truoc scale da worker/may. Khop R1 P2-2 expected.
- Config giu 1.0.0-unverified, ca hai verified=false + live FAIL truoc mang (dung cho W0, chua nhap EXT-01B delta).

## Hai finding da sua (xac nhan)

1. P2-1 not_requested->filter_coverage=none: DA SUA (code + 2 reject tests + 1 positive + docs). Reproducer R1 gio FAIL dung.
2. P2-2 arXiv politeness gap: DA SUA (docs ghi process-local + gap van hanh, khong claim cross-machine). Code dung san duoc giu, khong them lock ngoai pham vi.

## Con lai / deferred (khong chan R2 nay, ghi ro de khong overclaim)

- P1-1 auth (api_key param bi cam, chi bearer header): VAN MO trong code (transport.py:106-108). Defer hop ly cho W0: config con unverified + live FAIL, anonymous du cho W0; quyet dinh param vs Bearer + keyed probe can coordinator + user key (agents khong tao account), thuoc EXT-02.
- P1-2 initialize_store/open_existing: VAN VANG trong SOL src (grep khong thay). Defer hop ly: CONTRACT.md:140-141 giao MUSE store.py (EXT-04A) xuat 2 ham nay; card EXT-01A paths khong gom store.py.
- W0 freeze van PENDING: chua nhap EXT-01B policy delta (config van unverified), can MUSE kiem contract/config delta + review du ba outputs theo task cards muc 4. Report nay khong claim DONE/freeze.

## Regression / silent fallback

- Khong thay: 111 passed (0 failed), transport 24/24, diff-check exit 0, khong .get, khong doi wire/version/endpoint/interval/deadline, khong doc qrels/labels.
- NOT_RUN: live sources, latency/pilot/relevance, offline full regression, storage transaction, full split/integration leakage audit (EXT-06), keyed OpenAlex probe (can user key).

## Verdict: PASS (pham vi R2: hai finding accepted da sua, khong regression/silent fallback)

- Dieu kien: P1-1/P1-2 deferred nhu tren; W0 freeze/DONE can policy EXT-01B + review du ba outputs. Khong tu sua code SOL.
- Next: coordinator nhap EXT-01B delta + quyet dinh auth truoc EXT-02; MUSE EXT-04A implement init/open theo CONTRACT.md; re-review neu contract doi version.