# Kiến trúc dự kiến và hợp đồng dữ liệu

Đây là thiết kế triển khai; các module bên dưới chưa được tạo.

## 1. Lựa chọn kỹ thuật ban đầu

- Python trong môi trường riêng, thử Python 3.11 nếu phù hợp thư viện; version chốt sau SG-002/SG-005.
- JSONL/Parquet cho corpus, SQLite cho metadata/demo, sparse matrix cho graph.
- Lexical index BM25/TF-IDF; dense encoding batch + vector index. Dùng exact search khi corpus nhỏ, đánh giá ANN recall trước dùng approximate search.
- NetworkX cho pilot/kiểm chứng, sparse implementation nếu profile chỉ ra cần thiết.
- FastAPI + giao diện nhẹ; frontend chọn ở SG-005 theo khả năng nhóm. Không cần database graph hoặc vector service trả phí ở MVP.
- CLI evaluation độc lập UI; không gọi API ngoài trong benchmark offline.

## 2. Luồng dữ liệu

BEIR → immutable snapshot → validator → lexical/dense index → text rankers → TREC run → evaluator.

OpenAlex → resumable ingestion → normalized papers + citations → graph audit/masking → graph snapshot → PPR/reranker → run → evaluator.

API/UI dùng cùng dịch vụ retrieval đã được benchmark; snapshot demo có manifest riêng. Nhãn qrels không đi vào indexer hoặc dịch vụ production.

## 3. Cấu trúc sẽ triển khai ở SG-005

```text
scholargraph/
  AGENTS.md
  README.md
  docs/
  management/
    tasks.json
    state.json
    HANDOFF.md
    DECISIONS.md
    logs/
    templates/
  scripts/check_project.ps1        # đã có ở bước planning
  pyproject.toml                  # tương lai
  configs/                        # dataset, model, graph, experiment
  src/scholargraph/
    ingest/
    data/
    retrieval/
    graph/
    evaluation/
    api/
  ui/
  tests/
    unit/
    integration/
    fixtures/
  data/raw/                       # bất biến; không version raw lớn
  data/processed/
  artifacts/indexes/
  artifacts/runs/
  artifacts/reports/
```

## 4. Schema tối thiểu

| Entity | Trường cần có | Quy tắc |
|---|---|---|
| Paper | id, source, source_id, title, abstract, year, doi, topics, source_url, retrieved_at | ID namespace; null khác chuỗi rỗng; giữ bản raw |
| Citation | citing_id, cited_id, source, snapshot_id | Có hướng; không tự sinh từ qrels |
| Query | query_id, text, language, task_type, seed_paper_id | seed_paper_id chỉ cho paper-to-paper |
| Qrel | query_id, doc_id, relevance, label_source, split | evaluator-only; label scale có tài liệu |
| Ranking | query_id, doc_id, rank, score, run_id | rank unique; score hữu hạn; doc ID thuộc candidate universe |
| Explanation | text_score, graph_score, graph_path, metadata_status | Nguồn score rõ; không dùng làm bằng chứng paper đúng |
| Manifest | dataset_id, source_url, revision, retrieved_at, checksum, counts, license, transformations | Không dùng ID snapshot mơ hồ |
| Run | id, status, config_hash, data_hash, graph_hash, model_revision, code_version | completed chỉ khi outputs và checks đủ |

## 5. Interface cần ổn định

- Ingestor: tải/cache/resume → manifest + raw snapshot.
- Validator: kiểm tra schema/ID/qrels/time → report.
- Retriever: `search(query, top_k, filters)` → list kết quả.
- Recommender: `recommend(paper_id, top_k, filters)` → list bỏ self.
- Reranker: nhận query, candidates, graph context được phép; không nhận qrels.
- Evaluator: nhận qrels + runfile + metric config; không thay đổi ranking.
- API trả snapshot_id, method_id và metadata thiếu; lỗi phụ thuộc không được thay bằng dữ liệu bịa.
- Benchmark UI chỉ đọc completed run manifest.

## 6. Kiểm thử quan trọng

- DOI dedup/mapping không nhập nhằng; mọi transformation có audit.
- Download bị ngắt resume không làm mất/trùng records.
- qrels ID tồn tại; split group không chồng; labels không lọt ranker.
- Mask held-out cạnh/cạnh đảo và recompute graph features.
- PPR trên toy graph có đáp án kỳ vọng; không nối node giả khi missing.
- Metrics so với evaluator chuẩn và case tie/zero relevant/no results.
- Hybrid dùng common candidates đúng ablation; graph isolated fallback minh bạch.
- API/UI trả metadata và nguồn khớp snapshot.
- Offline smoke test không gọi mạng; thiếu model/index trả lỗi hữu ích.
