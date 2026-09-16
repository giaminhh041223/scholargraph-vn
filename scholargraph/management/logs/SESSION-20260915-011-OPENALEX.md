# SESSION-20260915-011-OPENALEX

- Bắt đầu: 2026-09-15T21:22:46+07:00.
- Worker: `/root/sg013_openalex_pilot`; lane D.
- Task: SG-013 — OpenAlex pilot có resume.
- Phạm vi được giao: ingestion pilot, tests, raw snapshot, manifest và báo cáo pilot OpenAlex.
- Không sửa shared board/state/handoff/chat registry. Chưa có kết quả kiểm tra tại thời điểm nhận việc.

## Đã đọc và đối chiếu

- Đọc `AGENTS.md`, `management/state.json`, `management/HANDOFF.md`, task card và registry SG-013, `management/DECISIONS.md`, `docs/RESEARCH_PROTOCOL.md`, cùng schema/interface thực tế của SG-006.
- Xác minh SG-005 và SG-006 đã DONE; SG-013 được coordinator gán đúng owner/session/phạm vi file.
- Đối chiếu tài liệu OpenAlex chính thức cập nhật 2026 về API response/cost, giới hạn `per_page=100`, basic/cursor pagination, retry 429/5xx, seeded sampling, topic inference, citation matching và CC0:
  - `https://help.openalex.org/api/`
  - `https://help.openalex.org/api/authentication/`
  - `https://help.openalex.org/api/errors/`
  - `https://help.openalex.org/api/paging/`
  - `https://help.openalex.org/how-to/api-recipes/`
  - `https://help.openalex.org/data/topics/`
  - `https://help.openalex.org/data/works/citations/`
- Truy vấn lookup công khai xác định `T10286` là topic “Information Retrieval and Search Behavior”; không chọn bằng retrieval score.

## File đã tạo/thay đổi trong phạm vi worker

- `src/scholargraph/ingest/openalex.py`
  - Loader pilot 1.000–3.000 work với seeded topic sample, basic pagination, timeout, rate interval, retry/backoff cho 429/5xx/network timeout.
  - API key nếu có chỉ đi qua Bearer header; request/page/checkpoint/manifest không lưu credential.
  - Cache mỗi page bằng atomic write và SHA-256; resume dựng lại từ raw page cache đã kiểm checksum, không phụ thuộc checkpoint còn tồn tại.
  - Deduplicate theo canonical OpenAlex work ID; output đúng `target_count`; completed manifest ngăn ghi đè và phát hiện artifact bị sửa.
  - CLI mặc định SG-013: topic `T10286`, target 2.000, seed `20260915`.
- `tests/unit/test_openalex.py`: 5 tests cho validation/canonical ID, retry/backoff + secret hygiene, resume khi mất checkpoint + duplicate page boundary, và tamper detection cho output lẫn raw-page hash trong manifest.
- `data/raw/openalex/pages/page-00001.json` … `page-00020.json`: raw projected API responses và request metadata đã loại credential.
- `data/raw/openalex/works.jsonl`: 2.000 raw projected work records duy nhất, SHA-256 `3f301e4fc6c9b0de1fa95f736d0ceff2fa6fac137c086e0716fc3afe761c4980`.
- `data/raw/openalex/checkpoint.json`: checkpoint trạng thái COMPLETED.
- `data/manifests/openalex_pilot.json`: manifest snapshot/source/filter/topic/seed/time/hash/license/namespace/immutability.
- `artifacts/reports/openalex_pilot.json`: coverage, internal graph evidence và cost/time/size projection.

## Pilot thật và kết quả đo

- Snapshot ID: `openalex-api-t10286-seed20260915-3c6a3a485dfc`.
- Selection: OpenAlex core corpus, `topics.id:T10286`, seeded random sample `20260915`; API sample size 2.100 để chừa một page xử lý merged/duplicate IDs, dừng khi đủ 2.000 unique works.
- Cửa sổ tải: `2026-09-15T21:36:38.262439+07:00` đến `2026-09-15T21:37:19.525416+07:00`.
- 20 pages; 2.000 API records; 2.000 unique selected; 0 duplicate; 0 retry.
- API-reported cost: USD 0,002; active request time 39,612 giây.
- Coverage: title 99,8%; abstract inverted index 60,4%; valid year 98,75%; DOI 60,1%; có reference 41,85%.
- Tổng 20.102 references tới OpenAlex work nhưng chỉ 190 occurrences/190 directed edges nằm trong pilot (0,9452%); 1.779/2.000 node cô lập trong induced snapshot.
- Theo điều kiện đầu vào protocol B (year/title/abstract hợp lệ và ≥2 internal references không ở tương lai), không năm nào có hơn 2 source hợp lệ. Pilot này không đạt floor cohort 30 dev/50 test; kết luận go/no-go thuộc SG-014 và không được hạ floor dựa trên kết quả này.
- Linear projection từ measured API pages: 10K ≈ USD 0,01, 198,062 active seconds, 53.569.900 bytes; 20K ≈ USD 0,02, 396,124 active seconds, 107.139.800 bytes. Đây không phải cam kết vì chưa tính rate-limit wait, drift upstream hay thay đổi pricing/record size.

## Kiểm tra/lệnh và kết quả

- `python -m pytest tests/unit/test_openalex.py -q`: không chạy vì `python` không có trong PATH của worker shell.
- Bundled Python `...codex-primary-runtime...python.exe -m pytest`: không chạy vì bundled runtime không có pytest.
- Local Python 3.13 `-m pytest tests/unit/test_openalex.py -q`: lần đầu **4 passed in 2.49s**; sau khi bổ sung kiểm tra raw-page manifest hash, **5 passed in 3.04s**.
- Lần đầu chạy `-m scholargraph.ingest.openalex`: không tìm thấy package vì project chưa được install/PYTHONPATH không đặt; không tạo artifact.
- Chạy trực tiếp `python src/scholargraph/ingest/openalex.py ...`: **COMPLETED**, 2.000 unique works.
- Local Python 3.13 `-m pytest tests -q`: lần đầu **61 passed in 7.94s**; closeout **62 passed in 3.93s** (full suite tại từng thời điểm kiểm tra).
- `powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1`: **PASS**, 50 tasks, DAG/state/model routes/198 local links hợp lệ.
- Secret scan trên raw pages, works, checkpoint, manifest và report theo các pattern credential: không có match. Log chỉ nêu tên cơ chế/biến môi trường phục vụ tái lập, không chứa giá trị credential.
- Chạy lại cùng CLI sau COMPLETED: trả manifest đã xác minh, không gọi hoặc ghi lại API; raw-page inventory và SHA-256 từng page khớp manifest.

## Hạn chế và bàn giao

- Đây là local extraction bất biến từ live API, không phải official OpenAlex bulk snapshot release. Seed chỉ tái tạo cùng mẫu nếu database upstream chưa đổi; local page hashes mới là bằng chứng snapshot.
- `topics.id` khớp một trong tối đa ba topic do OpenAlex suy luận bằng model; có selection bias. OpenAlex `referenced_works` chỉ gồm reference đã được họ map thành công.
- Graph coverage của sample ngẫu nhiên 2K/39K topic works rất thấp; SG-014 phải audit và quyết định no-go hoặc thay đổi chiến lược sampling/snapshot bằng ADR trước test, không được biến SG-013 thành kết quả graph chính thức.
- Task đã có đủ implementation, raw snapshot, manifest, measured report và tests để fresh-context review. Worker không tự sửa `management/tasks.json`, `state.json`, `HANDOFF.md` hoặc tự chuyển DONE.
- Kết thúc/checkpoint: 2026-09-15T21:43:02+07:00.
