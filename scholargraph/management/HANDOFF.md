# Bàn giao ScholarGraph

NEXT_TASK: SG-018

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
