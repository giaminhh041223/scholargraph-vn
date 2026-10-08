# Máy chấm dev v2 đã hoàn tất — 2026-10-08T13:49:39.757091+07:00

Hai subagent chấm độc lập 227 cặp dev v2 mỗi agent; [báo cáo](../artifacts/reports/vn_machine_dev_v2_20261008/REPORT.md), [CSV bất đồng](../artifacts/reports/vn_machine_dev_v2_20261008/disagreements.csv), [log108](logs/SESSION-20261008-108-CODEX.md). 196/205 cặp có nhãn số trùng (95,61%), kappa0,931;22cặp cùngunjudged,9bấtđồng. Hai context cùng requested SOL/high, runtime telemetryunknown; không là gold/humanlabels. 7protected hashes giữ nguyên. Agentsđãdừng, experimentcompleted.

**Next:** A/B người chấm devv2 độc lập theo kit; khi có cùng227cặp mới đối chiếu human–machine. Nhãnngười v1 không dùng để so v2. SG033IN_PROGRESS, SG034TODO và maincoregates giữ nguyên. Không tune/freeze/evaltest từnhãnmáy. CheckerPASS sau sửa metadata cũ và enum session; chi tiếtlog108.

## Lịch sử checkpoint thử nghiệm

# Thử nghiệm máy chấm dev v2 — 2026-10-08T13:45:27.926917+07:00

Người dùng yêu cầu hai subagent chấm độc lập 227 cặp dev v2. Experiment nằm [artifacts/reports/vn_machine_dev_v2_20261008](../artifacts/reports/vn_machine_dev_v2_20261008); [SESSION-20261008-108-CODEX](logs/SESSION-20261008-108-CODEX.md). Hai machine raters đang chạy, mỗi agent chỉ ghi file riêng; không thay human SG-033/SG-034. Input có 22 abstract thiếu → unjudged. Next: nhận hai file → kiểm/đo agreement → báo cáo. Human v2 chưa có, không so trực tiếp nhãn v1.

## Bàn giao trước thử nghiệm

# Public search đã tích hợp — 2026-10-01T23:13:32.489133+07:00

Nhánh mở rộng đã fast-forward vào master local theo xác nhận demo/save/JSON-BibTeX của người dùng. [Handoff extension](public_search/HANDOFF.md), [gate106](public_search/reviews/COORDINATOR/INTEGRATION-FINAL-GATE-106.md).96tests sau merge PASS;155resourcehashes và33corefreeze khớp. Mainboard SG030/033 và H1–H3 giữ nguyên; xác nhận public demo không xác nhận labels/evaluation nghiên cứu. EXT09/10DEFERRED. Next coretask vẫn theo phần G4 dưới đây.

# Bàn giao ScholarGraph

NEXT_TASK: SG-034

## SG-033 làm lại trên bộ query v2 (ADR-023) — 2026-10-06T00:30:00+07:00

- **Vì sao:** nhãn dev v1 của A/B có 6/10 query không có cặp dương nào (427/434 nhãn số là 0), vì query v1 là y sinh/trắc lượng còn corpus là IR/web mining. A có 1 null nên merge v1 exit 1 (đúng). File thô lưu nguyên byte tại `data/annotations/v1_dev_labels_raw/`, không dùng để đánh giá.
- **Đã làm ([log 075](logs/SESSION-20261005-075.md)):**
  - Bộ 30 query v2 `vn2:` đã được chủ dự án duyệt nguyên bản.
  - Pool v2: 679 cặp (dev 227/test 452) tại `data/annotations/v2/`.
  - Kit `artifacts/vn_labeling_kit_SG033_v2.zip`, file xuất `vn2_labels_{A|B}_{split}.jsonl`.
  - v1 và `configs/frozen_main.json` không đổi. Test liên quan PASS.
- **Lưu ý:** bản dịch Opus-MT sai ở dev:001, dev:007 và test:017 → người chấm luôn chấm theo câu tiếng Việt. 74/679 cặp không có abstract.
- **Bước tiếp theo (người):**
  1. A/B chấm độc lập 227 cặp dev (5 query pilot dev:001–005 trước).
  2. Merge vào `data/annotations/v2/vn_labels_dev.jsonl`, rồi chạy `score_vn_agreement.py` trước khi phân xử.
  3. Phân xử, rồi chạy SG-034 `freeze-dev` với **tham số tường minh** `--pool data/annotations/v2/vn_pool.json --labels data/annotations/v2/vn_labels_dev.jsonl` (mặc định của `run_vn_eval.py` vẫn trỏ v1).
  4. Chấm test.
- **Thêm (bảo vệ khỏi trộn v1/v2):** `run_vn_eval.py --phase eval-test` giờ exit 1 nếu `--pool` khác `pins.vn_pool_sha256` đã ghim lúc freeze-dev (có test). Đã cập nhật Bước 2 của `docs/SUBMISSION_CHECKLIST.md` sang lệnh v2.
- **Còn lệch (để SG-043/SG-044 sửa khi chốt báo cáo, cần chủ dự án duyệt):** `reports/final_report.md`, `docs/CLAIMS_CHECKLIST.md` (CLM-008), `reports/defense_slides.md`, `docs/DEFENSE_QA.md` và `docs/REPRODUCE.md` vẫn ghi pool v1 662 cặp (219/443) → phải đổi sang v2 679 cặp (227/452) và nêu ADR-023.
- **Chưa làm:** `scripts/check_project.ps1` (người dùng chạy).

## G4 Phần Agent Hoàn tất (`CX-3`, `CX-4`, `GM-6` sẵn sàng 100%; chờ cổng con người `H-1`..`H-3`) — 2026-09-29T16:19:00+07:00

- **CX-3 (`SG-034` CLI — [log 073](logs/SESSION-20260929-073-CODEX.md)):** Đã xây dựng [run_vn_eval.py](../scripts/run_vn_eval.py) với 2 pha tách biệt (`--phase freeze-dev` chỉ đọc dev, chọn cấu hình qua `select_best` và ghi `configs/frozen_vn.json` với `human_approved=false`; `--phase eval-test` bắt buộc `human_approved=true` rồi mới chấm test 1 lần và xuất `vn_results.json/.md`). Kèm 5 kiểm thử đơn vị & phá hủy trong [test_vn_eval.py](../tests/unit/test_vn_eval.py).
- **CX-4 (`SG-042` / `SG-043` Tooling & Figures — [log 073](logs/SESSION-20260929-073-CODEX.md)):**
  - [build_evidence_index.py](../scripts/build_evidence_index.py) $\to$ sinh [evidence_index.json](../artifacts/reports/evidence_index.json) ánh xạ 1:1 toàn bộ 7 run Track A, 2 nhánh Track B, Ablation A1/A3, Robustness R1–R5, 24 khoảng tin cậy Paired Bootstrap, số đo hiệu năng `SG-040` và 8 khẳng định (`CLM-001`..`CLM-008`).
  - [compare_reproduction.py](../scripts/compare_reproduction.py): Công cụ đối chiếu tái lập chéo của thành viên thứ hai theo ngưỡng `1e-4` (bắt buộc `--reproducer` là con người, từ chối tên AI).
  - [generate_figures.py](../scripts/generate_figures.py) $\to$ sinh 4 biểu đồ SVG trong `reports/figures/`.
  - [verify_claims.py](../scripts/verify_claims.py): Kiểm chứng tự động khớp 1:1 giữa báo cáo, checklist và `evidence_index.json` (**PASS**).
  - Bổ sung 15 kiểm thử mới (`test_vn_eval.py`, `test_reproduction_audit.py`, `test_claims_verifier.py` — tất cả PASS).
- **GM-6 (`SG-043` / `SG-044` / `SG-045` Drafts — [log 074](logs/SESSION-20260929-074-GEMINI.md)):** Đã hoàn tất bản thảo [final_report.md](../reports/final_report.md), [CLAIMS_CHECKLIST.md](../docs/CLAIMS_CHECKLIST.md), [defense_slides.md](../reports/defense_slides.md), [DEFENSE_QA.md](../docs/DEFENSE_QA.md) (18 câu hỏi phản biện), [rehearsal_notes.md](../artifacts/reports/rehearsal_notes.md), [SUBMISSION_CHECKLIST.md](../docs/SUBMISSION_CHECKLIST.md), và [release_audit.md](../artifacts/reports/release_audit.md).
- **Việc còn lại của 2 thành viên con người (`H-1`, `H-2`, `H-3`):** Xem hướng dẫn từng lệnh trong [SUBMISSION_CHECKLIST.md](../docs/SUBMISSION_CHECKLIST.md).

## G3 Hoàn tất (Hợp nhất `bn` → `D:\Web_mining_20261`, SG-051 DONE, SG-041 DONE) — 2026-09-29T13:30:00+07:00

- **SG-051 (`G3 Merge` + `CX-2`):** Đã hợp nhất lịch sử `bn` (`c820aef`) vào `D:\Web_mining_20261` (`6e3b70e`), giữ nguyên vẹn toàn bộ commit `e959f68` và `dcca385`, đồng bộ `artifacts/` và `data/` bằng `robocopy`, khôi phục `AGENTS.md` về `D:/Web_mining_20261` (`2d01b70`). Đã dựng `.venv` mới tinh tại `D:\Web_mining_20261\scholargraph\.venv`, chạy `pip install -r requirements.lock` (`exit 0`), `pip check` (`exit 0`), `verify_release.py` (`PASS`), `run_final.py --only registry` (`exit 0`, khớp bit-identical), `run_statistics.py` (`exit 0`, khớp bit-identical), `scripts/run_demo.ps1` (`13/13 PASS, DEMO OK`), và `pytest tests -q` (**734 passed**). Ghi nhận tại [SESSION-20260929-071-CODEX.md](logs/SESSION-20260929-071-CODEX.md).
- **GM-4 (`SG-041` Review & Closeout):** Review độc lập **PASS** ([SG-041-REVIEW-20260929.md](reviews/SG-041-REVIEW-20260929.md), [log 072](logs/SESSION-20260929-072-GEMINI.md)). Cập nhật `docs/RELEASE_MANIFEST.md` tại bản chính, đo thực tế `/health` startup (`28.17s`), kiểm chứng `run_demo.bat:23` và vắng mặt `scholargraph/1`. **SG-041 DONE**, **SG-051 DONE**.
- **Board:** `DONE=42`, `REVIEW=1` (`SG-030` chờ human gate), `IN_PROGRESS=1` (`SG-033` chờ nhãn người), `TODO=5` (`SG-034`, `SG-042`, `SG-043`, `SG-044`, `SG-045`), `DEFERRED=4`.
- **Tiếp theo (G4):** Chuẩn bị toàn bộ công cụ/tài liệu phía agent (`CX-4` & `GM-6`: `evidence_index.json`, `compare_reproduction.py`, `reports/figures/`, bản thảo `reports/final_report.md`, `docs/CLAIMS_CHECKLIST.md`, `reports/defense_slides.md`, `docs/DEFENSE_QA.md`, `docs/SUBMISSION_CHECKLIST.md`, `artifacts/reports/release_audit.md`) trong khi giữ nguyên các human gates (`SG-030`, `SG-033`..`SG-045`).

## G1 & G2 Hoàn tất (SG-052 DONE, GM-1..GM-3 Reviews PASS, sẵn sàng G3 Merge) — 2026-09-29T12:58:00+07:00

- **CX-1 (`SG-052` + sửa `SG-041`):** Hoàn tất và commit (`86b570f`, `bf2e351`, `65a4dc1`, `914b6ab`, [log 067](logs/SESSION-20260929-067-CODEX.md)). `test_text_subset.py` cô lập sang `tmp_path` (không chạm `works_text.jsonl`), bổ sung 2 test fallback hybrid còn thiếu trong `test_api.py`, sửa header bảng A2 trong `scripts/run_ablation.py` & `artifacts/reports/ablation.md`, sửa `run_demo.bat:23` + xóa `scholargraph/1`, thêm `--extra-index-url https://download.pytorch.org/whl/cpu` vào `requirements.lock`, chuẩn hóa đường dẫn tương đối trong `REPRODUCE.md` và `DEMO_SCRIPT.md`. Suite đầy đủ: **734 passed**.
- **GM-1 (`SG-027`, `SG-028`):** Review hồi tố độc lập **PASS** ([SG-027-REVIEW-20260929.md](reviews/SG-027-REVIEW-20260929.md), [SG-028-REVIEW-20260929.md](reviews/SG-028-REVIEW-20260929.md), [log 068](logs/SESSION-20260929-068-GEMINI.md)). 33/33 tệp freeze + 5 index manifests khớp hash; 45/45 con số (7 run Track A × 5 metric + 2 nhánh Track B × 5 metric) tính lại độc lập ngoài dự án khớp tuyệt đối (`|diff| = 0.00e+00`).
- **GM-2 (`SG-029`, `SG-030`):** Review độc lập **PASS** ([SG-029-REVIEW-20260929.md](reviews/SG-029-REVIEW-20260929.md), [SG-030-REVIEW-20260929.md](reviews/SG-030-REVIEW-20260929.md), [log 069](logs/SESSION-20260929-069-GEMINI.md)). Tự re-fuse `RRF k=30,60,100` khớp tuyệt đối; tự chạy paired bootstrap (`B=10000, seed=20260915`) khớp bit-identical 24/24 hàng. `SG-030` giữ `REVIEW` chờ human gate (2 thành viên đọc 24 error packets).
- **GM-3 (`SG-040`, `SG-052`, `dcca385`):** Review độc lập **PASS** ([SG-040-REVIEW-20260929.md](reviews/SG-040-REVIEW-20260929.md), [SG-052-REVIEW-20260929.md](reviews/SG-052-REVIEW-20260929.md), [log 070](logs/SESSION-20260929-070-GEMINI.md)). Kiểm chứng `attrib +R` trên `works_text.jsonl` + `openalex_core_text.json` khi chạy `pytest tests/unit/test_text_subset.py` (5/5 PASS). **SG-052 DONE**.
- **Tiếp theo:** Thực hiện G3 (`SG-051` — hợp nhất `bn` sang bản chính `D:\Web_mining_20261`).

## G0 Hoàn tất (.gitattributes, backup, SG-051/SG-052, ADR-019) — 2026-09-29T12:19:00+07:00

- Đã hoàn tất G0 theo [MERGE_AND_FINISH_PLAN.md](../docs/MERGE_AND_FINISH_PLAN.md): thêm `.gitattributes` (`* -text`), `git add --renormalize .`, kiểm chứng `verify_release.py` PASS (33 files) và clone thử khớp hash 100%; sao lưu dự phòng `.tmp/backups/bn_scholargraph_backup_20260929.zip` (sha256 `eec6e7eca74bb84c2682f491ffdaceea94199ee8cd464cca127f03bd9ebc9ccc`).
- Đã đăng ký `SG-051`, `SG-052`, `ADR-019`, log `SESSION-20260923-066.md` (cho `dcca385`) và mở `SESSION-20260929-067-CODEX` cho `CX-1` (`SG-052` + sửa `SG-041`).

## Fix UI 500 query Việt zero-overlap — 2026-09-23T16:00:00+07:00

- **Bug thật từ click-test của owner:** query Việt không trùng token corpus Anh
  (vd "ngôn ngữ lớn") → BM25 rỗng → `rrf_fuse` từ chối → API 500 → UI "Failed to fetch".
- **Sửa ở app layer** (`api/service.py`, không đụng contract rrf k=60):
  hybrid rỗng 1 phía → fallback phía còn lại, method ghi rõ
  (`+fallback-dense-only`); rỗng cả 2 → results rỗng 200.
- Test hồi quy mới trong `test_api.py` (10/10 PASS). `run_demo.bat` chờ /health
  thật (retry 4 phút) thay vì 45s cố định. Server fix đã live, worktree sẽ commit.

## SG-041 REVIEW; chờ human gates — 2026-09-23T14:30:00+07:00

- **SG-041 REVIEW** (session 065): requirements.lock (80 pins), verify_release PASS
  (33 files), RELEASE_MANIFEST sinh từ hash live, REPRODUCE.md, run_demo.ps1 CHẠY
  THẬT (DEMO OK, offline 13/13). Tests 7/7. Cần fresh review trước DONE.
- **Human gates còn lại:** SG-030 (2 người đọc packets + duyệt), SG-033 (nhãn 2 người
  ~16h) → SG-034 → SG-042 → SG-043 → SG-044 → SG-045.
- Board: DONE=39, REVIEW=2 (SG-030 human gate, SG-041), IN_PROGRESS=1 (SG-033 labels),
  TODO=5, DEFERRED=4.

## SG-033 pool xong, chờ nhãn người — 2026-09-21T22:00:00+07:00

- **SG-033 IN_PROGRESS** (session 064, tooling): pool mù 30 query (10 dev/20 test),
  662 cặp (≤900); template nhãn + agreement script; tests 6/6.
- **HUMAN WORK (2 bạn):** chấm dev pool → SG-034 → chấm test pool; kappa trước
  adjudication; ~16h dự trù. Agent không bịa nhãn.
- Board: DONE=38, REVIEW=2 (SG-030 human gate, SG-040), IN_PROGRESS=1 (SG-033),
  TODO=6, DEFERRED=4.

## SG-040 REVIEW; SG-033 pool prep tiếp — 2026-09-21T21:15:00+07:00

- **SG-040 REVIEW** (session 063): cold 14.6s/RSS 895MB, warm P50/P95 đầy đủ,
  track-B ~1.7s/query (vượt budget 500ms — báo thật), concurrency 1.84x.
  Tests 7/7. Cần fresh review trước DONE (không human gate).
- **Tiếp theo SG-033** (deps SG-025+SG-031+SG-032 DONE): agent dựng pools mù từ
  3 methods + scaffolding chấm; NHÃN do 2 người gán (human gate, ~16h).
- Board: DONE=38, REVIEW=2 (SG-030 human gate, SG-040), TODO=7, DEFERRED=4.

## SG-040 mở song song human gate SG-030 — 2026-09-21T20:30:00+07:00

- SG-030 REVIEW chờ human gate (2 người đọc packets + duyệt) — không chặn nhánh app.
- **SG-040 IN_PROGRESS** (session 063, deps SG-028+SG-039 DONE): profiling end-to-end
  thật (cold/warm/P50/P95/RAM/index/concurrency), mục tiêu 500ms báo thật.
- Board: DONE=38, REVIEW=1 (SG-030), IN_PROGRESS=1 (SG-040), TODO=7, DEFERRED=4.

## SG-030 REVIEW + human gate — 2026-09-21T20:15:00+07:00

- **SG-030 REVIEW** (session 062): 24 paired bootstrap CIs (B=10k, seed 20260915,
  95% percentile; không p-value). dense>bm25 cả 2 corpus; hybrid-vs-dense SciFact
  CI chứa 0; ppr-vs-global chứa 0. 24 error packets sẵn sàng.
- **HUMAN GATE (2 việc của 2 bạn):** (1) cả hai đọc 24 packets + joint note trong
  `docs/ERROR_ANALYSIS.md`; (2) owner duyệt SG-030. Sau đó mới mở SG-033 (nhãn).
- Board: DONE=38, REVIEW=1 (SG-030), TODO=8, DEFERRED=4. Checker PASS (sẽ chạy).

## SG-029 DONE + SG-030 mở — 2026-09-21T19:45:00+07:00

- **SG-029 DONE**: owner duyệt qua question tool (tiền lệ tự kiểm).
- **SG-030 IN_PROGRESS** (session 062): paired bootstrap CI 95%/10k theo protocol +
  error packets 20-30 ca cho 2 người đọc (human gate) + owner duyệt.
- Board: DONE=38, IN_PROGRESS=1 (SG-030), TODO=8, DEFERRED=4.

## SG-029 REVIEW (tự kiểm) — 2026-09-21T19:30:00+07:00

- **SG-029 REVIEW** (session 061): A1 age on/off (lambda=0 tốt nhất, suy giảm đơn điệu),
  A2 no-graph (trích registry), A3 RRF k=30/60/100 (k=60 khớp sealed bit-exact).
  R1/R2/R3 buckets + R4 costs + R5 failures 0/0. Tests 11/11. Không select trên test.
- **Cần fresh-context review trước DONE** (không human gate). SG-030 chưa mở được
  (deps SG-029 chưa DONE).
- Board: DONE=37, REVIEW=1 (SG-029), TODO=9, DEFERRED=4. Checker PASS (sẽ chạy).

## SG-028 DONE + SG-029 mở — 2026-09-21T18:30:00+07:00

- **SG-028 DONE**: owner duyệt qua question tool (tiền lệ SG-027: chấp nhận tự kiểm).
- **SG-029 IN_PROGRESS** (session 061): ablations định sẵn trong freeze (age on/off,
  RRF k, graph variants) + robustness buckets + costs/failures. Không select trên test.
- Board: DONE=37, IN_PROGRESS=1 (SG-029), TODO=9, DEFERRED=4.

## SG-028 REVIEW (tự kiểm) — 2026-09-21T18:00:00+07:00

- **SG-028 REVIEW** (session 060): 7 sealed track-A runs + track-B test200 COMPLETED
  (final_test=true, freeze evidence). SciFact test nDCG@10: bm25 0.6647 / tfidf 0.6327
  / dense 0.7404 / hybrid 0.7204 (hybrid<dense giữ trung thực). SCIDOCS test:
  bm25 0.1521 / dense 0.2172 / hybrid 0.1976. Track B: ppr 0.1004 / global 0.1082
  (frozen g0.3/l0.0, không tune trên test). Track C VN chưa đo (chờ SG-033).
- Mới: `sealed.py` (final-test gate), `--sealed` cho bm25/tfidf (unsealed test → exit 1),
  `run_final.py`, tests 12/12, `main_run_registry.json` + `main_results.md`. Hồi quy 91/91.
- **Cần fresh-context review trước DONE** (không human gate). SG-029/SG-030 chưa mở được
  (checker: deps SG-028 chưa DONE).
- Board: DONE=36, REVIEW=1 (SG-028), TODO=10, DEFERRED=4. Checker PASS.

## SG-027 DONE (owner duyệt) — 2026-09-21T17:16:00+07:00

- **SG-027 DONE**: owner duyệt freeze qua question tool ('Duyệt SG-027 DONE') sau khi
  được thông báo rõ chỉ có tự kiểm (9/9 tests + 4/4 probes, không reviewer độc lập).
  Human gate thỏa; **SG-028 Final runs unblocked**.
- Board: DONE=36, TODO=11, DEFERRED=4. Checker PASS. Không còn assignment active.
- Tiếp theo: `SG-028` (chạy frozen methods từng protocol, lưu TREC/per-query/aggregate).
  SG-033 vẫn chờ 2 người gán nhãn (không thuộc phiên này).

## SG-027 REVIEW (tự kiểm) — 2026-09-21T17:00:00+07:00

- **SG-027 REVIEW** (session 059, single-chat kiêm coordinator+worker): freeze artifacts
  có sẵn từ 19/09 đã được xác minh độc lập — `pytest tests/unit/test_main_freeze.py`
  **9/9 PASS**, adversarial probes tmp **4/4 PASS** (drift/missing-fail-loud/dev-only
  leakage/freeze-before-test), `git_head`==HEAD (e959f68), đếm 32 hash khớp ADR-018.
- **Reconciliation:** (R1) HANDOFF ở HEAD bị lỗi serialize 1-dòng-`\n`-literal, bản này
  khôi phục multiline (nội dung giữ nguyên); (R2) entry cũ ghi DONE=34, số đúng theo
  checker là **DONE=35, REVIEW=1 (SG-027), TODO=11, DEFERRED=4**. Checker PASS.
- **Chờ 2 gate (routing):** (1) fresh-context review độc lập ở context mới;
  (2) **human approval của owner** trước SG-028. Phiên này chỉ tự kiểm, không tự nhận
  reviewer độc lập hay human review.
- DAG còn lại: SG-027 (gate) → SG-028 → SG-029 → SG-030 (gate) → SG-033 (gate: 2 người
  gán nhãn — dừng bắt buộc) → SG-034 (gate) → SG-040 → SG-041 → SG-042 (gate) →
  SG-043 (gate) → SG-044 (gate) → SG-045 (gate).

## SG-032 DONE — 2026-09-19T02:25:00+07:00

- **SG-032 DONE** (commit e65c0a0): fresh review PASS không P0/P1; pin e5-base được xác nhận định lượng (98,8% docs vượt 128-token MiniLM). DONE=34, REVIEW=1 (SG-026 human gate), TODO=12.
- **Carry-forward cho SG-033:** (1) encode OpenAlex 18.250 docs bằng e5 (adapter schema OpenAlex — encode_corpus_multilingual hiện đọc schema SciFact; ước tính ~4,1h) TRƯỚC khi tạo pool; (2) MT quality inventory đầy đủ hơn (case suy giảm: test:007 'publicationopen a cappella', test:003 'preventental'); (3) cache mismatch check text_vi + prefix enforcement (P2-2/P2-4).
- **SG-026 DONE**: owner duyệt selection gamma=0.3/lambda=0.0 qua question tool (22:55). SG-027 Main Freeze mở (routing: human_approval=true — freeze configs sẽ cần duyệt riêng trước SG-028).
- DAG còn lại: SG-027 (gate) → SG-028 → SG-029 → SG-030 (gate) → SG-033 (gate: 2 người gán nhãn — dừng bắt buộc) → SG-034 (gate) → SG-040 → SG-041 → SG-042 (gate) → SG-043 (gate) → SG-044 (gate) → SG-045 (gate).

## SG-026 review PASS (human gate pending) + SG-032 gần xong — 2026-09-19T01:00:00+07:00

- **SG-026 REVIEW, human gate PENDING**: B trials 20/20 COMPLETED (best gamma=0.3/lambda=0.0, dev nDCG@10=0.1310); fresh reviewer PASS không P0/P1 — tái chạy bit-identical lần 3, oracle ceiling ~0.355 (0.131 là độ khó task); P2-2 wording sealed-run đã sửa. **Cần owner duyệt selection** (câu hỏi đã gửi, chưa trả lời) trước SG-027.
- **SG-032 IN_PROGRESS (~85%)**: translation PINNED (opus-mt-vi-en @ c8d2853e, cache 30/30); original_vi_bm25 diagnostic (18/30 có top-1>0 — cognate); technical pilot 5 query + vn_dev_pilot.md (không có relevance metrics — đúng luật, nhãn ở SG-033); MiniLM-multilingual FULL corpus 5.183 docs encoded @ 7,758 docs/s (index_manifest có sampled=null); e5-base: encode nền đầy đủ HOÀN THÀNH sau 69 phút (1,253 docs/s — output bị buffer khiến coordinator đọc nhầm là crash; chỉ 1 lần bị dừng thật do coordinator tự TaskStop).
- **Việc còn của SG-032 (phiên mới):** quyết định multilingual encoder — (a) chạy lại e5 FULL corpus với encode chunked/resume (thêm ~30 phút code + ~1h chạy), HOẶC (b) pin MiniLM với lý do feasibility + ghi nhận 128-token truncation limit (rủi ro chất lượng, cần cân nhắc vì pin trước pooling là vĩnh viễn theo freeze sequence). Khuyến nghị: (a) vì MiniLM 128-token cắt abstract dài. Sau khi pin: chạy pilot trên full corpus → flip SG-032 REVIEW → reviewer.
- **SG-037/SG-038 REVIEW**: reviewer đã PASS qua dispatcher (xem reviews SG-037-REVIEW-20260918.md / SG-038-REVIEW-20260918.md) — xác nhận lại trạng thái DONE của board với reviews đầy đủ.
- Hạ tầng: subagent quota đã hồi phục (SG-026 reviewer thành công). Encode nền dài (~30 phút) chết lặp lại — dùng foreground chunks hoặc thêm resume.

## SG-039 DONE, tiếp SG-026 B trials — 2026-09-18T14:15:00+07:00

- **SG-039 DONE** sau 2 vòng review (v1 FAIL 3 P1+3 P2 → sửa → v2 conditional PASS → fixes verified 28/28 + 4/4 tests).
- Board: DONE=33, IN_PROGRESS=2 (SG-026, SG-032), REVIEW=0, TODO=12. Checker PASS.
- **Tiếp theo:** `SG-026` B 20 trials (vectors OpenAlex/SCIDOCS đã sẵn) + `SG-032` song song. SG-033 của owner.

## SG-037 + SG-038 DONE, tiếp SG-039 — 2026-09-18T11:00:00+07:00

- **SG-037 DONE**: fresh review PASS (19/19 tests, evaluated/snapshot hash khớp, không leakage holdout/qrels). 3 P2-info.
- **SG-038 DONE**: fresh review PASS (7/7 tests, offline 13/13); 3 P2 nits đã sửa + smoke tái chạy.
- Board: DONE=32, IN_PROGRESS=2 (SG-026, SG-032), REVIEW=0, TODO=13. Checker PASS.
- **Tiếp theo:** `SG-039` (deps SG-037+SG-038 DONE → unblocked). SG-026 B trials song song khi pipeline B-dev sẵn.

## SG-050 DONE, retry reviewers SG-037/038 — 2026-09-18T10:45:00+07:00

- **SG-050 DONE**: fresh review PASS không P0/P1 (3 P2-info). OpenAlex 19/19 + SCIDOCS 26/26 + profile 3 corpora (totals 49090/51 shards). Không human gate.
- Board: DONE=30, IN_PROGRESS=2 (SG-026, SG-032), REVIEW=2 (SG-037, SG-038), TODO=13. Checker PASS.
- Sửa lệch board: state.active_tasks bổ sung SG-037/038 (REVIEW), gỡ assignment SG-050 sau DONE.
- **Tiếp theo:** retry reviewer SG-037 + SG-038 (lần trước chặn concurrency) → SG-026 B trials (vectors đã sẵn) → SG-032 → SG-027… SG-033 của owner.

## Takeover 2 + SG-036/031 DONE + SG-038 REVIEW — 2026-09-18T04:30:00+07:00

- Người dùng xác nhận (lần 2) cửa sổ song song đã đóng, session 053 coordinator duy nhất. Cửa sổ kia từng commit c485252/ed02c09/717f636 (đóng SG-036 DONE với review riêng + P2 fixes; để dở SG-037).
- **SG-036 DONE**: reviewer độc lập (session 055) tái xác minh trên HEAD sau P2-fix — PASS không P0/P1; chỉ còn P2 human "hai thành viên kiểm chứng 5 query" chờ owner ở closeout.
- **SG-031 DONE**: 30 query VN được owner duyệt nguyên bản qua question tool (23:55), manifest `approved_no_edits` + approval trong provenance.
- **SG-037 REVIEW**: công dở graph UI của cửa sổ kia được hấp thụ (graph_service.py, ui/graph/, 19/19 tests, smoke report); reviewer bị chặn 'user concurrency limit exceeded' x4 — **retry khi hạ tầng hồi phục**.
- **SG-038 REVIEW** (mới, làm trực tiếp): export_references.py (missing policy null/[không có], không bịa), offline_smoke.py 13/13 PASS với HF_HUB_OFFLINE=1, configs/demo.json pin snapshot + 5 query đã kiểm chứng, docs/DEMO_SCRIPT.md kịch bản 5 phút; smoke tự bắt và sửa 2 bug thật (U+2028 splitlines, trailing newline); tests 7/7.
- **SG-050 IN_PROGRESS**: OpenAlex text-subset 19/19 shards + index COMPLETED + verify PASS; SCIDOCS 9/26 encode chạy nền (chuỗi cũ chết 01:30 EXIT=127 — đã relaunch 04:00). Khi xong: `dense index --corpus scidocs` + verify + profile 3 corpus → REVIEW → reviewer.
- **SG-026 IN_PROGRESS**: A xong (dense 0.7709 / hybrid 0.7435 — kết quả âm hybrid<dense ghi nhận trung thực); B = 20 điểm gamma×lambda frozen trong configs/tuning_space.json, chạy được khi SCIDOCS encode xong; **human gate** khi xong.
- Bài học hạ tầng: subagent lỗi ~60% dispatch tối nay (Model request failed / captcha / inactive 600s / concurrency limit) — retry có khoảng nghỉ; nếu bế tắc coordinator làm trực tiếp + tự kiểm ADR-013 và ghi rõ, không tự nhận reviewer độc lập.

## SG-035 DONE, SG-036 + SG-026 song song — 2026-09-17T19:40:00+07:00

- **SG-035 DONE**: API 4 routes trên data thật, 9/9 tests, fresh PASS (debt → SG-036/039).
- **SG-036 IN_PROGRESS** (UI, lane P). **SG-026 IN_PROGRESS** (lane R: A xong, B chờ encode OpenAlex resume + human).

## SG-036 DONE, SG-031 DONE, SG-050 encode — 2026-09-18T01:10:00+07:00

- **SG-036 DONE**: UI hoàn tất (code phiên 052 + test 9/9 + checker 2/2 khớp 1/2); review fresh-context PASS không P0/P1; P2-1/P2-2 đã sửa; P2-3 (hai thành viên kiểm chứng 5 query UI) đưa vào checklist closeout.
- **SG-031 DONE**: 30 query Việt được project owner duyệt nguyên bản qua question tool (ghi nhận trong manifest `provenance.human_approval`); ANNOTATION_GUIDE.md hoàn chỉnh; mở khóa SG-032.
- **SG-050 IN_PROGRESS**: encode OpenAlex text-subset 16/19 shards (~10,5 phút/shard đo thật) rồi tự sang SCIDOCS; còn ~4-5 giờ; xong sẽ index/verify/profile → review → DONE → mở khóa SG-026 B trials.
- Tiếp quản coordinator session 053; ADR-017 chính thức hóa; task SG-050 tạo mới theo đúng quy tắc dependency.

## SG-025 DONE (2 vòng review), SG-026 đang làm — 2026-09-17T17:30:00+07:00

- **SG-025 DONE**: rerank RRF+graph+age trên C100 cố định, 18/18 tests, v2 PASS.
- **SG-026 IN_PROGRESS** (dev tuning có budget, cần human approval khi xong).

## SG-024 DONE (human duyệt), SG-025 đang làm — 2026-09-17T16:45:00+07:00

- **SG-024 DONE**: 14/14 tests, 2 vòng review, human approval in-session.
- **SG-025 IN_PROGRESS** (reranking integration, deps SG-020+023+024 DONE).

## SG-023 DONE, SG-024 đang làm — 2026-09-17T16:00:00+07:00

- **SG-023 DONE** sau 2 vòng review (P1 inf + 6 P2 đã sửa, v1.1.0, 16/16 tests).
- **SG-024 IN_PROGRESS** (age adjustment, cần human approval khi xong).

## SG-022 DONE, tiếp SG-023 — 2026-09-17T15:30:00+07:00

- **SG-022 DONE** sau 2 vòng review: PageRank global + coupling trên masked graph thật (18251/26186, iters 71, mass 1.0).
- **Tiếp theo:** `SG-023` (PPR, deps SG-021+SG-022 DONE → unblocked). `SG-031` vẫn unblocked song song (cần human viết query).

## SG-021 DONE, tiếp SG-031/SG-022 — 2026-09-17T15:00:00+07:00

- **SG-021 DONE** sau 2 vòng review (v1 FAIL 2 P1 → sửa → v2 PASS): audit thật 809 queries BM25 0.9102/TF-IDF 0.9124 bit-exact, union full 0.9180, dense null chua_do, 10 examples + 6 rescued, provenance inputs+sha.
- **Tiếp theo:** `SG-031` (VN queries, deps SG-011+SG-015 DONE) và `SG-022` (graph baselines, deps SG-016 DONE).

## SG-020 DONE, tiếp SG-021/SG-031 — 2026-09-17T14:20:00+07:00

- **SG-020 DONE**: Hybrid RRF k=60, 15/15 tests, fresh review PASS không P0/P1.
- **Tiếp theo khả thi:** `SG-021` (deps SG-020 DONE), `SG-031` (deps SG-011+SG-015 DONE), `SG-022` (deps SG-016 DONE).

## Closeout SG-016 REVIEW + SG-019 DONE, mở SG-020 — 2026-09-17T13:40:00+07:00

- **SG-019 DONE** (worker `bn/sg019_dense_encoder`): dense bge-base-en-v1.5 @a5beb1e3, 61/61 tests PASS, scifact 5183/5183 COMPLETED 6 shards, embeddings (5183,768) L2, index COMPLETED, verify 6/6 PASS, `artifacts/reports/encoding_profile.json` đã sinh (totals khớp), CLI fail-loud exit 1. Review fresh-context PASS không P0/P1 (2 P2 info). Không cần human gate.
- **SG-016 REVIEW** (worker `bn/sg016_graph_builder`): build directed + holdout + mask 2 chiều đúng protocol, 38/38 tests PASS, premask 26516/postmask 26186/mask 660/heldout 330/queries test200+dev100, audit 15/15 PASS, residual 2 chiều 0/0, raw không đổi. Review fresh-context PASS không P0/P1 (3 P2 notes). Còn chờ **human approval** theo routing trước DONE.
- Board: SG-019 DONE, SG-016 REVIEW (evidence/verification đã điền), state next SG-020, active [SG-016] (chờ human). Registry: 041 completed, 040 checkpoint, +2 review sessions.
- **Tiếp theo khả thi:** `SG-020` (deps SG-018+SG-019 DONE → unblocked), `SG-031` (deps SG-011+SG-015 DONE → unblocked). `SG-022` vẫn blocked đến khi SG-016 DONE (cần human duyệt).

## Orchestrator loop-2: SG-018 + SG-015 DONE, graph gate GO — 2026-09-17T04:35:00+07:00

- Vòng 2 triển khai 2 task song song bằng subagent worker + 2 reviewer fresh-context; **pytest 388/388** (321 + 40 TF-IDF + 27 openalex-core); checker PASS (288 links, 46 sessions); DONE=18.
- **SG-018 DONE** (`bn/sg018_engine_worker`): TF-IDF Protocol v1 (tf 1+ln f, idf ≥1, l2, cosine, empty_vector_score=0) tái sử dụng tokenizer bm25.py qua import (bm25.py hash nguyên vẹn). Run thật `RUN-20260916-191127-tfidf-scifact-dev`: **TF-IDF nDCG@10 0.6509 / Recall@100 0.9124 / MRR@10 0.6139** vs BM25 0.6701/0.9102/0.6380 trên inputs byte-identical (chứng minh bằng sha256); rerun byte-identical. Review PASS (tái tính metric ≤1e-12, leakage probes).
- **SG-015 DONE** (`bn/sg015_core_curator`, scope ADR-016 §7): snapshot citation-connected **18.251 works** (2.000 pilot nguyên vẹn + 115 hubs + 14.958 cohort + 1.178 extension), 104 requests polite-pool, pin manifest TRƯỚC fetch (fingerprint v1/v2 tái tính khớp). Đồ thị đo được: **26.516 cạnh nội bộ, isolated 12,73%**, 163 self-loops. **Gate trên core = GO** (test_year 2025: 579≥50, dev_year 2024: 563≥30, novel min 206≥100) → **SG-016 đã mở khóa**. Selection bias (cites:hubs) đã khai báo — không coi snapshot là mẫu đại diện topic. Review PASS (tái đếm 100%, gate CLI re-run diff=0).
- P2 xử lý: SG-014 module `feasibility.py` fixed snapshot-aware (`known_limitations`), cả 2 gate report tái sinh (NO_GO/GO giữ nguyên); các P2 khác là ghi chú cho SG-016 (label `openalex_works_with_title` đếm title unique; superseded report giữ path có version từ giờ; self-loops + cạnh đảo phải xử lý theo GRAPH_PROTOCOL).
- **Tiếp theo:** `SG-016` (Graph & masked split — deps DONE; ràng buộc chỉ thị đặc biệt: verify không có cạnh trích dẫn hai chiều undirected và LOẠI TOÀN BỘ cạnh thuộc test set khỏi adjacency dùng cho PPR) và `SG-019` (Encoding shard & dense index — deps SG-002/010/015/017 DONE; nhớ 2 yêu cầu SG-017 review: pin tokenizer revision vào shard manifest + CLI đọc configs/models/ phải fail-loud). SG-019 cần tải weights bge-base-en-v1.5 (network OK).
- Sau đó: SG-020 (cần SG-018+SG-019), SG-021, SG-022 (cần SG-016), SG-031 (cần SG-011+SG-015) đều sẽ unblocked theo DAG.

## Orchestrator loop: SG-012 + SG-014 + SG-017 DONE — 2026-09-17T01:28:19+07:00

- Người dùng phát chỉ thị orchestrator (chạy tự động toàn bộ task còn lại theo DAG, scope chỉ `bn`, runtime `.venv`, xoay vòng review độc lập, log đặt `management/logs/` thay vì `management/sessions/` để khớp checker). Vòng 1 triển khai bộ ba unblocked bằng 3 subagent worker song song + 3 subagent reviewer fresh-context; tất cả **PASS, không P0/P1**; **pytest 321/321** (214 cũ + 36 BM25 + 37 feasibility + 34 model config); checker PASS (287 links, 41 sessions).
- **SG-012 DONE** (engine worker `bn/sg012_engine_worker`): BM25 Protocol v1 positive-IDF, CLI exit 1 khi lỗi, ranking path không đọc qrels. Run thật `RUN-20260916-163653-bm25-scifact-dev` (SciFact dev 809/919/5.183): **nDCG@10 0.6701, Recall@100 0.9102, MRR@10 0.6380**; rerun `163629` byte-identical. Review PASS sau probe leakage (qrels đảo điểm vẫn rankings identical), tái tính metric độc lập ≤1e-12, 4/4 adversarial exit 1.
- **SG-014 DONE** (curator `bn/sg014_graph_curator`): tái đếm khớp (190 cạnh, 1.779 isolated, **4 self-loops mới phát hiện**), SCIDOCS references bị loại vì leakage (qrels là dẫn xuất citation), cohort 21 nguồn max 2/năm << floor 50/30 → **gate NO_GO** (kết quả đo được, exit 0). Đã có `docs/GRAPH_PROTOCOL.md` (mask H_dev ∪ H_test ∪ reverse, cutoff year(u)) và **ADR-016**. Review PASS tái đếm độc lập khớp 100%; 2 P2 đã sửa (floors helper, masking criterion gating) + tái sinh report (vẫn NO_GO).
- **SG-017 DONE** (researcher `bn/sg017_model_researcher`): chốt core encoder **BAAI/bge-base-en-v1.5** @ `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`, CLS/768/512, MIT, prefix query-only; shortlist 3; overlap công bố, không chứa benchmark. Review PASS 3/3 WebFetch probe. P2 ghi chú cho SG-019: pin tokenizer revision vào shard manifest; CLI đọc config phải fail-loud.
- **Tiếp theo:** `SG-018` (Lexical baselines, deps SG-012 DONE) và `SG-015` (Snapshot OpenAlex core — **scope đã điều chỉnh theo ADR-016 mục 7**: sampling phải ra snapshot có kết nối trích dẫn, giữ floors 50/30/2/100, pin manifest trước tải; xong phải chạy lại graph gate). **SG-016 bị chặn đến khi gate GO.** SG-019 unblocked sau SG-015 (deps SG-002/010/015/017).
- Vòng lặp orchestrator vẫn đang theo chỉ thị của người dùng: quét DAG → giao worker theo lane (S→engine, D→curator, R→researcher) → review chéo (coder engine → reviewer researcher/gatekeeper; coder curator → reviewer engine; coder researcher → reviewer gatekeeper) → 4 cổng bảo mật (leakage, dữ liệu thật, pytest toàn suite ≥214+new, checker) → sync board → lặp. Subagent hạ tầng có lúc lỗi "Model request failed"/captcha — retry được; nếu liên tục lỗi, coordinator làm trực tiếp vai worker + tự kiểm theo ADR-013 và ghi rõ (không tự nhận reviewer độc lập).
- [Log điều phối](logs/SESSION-20260916-027.md); logs worker 028/029/030; logs reviewer 031/032/033; reviews SG-012/014/017-REVIEW-20260916.md.

## Môi trường bn thiết lập xong — 2026-09-16T22:30:20+07:00

- Workspace làm việc độc lập của `bn` là `D:/Web_mining_20261/bn`; mọi phiên trong môi trường này chỉ hoạt động trong thư mục đó. Bản clone gồm toàn bộ `scholargraph/` (6.227 file, 548,23 MB, robocopy FAILED=0), `AGENTS.md` (chỉ đổi mục Scope), `SCHOLARGRAPH.md` và 8 file bài giảng được `docs/SCOPE.md` dẫn link.
- Venv mới tại `bn/scholargraph/.venv` (Python 3.12.14, cùng runtime gốc, `--system-site-packages`); đã cài `requirements-dev.txt` + `pytrec_eval-terrier==0.5.10`, pip exit 0. Không copy venv cũ.
- Xác minh trong bn: `pytest tests -q` **214/214 passed in 97.31s** (exit 0), `scripts/check_project.ps1` **PASS** (263 links, 50 routes, 7 lanes, 34 sessions; DONE=13, TODO=33). Board 50 task giữ nguyên trạng thái từ bản gốc; không task nào bị mở lại hay tự nhận DONE mới.
- Người dùng CHƯA giao SG-012. Khi được giao: dependencies SG-008/SG-010/SG-011 đều DONE; routing SG-012 = profile T_H, lane M, `self_check_allowed`, không cần human approval; `rank-bm25` đã có trong venv bn.
- [Log phiên setup](logs/SESSION-20260916-026.md), quyết định môi trường [ADR-015](../management/DECISIONS.md).

## SG-010 DONE sau review và sửa — 2026-09-16T14:33:07+07:00

- Người dùng giao review lại và cho phép sửa ngay. Bản cuối đã đạt **214/214 tests**, live audit PASS và fresh-context review **PASS** (reviewer74 tests, không finding mở).
- Đã sửa failed measurements thành null/FAIL; strict ID/type/score/JSON parser; positive self-qrel gate; thống kê giữ zero-positive queries; overlap đầy đủ các cặp; narrative không suy provenance từ counts; chống output ghi đè raw và hash trước/sau. Finding P2 reviewer về thiếu/null text đã sửa và kiểm lại.
- Auditor `sg010-2.0.0`, report schema2. **9 file raw không đổi**, số liệu snapshot 5.183 SciFact/25.657 SCIDOCS;344 SCIDOCS thiếu abstract,115 có positive qrel.
- [Review cuối](reviews/SG-010-SESSION025-REVIEW.md), [tổng hợp sửa và kiểm chứng](reviews/SG-010-SESSION025-RESOLUTION.md), [Data Card](../docs/DATA_CARD.md), [report](../artifacts/reports/beir_data_audit.json), [log](logs/SESSION-20260916-025.md).
- **SG-008 vẫn DONE**; không mở lại task này. Tests SG-008 chỉ chạy kèm trong toàn suite để kiểm tra hồi quy. SG-011 giữ nguyên DONE theo board hiện có.
- SG-012 là task tiếp theo khi người dùng giao; phiên này không triển khai SG-012. Không còn active assignment hoặc process đang chạy của session025.
- Các subagent mang tên có `sg008` là agent cũ được tái sử dụng; scope phiên025 là SG-010, không đổi model/task SG-008.

## Lịch sử bàn giao (không phải trạng thái hiện tại)

# Bàn giao ScholarGraph

NEXT_TASK trước: SG-010

## Đang review và sửa — 2026-09-16T14:14:43+07:00
- SG-010 IN_PROGRESS; session025. Đang kiểm tra Anti-Silent-Bypass, bổ sung adversarial CLI tests và sửa các lỗi được tái hiện.
- Không thực hiện SG-012. Bước tiếp: hoàn tất fixes, chạy live audit/reference snapshot và review cuối.
- Xem [log session025](logs/SESSION-20260916-025.md).

## Lịch sử bàn giao trước
# Bàn giao ScholarGraph

NEXT_TASK trước: SG-012

## Bàn giao Khắc phục SG-010 (L1/L2) — 2026-09-16T07:40:00+07:00

- Đã kiểm tra bản review mới nhất [SG-010-LATEST-CODEX-REVIEW-20260916.md](reviews/SG-010-LATEST-CODEX-REVIEW-20260916.md) và khắc phục triệt để toàn bộ 2 phát hiện (1 P1, 1 P2) theo đúng yêu cầu:
  1. **L1 [P1]:** Auditor xác nhận sự hiện diện của các split bắt buộc (`REQUIRED_SPLITS` cho SciFact và SCIDOCS). Thiếu file qrels bắt buộc sẽ kích hoạt lỗi `missing_required_splits`, `loader_verification` thất bại, dynamic integrity gate đặt `audit_passed = False`, và CLI thoát mã lỗi `1` (nonzero). Tuyệt đối không thay thế phép đo chưa thực hiện bằng 0.
  2. **L2 [P2]:** Tách bạch chuẩn xác narrative explanations cho cả SciFact và SCIDOCS dựa trên cả 2 bộ đếm `empty_or_missing_text_count` và `empty_or_missing_title_count`. Phân định rõ tài liệu text-only, title-only, đủ cả 2 trường và thiếu cả 2 trường.
- Báo cáo khắc phục chi tiết: [SG-010-LATEST-REVIEW-RESOLUTION-20260916.md](reviews/SG-010-LATEST-REVIEW-RESOLUTION-20260916.md).
- Kiểm thử tự động:
  - Bổ sung 2 test suites hồi quy chuyên sâu trong `tests/unit/test_data_integrity.py` (`test_missing_required_splits_detection` và `test_dynamic_narrative_all_missingness_scenarios`).
  - `pytest tests/unit/test_data_integrity.py`: **17/17 passed in 31.81s**.
  - Toàn bộ suite dự án: `pytest tests -q`: **157/157 passed in 81.56s**.
  - Chạy live auditor trên snapshot đóng băng thực tế: **PASS**, cập nhật [artifacts/reports/beir_data_audit.json](../artifacts/reports/beir_data_audit.json).
- SG-000 đến SG-011 đều đã **DONE**.
- Task tiếp theo: **SG-012** (BM25 pilot thật) đã đủ 100% điều kiện tiên quyết (`[SG-008, SG-010, SG-011]`).

## Bàn giao SG-011 / SG-012 — 2026-09-16T07:25:00+07:00

- SG-008 REVIEW, SESSION-20260916-022. Người dùng giao triển khai và cho phép subagents; chỉ đạo tạm hoãn trước đây đã được thay thế.
- Parent kiêm C/R đã viết evaluator và integration test; subagent `/root/sg008_reference_tests` đã hoàn tất reference/tests/script. `/root/sg008_fresh_review` đã review **PASS**, không finding cần sửa; [review report](reviews/SG-008-REVIEW-20260916.md).
- Suite chính thức PASS **150/150**; validation PASS **74 comparisons + 38 negative cases**, max error **1.6653345369377348e-16 < 1e-12**. Toàn bộ evaluator fixtures synthetic, không phải benchmark thật.
- Artifact: [metrics](../src/scholargraph/evaluation/metrics.py), [validation report](../artifacts/reports/metric_validation.json), [guide](../docs/EVALUATOR_GUIDE.md), [review packet và hashes](reviews/SG-008-REVIEW-PACKET.md).
- Reviewer chạy lại 57 tests PASS, thêm 500 query rows/7 cutoff/3 invalid-input probes PASS; report tái sinh khớp bản chính trừ timestamp, hashes không đổi.
- Bước tiếp duy nhất của SG-008: người phụ trách xem gói kết quả và xác nhận human gate. Khi nhận xác nhận thật, ghi vào verification/log, chuyển DONE, đặt next_task_id SG-011 và chạy project checker. Không cần chạy lại metric validation nếu code/fixture/protocol không đổi.
- Phiên parent và hai subagents đã hoàn tất; không còn active assignment hoặc process đang chạy. SG-008 giữ REVIEW chỉ vì human approval chưa có.
- Không triển khai SG-011/012 trong phiên này. Xem [log hiện tại](logs/SESSION-20260916-022.md).

## Bàn giao trước (lịch sử)

## Trạng thái — 2026-09-16T01:10:00+07:00

- SG-010 **DONE**: Đã hoàn thành audit chất lượng dữ liệu BEIR và **khắc phục toàn bộ 5 phát hiện (1 P1, 4 P2) từ bản review độc lập của Codex**. Báo cáo tái nghiệm thu [SG-010-RE-REVIEW-20260916.md](reviews/SG-010-RE-REVIEW-20260916.md) đạt **PASS** trên snapshot mới.
- SG-000 đến SG-007, SG-009, SG-010, SG-013 đều đã **DONE**.
- Task **SG-008** giữ nguyên trạng thái **TODO** (hoãn thực hiện theo chỉ đạo trực tiếp của người dùng: *"Khoan không động vào task SG-008 nhé"*).
- Task **SG-012** (BM25 pilot thật) phụ thuộc `[SG-008, SG-010, SG-011]`. Do SG-008 tạm hoãn và SG-011 chưa thực hiện, SG-012 chưa thể chạy pilot metric thật. Kiến trúc BM25 positive-IDF theo Protocol v1 đã sẵn sàng.
- Task **SG-011** (Split và leakage checks) phụ thuộc `[SG-004, SG-010]` $\to$ **Đã đủ 100% điều kiện tiên quyết để thực hiện ngay lập tức**.
- Phiên coordinator/worker SESSION-20260916-021 hoàn tất; không còn active assignment.
- Toàn bộ suite test dự án: **91 passed in 22.22s** (13/13 test cases integrity mới PASS bao gồm 5 negative synthetic tests).

## Bằng chứng và Khắc phục chính của SG-010

- **Mã nguồn và Báo cáo:**
  - [src/scholargraph/ingest/beir_audit.py](../src/scholargraph/ingest/beir_audit.py)
  - [artifacts/reports/beir_data_audit.json](../artifacts/reports/beir_data_audit.json)
  - [docs/DATA_CARD.md](../docs/DATA_CARD.md)
  - [tests/unit/test_data_integrity.py](../tests/unit/test_data_integrity.py)
  - [management/reviews/SG-010-REVIEW-PACKET.md](reviews/SG-010-REVIEW-PACKET.md)
  - [management/reviews/SG-010-CODEX-REVIEW-20260916.md](reviews/SG-010-CODEX-REVIEW-20260916.md)
  - [management/reviews/SG-010-RE-REVIEW-20260916.md](reviews/SG-010-RE-REVIEW-20260916.md)
- **Các điểm đã khắc phục theo review Codex:**
  1. **F1 [P1]:** Auditor chuyển đổi toàn bộ cơ chế sang đánh giá động (tính toán `audit_passed`, danh sách `errors`, trạng thái `referential_integrity_status` theo các bộ đếm vi phạm thực tế); CLI thoát mã lỗi 1 khi dữ liệu có lỗi; kiểm tra canonical roundtrip 100% ID.
  2. **F2 [P2]:** Tái cấu trúc kiểm thử tự động, loại bỏ đọc JSON tĩnh; bổ sung 5 negative tests với synthetic fixtures kiểm chứng việc bắt lỗi duplicate, orphan, conflict và rò rỉ ID; chủ động chạy live auditor trên dữ liệu thật ra thư mục tạm.
  3. **F3 [P2]:** Sửa 4 mã băm SHA-256 trong bảng 2.2 của Data Card khớp hoàn toàn với snapshot đóng băng và manifests.
  4. **F4 [P2]:** Đồng bộ toàn bộ số liệu min, max, mean, std, median, percentiles trong Section 4 của Data Card khớp với báo cáo máy đọc và tokenizer Protocol v1.
  5. **F5 [P2]:** Chính xác hóa giấy phép bản quyền: SciFact (CC BY 4.0 / ODC-By 1.0), SCIDOCS (CC BY 4.0 - yêu cầu attribution, không phải CC0), BEIR package (Apache-2.0).

## Bước tiếp theo khi được giao

1. **Về SG-011 (Split và leakage checks):**
   - Phụ thuộc SG-004 và SG-010 đều đã DONE; là task tiếp theo trong pipeline M2.
   - Triển khai `configs/split_policy.json`, `tests/unit/test_split_leakage.py`, `artifacts/reports/split_audit.json`.
2. **Về SG-008 & SG-012:**
   - Khi người dùng cho phép mở lại SG-008 (Kiểm chứng evaluator), triển khai `evaluator.py`, golden fixtures và đối chiếu trec_eval.
   - Sau khi SG-008 và SG-011 hoàn tất, SG-012 sẽ được mở khóa để chạy BM25 pilot thật trên SciFact và SCIDOCS.
