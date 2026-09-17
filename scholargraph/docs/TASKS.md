# Task chi tiết — 7 tuần, 2 người + agent hỗ trợ

Phiên bản 1.1 — 2026-09-15. Có 50 task: 46 core (gồm SG-000) và 4 stretch. Core dự trù 142 giờ-người với agent hỗ trợ; chưa gồm chờ GPU/API và annotation phát sinh ngoài pilot. So với 168–210 giờ-người dự trù, giữ phần còn lại cho dự phòng.

Trạng thái/owner thực tế cập nhật tại [tasks.json](../management/tasks.json); file này chỉ giữ đặc tả công việc. Đường dẫn đầu ra bên dưới là dự kiến, chưa đồng nghĩa file đã tồn tại.

R = Research/Evaluation; D = Data/Graph; S = Search/System; H = hai người gán nhãn; C = Coordinator. Giờ là thời gian con người cần đọc, kiểm tra, chạy, giải thích với agent hỗ trợ; không phải cam kết thời gian agent. Mỗi task có thể giao implementation cho agent theo hợp đồng, người sở hữu kiểm chứng đầu ra.

## Mục lục

| Task | Việc | Tuần | Giờ-người | Phụ thuộc |
|---|---|---|---:|---|
| [SG-000](#sg-000) | Thiết lập kế hoạch, rules và log | 0 | 0 | — |
| [SG-001](#sg-001) | Chốt scope và yêu cầu môn | 1 | 2 | SG-000 |
| [SG-002](#sg-002) | Khảo sát local và GPU pilot | 1 | 3 | SG-000 |
| [SG-003](#sg-003) | Related work và novelty | 1 | 5 | SG-001 |
| [SG-004](#sg-004) | Protocol nghiên cứu v1 | 1 | 3 | SG-001, SG-003 |
| [SG-005](#sg-005) | Package, môi trường và Git local | 1 | 2 | SG-001 |
| [SG-006](#sg-006) | Schema và interface | 1 | 2 | SG-004, SG-005 |
| [SG-007](#sg-007) | Runner và run manifest | 1 | 2 | SG-006 |
| [SG-008](#sg-008) | Kiểm chứng evaluator | 1 | 3 | SG-006, SG-007 |
| [SG-009](#sg-009) | Tải và đóng băng BEIR | 1–2 | 2 | SG-005, SG-006 |
| [SG-010](#sg-010) | Audit chất lượng dữ liệu | 2 | 2 | SG-009 |
| [SG-011](#sg-011) | Split và leakage checks | 2 | 3 | SG-004, SG-010 |
| [SG-012](#sg-012) | BM25 pilot thật | 2 | 2 | SG-008, SG-010, SG-011 |
| [SG-013](#sg-013) | OpenAlex pilot có resume | 1–2 | 3 | SG-005, SG-006 |
| [SG-014](#sg-014) | Graph feasibility gate | 2 | 4 | SG-011, SG-013 |
| [SG-015](#sg-015) | Snapshot OpenAlex core | 2–3 | 2 | SG-013, SG-014 |
| [SG-016](#sg-016) | Graph và masked split | 3 | 3 | SG-014, SG-015 |
| [SG-017](#sg-017) | Chọn dense model | 2 | 2 | SG-003, SG-005, SG-011 |
| [SG-018](#sg-018) | Lexical baselines | 2–3 | 2 | SG-012 |
| [SG-019](#sg-019) | Encoding shard và dense index | 2–3 | 3 | SG-002, SG-010, SG-015, SG-017 |
| [SG-020](#sg-020) | Hybrid RRF | 3 | 3 | SG-018, SG-019 |
| [SG-021](#sg-021) | Candidate recall | 3 | 2 | SG-020 |
| [SG-022](#sg-022) | Graph baselines | 3 | 2 | SG-016 |
| [SG-023](#sg-023) | Personalized PageRank | 3–4 | 4 | SG-021, SG-022 |
| [SG-024](#sg-024) | Age adjustment | 4 | 3 | SG-023 |
| [SG-025](#sg-025) | Reranking integration | 4 | 2 | SG-020, SG-023, SG-024 |
| [SG-026](#sg-026) | Dev tuning có budget | 4 | 3 | SG-011, SG-025 |
| [SG-027](#sg-027) | Main freeze | 4 | 2 | SG-008, SG-026 |
| [SG-028](#sg-028) | Final runs | 5 | 3 | SG-027 |
| [SG-029](#sg-029) | Ablation và robustness | 5 | 3 | SG-028 |
| [SG-030](#sg-030) | Thống kê và error analysis | 5–6 | 4 | SG-029 |
| [SG-031](#sg-031) | Query Việt và annotation guide | 4 | 3 | SG-011, SG-015 |
| [SG-032](#sg-032) | Cross-lingual baselines | 4–5 | 3 | SG-017, SG-020, SG-031 |
| [SG-033](#sg-033) | Pool và nhãn hai người | 5 | 16 | SG-025, SG-031, SG-032 |
| [SG-034](#sg-034) | Freeze và final VN eval | 5–6 | 2 | SG-027, SG-032, SG-033 |
| [SG-035](#sg-035) | API search/metadata | 3–4 | 3 | SG-006, SG-015, SG-020 |
| [SG-036](#sg-036) | UI search/recommend | 4–5 | 4 | SG-025, SG-035 |
| [SG-037](#sg-037) | Citation graph UI | 5 | 2 | SG-016, SG-036 |
| [SG-038](#sg-038) | Offline và xuất tham khảo | 5 | 2 | SG-036 |
| [SG-039](#sg-039) | Integration checks | 5 | 3 | SG-037, SG-038 |
| [SG-040](#sg-040) | Performance profiling | 5–6 | 3 | SG-028, SG-039 |
| [SG-041](#sg-041) | Packaging và tái lập | 6 | 3 | SG-040 |
| [SG-042](#sg-042) | Tái lập chéo và audit | 6 | 4 | SG-030, SG-034, SG-041 |
| [SG-043](#sg-043) | Báo cáo học thuật | 6 | 7 | SG-030, SG-034, SG-040 |
| [SG-044](#sg-044) | Slides và diễn tập | 6–7 | 4 | SG-043 |
| [SG-045](#sg-045) | Gói nộp và handoff cuối | 7 | 2 | SG-042, SG-044 |
| [SG-046](#sg-046) | Stretch: cross-encoder | sau core | 4 | SG-027 |
| [SG-047](#sg-047) | Stretch: fine-tuning | sau core | 6 | SG-026 |
| [SG-048](#sg-048) | Stretch: SciRepEval task | sau core | 4 | SG-027 |
| [SG-049](#sg-049) | Stretch: TREC-COVID | sau core | 3 | SG-027 |

<a id="sg-000"></a>

## SG-000 — Thiết lập kế hoạch, rules và log

- Mốc: M0; tuần: 0; ưu tiên: CORE.
- Vai trò: C; dự trù: 0 giờ-người.
- Phụ thuộc: không.

**Việc phải làm**

1. Tạo entry point/AGENTS và hồ sơ dự án.
2. Ghi board/state/handoff/decision.
3. Kiểm tra dependency/liên kết.

**Đầu ra dự kiến**

- `docs/MASTER_PLAN.md`
- `docs/TASKS.md`
- `management/tasks.json`
- `management/HANDOFF.md`
- `scripts/check_project.ps1`

**Nghiệm thu**

- File có thật và checker pass.
- Không nhận ứng dụng đã triển khai.

**Hai bạn cần hiểu:** Biết cách tiếp nối từ HANDOFF.

<a id="sg-001"></a>

## SG-001 — Chốt scope và yêu cầu môn

- Mốc: M1; tuần: 1; ưu tiên: CORE.
- Vai trò: R/C; dự trù: 2 giờ-người.
- Phụ thuộc: SG-000.

**Việc phải làm**

1. Ghi deadline/rubric/chính sách AI khi có.
2. Map RQ/FR với đầu ra.
3. Unknown ghi provisional có owner.

**Đầu ra dự kiến**

- `docs/SCOPE.md`
- `docs/RUBRIC_MAP.md`

**Nghiệm thu**

- Phạm vi 7 tuần/2 người rõ.
- Không coi giả định là rubric chính thức.

**Hai bạn cần hiểu:** Giải thích vấn đề, người dùng, đóng góp trong 2 phút.

<a id="sg-002"></a>

## SG-002 — Khảo sát local và GPU pilot

- Mốc: M1; tuần: 1; ưu tiên: CORE.
- Vai trò: D/S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-000.

**Việc phải làm**

1. Kiểm tra runtime/RAM/disk.
2. Notebook encode 1.000 mẫu pretrained, đo GPU/VRAM/docs-giây.
3. Dự toán và shard/resume/storage plan.

**Đầu ra dự kiến**

- `docs/COMPUTE_PLAN.md`
- `notebooks/compute_smoke.ipynb`
- `artifacts/reports/compute_pilot.json`

**Nghiệm thu**

- Đo thật và phân biệt phần chưa xác minh.
- Nếu tài khoản chưa truy cập được giữ blocker rõ, không bịa kết quả.

**Hai bạn cần hiểu:** Hiểu encoding khác training, tính thời gian từ tốc độ pilot.

<a id="sg-003"></a>

## SG-003 — Related work và novelty

- Mốc: M1; tuần: 1; ưu tiên: CORE.
- Vai trò: R; dự trù: 5 giờ-người.
- Phụ thuộc: SG-001.

**Việc phải làm**

1. Đọc BM25/RRF/PPR/scientific embeddings/temporal bias.
2. Ma trận 8–12 primary sources.
3. Cả hai đọc kỹ 3 paper.

**Đầu ra dự kiến**

- `docs/RELATED_WORK.md`
- `docs/references.bib`

**Nghiệm thu**

- Nguồn/limitations rõ.
- Không claim novelty/SOTA trước đối chiếu.

**Hai bạn cần hiểu:** Giải thích citation là proxy relevance.

<a id="sg-004"></a>

## SG-004 — Protocol nghiên cứu v1

- Mốc: M1; tuần: 1; ưu tiên: CORE.
- Vai trò: R; dự trù: 3 giờ-người.
- Phụ thuộc: SG-001, SG-003.

**Việc phải làm**

1. Chốt tuyến A/B/C và metric.
2. Đặt split/candidates/primary comparisons/ablations.
3. Ghi graph gate và phần chờ freeze.

**Đầu ra dự kiến**

- `docs/RESEARCH_PROTOCOL.md`
- `configs/protocol_v1.json`

**Nghiệm thu**

- Mỗi RQ có data/labels/method/metric.
- Ranh giới dev/test rõ.

**Hai bạn cần hiểu:** Biết dữ liệu nào chỉ evaluator được đọc.

<a id="sg-005"></a>

## SG-005 — Package, môi trường và Git local

- Mốc: M1; tuần: 1; ưu tiên: CORE.
- Vai trò: S; dự trù: 2 giờ-người.
- Phụ thuộc: SG-001.

**Việc phải làm**

1. Tạo package/tests/configs/env riêng.
2. Chọn frontend nhẹ và lock versions.
3. Thiết lập Git local phù hợp/ignore dữ liệu lớn, không tự push.

**Đầu ra dự kiến**

- `pyproject.toml`
- `src/scholargraph/__init__.py`
- `docs/ENVIRONMENT.md`
- `.gitignore`

**Nghiệm thu**

- Import và cài lại chạy được.
- Ghi root/version thật, không trộn E-COMASPECT.

**Hai bạn cần hiểu:** Biết cách chạy và tìm phiên bản code.

<a id="sg-006"></a>

## SG-006 — Schema và interface

- Mốc: M1; tuần: 1; ưu tiên: CORE.
- Vai trò: D/S; dự trù: 2 giờ-người.
- Phụ thuộc: SG-004, SG-005.

**Việc phải làm**

1. Paper/Citation/Query/Qrel/Ranking/Run schemas.
2. Namespace ID/null policy.
3. Fixtures synthetic và hợp đồng module.

**Đầu ra dự kiến**

- `src/scholargraph/data/schemas.py`
- `tests/fixtures/`
- `docs/ARCHITECTURE.md`

**Nghiệm thu**

- Bắt ID/score/year sai.
- Ranker không nhận qrels.

**Hai bạn cần hiểu:** Phân biệt DOI/paper ID/query ID/label.

<a id="sg-007"></a>

## SG-007 — Runner và run manifest

- Mốc: M1; tuần: 1; ưu tiên: CORE.
- Vai trò: S; dự trù: 2 giờ-người.
- Phụ thuộc: SG-006.

**Việc phải làm**

1. Run ID/status/config/code-data-model hashes.
2. Lưu hardware/seed/lệnh/ranking/per-query.
3. Resume/export notebook không overwrite.

**Đầu ra dự kiến**

- `src/scholargraph/evaluation/runner.py`
- `tests/unit/test_run_integrity.py`

**Nghiệm thu**

- Smoke run có manifest.
- Completed run bất biến, failed run có lỗi.

**Hai bạn cần hiểu:** Từ metric tìm lại model/data/config.

<a id="sg-008"></a>

## SG-008 — Kiểm chứng evaluator

- Mốc: M1; tuần: 1; ưu tiên: CORE.
- Vai trò: R/S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-006, SG-007.

**Việc phải làm**

1. Fixture tính tay nDCG/Recall/MRR/MAP.
2. So reference evaluator.
3. Kiểm tra ties/duplicates/0-1-2 labels/no-result.

**Đầu ra dự kiến**

- `src/scholargraph/evaluation/metrics.py`
- `tests/unit/test_metrics_reference.py`
- `artifacts/reports/metric_validation.json`

**Nghiệm thu**

- Khớp tính tay/reference trong tolerance.
- Metric convention rõ.

**Hai bạn cần hiểu:** Tính được MRR và hiểu nDCG.

<a id="sg-009"></a>

## SG-009 — Tải và đóng băng BEIR

- Mốc: M2; tuần: 1–2; ưu tiên: CORE.
- Vai trò: D; dự trù: 2 giờ-người.
- Phụ thuộc: SG-005, SG-006.

**Việc phải làm**

1. Tải SciFact/SCIDOCS chính thức.
2. Lưu raw/revision/checksum/license.
3. Loader corpus/queries/qrels và splits.

**Đầu ra dự kiến**

- `src/scholargraph/ingest/beir_loader.py`
- `data/manifests/beir_scifact.json`
- `data/manifests/beir_scidocs.json`

**Nghiệm thu**

- Counts/hash/source thật.
- Không tự tạo official dev SCIDOCS.

**Hai bạn cần hiểu:** Hiểu cấu trúc benchmark.

<a id="sg-010"></a>

## SG-010 — Audit chất lượng dữ liệu

- Mốc: M2; tuần: 2; ưu tiên: CORE.
- Vai trò: D/R; dự trù: 2 giờ-người.
- Phụ thuộc: SG-009.

**Việc phải làm**

1. Unique IDs/qrels references.
2. Missing text/label distribution/duplicates.
3. Giữ raw benchmark, báo anomalies.

**Đầu ra dự kiến**

- `artifacts/reports/beir_data_audit.json`
- `docs/DATA_CARD.md`
- `tests/unit/test_data_integrity.py`

**Nghiệm thu**

- Không có ID lỗi chưa xử lý.
- Không lọc benchmark ngầm để tăng score.

**Hai bạn cần hiểu:** Hiểu tác động missingness/duplicates.

<a id="sg-011"></a>

## SG-011 — Split và leakage checks

- Mốc: M2; tuần: 2; ưu tiên: CORE.
- Vai trò: R/D; dự trù: 3 giờ-người.
- Phụ thuộc: SG-004, SG-010.

**Việc phải làm**

1. Khóa query groups/dev độc lập.
2. Tách labels khỏi ranker.
3. Audit overlap và lineage.

**Đầu ra dự kiến**

- `data/splits/`
- `configs/split_policy.json`
- `tests/unit/test_split_leakage.py`
- `artifacts/reports/split_audit.json`

**Nghiệm thu**

- Split không chồng và có hash.
- Test labels không vào index/model/features.

**Hai bạn cần hiểu:** Giải thích vì sao không tune test.

<a id="sg-012"></a>

## SG-012 — BM25 pilot thật

- Mốc: M2; tuần: 2; ưu tiên: CORE.
- Vai trò: S/R; dự trù: 2 giờ-người.
- Phụ thuộc: SG-008, SG-010, SG-011.

**Việc phải làm**

1. Dựng BM25 full corpus.
2. Chạy SciFact dev và đọc 10 query.
3. Lưu run rồi chạy lại.

**Đầu ra dự kiến**

- `src/scholargraph/retrieval/bm25.py`
- `artifacts/reports/bm25_pilot.md`

**Nghiệm thu**

- Có run ID/metric thật.
- Dev run tái lập.

**Hai bạn cần hiểu:** Nêu một query đúng và một query sai.

<a id="sg-013"></a>

## SG-013 — OpenAlex pilot có resume

- Mốc: M2; tuần: 1–2; ưu tiên: CORE.
- Vai trò: D; dự trù: 3 giờ-người.
- Phụ thuộc: SG-005, SG-006.

**Việc phải làm**

1. Tải 1.000–3.000 paper theo topic.
2. Cache/pagination/rate-limit/retry.
3. Đo coverage và chi phí mở rộng.

**Đầu ra dự kiến**

- `src/scholargraph/ingest/openalex.py`
- `data/manifests/openalex_pilot.json`
- `artifacts/reports/openalex_pilot.json`

**Nghiệm thu**

- Resume không mất/trùng.
- Snapshot/source/time rõ và key không vào log.

**Hai bạn cần hiểu:** Hiểu selection bias/missing references.

<a id="sg-014"></a>

## SG-014 — Graph feasibility gate

- Mốc: M2; tuần: 2; ưu tiên: CORE.
- Vai trò: R/D; dự trù: 4 giờ-người.
- Phụ thuộc: SG-011, SG-013.

**Việc phải làm**

1. Audit graph/mapping/isolated nodes.
2. Timebox BEIR enrichment, ưu tiên OpenAlex custom protocol.
3. Chốt holdout/cutoff/masking bằng ADR.

**Đầu ra dự kiến**

- `docs/GRAPH_PROTOCOL.md`
- `artifacts/reports/graph_feasibility.json`
- `management/DECISIONS.md`

**Nghiệm thu**

- Không dùng qrels làm graph.
- No-go có evidence và sửa scope/dependencies chính thức.

**Hai bạn cần hiểu:** Nhận ra test citation trong adjacency gây leakage.

<a id="sg-015"></a>

## SG-015 — Snapshot OpenAlex core

- Mốc: M2; tuần: 2–3; ưu tiên: CORE.
- Vai trò: D; dự trù: 2 giờ-người.
- Phụ thuộc: SG-013, SG-014.

**Việc phải làm**

1. Mở rộng 10–20K theo budget.
2. Normalize DOI/metadata và giữ transformations.
3. Pin snapshot/hash demo-graph riêng.

**Đầu ra dự kiến**

- `data/manifests/openalex_core.json`
- `data/processed/openalex/`
- `artifacts/reports/openalex_quality.json`

**Nghiệm thu**

- Coverage/count đo thật.
- Mapping có audit, không đổi snapshot ngầm.

**Hai bạn cần hiểu:** Hiểu giới hạn tập con theo topic.

<a id="sg-016"></a>

## SG-016 — Graph và masked split

- Mốc: M2; tuần: 3; ưu tiên: CORE.
- Vai trò: D; dự trù: 3 giờ-người.
- Phụ thuộc: SG-014, SG-015.

**Việc phải làm**

1. Directed graph/self/dangling/missing edges.
2. Tạo holdout và xóa cạnh đảo.
3. Recompute graph features, lưu hashes.

**Đầu ra dự kiến**

- `src/scholargraph/graph/build.py`
- `data/manifests/graph_core.json`
- `tests/unit/test_graph_masking.py`
- `artifacts/reports/graph_audit.json`

**Nghiệm thu**

- Không có held-out/derived leakage.
- Candidates/năm đúng protocol.

**Hai bạn cần hiểu:** Chỉ cạnh biết/ẩn và candidate hợp lệ cho một query.

<a id="sg-017"></a>

## SG-017 — Chọn dense model

- Mốc: M3; tuần: 2; ưu tiên: CORE.
- Vai trò: R/S; dự trù: 2 giờ-người.
- Phụ thuộc: SG-003, SG-005, SG-011.

**Việc phải làm**

1. Đọc 2 model cards nhỏ/base.
2. Ghi revision/pooling/prompt/adapter/license/training overlap.
3. Chốt encoder core theo task.

**Đầu ra dự kiến**

- `docs/MODEL_CARD.md`
- `configs/models/`

**Nghiệm thu**

- Đúng pretrained weights/tokenizer.
- Overlap được công bố.

**Hai bạn cần hiểu:** Hiểu cosine/pooling và English encoder không tự chứng minh hiểu Việt.

<a id="sg-018"></a>

## SG-018 — Lexical baselines

- Mốc: M3; tuần: 2–3; ưu tiên: CORE.
- Vai trò: S; dự trù: 2 giờ-người.
- Phụ thuộc: SG-012.

**Việc phải làm**

1. TF-IDF/BM25 cùng corpus fields.
2. Reusable index/tokenization config.
3. Dev diagnostics/ties/filters.

**Đầu ra dự kiến**

- `src/scholargraph/retrieval/tfidf.py`
- `tests/unit/test_lexical.py`
- `artifacts/reports/lexical_dev.md`

**Nghiệm thu**

- Cùng inputs/candidates.
- Index hash và dev run thật.

**Hai bạn cần hiểu:** Phân biệt TF-IDF và BM25.

<a id="sg-019"></a>

## SG-019 — Encoding shard và dense index

- Mốc: M3; tuần: 2–3; ưu tiên: CORE.
- Vai trò: S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-002, SG-010, SG-015, SG-017.

**Việc phải làm**

1. Encode theo từng corpus manifest.
2. GPU batch/checksum/resume/export bền vững.
3. Exact index trước, ANN có recall audit nếu dùng.

**Đầu ra dự kiến**

- `notebooks/encode_corpus.ipynb`
- `src/scholargraph/retrieval/dense.py`
- `artifacts/reports/encoding_profile.json`
- `tests/unit/test_embedding_manifest.py`

**Nghiệm thu**

- Doc-ID order/model revision đúng.
- Resume không trộn config, VRAM/tốc độ đo thật.

**Hai bạn cần hiểu:** Tìm được vector thuộc paper nào và estimate thời gian còn lại.

<a id="sg-020"></a>

## SG-020 — Hybrid RRF

- Mốc: M3; tuần: 3; ưu tiên: CORE.
- Vai trò: S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-018, SG-019.

**Việc phải làm**

1. Union lexical/dense top-k.
2. RRF constant/depth trên dev.
3. Filter/tie policy chung và lưu component ranks.

**Đầu ra dự kiến**

- `src/scholargraph/retrieval/hybrid.py`
- `configs/hybrid.json`
- `tests/unit/test_rrf.py`

**Nghiệm thu**

- Fixture khớp tính tay.
- Deterministic và không dùng qrels.

**Hai bạn cần hiểu:** Hiểu RRF tránh cộng raw score khác thang.

<a id="sg-021"></a>

## SG-021 — Candidate recall

- Mốc: M3; tuần: 3; ưu tiên: CORE.
- Vai trò: R/S; dự trù: 2 giờ-người.
- Phụ thuộc: SG-020.

**Việc phải làm**

1. Recall@100/oracle quality trên dev.
2. Phân biệt candidate miss/rank error.
3. Chốt depth/latency budget.

**Đầu ra dự kiến**

- `artifacts/reports/candidate_audit.md`
- `configs/candidate_policy.json`

**Nghiệm thu**

- Ablation dùng cùng pool.
- 10 query examples có lý do.

**Hai bạn cần hiểu:** Hiểu reranker không cứu paper đã mất khỏi pool.

<a id="sg-022"></a>

## SG-022 — Graph baselines

- Mốc: M4; tuần: 3; ưu tiên: CORE.
- Vai trò: D; dự trù: 2 giờ-người.
- Phụ thuộc: SG-016.

**Việc phải làm**

1. Global PageRank.
2. Bibliographic coupling hoặc đối chứng related-paper đơn giản.
3. Audit popularity/coverage.

**Đầu ra dự kiến**

- `src/scholargraph/graph/baselines.py`
- `tests/unit/test_graph_baselines.py`

**Nghiệm thu**

- Toy graph đúng chiều.
- Cùng graph/candidates, fallback rõ.

**Hai bạn cần hiểu:** Phân biệt phổ biến với liên quan.

<a id="sg-023"></a>

## SG-023 — Personalized PageRank

- Mốc: M4; tuần: 3–4; ưu tiên: CORE.
- Vai trò: D/S; dự trù: 4 giờ-người.
- Phụ thuộc: SG-021, SG-022.

**Việc phải làm**

1. Teleport từ text ranks/scores.
2. Damping/tolerance/dangling/cache version.
3. Tách seed/expansion/final set.

**Đầu ra dự kiến**

- `src/scholargraph/graph/ppr.py`
- `tests/unit/test_ppr_reference.py`
- `configs/ppr.json`

**Nghiệm thu**

- Toy graph khớp reference.
- Seeds không lấy labels, graph trống có fallback.

**Hai bạn cần hiểu:** Giải thích teleport trên 4–5 node.

<a id="sg-024"></a>

## SG-024 — Age adjustment

- Mốc: M4; tuần: 4; ưu tiên: CORE.
- Vai trò: R/D; dự trù: 3 giờ-người.
- Phụ thuộc: SG-023.

**Việc phải làm**

1. Công thức/reference time/missing-year policy.
2. Grid dev nhỏ.
3. Đo relevance-age exposure theo topic/relevance.

**Đầu ra dự kiến**

- `src/scholargraph/graph/age_adjustment.py`
- `configs/age_adjustment.json`
- `docs/AGE_ANALYSIS.md`

**Nghiệm thu**

- Cutoff cố định.
- Không coi tăng bài mới là chứng minh fairness.

**Hai bạn cần hiểu:** Hiểu đánh đổi với paper nền tảng.

<a id="sg-025"></a>

## SG-025 — Reranking integration

- Mốc: M4; tuần: 4; ưu tiên: CORE.
- Vai trò: S/D; dự trù: 2 giờ-người.
- Phụ thuộc: SG-020, SG-023, SG-024.

**Việc phải làm**

1. Fusion chuẩn hóa per-query.
2. Candidates cố định cho ablation.
3. Component scores/graph evidence và fallback.

**Đầu ra dự kiến**

- `src/scholargraph/retrieval/rerank.py`
- `tests/integration/test_reranking.py`

**Nghiệm thu**

- Không đổi universe ngầm/self-recommend.
- Data/model/graph hashes đủ.

**Hai bạn cần hiểu:** Giải thích vì sao hai paper đổi chỗ.

<a id="sg-026"></a>

## SG-026 — Dev tuning có budget

- Mốc: M4; tuần: 4; ưu tiên: CORE.
- Vai trò: R/S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-011, SG-025.

**Việc phải làm**

1. Grid 12–20 cấu hình nhẹ.
2. Chọn theo primary relevance và theo dõi latency.
3. Lưu tất cả trials.

**Đầu ra dự kiến**

- `configs/tuning_space.json`
- `artifacts/reports/dev_selection.md`

**Nghiệm thu**

- Không chọn bằng test.
- Graph kém vẫn có log.

**Hai bạn cần hiểu:** Nêu bằng chứng chọn config.

<a id="sg-027"></a>

## SG-027 — Main freeze

- Mốc: M4; tuần: 4; ưu tiên: CORE.
- Vai trò: R/C; dự trù: 2 giờ-người.
- Phụ thuộc: SG-008, SG-026.

**Việc phải làm**

1. Khóa data/split/graph/model/config/evaluator.
2. Chốt primary comparison và ablations.
3. Hai người review leakage/ADR.

**Đầu ra dự kiến**

- `configs/frozen_main.json`
- `docs/MAIN_FREEZE.md`
- `management/DECISIONS.md`

**Nghiệm thu**

- Freeze timestamp/hashes có thật.
- Thay đổi sau freeze có version/lý do.

**Hai bạn cần hiểu:** Phân biệt sửa bug và tune theo test.

<a id="sg-028"></a>

## SG-028 — Final runs

- Mốc: M6; tuần: 5; ưu tiên: CORE.
- Vai trò: R/S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-027.

**Việc phải làm**

1. Chạy frozen methods từng protocol.
2. Lưu TREC/per-query/aggregate.
3. Check NaN/query/candidate policies.

**Đầu ra dự kiến**

- `artifacts/reports/main_results.md`
- `artifacts/reports/main_run_registry.json`

**Nghiệm thu**

- Mỗi dòng bảng nối completed run.
- Bảng graph/custom riêng và không sửa score thấp.

**Hai bạn cần hiểu:** Đọc được metric và giới hạn một dòng bảng.

<a id="sg-029"></a>

## SG-029 — Ablation và robustness

- Mốc: M6; tuần: 5; ưu tiên: CORE.
- Vai trò: R/D; dự trù: 3 giờ-người.
- Phụ thuộc: SG-028.

**Việc phải làm**

1. No graph/no age/global PR/PPR đã freeze.
2. Sparse graph/missing abstracts/query length.
3. Component costs và failures.

**Đầu ra dự kiến**

- `artifacts/reports/ablation.md`
- `artifacts/reports/robustness.md`

**Nghiệm thu**

- Cùng pool/metric.
- Có cả phương án không cải thiện.

**Hai bạn cần hiểu:** Chỉ component có ích và bằng chứng còn yếu.

<a id="sg-030"></a>

## SG-030 — Thống kê và error analysis

- Mốc: M6; tuần: 5–6; ưu tiên: CORE.
- Vai trò: R; dự trù: 4 giờ-người.
- Phụ thuộc: SG-029.

**Việc phải làm**

1. Paired bootstrap/absolute-relative deltas.
2. Subgroups với sample size/exploratory labels.
3. Cả hai đọc 20–30 lỗi.

**Đầu ra dự kiến**

- `src/scholargraph/evaluation/statistics.py`
- `artifacts/reports/statistics.md`
- `docs/ERROR_ANALYSIS.md`

**Nghiệm thu**

- CI/run IDs tái lập.
- Không dùng lặp seed deterministic làm uncertainty.

**Hai bạn cần hiểu:** Hiểu CI chứa 0 và kết quả âm.

<a id="sg-031"></a>

## SG-031 — Query Việt và annotation guide

- Mốc: M5; tuần: 4; ưu tiên: CORE.
- Vai trò: R/H; dự trù: 3 giờ-người.
- Phụ thuộc: SG-011, SG-015.

**Việc phải làm**

1. Hai người viết khoảng 30 query; chỉ tăng 50 nếu annotation pilot còn thời gian.
2. 10 dev/20 test theo intent/topic; đây là pilot nội bộ nhỏ.
3. Rubric relevance 0/1/2 có ví dụ.

**Đầu ra dự kiến**

- `data/annotations/vn_query_manifest.json`
- `docs/ANNOTATION_GUIDE.md`

**Nghiệm thu**

- Không sinh query từ positive test doc.
- Không paraphrase xuyên split.

**Hai bạn cần hiểu:** Giải thích intent và nhãn của 5 query.

<a id="sg-032"></a>

## SG-032 — Cross-lingual baselines

- Mốc: M5; tuần: 4–5; ưu tiên: CORE.
- Vai trò: S/R; dự trù: 3 giờ-người.
- Phụ thuộc: SG-017, SG-020, SG-031.

**Việc phải làm**

1. Raw BM25/dịch-BM25/multilingual dense.
2. Pin model/translation/prompt và cache.
3. Dev pilot technical terms/code-switching.

**Đầu ra dự kiến**

- `src/scholargraph/retrieval/cross_lingual.py`
- `configs/vn_methods.json`
- `artifacts/reports/vn_dev_pilot.md`

**Nghiệm thu**

- Query Việt thật, bản dịch có nguồn.
- Core không phụ thuộc paid LLM.

**Hai bạn cần hiểu:** Hiểu vì sao English encoder không tự đạt cross-lingual.

<a id="sg-033"></a>

## SG-033 — Pool và nhãn hai người

- Mốc: M5; tuần: 5; ưu tiên: CORE.
- Vai trò: H; dự trù: 16 giờ-người.
- Phụ thuộc: SG-025, SG-031, SG-032.

**Việc phải làm**

1. Pool top-10 từ 3 phương pháp đại diện, dedup; đo workload trước trên 5 query.
2. Ẩn system/score, chấm độc lập.
3. Agreement trước adjudication, giữ raw labels. Budget khoảng 600 cặp query-paper duy nhất được hai người chấm; nếu vượt thì giảm số query hoặc depth đồng đều trước chấm test và ghi ADR.

**Đầu ra dự kiến**

- `data/annotations/vn_labels.jsonl`
- `data/manifests/vn_benchmark.json`
- `artifacts/reports/annotation_agreement.md`

**Nghiệm thu**

- Provenance/annotator IDs rõ.
- Agent không giả làm human raters, 16 giờ chỉ là dự trù cần cập nhật pilot.

**Hai bạn cần hiểu:** Hiểu bất đồng và pooled judgment bias.

<a id="sg-034"></a>

## SG-034 — Freeze và final VN eval

- Mốc: M6; tuần: 5–6; ưu tiên: CORE.
- Vai trò: R; dự trù: 2 giờ-người.
- Phụ thuộc: SG-027, SG-032, SG-033.

**Việc phải làm**

1. Chọn từ dev và freeze trước mở test.
2. nDCG/P@5/MRR/unjudged ratio.
3. Phân tích lỗi dịch/intent.

**Đầu ra dự kiến**

- `configs/frozen_vn.json`
- `artifacts/reports/vn_results.md`

**Nghiệm thu**

- Freeze/run IDs đầy đủ.
- Không gộp English BEIR hay claim benchmark quốc tế.

**Hai bạn cần hiểu:** Giải thích evidence hữu ích cho người Việt và giới hạn cỡ mẫu.

<a id="sg-035"></a>

## SG-035 — API search/metadata

- Mốc: M5; tuần: 3–4; ưu tiên: CORE.
- Vai trò: S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-006, SG-015, SG-020.

**Việc phải làm**

1. Search/paper/recommend contracts.
2. Filters/pagination/shared service.
3. Snapshot/method IDs và missing/error states.

**Đầu ra dự kiến**

- `src/scholargraph/api/`
- `tests/integration/test_api.py`

**Nghiệm thu**

- API dữ liệu thật/filters đúng.
- Không đọc qrels hoặc dựng result giả.

**Hai bạn cần hiểu:** Biết pipeline request và cost.

<a id="sg-036"></a>

## SG-036 — UI search/recommend

- Mốc: M5; tuần: 4–5; ưu tiên: CORE.
- Vai trò: S; dự trù: 4 giờ-người.
- Phụ thuộc: SG-025, SG-035.

**Việc phải làm**

1. Search cards/detail/related.
2. Title/abstract/DOI/source và explanation.
3. Loading/error/no-results/fallback.

**Đầu ra dự kiến**

- `ui/`
- `artifacts/reports/ui_smoke.md`

**Nghiệm thu**

- End-to-end dùng API thật.
- Hai người kiểm chứng 5 queries/IDs/sources.

**Hai bạn cần hiểu:** Demo nhu cầu và giải thích kết quả.

<a id="sg-037"></a>

## SG-037 — Citation graph UI

- Mốc: M5; tuần: 5; ưu tiên: CORE.
- Vai trò: S/D; dự trù: 2 giờ-người.
- Phụ thuộc: SG-016, SG-036.

**Việc phải làm**

1. Neighborhood cap/hướng cạnh.
2. Node link/legend/snapshot date.
3. Fallback graph thiếu/lớn.

**Đầu ra dự kiến**

- `ui/graph/`
- `artifacts/reports/graph_ui_smoke.md`

**Nghiệm thu**

- Graph UI khớp snapshot.
- Evaluated mode không dùng held-out edges như input.

**Hai bạn cần hiểu:** Giải thích cited-by/cites.

<a id="sg-038"></a>

## SG-038 — Offline và xuất tham khảo

- Mốc: M5; tuần: 5; ưu tiên: CORE.
- Vai trò: S; dự trù: 2 giờ-người.
- Phụ thuộc: SG-036.

**Việc phải làm**

1. Pin snapshot/sample query sources.
2. Export DOI/title/link với missing policy.
3. Chạy khi tắt mạng.

**Đầu ra dự kiến**

- `docs/DEMO_SCRIPT.md`
- `configs/demo.json`
- `artifacts/reports/offline_smoke.md`

**Nghiệm thu**

- Offline chạy không synthetic substitution.
- Không bịa author/citation.

**Hai bạn cần hiểu:** Demo 5 phút mất mạng.

<a id="sg-039"></a>

## SG-039 — Integration checks

- Mốc: M5; tuần: 5; ưu tiên: CORE.
- Vai trò: S/R; dự trù: 3 giờ-người.
- Phụ thuộc: SG-037, SG-038.

**Việc phải làm**

1. Ingest/index/search/UI/export.
2. IDs/self/duplicates/filters/cache.
3. Missing model/index/graph và query Việt.

**Đầu ra dự kiến**

- `tests/integration/`
- `artifacts/reports/integration_checks.md`

**Nghiệm thu**

- Critical flows pass hoặc issue rõ.
- Đối chiếu data thật ngoài screenshot.

**Hai bạn cần hiểu:** Nêu lỗi đã bắt và hậu quả.

<a id="sg-040"></a>

## SG-040 — Performance profiling

- Mốc: M6; tuần: 5–6; ưu tiên: CORE.
- Vai trò: S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-028, SG-039.

**Việc phải làm**

1. Đo encoding/retrieval/rerank end-to-end.
2. P50/P95/cold/RAM/index/concurrency.
3. Profile trước tối ưu, kiểm tra quality nếu ranking đổi.

**Đầu ra dự kiến**

- `src/scholargraph/evaluation/performance.py`
- `artifacts/reports/performance.md`

**Nghiệm thu**

- Không gọi cache lookup là inference toàn trình.
- Hardware/workload rõ, báo thật mục tiêu 500ms.

**Hai bạn cần hiểu:** Hiểu build/cold/warm tradeoff.

<a id="sg-041"></a>

## SG-041 — Packaging và tái lập

- Mốc: M7; tuần: 6; ưu tiên: CORE.
- Vai trò: S; dự trù: 3 giờ-người.
- Phụ thuộc: SG-040.

**Việc phải làm**

1. Lock env/CLI/config/notebook version.
2. Offline bundle hoặc manifests.
3. Fresh-env instructions/Windows launcher.

**Đầu ra dự kiến**

- `docs/REPRODUCE.md`
- `docs/RELEASE_MANIFEST.md`
- `scripts/run_demo.ps1`

**Nghiệm thu**

- Lệnh tồn tại và đã thử.
- Checksums/model-data requirements đủ.

**Hai bạn cần hiểu:** Chạy lại không cần nhớ chat.

<a id="sg-042"></a>

## SG-042 — Tái lập chéo và audit

- Mốc: M7; tuần: 6; ưu tiên: CORE.
- Vai trò: R/S; dự trù: 4 giờ-người.
- Phụ thuộc: SG-030, SG-034, SG-041.

**Việc phải làm**

1. Người kia chạy text baseline/graph run.
2. So theo tolerance.
3. Audit tables/run IDs/issues.

**Đầu ra dự kiến**

- `artifacts/reports/reproduction_audit.md`
- `artifacts/reports/evidence_index.json`

**Nghiệm thu**

- Reviewer/commands/results thật.
- Không gọi agent run là human reproduction.

**Hai bạn cần hiểu:** Cả hai bảo vệ được run người kia tạo.

<a id="sg-043"></a>

## SG-043 — Báo cáo học thuật

- Mốc: M7; tuần: 6; ưu tiên: CORE.
- Vai trò: R; dự trù: 7 giờ-người.
- Phụ thuộc: SG-030, SG-034, SG-040.

**Việc phải làm**

1. Viết RQ/related/data/protocol/method/results/errors/limits.
2. Hình bảng từ artifact.
3. AI assistance theo rubric và review chéo.

**Đầu ra dự kiến**

- `reports/final_report.md`
- `reports/figures/`
- `docs/CLAIMS_CHECKLIST.md`

**Nghiệm thu**

- Claims dẫn source/run.
- Không vượt evidence về novelty/fairness.

**Hai bạn cần hiểu:** Trình bày leakage/kết quả âm/giới hạn.

<a id="sg-044"></a>

## SG-044 — Slides và diễn tập

- Mốc: M7; tuần: 6–7; ưu tiên: CORE.
- Vai trò: R/S; dự trù: 4 giờ-người.
- Phụ thuộc: SG-043.

**Việc phải làm**

1. Slides theo thời lượng.
2. 15–20 Q&A.
3. Hai lần rehearsal đổi người và offline fallback.

**Đầu ra dự kiến**

- `reports/defense_slides.md`
- `docs/DEFENSE_QA.md`
- `artifacts/reports/rehearsal_notes.md`

**Nghiệm thu**

- Cả hai giải thích flow/metrics.
- Có feedback sửa và thời lượng demo.

**Hai bạn cần hiểu:** Mỗi module hiểu input/output/assumption/error.

<a id="sg-045"></a>

## SG-045 — Gói nộp và handoff cuối

- Mốc: M7; tuần: 7; ưu tiên: CORE.
- Vai trò: C; dự trù: 2 giờ-người.
- Phụ thuộc: SG-042, SG-044.

**Việc phải làm**

1. Rà rubric/claims/deliverables.
2. Pin release/code/data/model.
3. Chốt logs/board/issues, chỉ submit ngoài khi được yêu cầu.

**Đầu ra dự kiến**

- `docs/SUBMISSION_CHECKLIST.md`
- `management/HANDOFF.md`
- `artifacts/reports/release_audit.md`

**Nghiệm thu**

- Gói local hoàn chỉnh/checksum.
- Không DONE nếu thiếu core evidence.

**Hai bạn cần hiểu:** Biết bản nộp và cách tái lập.

<a id="sg-046"></a>

## SG-046 — Stretch: cross-encoder

- Mốc: M8; tuần: sau core; ưu tiên: STRETCH.
- Vai trò: S/R; dự trù: 4 giờ-người.
- Phụ thuộc: SG-027.

**Việc phải làm**

1. Model card/overlap/cost.
2. Same candidates và protocol extension.
3. So gain/latency.

**Đầu ra dự kiến**

- `configs/stretch_cross_encoder.json`
- `artifacts/reports/cross_encoder.md`

**Nghiệm thu**

- Không tune test đã xem.
- Exploratory disclosure nếu cần.

**Hai bạn cần hiểu:** Hiểu cross-encoder đắt hơn bi-encoder.

<a id="sg-047"></a>

## SG-047 — Stretch: fine-tuning

- Mốc: M8; tuần: sau core; ưu tiên: STRETCH.
- Vai trò: R/S; dự trù: 6 giờ-người.
- Phụ thuộc: SG-026.

**Việc phải làm**

1. Train data độc lập.
2. Budget/3 stochastic seeds.
3. Checkpoint/resume và compare baseline.

**Đầu ra dự kiến**

- `configs/stretch_finetune.json`
- `artifacts/reports/finetuning.md`

**Nghiệm thu**

- Data/split/model/GPU logs rõ.
- Không thuê chưa có quyết định chi phí.

**Hai bạn cần hiểu:** Hiểu overfit và tradeoff training.

<a id="sg-048"></a>

## SG-048 — Stretch: SciRepEval task

- Mốc: M8; tuần: sau core; ưu tiên: STRETCH.
- Vai trò: R; dự trù: 4 giờ-người.
- Phụ thuộc: SG-027.

**Việc phải làm**

1. Chọn proximity/search task.
2. Official evaluator/adapter/candidate convention.
3. Pin revision và báo riêng.

**Đầu ra dự kiến**

- `configs/stretch_scirepeval.json`
- `artifacts/reports/scirepeval.md`

**Nghiệm thu**

- Task format rõ.
- Không trộn score với BEIR.

**Hai bạn cần hiểu:** Hiểu cùng tên suite có protocol khác.

<a id="sg-049"></a>

## SG-049 — Stretch: TREC-COVID

- Mốc: M8; tuần: sau core; ưu tiên: STRETCH.
- Vai trò: S/R; dự trù: 3 giờ-người.
- Phụ thuộc: SG-027.

**Việc phải làm**

1. Tải official revision/policy.
2. Frozen text baselines.
3. Đo scale/domain shift.

**Đầu ra dự kiến**

- `data/manifests/trec_covid.json`
- `artifacts/reports/trec_covid.md`

**Nghiệm thu**

- Full corpus và không tune test.
- Không proxy đánh giá VN.

**Hai bạn cần hiểu:** Hiểu domain shift và số query ít.

<a id="sg-050"></a>

## SG-050 — Hoàn tất dense encoding OpenAlex text-subset + SCIDOCS

- Mốc: M3; tuần: 3; ưu tiên: CORE.
- Vai trò: S; dự trù: 2 giờ-người.
- Phụ thuộc: SG-019.

**Việc phải làm**

1. Encode nốt OpenAlex text-subset (18.250 docs, namespace `openalex_core_text`, tiếp 2/19 shards đã pin).
2. Encode SCIDOCS (25.657 docs; work thiếu abstract dùng title — combined không rỗng).
3. Exact index + verify + profile cho đủ 3 corpus; exclusion 1 work tường minh theo ADR-017.

**Đầu ra dự kiến**

- `artifacts/indexes/` (openalex_core_text + scidocs)
- `artifacts/reports/encoding_profile.json` (đủ 3 corpus)

**Nghiệm thu**

- Checksum/ID alignment từng shard; resume không trộn config.
- Profile đo thật, GPU ghi not_measured_local.

**Hai bạn cần hiểu:** Vector trả về thuộc work nào và exclusion ảnh hưởng mapping thế nào.
