# Final re-review SG-013 — OpenAlex pilot có resume

- Bắt đầu: 2026-09-15T22:13:27+07:00.
- Reviewer: `/root/sg013_final_review`; fresh context.
- Scope chỉ đọc: OpenAlex code/tests, raw snapshot, manifest, original report, versioned correction artifact, worker/review logs.
- Must verify F1–F3, raw/manifest preservation and correction-artifact provenance.
- Verdict: **PASS — F1–F3 đã được xử lý; không có finding P0–P2 còn mở trong phạm vi tái thẩm định.**
- Hoàn tất kiểm tra nội dung: 2026-09-15T22:18:00+07:00. Reviewer không tự chuyển task DONE.

## Phiên bản được kiểm tra

| Artifact | SHA-256 |
|---|---|
| `src/scholargraph/ingest/openalex.py` | `573e64947622249c74668da6ce1f8e6550a4014b44ba9ecce56e0eaa3b628919` |
| `tests/unit/test_openalex.py` | `51f41319aa7b39bd01b710236908e541bdde10e0f1febfe137f4fc97eb788c50` |
| `data/manifests/openalex_pilot.json` | `830391357c29ce3e197cd0b4b83eff0c4ce835bd5d59119535e59618962f87b8` |
| `artifacts/reports/openalex_pilot.json` | `c55dd5ca74e63edb6eece6966edc12c5521c6c17eea979841f95281736b90a27` |
| `data/raw/openalex/works.jsonl` | `3f301e4fc6c9b0de1fa95f736d0ceff2fa6fac137c086e0716fc3afe761c4980` |
| `artifacts/reports/openalex_pilot_correction.json` | `fd01d9fb396710e0f68f49b8b4c58d72240dc4e0db1a486579a2054a656b2f7a` |
| `docs/RESEARCH_PROTOCOL.md` | `90e6b80f5c54b8a4bc445faffaaca9d7174f9024cb551feb9cc86e489b093351` |

Đã đối chiếu AGENTS, state/HANDOFF, task/dependency/routing/registry SG-013, chiến lược model, ADR-012, protocol B và giới hạn research evidence, task card, log worker ban đầu, review ban đầu, log correction và correction artifact. Working tree có các file của coordinator/worker khác; reviewer chỉ ghi report này và log phiên được giao.

## Kết quả tái thẩm định

### F1 — PASS: error diagnostics không phản chiếu secrets

- `_safe_error_message()` ở dòng 651 chỉ trả thông báo cố định theo dạng response; không đưa giá trị hoặc khóa từ body vào exception. Nhánh `_fetch_page()` bắt `httpx.RequestError` cùng lỗi JSON/ValueError ở dòng 282, chỉ giữ tên lớp, rồi tạo lỗi cuối bên ngoài khối `except`.
- Chạy trực tiếp source hiện tại với fake client và dependency stub trong bộ nhớ: HTTP 401 với message đơn, nested object, list, string và JSON decode failure chứa cùng secret synthetic. Cả năm trường hợp không chứa secret trong exception hoặc traceback.
- Bốn dạng transport/parse exception chứa secret synthetic (`RequestError`, `RemoteProtocolError`, `ValueError`, `JSONDecodeError`), mỗi dạng đi hết vòng retry: exception cuối và traceback đều không chứa secret. Không có exception chaining làm lộ lại message đã loại bỏ trong các đường này.
- Đọc regression test mới và cơ chế endpoint validation: query credentials/userinfo bị từ chối bằng diagnostic cố định. Đây là xác minh các đường lỗi đã nêu; không phải tuyên bố đã chạy HTTP integration hoặc quét mọi hành vi của thư viện HTTP thật.

### F2 — PASS: server delay được giữ làm cận dưới

- Dòng 289–296 chỉ cap exponential backoff do client tự chọn; tổng delay là max của client backoff, Retry-After và quota reset.
- Fake sleeper ghi nhận đúng: numeric `Retry-After: 120` → 120 giây; HTTP-date sau clock cố định 180 giây → 180; remaining=0/reset=240 → 240; kết hợp Retry-After=120 và quota reset=240 → 240. Các delay này vượt cap client 60 giây mà không bị rút ngắn.
- Header không hợp lệ và HTTP-date đã qua trả 0; parser date dùng timezone-aware clock. Không có lần chờ thật hoặc API request trong probes.

### F3 — PASS: correction có định nghĩa và provenance nhất quán

- Builder phân biệt object primary location hiện hữu với venue có `source.display_name` hoặc `raw_source_name` là chuỗi không rỗng, tại dòng 624–640.
- Chạy builder hiện tại trên đúng 2.000 raw works trong bộ nhớ: primary location **2.000/2.000 = 100%**, venue **1.627/2.000 = 81,35%**. Count, denominator và fraction khớp từng field của correction artifact.
- SHA-256 của raw works, manifest, builder và report bị supersede đều khớp provenance ghi trong correction. Snapshot ID và query fingerprint khớp manifest, original report và config. Giá trị venue bị thay thế khớp 2.000/2.000 trong bản gốc.
- Correction chỉ supersede `coverage.venue` và bổ sung `coverage.primary_location`, khai báo rõ không đo lại mọi metric khác. Report gốc vẫn được bảo toàn để audit. Downstream phải đọc correction cùng report gốc và dùng venue **81,35%**.

## Bảo toàn snapshot và giới hạn graph claim

- SHA-256 manifest, works và original report giữ nguyên so với review trước. Cả 20 raw page hashes khớp manifest; completed verification kiểm lại payload hashes thành công và không gọi mạng.
- Ghép results từ pages đúng bằng 2.000 records JSONL, có 2.000 IDs duy nhất; mỗi record chứa assigned topic T10286. Dedup khi thêm lại page đầu vẫn giữ 2.000 works.
- Đếm độc lập từ raw bằng tập cạnh/ID/năm: **190** internal directed edges; **1.779** isolated nodes; cohort sơ bộ đúng **21** sources tổng cộng, nhiều nhất **2/năm**. Tổng API-reported cost từ page metadata là **0,002 USD**, không phải xác nhận hóa đơn.
- Đếm cohort chỉ dùng year/title/abstract/≥2 internal references không tương lai như report; chưa phải audit đầy đủ duplicate groups, novel candidates hay masking. Chưa đủ floors 30 dev/50 test của protocol v1. SG-014 vẫn chịu trách nhiệm quyết định graph go/no-go; SG-013 PASS không phải graph gate PASS và không chứng minh chất lượng retrieval.

## Phương pháp, runtime và giới hạn

- Bundled executable: `C:/Users/ADMIN/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
- Lệnh import `httpx, pytest` thất bại với `ModuleNotFoundError: httpx`; lệnh `-B -m pytest tests/unit/test_openalex.py -q` thất bại với `No module named pytest` (exit 1). Không xác minh được exact executable Python 3.13 của worker; **không ghi pytest PASS cho reviewer**, không nhận lại 8/70 tests của worker thành bằng chứng tự chạy.
- Probes dùng stdlib, source module thật, stub `httpx`/fake responses/fake sleeper trong bộ nhớ; exit 0. Đây là kiểm tra luồng điều khiển unit, hash/provenance và đếm dữ liệu, không phải pytest hay HTTP integration. Đã đọc toàn bộ 8 regression tests nhưng không thực thi chúng trong runtime này.
- Không ghi hoặc tải lại raw/manifest/reports; không sửa implementation, board, task card hay shared state. Coordinator nhận verdict cùng giới hạn kiểm thử để quyết định closeout.
