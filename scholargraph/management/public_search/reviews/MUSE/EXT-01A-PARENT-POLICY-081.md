# Review doc lap EXT-01A parent policy delta 081 - MUSE (fresh context, khong phai author)

- Task: EXT-01A parent policy delta, reviewer doc lap MUSE (phien moi, khong phai author).
- Requested model/effort: xhigh da cau hinh. Actual model/effort: unknown (khong suy tu nhan prompt; phien CLI moi).
- Reviewer checkout (ghi): D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph.
- Target READ ONLY (khong sua): parent D:/Web_mining_20261/scholargraph (khong phai config cu trong checkout).
- Ngay: 2026-09-30 (Asia/Ho_Chi_Minh, UTC+07:00).
- Pham vi ghi: chi hai file nay (report + log MUSE 081). Khong sua implementation/board/config cua bat ky checkout. Khong mo task moi.
- Han che doc: khong goi live API; khong doc key/qrels/labels/offline corpus; khong cai dependency.

## Inputs da doc (parent, read-only)

- management/public_search/policy-review-input-081.json (hashes de kiem target bat bien).
- configs/public_search.json (parent).
- src/scholargraph/public_search/contracts.py va transport.py (parent).
- tests/unit/test_public_contracts.py va test_public_transport.py (parent).
- docs/public_search/CONTRACT.md, SOURCE_AUDIT.md (parent).
- artifacts/reports/public_search/muse/source_audit.json (parent).
- management/public_search/reviews/COORDINATOR/W0-R2-GATE.md (parent).
- management/public_search/reviews/MUSE/EXT-01A-R2.md (history, khong thay review moi).
- AGENTS.md workspace/project va instructions lien quan.

## Phuong phap (chi doc + fixtures tam he thong)

- Runtime: D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe, Python 3.12.14. PYTHONPATH=parent/src tung shell, kiem import thuc te (contracts tu parent src, CONTRACT_VERSION 1.0.0, SCHEMA_VERSION 1).
- Thu hash truoc/sau bang sha256 bytes de chung minh khong sua target.
- Rerun pytest doc lap tren parent src (khong copy code).
- Probe adversarial tam trong thu muc TEMP he thong (TEMP/opencode/muse-ext01a-081): false_verified giu evidence, unverified valid, unverified chan network voi forbidden handler, secret params.
- Grep .get / initialize_store / open_existing / auth / quota trong parent src.
- Doi chieu hash config vs byte audit actual; doi chieu docs vs dieu kien anonymous; kiem OpenAlex CONDITIONAL va sustained quota unverified.
- Gate da bac hai finding lich su duoc ton trong: khong yeu cau API key bat buoc khi anonymous duoc phep; khong yeu cau factory store o contracts.py (dung module store.py cua EXT-04A). Khong lap finding thieu can cu.

## Target hashes (xac minh bat bien)

policy-review-input-081.json (created_at 2026-09-30T13:26:34.697333+07:00) khai:

- configs/public_search.json: 1e188af340572a8fc51124fd8bd5b31f615d607a85967a3ee88871374853c4ed
- src/scholargraph/public_search/contracts.py: 5d752064888f0558f121407bfa3bbc2d2c1a921f7991a39d5716ced79a553908
- src/scholargraph/public_search/transport.py: a775b1e99c2dc64d4b6f523567a6543d1b536deed35c255a1b66c894e3607baf
- tests/unit/test_public_contracts.py: 28a4b884bce6a47bda452c8aec6e19e144e21b1e555762b454b6119ea5d407f5
- tests/unit/test_public_transport.py: 7c7578bbf706930449cf8a1aaf87a3fed78d61a00db3729d038de666be688a74
- docs/public_search/CONTRACT.md: 2c4acf74c68fa9701908b5fa82a7ed66f77dd8e684da9f6b2a448a98bf566812
- docs/public_search/SOURCE_AUDIT.md: d213f075ae2256bfc21b3bf847699346b09c66c108962ccbd814444da254e312
- artifacts/reports/public_search/muse/source_audit.json: a37778605f63821b820edc27b20ad5c859b05761d450980650336a4b8b727923

Do thuc te truoc chay (sha256 bytes, parent): khop 8/8.
Do thuc te sau chay (sha256 bytes, parent): khop 8/8, khong doi.
git status --porcelain (parent, 8 paths): sach (khong modified).
Ket luan bat bien: PASS (target khong bi sua trong phien review).

## Config parent delta (xac minh)

- config_version: 1.0.0-audited (parent configs/public_search.json:4). contract_version 1.0.0, schema_version 1.
- openalex: endpoint https://api.openalex.org/works, source_policy_verified=true, policy_evidence_sha256=a37778605f63821b820edc27b20ad5c859b05761d450980650336a4b8b727923, auth_mode=anonymous, key_env=null, interval_seconds=1.0.
- arxiv: endpoint https://export.arxiv.org/api/query, source_policy_verified=true, policy_evidence_sha256=a37778605f63821b820edc27b20ad5c859b05761d450980650336a4b8b727923, auth_mode=anonymous, key_env=null, interval_seconds=3.0.
- Audit hash thuc te (sha256 bytes artifacts/reports/public_search/muse/source_audit.json): a37778605f63821b820edc27b20ad5c859b05761d450980650336a4b8b727923. Khop ca hai source trong config. PASS.
- Auth anonymous/key_env=null hop le theo contracts.py:325-333; Transport.py:112-118 chi yeu cau key khi bearer; anonymous khong can key. Khong yeu cau API key bat buoc la dung (ton trong gate). PASS.
- arXiv interval 3s giu dung Terms (SOURCE_AUDIT.md:26, audit json arxiv READY). PASS.
- Config khong co quota/remaining/counter (grep: 0). Khong nhan fake quota/counter. PASS.
- policy_verified pham vi: chi la terms/access policy da audit, khong phai sustained quota hay pilot toan luong da pass. W0-R2-GATE.md:7-8 ghi ro; SOURCE_AUDIT.md:31-32,44-47 va audit json (openalex CONDITIONAL, sustained quota/runtime not measured, retry wait/headers/timestamps author-reported/unverified, remaining 990 author-reported/unverified) khong overclaim. CONTRACT.md:122 ghi verified la integrity anchor, chua tu chung minh policy dung. PASS.

## Code truoc da PASS (khong mo lai, tru risk that cua delta)

- contracts.py SourceResult.coherent:169-173 giu nguyen tu R2 (hash 5d752064... khop input).
- transport.py RateState:28-32 process-local; secret params:106-108; bearer:112-118; policy gate:101-102; 429/retry:142-146,174-182 giu nguyen (hash a775b1e9... khop input).
- Grep .get( trong parent src: 0 (khong silent fallback). PASS.
- Grep initialize_store/open_existing trong contracts.py: vang mat (dung, thuoc MUSE store.py EXT-04A theo CONTRACT.md:140-141; ton trong gate, khong lap finding). PASS.
- Import thuc te: scholargraph tu parent src, CONTRACT_VERSION 1.0.0, SCHEMA_VERSION 1. PASS.

## Test adaptations (khong che coverage)

- Tong: pytest 2 files -q -p no:cacheprovider: 111 passed, exit 0 (87 contracts + 24 transport).
- test_public_contracts.py:148-158 false_verified giu evidence -> ValidationError (contracts.py:330-331). Rerun -k false_verified: PASS.
- test_public_transport.py:41-46 verified=false/evidence=null voi forbidden handler -> kind=policy truoc network. Rerun -k policy_and_auth: PASS. Chung minh khong network.
- test_not_requested (107-119): server/bounded_pool FAIL, none valid. PASS.
- quota/malformed/timeout/redirect/secret/concurrent/cooldown/cap/deadline: con du trong file parent, rerun mau 7 cases PASS. Khong mat coverage.
- boundary_subprocess + no_label_reads: 4 passed. Khong doc qrels/labels.
- So voi R2 (111 passed): giu 111, khong giam. PASS.

## Lenh / ket qua / exit

- python hash 8 files (truoc): khop input 8/8, exit 0.
- python import check: CONTRACT 1.0.0 SCHEMA 1, init/open False, exit 0.
- python load_config+digest: audited, audit match True ca hai, anonymous/null, 1.0/3.0, exit 0.
- pytest 2 files -q: 111 passed in 4.14s, exit 0.
- collect-only: contracts 87, transport 24, exit 0.
- pytest -k false_verified/duplicate/boundary/no_label: 4 passed, exit 0.
- pytest -k policy_and_auth/quota_wait/malformed_retry: 7 passed, exit 0.
- probe TEMP: false_verified->ValidationError PASS; unverified valid PASS; unverified blocks kind=policy PASS; verified mock attempts=1 PASS; secret kind=config PASS; exit 0.
- grep .get/init/auth/quota: 0 / absent / anonymous dung / 429 that, exit 0.
- python hash 8 files (sau): khop 8/8, exit 0.
- git status 8 paths: sach, exit 0.
- NOT_RUN: live, latency/pilot/relevance, offline regression, storage, full leakage EXT-06, keyed probe. Khong suy ket qua chua do.

## Findings

- P0/P1: none (khong risk that cua delta can mo lai code da PASS).
- P2-info (docs sync, khong chan PASS): docs/public_search/CONTRACT.md:5 (chua audit, giu false) va :10 (1.0.0-unverified) la header cu, chua sync voi parent 1.0.0-audited (verified=true). Dong :184-185 da ghi parent verified cho anonymous MVP, delta chua review, chua claim PASS/DONE nen khong overclaim PASS. Coordinator nen sync header len 1.0.0-audited sau chap nhan. Can cu: configs/public_search.json:4 vs CONTRACT.md:5,10. Khong phai finding lich su da bac; khong sua code.
- Anonymous: khong mau thuan. CONTRACT.md:122-124 + SOURCE_AUDIT.md:17,21,26-28 + audit json (arxiv READY, openalex CONDITIONAL) khop config anonymous/null. PASS.
- Hai finding lich su da bac duoc ton trong, khong lap lai.

## Limitation / provenance

- Review tren bytes parent tai hash tren; actual model/effort unknown; khong suy model tu prompt.
- Da kiem byte hash, import thuc, rerun tests, probe TEMP; khong live; khong doc key/qrels/labels/offline corpus.
- Unverified valid van chan network (forbidden handler); verified chi la anchor, sustained quota/runtime chua do.
- Full pilot/latency/relevance/storage/leakage thuoc EXT-02/04A/05B/06, NOT_RUN.

## Verdict: PASS (pham vi parent policy delta 081)

- Dieu kien: verified dung pham vi terms/access; OpenAlex CONDITIONAL; khong fake quota; hash khop byte; unverified chan network; test giu coverage; khong regression/silent fallback.
- Khong sua code/config/board. Next do coordinator quyet (freeze W0 chi sau acceptance).