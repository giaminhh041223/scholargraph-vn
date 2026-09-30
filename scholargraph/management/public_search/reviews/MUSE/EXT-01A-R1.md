# REVIEW doc lap EXT-01A R1 - Contract, schema va transport (SOL snapshot 93f8c75)

- Task: EXT-01A, owner SOL, reviewer MUSE.
- Review assignment: REV-W0-01A-R1-MUSE, target head 93f8c75.
- Requested model: opencode/muse-spark-1.3-contributor-free, reasoning variant xhigh.
- Actual model/effort: unknown (khong suy tu nhan prompt; phien CLI moi, khong resume probe).
- Reviewer checkout: D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph, branch codex/public-search-muse, head 8cee172edd2b295b95ec06323efbb6b900a11371.
- SOL checkout: D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph, review snapshot 93f8c75e7599a96598f36421254608f3ccb081fc (code 30434f0c173ec6fdef01f367a3fe783e427d438f + packet/log; HEAD hien tai f6582d9 chi them review EXT-01B, khong doi code EXT-01A).
- Ngay: 2026-09-30T09:30:00+07:00.
- Pham vi ghi: chi hai file nay + repro tam trong data/public_search/muse/review_r1 (git-ignored). Khong sua board/state/HANDOFF/routing, khong sua code SOL, khong review EXT-01C.

## Inputs da doc (dung snapshot)

- management/public_search/packets/SOL/EXT-01A-SESSION-20260930-SOL-01.md (SOL, implementation head 30434f0, packet head 93f8c75).
- docs/public_search/CONTRACT.md 1.0.0 (SOL).
- configs/public_search.json 1.0.0-unverified.
- src/scholargraph/public_search/__init__.py, contracts.py, transport.py.
- tests/unit/test_public_contracts.py, tests/unit/test_public_transport.py.
- Raw/source audit MUSE cua chinh checkout: docs/public_search/SOURCE_AUDIT.md + artifacts/reports/public_search/muse/source_audit.json + data/public_search/muse/source_pilot/MANIFEST.json (3 requests: OpenAlex 429 + retry 200, arXiv 200; chua tu bat verified).
- Task cards goc: docs/PUBLIC_PAPER_SEARCH_TASKS.md muc 4 + EXT-01A; khong doc labels/qrels/held-out; khong goi live them.

## Phuong phap

- Runtime Python chi doc: D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe, Python 3.12.14, httpx 0.28.1, pydantic 2.13.5.
- PYTHONPATH rieng tung shell: D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph/src.
- Import thuc te: D:\Web_mining_20261\scholargraph\.worktrees\public-sol\scholargraph\src\scholargraph\__init__.py; contract 1.0.0 schema 1.
- Chay lai hai tests goc tren source SOL (khong copy code).
- Tu probe adversarial doc lap trong data/public_search/muse/review_r1/r1_adv_a.py, r1_adv_b.py, r1_adv_c.py, r1_cfg.py (tempfile cho config/request lech, sentinel qrels/held-out, subprocess CLI, mock HTTP, concurrency). Khong coi dem so tests tac gia la du; moi bug co reproducer rieng.
- Kiem signatures storage/cache/refresh cho W1; doi chieu spec vs config (OpenAlex auth query-param vs Bearer, arXiv delay, false policy, elapsed/error/counter math).
- Khi thieu tai nguyen: FAIL ro, CLI exit 1; khong silent fallback.

## Ket qua lenh va hash

- `pytest tests/unit/test_public_contracts.py -q`: 84 passed, exit 0.
- `pytest tests/unit/test_public_transport.py -q`: 24 passed, exit 0.
- Tong: 108 passed in ~1.8s, exit 0 (khop packet SOL 108 passed).
- Probe A (contracts: missing/title-only/bool/NaN/counts/provenance/URL/DOI/digest/dup-json): 12/12 PASS.
- Probe B (overall truth 6 cases + edge, priorities, cache key, leakage sentinel, CLI 4 cases, store sigs): 27/27 PASS (trong do 2 OBSERVE la hanh vi lax duoc ghi nhan, khong phai PASS chuc nang).
- Probe C (transport policy/auth/redaction/429/malformed/oversized/deadline/timeout/redirect/cooldown/cross-request/concurrent): 16/17 PASS truc tiep; 1 truong hop arXiv retry cho waits [1.0, 2.0] thay vi [1.0] la dung (giua 2 calls 3s, bao toan interval) - xac nhan dat, khong bug.
- CLI boundary: valid config/request exit 0 VALIDATED; missing config exit 1 FAIL; malformed request exit 1; duplicate JSON exit 1.
- Leakage: Path.open instrumentation chi mo config, khong mo qrels/held-out sentinel.
- NOT_RUN: live sources, latency/pilot/relevance, offline full regression, storage transaction, full split/integration leakage audit (EXT-06), keyed OpenAlex probe (can user key), EXT-01C review.
- Hashes (SHA256 bytes, khop packet): contracts.py 6a9a3d464dc7e8b68661ced95122515809ca77b916f602c107b963e02845878c; transport.py a775b1e99c2dc64d4b6f523567a6543d1b536deed35c255a1b66c894e3607baf; configs/public_search.json 9f2069f22cdfffa6021cb480a756b994663636820579cf31cbe02672ea4e5ce2; CONTRACT.md b71cb186b2680946923d36bf750744ba2f658f91bcec5e4694f30d5e865ee6ca.
- Config: config_version 1.0.0-unverified, data_root data/public_search/sol, deadline 30.0s; openalex endpoint https://api.openalex.org/works verified=false interval 1.0s; arxiv endpoint https://export.arxiv.org/api/query verified=false interval 3.0s.
- MUSE audit delta: OpenAlex docs noi api_key query param, prior art Bearer, chua nga ngu (SOURCE_AUDIT.md:21-24); arXiv Terms <=1 req/3s single connection cross-machine (SOURCE_AUDIT.md:29-31); raw hashes e2853e10 (429 Retry-After 33), 8050e77a (200 101458 bytes, remaining 990), e38e5778 (200 4457 bytes, totalResults 186833); MUSE checkout khong co configs/public_search.json (chua tu bat verified) - dung.

## Doi chieu spec vs config/code

- False policy chan live: DAT. Transport.py:101-102 FAIL policy truoc mang; config ca hai false+null hop le; probe policy-blocks PASS (khong goi mang). MUSE chua bat verified - dung.
- Elapsed/error/result counter math: DAT co ban. Attempted yeu cau elapsed (contracts.py:172-173); TransportResponse elapsed tu clock bao queue/rate/backoff/body; overall_status (226-243) dung 6-case + hits-phai-tu-success; FusionCounts identities (206-212) raw=valid+invalid, valid=eligible+excluded, eligible=groups+dup, returned=len(hits); snapshot valid==len(records) invalid==0; error_http_status (245-251) request 422 > storage/config 500 > quota 503 > timeout 504 > upstream/schema/auth/policy 502, khop CONTRACT.md:86-87.
- arXiv delay toan request/retries: DAT trong code, thieu ghi ro trong docs. Config arxiv interval 3.0s; transport giu lock/source tu truoc rate wait den het retries, khac source song song; RateState tai su dung xuyen request; probe cross-request waits [3.0], concurrent peak==1, arxiv retry waits [1.0,2.0] (call cach 3s) - dung Terms single-process. Nhung contract chi noi cung process, khong canh bao pilot da process/machine (xem P2-2).
- OpenAlex auth query-param vs Bearer: KHONG DAT (xem P1-1). Transport cam api_key/apiKey/key/token/authorization/access_token trong params (106-108); auth bearer chi header (112-118). Docs live yeu cau api_key param - transport hien tai khong the keyed OpenAlex theo docs.
- Storage/cache/refresh cho W1: CHUA DU (xem P1-2). 6 methods PublicStore co trong protocol (371-379); thieu initialize_store/open_existing typed du CONTRACT.md:140-141 hua. Refresh khong nam trong cache key (dung, probe cache-refresh-excluded PASS, case-sensitive PASS); lifecycle atomic pointer/refresh-failure-giu-cu chi co trong docs, chua co code (dung cho EXT-01A, nhung thieu typed anchor).

## Findings (P0..P3, path+line+reproducer+impact)

### P1-1: OpenAlex auth query-param bi cam, mau thuan docs live - chan EXT-02 neu can key

- Path: src/scholargraph/public_search/transport.py:106-108; src/scholargraph/public_search/contracts.py:310-334; docs/public_search/CONTRACT.md:123-124; configs/public_search.json:9-23; doi chieu docs/public_search/SOURCE_AUDIT.md:12,21-24 (MUSE).
- Reproducer doc lap (r1_adv_c.py):
  ```
  cfg = verified bearer/key_env (hoac verified anonymous)
  tr.get("openalex", {"api_key": "K"}, deadline=30.)
  # -> TransportError kind=config "secret parameters forbidden"
  ```
  Da chay: OBSERVE-apikey-forbidden PASS (bi cam). Trong khi audit live ghi docs noi api_key param; prior art trong repo dung Bearer; chua co keyed probe de phan giai.
- Impact: Anonymous da bi throttle (429 Retry-After 33 trong raw e2853e10). Neu pilot W1 can key de dat quota, adapter EXT-02 khong the gui key theo docs voi transport hien tai. Day la vi pham acceptance EXT-01A (param/auth encoding, config policy verification) va dieu kien freeze W0 (SOL nhap policy audit vao config). Chan freeze.
- Expected: Coordinator quyet dinh auth (param vs Bearer vs ca hai co redaction); SOL bo sung auth_mode (vi du api_key_param) hoac chung minh Bearer duoc chap nhan bang 1 keyed probe (user tao key, agents khong tao account); bump contract/config version + delta/re-review; khong tu bat verified.

### P1-2: Thieu initialize_store/open_existing typed trong code - W1 khong co anchor

- Path: src/scholargraph/public_search/contracts.py:371-379; docs/public_search/CONTRACT.md:136-149 (dac biet 140-141).
- Reproducer (r1_adv_b.py):
  ```
  src = open("src/scholargraph/public_search/contracts.py").read()
  assert "initialize_store" not in src and "open_existing" not in src
  from scholargraph.public_search.contracts import initialize_store  # ImportError
  ```
  Da chay: OBSERVE-init-missing / OBSERVE-open-missing (xac nhan vang mat).
- Impact: CONTRACT.md hua 8 signatures (2 ham + 6 methods) nhung code chi co 6 methods + close. MUSE EXT-04A can exact signatures de implement init/open, marker/version, data_root duoi data/public_search, idempotent/FAIL semantics. Thieu anchor typed de review truoc EXT-04A. Chan freeze (acceptance store lifecycle + store signatures voi MUSE review).
- Expected: Them typing-only `initialize_store(project_root: Path, config: PublicSearchConfig) -> PublicStore` va `open_existing(...)` vao contracts.py (khong stub impl), hoac sua CONTRACT.md + decision neu co y de EXT-04A dinh nghia; bump version neu doi.

### P2-1: not_requested cho phep filter_coverage=server - nhan quan sat khong co request

- Path: src/scholargraph/public_search/contracts.py:169-171.
- Reproducer (r1_adv_b.py):
  ```
  SourceResult(source="openalex", status="not_requested", records=[], error=None,
    source_total=None, elapsed_seconds=None, filter_coverage="server", truncated=None, raw_references=[])
  # PASS hien tai, dang le FAIL
  ```
  Da chay: OBSERVE-notreq-server PASSES (ghi nhan lax). Code chi cam raw/elapsed/total/truncated, khong cam filter_coverage.
- Impact: Vi pham SourceResult/not_requested (khong goi mang, khong quan sat). Service/fusion co the hieu sai coverage. P2 vi pham acceptance cung chan freeze theo yeu cau review.
- Expected: Them `if self.status=="not_requested" and self.filter_coverage!="none": raise`; them regression test.

### P2-2: Thieu canh bao phoi hop xuyen process/machine cho rate (arXiv Terms)

- Path: src/scholargraph/public_search/transport.py:28-32,115-116,123-182; docs/public_search/CONTRACT.md:115-118; configs/public_search.json:31 (arxiv 3.0s).
- Reproducer/evidence: Code dung (probe cross-rate waits [3.0], concurrent peak==1, arxiv retry [1.0,2.0] bao toan 3s; RateState locks/next xuyen request cung process). Nhung docs chi noi cung process, khong neu pilot da worker/process/machine phai dieu phoi single-connection theo Terms (MUSE SOURCE_AUDIT.md:29-31: counted across all machines). W1 co 3 workers co the chay adapters song song.
- Impact: Nguy co vi pham Terms (block) neu moi process giu RateState rieng. P2 policy.
- Expected: Bo sung CONTRACT.md limitation: pilot chi mot process/machine tai mot thoi diem hoac coordinator dieu phoi timing; interval ap dung moi attempt/retries (da dung, can ghi ro); distributed lock ngoai MVP (ghi ro chua co).

### P3-1: config_version free Text, khong rang buoc hau to -unverified

- Path: src/scholargraph/public_search/contracts.py:336-355.
- Hien tai verified=false doi null evidence, true doi hash (dung), nhung config_version tu do - co the dat 1.0.0 voi false hoac 1.0.0-unverified voi true+hash ma van PASS. De nham khi freeze.
- Expected: Rang buoc hoac ghi convention + test (khong chan neu co ly do, nhung nen sua).

### P3-2: DOI chi validate, khong co helper normalize

- Path: contracts.py:106-111.
- Adapter EXT-02 phai tu normalize 10.xxxx/suffix truoc validate; raw giu trong evidence (dung). De lech neu moi adapter tu lam. Ghi ro trach nhiem adapter + test.

- P0: Khong co. Da kiem: khong silent fallback (.get mac dinh che thieu khong thay), khong doc labels/qrels/held-out (sentinel + instrumentation PASS), khong hard-code floor metric, khong dung test labels lam feature/edge/seed, BEIR/OpenAlex tach (chua co benchmark), khong goi citation count la correctness, secrets redacted (401/timeout/params/URL/header PASS), 401/403 khong retry/fallback, 429 qua deadline FAIL khong cat wait, malformed headers/payload FAIL, oversized/empty FAIL, redirect FAIL, timeout bounded retries, cooldown giu, deadline pin, auth thieu FAIL truoc mang.

## Verdict: CHANGES_REQUIRED

- Ly do: P1-1 + P1-2 chan W1/downstream va dieu kien freeze W0 (nhap policy audit + store signatures review); P2-1 + P2-2 vi pham acceptance cung chan freeze. Khong du dieu kien PASS. Khong phai INSUFFICIENT_EVIDENCE (da du evidence de yeu cau sua).
- Khong tu sua implementation; findings giao SOL sua owned paths, bump version + delta/review neu doi contract; commit/packet/re-review moi.
- Han che: Review tren snapshot code 93f8c75 (hashes khop); SOL HEAD hien f6582d9 chi them review EXT-01B, khong doi EXT-01A (da kiem diff). Phien CLI moi, khong resume probe truoc (failed run c03402b8 chi la context, khong dung lam evidence). Chua review EXT-01C.

## Next executable

1. SOL sua P1-1 (quyet dinh auth + keyed probe can user key), P1-2 (them typed init/open), P2-1 (not_requested filter check + regression), P2-2 (bo sung docs limitation); chay lai 2 unit files + repro moi; bump contract/config version, cap nhat packet/log, bao coordinator.
2. MUSE re-review tren snapshot moi (rerun repro + relevant regression).
3. Coordinator nhap policy delta (evidence hash) vao config truoc freeze W0; khong bat verified de code/pilot.
4. Sau DONE EXT-01A moi mo EXT-02/03/04A theo dependencies.

---
- Reviewer MUSE (requested opencode/muse-spark-1.3-contributor-free xhigh, actual unknown), session CLI moi.
- Bao commands/exit/counts/not-run, hashes/head/version, pham vi o tren; khong key/token trong log; LF.
