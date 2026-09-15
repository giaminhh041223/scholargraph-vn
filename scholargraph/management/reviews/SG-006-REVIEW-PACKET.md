# SG-006 — Gói review artifact Schema và interface

- Coordinator/session: SESSION-20260915-009; task SG-006, lane D/C.
- Snapshot: danh sách file và mã SHA-256 dưới đây; không sửa các file này trong lượt review.
- Acceptance nguyên gốc: Bắt ID/score/year sai; Ranker không nhận qrels; Phân biệt rõ Paper ID, DOI, Query ID, Qrel Label; Null policy nhất quán; Fixtures synthetic đầy đủ.
- Đầu ra chính: `src/scholargraph/data/schemas.py`, `src/scholargraph/data/interfaces.py`, `src/scholargraph/data/__init__.py`, `docs/ARCHITECTURE.md`, `tests/fixtures/`, `tests/unit/test_schemas.py`.

## 1. Snapshot đầu vào

| File | SHA-256 |
|---|---|
| `src/scholargraph/data/schemas.py` | `6F7CA4BC0932DB05E488FCA6EFC5C7A9C4CAC7B851B2396FC07A3A4E43378682` |
| `src/scholargraph/data/interfaces.py` | `87D5127447688E6A6CD591F6303BD1375B28A848F4AD27C34809BB7C6F957A82` |
| `src/scholargraph/data/__init__.py` | `6C975E89AAE9B8D26B94245ED63CCF136F41525FB7F511D65DC22C845CDA75AB` |
| `docs/ARCHITECTURE.md` | `D790006C5A8FAB8AAA88AB9A42364BEEEED7674060DCD81931CE86D9D62C8C21` |
| `tests/unit/test_schemas.py` | `5A21F8265978410BF4CA677E4F6025B4456B00C820358A1B72A30357150FA1AF` |
| `tests/fixtures/synthetic_papers.jsonl` | `11F12440202D470021DC3310BFE29FCA02300705382872E935058936758266D0` |
| `tests/fixtures/synthetic_queries.json` | `1BD7FBA972DF2F8A6FF182C24C2CD178B9580A427EEDAE42D26F99994ABA5AE6` |
| `tests/fixtures/synthetic_qrels.json` | `AB2D8F22BBEDA9516B01E3B566BDFCD6195CA23DB39214649C096EB8A35E7FC8` |
| `tests/fixtures/synthetic_manifest.json` | `0C337275512034AE370EC23D32811494AB0F6D8CC1C6B7412A2A725908E41CF3` |

## 2. Tiêu chí kiểm tra của Reviewer

1. **Schema Validation**:
   - `Paper`: Bắt ID rỗng, title rỗng, year ngoài khoảng `[1900, 2100]`. Missing abstract chuyển thành `""`, missing year giữ `None` (không impute median). DOI kiểm tra format `10.xxxx/...`.
   - `CitationEdge`: Cấm self-loop `source_id == target_id`.
   - `RankedDocument` & `RankingResult`: Cấm điểm `NaN` hoặc `Inf`. Cấm trùng lặp `doc_id` trong cùng query. Thứ tự chuẩn: score desc, ties theo doc_id asc.
   - `RunManifest`: Kiểm tra pattern run_id chuẩn hóa.
2. **Bảo vệ ranh giới (Data Leakage Protection)**:
   - `BaseRanker` từ chối `qrels`/`labels` ở cả constructor và phương thức `rank()`, kích hoạt `DataLeakageError`.
3. **Synthetic Fixtures**:
   - Đầy đủ papers, queries, qrels, manifest mẫu, đều đánh dấu `synthetic=True`.
4. **Kiến trúc hệ thống**:
   - `docs/ARCHITECTURE.md` phản ánh trung thực Giao thức nghiên cứu v1 và luồng dữ liệu.

## 3. Tự kiểm tra của Worker

- Đã chạy `pytest tests/unit/test_schemas.py -v`: 28/28 tests passed.
- Đã chạy `pytest tests -q`: 34/34 tests passed.
- Đã chạy `powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1`: exit 0.
