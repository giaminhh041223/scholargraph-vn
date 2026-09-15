# SG-006 — Gói review artifact Schema và interface

- Coordinator/session: SESSION-20260915-009, sửa đổi tại SESSION-20260915-010; task SG-006, lane D/C.
- Acceptance nguyên gốc: Bắt ID/score/year sai; Ranker không nhận qrels; Phân biệt rõ Paper ID, DOI, Query ID, Qrel Label; Null policy nhất quán; Fixtures synthetic đầy đủ.
- Đầu ra chính: `src/scholargraph/data/schemas.py`, `src/scholargraph/data/interfaces.py`, `src/scholargraph/data/__init__.py`, `docs/ARCHITECTURE.md`, `tests/fixtures/`, `tests/unit/test_schemas.py`.

## 1. Snapshot đầu vào (Lượt 1)

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

## 2. Review Codex độc lập (Lượt 2)

- Báo cáo: `management/reviews/SG-006-CODEX-REVIEW-20260915.md`
- Kết luận: CHANGES_REQUIRED (2 P1, 3 P2):
  - F1 [P1]: `to_trec_lines` xuất raw score làm mất thứ tự và gây ties giả trong `trec_eval`.
  - F2 [P1]: Guard qrels đặt trong abstract method không bảo vệ subclass không gọi super.
  - F3 [P2]: `CitationEdge` bỏ lọt whitespace ID và năm sai ngoài khoảng [1900, 2100]; `RankingResult` nhận whitespace query_id; `parse_namespace_id(":")` thiếu validation.
  - F4 [P2]: `RankingResult` direct initialization/deserialize không kiểm canonical order.
  - F5 [P2]: `RunManifest` thiếu cờ `synthetic: bool`; `synthetic_manifest.json` thiếu `synthetic: true`.

## 3. Snapshot sau khi sửa toàn bộ F1–F5 (Lượt 3)

| File | SHA-256 mới | Thay đổi chính |
|---|---|---|
| `src/scholargraph/data/schemas.py` | `FD82D3DD69376904B34D33EFD812F949FF1EA58A681B8969D22E24BA0BBD4291` | F1: `to_trec_lines` xuất strictly decreasing score $N - \text{rank} + 1$; F3: validator whitespace/year/namespace; F4: validator canonical order khi direct init; F5: thêm field `synthetic`. |
| `src/scholargraph/data/interfaces.py` | `3F984518E04536E34EE7AEF9BCD6294C2D8766D34D748800973004C507681029` | F2: Template Method Pattern cho `BaseRanker`: `rank()` là public concrete method duyệt `FORBIDDEN_RELEVANCE_KEYS`, subclass chỉ implement hook `_rank()`. |
| `src/scholargraph/data/__init__.py` | `6C975E89AAE9B8D26B94245ED63CCF136F41525FB7F511D65DC22C845CDA75AB` | Giữ nguyên. |
| `docs/ARCHITECTURE.md` | `7C7586BB0C21A6D1C85C430B1C3BCD26607229271480321BB5247481FF2042AE` | Cập nhật Template Method Pattern, TREC strictly decreasing serialization và cờ synthetic trong manifest. |
| `tests/fixtures/synthetic_manifest.json` | `45F93407EA0B672F00C5EF5F076837B999A95887D2804A6CDA8532B950AA2DDC` | F5: Thêm `"synthetic": true`. |
| `tests/unit/test_schemas.py` | `315ADE10265B9A94417A23C9118CCBE6FBAE9280DDB672F6024F9455268E911D` | Mở rộng 36 unit tests bao phủ 100% các ca F1–F5. |
| `tests/fixtures/synthetic_papers.jsonl` | `11F12440202D470021DC3310BFE29FCA02300705382872E935058936758266D0` | Giữ nguyên. |
| `tests/fixtures/synthetic_queries.json` | `1BD7FBA972DF2F8A6FF182C24C2CD178B9580A427EEDAE42D26F99994ABA5AE6` | Giữ nguyên. |
| `tests/fixtures/synthetic_qrels.json` | `AB2D8F22BBEDA9516B01E3B566BDFCD6195CA23DB39214649C096EB8A35E7FC8` | Giữ nguyên. |

## 4. Tự kiểm tra sau sửa đổi

- `pytest tests/unit/test_schemas.py -v`: **36/36 passed** (0.32s).
- `pytest tests -q`: **42/42 passed** (0.29s) trên toàn bộ dự án.
- `powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1`: exit 0.
