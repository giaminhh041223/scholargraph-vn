# Bàn giao ScholarGraph

NEXT_TASK: SG-007

- Phiên: SESSION-20260915-009; múi giờ Asia/Saigon (UTC+07:00).
- SG-006: **DONE**. Data schemas, boundary interfaces, synthetic fixtures và tài liệu kiến trúc đã hoàn tất; review PASS không có finding P0–P2.
- SG-000 đến SG-006: **DONE** (7 tasks). SG-007 (Runner và run manifest) đủ dependencies và sẵn sàng (TODO).
- Phiên coordinator kiêm worker lane D đã hoàn tất; không còn active assignment hoặc file bị lock.

## Đầu ra và bằng chứng SG-006

- [Data Schemas](../src/scholargraph/data/schemas.py): Định nghĩa Pydantic v2 cho `Paper`, `CitationEdge`, `Query`, `Qrel`, `RankedDocument`, `RankingResult`, `RunManifest`.
  - Phân biệt rõ Paper ID (canonical), DOI (định dạng regex `10.xxxx/...`), Query ID, và Qrel Label.
  - Bắt lỗi: ID/title rỗng, năm ngoài khoảng [1900, 2100], điểm không hữu hạn (NaN/Inf), self-loop citation (`source_id == target_id`), duplicate doc_id trong ranking.
  - Sắp xếp canonical: điểm giảm dần, ties phá bằng doc_id tăng dần theo Unicode code points.
  - Hỗ trợ xuất định dạng dòng chuẩn TREC qua `to_trec_lines()`.
  - Xử lý namespace ID (`parse_namespace_id`, `make_canonical_id`).
  - Null policy: `abstract` rỗng -> `""`; `year` thiếu -> `None` (cấm tự tiện điền median); `doi` thiếu -> `None`.
- [Data Access Interfaces](../src/scholargraph/data/interfaces.py):
  - Định nghĩa `BaseRanker` và `BaseEvaluator`.
  - Nghiệm thu quan trọng: `BaseRanker` kiểm tra chặt chẽ và từ chối nhận `qrels`/`labels` ở cả constructor và phương thức `rank()`, ném ra `DataLeakageError` nhằm ngăn rò rỉ dữ liệu.
- [Package init](../src/scholargraph/data/__init__.py): Re-export đầy đủ schemas, interfaces và helper functions.
- [Synthetic Fixtures](../tests/fixtures/):
  - `synthetic_papers.jsonl`: 6 paper nhân tạo có trích dẫn chéo, phủ các ca đủ metadata, thiếu abstract, thiếu năm (`synthetic=true`).
  - `synthetic_queries.json`: 3 truy vấn mẫu (Anh và Việt).
  - `synthetic_qrels.json`: 5 nhãn qrels ground-truth.
  - `synthetic_manifest.json`: Ví dụ run manifest.
- [Tài liệu Kiến trúc](../docs/ARCHITECTURE.md):
  - Sơ đồ Mermaid luồng dữ liệu (Data Flow) từ Raw Corpus -> Masking/Split -> Retrieval/Ranker -> Evaluator.
  - Ranh giới bảo vệ chống rò rỉ dữ liệu giữa Ranker, Split Builder và Evaluator.
  - Hướng dẫn phân biệt ID vs DOI vs Query ID vs Label.
  - Chính sách giá trị thiếu và quy tắc Namespace ID.
- [Unit Tests](../tests/unit/test_schemas.py): 28 test cases kiểm thử chi tiết mọi validation, tie-breaking, TREC format, DataLeakageError và fixture loading.
- [Review Packet](reviews/SG-006-REVIEW-PACKET.md) và [Báo cáo Review](reviews/SG-006-REVIEW-20260915.md): Review PASS, xác nhận đầy đủ SHA-256 các artifact.
- [Log phiên](logs/SESSION-20260915-009.md): Ghi nhận chi tiết diễn biến triển khai.

## Kiểm tra đã chạy

- `pytest tests/unit/test_schemas.py -v`: 28/28 passed in 0.45s.
- `pytest tests -q`: 34/34 passed in 0.17s across the entire project.
- `powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1`: exit code 0.
  - 50 tasks; dependency acyclic; state consistent.
  - 50 model routes match matrix; 7 logical lanes; 8 registered sessions.
  - Board: DONE=7, TODO=39, DEFERRED=4.

## Bước tiếp tục chính xác

1. SG-006 đã hoàn tất (DONE).
2. Task tiếp theo là **SG-007 — Runner và run manifest** (Mốc: M1, Vai trò: S, Ước tính: 2 giờ-người, Phụ thuộc: SG-006).
3. Đọc task card SG-007 trong `docs/TASKS.md`: triển khai `src/scholargraph/evaluation/runner.py`, cơ chế băm code/config/data/model, ghi nhận phần cứng/seed, xuất manifest và chạy smoke run không ghi đè (immutability).
4. Giữ vững các ranh giới và gate downstream (SG-008 Evaluator, SG-009 Ingestion, SG-014 Graph gate, v.v.).
