# SESSION-20260915-013-OPENALEX-FIX

- Bắt đầu: 2026-09-15T22:02:39+07:00.
- Worker: `/root/sg013_openalex_pilot`; lane D.
- Task: SG-013 correction after fresh-context review.
- Phạm vi: `src/scholargraph/ingest/openalex.py`, `tests/unit/test_openalex.py`, `artifacts/reports/openalex_pilot_correction.json`, và log này. Raw snapshot, manifest và report gốc are immutable; artifact correction có version được phép tạo mới.
- Must resolve only F1–F3 in `management/reviews/SG-013-REVIEW-20260915.md`; do not modify control files.

## Correction đã thực hiện

### F1 — Không cho upstream error/transport exception làm lộ credential

- `_safe_error_message()` không còn đưa bất kỳ nội dung error body nào vào exception. JSON object/list chỉ sinh diagnostic cố định `upstream JSON error details omitted`; non-JSON cũng chỉ ghi loại response.
- Catch toàn bộ `httpx.RequestError` và chỉ giữ tên lớp exception (`RemoteProtocolError`, `TimeoutException`, v.v.), không giữ message có thể phản chiếu header/token.
- Endpoint cấu hình bị từ chối nếu chứa query parameters, username hoặc password; lỗi parse URL được thay bằng thông báo cố định không echo URL đầu vào.
- Regression dựng nested JSON error phản chiếu Bearer/API key synthetic và transport exception phản chiếu cùng secret; kiểm cả `str(exception)` và traceback không chứa secret.

### F2 — Tôn trọng đầy đủ Retry-After/quota reset

- `max_backoff_seconds` giờ chỉ cap exponential backoff do client tự chọn.
- `Retry-After` hợp lệ là cận dưới không bị cap: hỗ trợ cả delay-seconds và HTTP-date theo RFC 9110.
- Khi `X-RateLimit-Remaining <= 0`, `X-RateLimit-Reset` của OpenAlex cũng là cận dưới; client không retry trước thời điểm quota reset.
- Regression xác minh ba trường hợp khi client backoff cap là 60 giây: `Retry-After: 120` chờ 120; HTTP-date +180 giây chờ 180; quota exhausted/reset 240 giây chờ 240.

### F3 — Phân biệt location với venue thật

- Report builder mới xuất riêng `coverage.primary_location` cho object location hiện hữu.
- `coverage.venue` chỉ đúng khi `primary_location.source.display_name` hoặc `primary_location.raw_source_name` là chuỗi không rỗng; landing URL hoặc source ID đơn thuần không còn được coi là venue coverage.
- Regression gồm: venue có `source.display_name`, venue chỉ có `raw_source_name`, location chỉ có URL, và location null. Kết quả mong đợi 3/4 location nhưng chỉ 2/4 venue.

## Bằng chứng kiểm tra

- Lần chạy unit đầu sau correction: 7 passed, 1 failed vì test interruption cũ còn chờ nguyên upstream message. Assertion được cập nhật để chờ diagnostic đã redacted; không phải lỗi implementation mới.
- Closeout `python -m pytest tests/unit/test_openalex.py -q`: **8 passed in 2.51s**.
- Closeout `python -m pytest tests -q`: **70 passed in 4.40s**.
- `scripts/check_project.ps1`: **PASS**; 50 tasks, dependency/state/model routes và 198 local Markdown links hợp lệ tại thời điểm chạy.
- Hash implementation correction:
  - `src/scholargraph/ingest/openalex.py`: `573e64947622249c74668da6ce1f8e6550a4014b44ba9ecce56e0eaa3b628919`.
  - `tests/unit/test_openalex.py`: `51f41319aa7b39bd01b710236908e541bdde10e0f1febfe137f4fc97eb788c50`.

## Immutability và report correction cần coordinator xử lý

- Không gọi mạng và không thay raw snapshot, manifest hay report trong correction này.
- Hash vẫn giữ nguyên so với review:
  - `data/raw/openalex/works.jsonl`: `3f301e4fc6c9b0de1fa95f736d0ceff2fa6fac137c086e0716fc3afe761c4980`.
  - `data/manifests/openalex_pilot.json`: `830391357c29ce3e197cd0b4b83eff0c4ce835bd5d59119535e59618962f87b8`.
  - `artifacts/reports/openalex_pilot.json`: `c55dd5ca74e63edb6eece6966edc12c5521c6c17eea979841f95281736b90a27`.
- Report immutable hiện tại vẫn mang số cũ `coverage.venue = 2000/2000`; field này phải được đánh dấu superseded/không dùng cho claim.
- Chạy report builder đã sửa trên 2.000 raw works ở chế độ chỉ đọc cho kết quả:
  - `primary_location`: **2.000/2.000 = 100%**.
  - tên venue thực (`source.display_name` hoặc `raw_source_name`): **1.627/2.000 = 81,35%**.
- Coordinator cần tạo artifact correction có version/provenance/hash mới và giữ nguyên report cũ để audit. Worker không có quyền sửa report hoặc control files trong session này.

## Bàn giao

- F1–F3 đã được sửa đúng phạm vi code/tests; không tự chuyển task DONE.
- Cần fresh-context re-review trên hai hash implementation correction ở trên.
- Không được dùng venue 100% từ report cũ trong SG-014 hoặc báo cáo học thuật; dùng correction artifact đã version hóa sau khi coordinator phát hành.
- Kết thúc/checkpoint: 2026-09-15T22:06:06+07:00.

## Bổ sung được coordinator cho phép — versioned report correction

- Tạo mới `artifacts/reports/openalex_pilot_correction.json`; không sửa hoặc ghi đè report gốc, raw snapshot hay manifest.
- Artifact correction liên kết bằng snapshot ID, query fingerprint và SHA-256 tới:
  - report gốc `c55dd5ca74e63edb6eece6966edc12c5521c6c17eea979841f95281736b90a27`;
  - raw works `3f301e4fc6c9b0de1fa95f736d0ceff2fa6fac137c086e0716fc3afe761c4980`;
  - snapshot manifest `830391357c29ce3e197cd0b4b83eff0c4ce835bd5d59119535e59618962f87b8`;
  - corrected report builder `573e64947622249c74668da6ce1f8e6550a4014b44ba9ecce56e0eaa3b628919`.
- Correction scope chỉ gồm `coverage.venue` và bổ sung `coverage.primary_location`. Artifact ghi rõ mọi metric khác vẫn được trích từ report bất biến ban đầu và không được tuyên bố là đã đo lại.
- Corrected values: primary location 2.000/2.000 = 1,0; venue name 1.627/2.000 = 0,8135.
- Kiểm tra parse/provenance: JSON parse PASS; snapshot ID/query fingerprint khớp manifest; các hash khớp file; record count raw là 2.000; count/total khớp fraction; original venue value khớp report bị supersede.
- SHA-256 artifact correction: `fd01d9fb396710e0f68f49b8b4c58d72240dc4e0db1a486579a2054a656b2f7a`.
- Checkpoint bổ sung: 2026-09-15T22:10:25+07:00.
