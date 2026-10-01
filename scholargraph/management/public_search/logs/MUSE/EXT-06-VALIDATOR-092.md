# EXT-06 validator — MUSE — 2026-10-01

## Phạm vi và bằng chứng

- Files: `tests/integration/test_public_adversarial.py`, `tests/integration/test_public_verifier.py`, `scripts/verify_public_search.py`.
- Mọi fixture/request/DB của test nằm trong `tmp_path`; không ghi vào core data. Không có live network: HTTP được bơm bằng `httpx.MockTransport`.
- Verifier chỉ đọc freeze/split/hash; path traversal, thiếu key, thiếu file, hash sai và dữ liệu split không hợp lệ đều trả `INSUFFICIENT_EVIDENCE`, CLI exit 1.
- Acceptance không được suy ra từ test synthetic: `pilot=NOT_RUN` bắt buộc `INSUFFICIENT_EVIDENCE` và exit 1.

## Ma trận bắt buộc

| Case | Status | Count | Evidence / reason |
|---|---:|---:|---|
| Missing config / duplicate request JSON | PASS | 2 | CLI subprocess exit 1, không traceback |
| Corrupt SQLite không rebuild | PASS | 1 | DB sentinel giữ nguyên, CLI exit 1 |
| Partial/all source failure | PASS | 1 | API non-2xx, overall `failed`, snapshot có lỗi |
| Leakage sentinel read interception | PASS | 1 | instrument `builtins.open` chặn đọc labels/qrels/heldout; service không chạm file |
| Real adapters + injected HTTP + SQLite/raw snapshot/export | PASS | 1 | OpenAlex và arXiv parser chạy qua MockTransport, snapshot/raw lưu được |
| Verifier missing acceptance key | PASS | 1 | exit 1, report `INSUFFICIENT_EVIDENCE`, không KeyError |
| Verifier missing required split | PASS | 1 | exit 1, reason `required_splits` |
| Verifier pilot NOT_RUN | PASS | 1 | exit 1, reason `pilot` |
| Live pilot | NOT_RUN | 0 | Không chạy live trong validator; cần query độc lập và raw evidence được người dùng xác nhận |
| Core freeze/split trên snapshot thật | NOT_RUN | 0 | Chưa được phép tự tạo hoặc thay thế required core manifest |

## Lệnh và kết quả

`\.venv\Scripts\python.exe -m pytest -q tests/integration/test_public_adversarial.py tests/integration/test_public_verifier.py` — **11 passed**, exit 0.

CLI negative cases được chạy trong test qua subprocess và đều exit 1. Không claim relevance metric hay pilot latency từ synthetic fixture.

## Giới hạn / bước tiếp theo

Cần coordinator cung cấp manifest core freeze/splits và acceptance evidence thật (pilot, regression, UI) để chạy verifier end-to-end. Khi pilot còn `NOT_RUN`, verdict chính thức vẫn `INSUFFICIENT_EVIDENCE`.

Public integration regression: `\.venv\Scripts\python.exe -m pytest -q tests/unit/test_public_service.py tests/integration/test_public_cli.py tests/integration/test_public_routes.py` — **21 passed**, exit 0.

Nested freeze data map negative case: PASS (missing frozen JSONL produces exit 1); focused verifier + adversarial suite total now 11 passed.

## Bổ sung sau audit schema — checkpoint 2026-10-01

- Coordinator là người ghi duy nhất `scripts/verify_public_search.py`; worker chỉ sửa `tests/integration/test_public_verifier.py` và log này.
- Fixture validator được tạo trong `tmp_path`: freeze đủ nonempty `data` (nhóm nested), `splits`, `graph`, `models`, `configs`; hai split có `query_ids` và `query_count`; acceptance dùng object + evidence paths có hash. Đây chỉ là synthetic test schema, không nghiệm thu học thuật/pilot thật.
- Lượt schema đầu: 1 failed / 51 passed do fixture chưa khai `pilot.evidence_status`; thêm trường đúng contract, chạy lại **52 passed**, exit 0.
- Bổ sung 8 negatives (hash/path traversal/pilot thiếu evidence_status/reason): lượt đầu combined **2 failed / 65 passed**; CLI traversal đã exit 1 đúng nhưng test helper đòi output file khi preflight chưa cho ghi. Test traversal đã sửa để kiểm report stdout, absence of outputs và toàn bộ input không đổi.
- Đang chờ coordinator pin schema report_path + rederived pilot counts trước final rerun. Chưa claim schema cuối PASS.

## Bàn giao cuối sau schema report/pilot đã pin — 2026-10-01

- Chỉ worker sửa `tests/integration/test_public_verifier.py` và log 092 trong lượt bổ sung này; verifier implementation do coordinator sửa.
- Helper positive tạo actual strict `SearchEnvelope` từ `PublicSearchService` với adapters synthetic + MemoryStore trong tmp; 5 query mỗi query có OpenAlex refresh/cache và 1 run hai nguồn. Mỗi stdout/report/config là file riêng có SHA-256. Đây không phải live pilot, không thay core dataset, không chứng minh hai nguồn thật hoạt động.
- Positive gọi `validate_manifest` trực tiếp để kiểm đầy đủ schema và read-only; không copy production project/test tree vào tmp. Test pilot FAIL kiểm evidence hợp lệ qua `validate_manifest` và CLI nonzero; temp project không có full adversarial test tree nên không claim đã chạy đủ nghiệm thu runtime production từ fixture.
- Lượt đầu sau schema strict report: **2 failed / 58 passed** trong 42.95s. Hai positive bắt lỗi verifier dùng `model_validate` với serialized datetime; coordinator chuyển sang `model_validate_json` sau kiểm duplicate JSON keys và che chi tiết lỗi schema.
- Đã bổ sung đúng risk của schema mới: primary report rỗng/count không hợp lệ; pilot count/P95/median/n sai, CLI không khớp envelope và cache flag sai.

| Nhóm test verifier cuối | PASS | FAIL | NOT_RUN | Lý do/bằng chứng |
|---|---:|---:|---:|---|
| Positive complete schema + complete failed pilot evidence | 2 | 0 | 0 | Strict envelopes, hashes; direct manifest validation không ghi input |
| Missing manifest keys | 5 | 0 | 0 | CLI exit1, report insufficient |
| Freeze object/sections/model/nested data lỗi | 14 | 0 | 0 | CLI exit1; không đọc bỏ qua empty/null sections |
| IDs/query_count/overlap split | 12 | 0 | 0 | CLI exit1, expected reason |
| Missing resources/hash corruption | 8 | 0 | 0 | Core/required files giữ nguyên sau rejection |
| Acceptance object/report/pilot metadata thiếu hoặc giả | 12 | 0 | 0 | Evidence report phải có valid run/count/command; NOT_RUN không PASS |
| Protected output collision/same output/traversal | 11 | 0 | 0 | CLI exit1, mọi input bytes bất biến; preflight không ghi output khi unsafe |
| Pilot narrative ↔ strict stdout/latency mismatch | 6 | 0 | 0 | Recompute count/n/P95/median/CLI/cache từ payload |
| Tổng verifier | **70** | **0** | **0** | Synthetic schema tests |

Lệnh cuối: `\.venv\Scripts\python.exe -m pytest -q tests/integration/test_public_verifier.py tests/integration/test_public_adversarial.py` — **77 passed, 2 warnings in 78.60s**, exit **0** (70 verifier + 7 adversarial). Các warnings là deprecation FastAPI/Starlette, không lỗi assertion.

Đã dừng viết để coordinator pin. Không commit; không sửa board/state/HANDOFF hoặc artifacts report/pilot. Pilot live/evidence operational final chỉ coordinator cung cấp từ runs thật.
