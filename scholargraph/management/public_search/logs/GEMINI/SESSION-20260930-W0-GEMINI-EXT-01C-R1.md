# SESSION-20260930-W0-GEMINI-EXT-01C-R1 — Reconciliation R1 trước review (`EXT-01C`)

- **Ngày thực hiện:** `2026-09-30T09:25:00+07:00`
- **Task ID:** `EXT-01C` — Luồng UI và request/response examples (Reconciliation R1)
- **Worker / Role:** `GEMINI` (Owner `EXT-01C`, Reviewer dự kiến: `MUSE`)
- **Dispatch ID nhận bàn giao:** `DISPATCH-20260930-W0-GEMINI`
- **Worker Execution Session ID:** `SESSION-20260930-W0-GEMINI-EXT-01C-R1`
- **Requested Model (theo prompt):** `gemini 3.8 flash high`, effort `high`
- **Actual Model / Effort (xác minh từ runtime):** `unknown (not exposed by Antigravity runtime environment; user-selected high effort)` — Không dùng nhãn prompt làm chứng cứ runtime.
- **Checkout / Project Root:** `D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/`
- **Git Branch:** `codex/public-search-gemini`
- **Starting Head Commit SHA:** `78177a8dce76322e43692dbe0ad90b4b70ba78b7`
- **Authoritative SOL Contract Reference (READ-ONLY):**
  - Checkout: `D:/Web_mining_20261/scholargraph/.worktrees/public-sol/scholargraph/`
  - Proposed SOL Head: `93f8c75e7599a96598f36421254608f3ccb081fc`
  - Contract Module: `src/scholargraph/public_search/contracts.py` (v1.0.0, schema 1, config 1.0.0-unverified)
  - Contract Status: PROPOSED (đang chờ review W0, source policy unverified, contract CHƯA freeze).

---

## 1. Mục tiêu phiên làm việc & Phạm vi cấp quyền

1. **Mục tiêu:**
   - Đối chiếu và chuẩn hóa 1:1 toàn bộ các ví dụ request/response trong `tests/fixtures/public_search/gemini/ux_examples.json` với typed models của SOL (`contracts.py`).
   - Sửa sai khác về tên trường, hình dạng (shapes), bộ đếm (counts), truy nguyên nguồn (field_provenance), trường nullable/missing_fields, phân loại lỗi (SearchError.kind), và trạng thái (overall_status -> overall).
   - Tách bạch các contract type tương ứng: `SearchEnvelope`, `SearchRequest` (ValidationError 422), `LibraryEntry` thay vì ép tất cả vào `SearchEnvelope`.
   - Cập nhật tài liệu đặc tả `docs/public_search/UX_SPEC.md` và `tests/fixtures/public_search/gemini/ux_examples.sidecar.json`.
   - Soạn thảo script kiểm chứng runnable `tests/fixtures/public_search/gemini/validate_fixtures.py` kiểm tra nạp typed models SOL và kiểm thử phá hủy (negative/adversarial tests).
   - Xuất packet bàn giao `management/public_search/packets/GEMINI/EXT-01C-R1.md`.
2. **Tuân thủ ranh giới và chỉ thị:**
   - Chỉ chỉnh sửa đúng các tệp thuộc quyền sở hữu của GEMINI (`docs/public_search/UX_SPEC.md`, `tests/fixtures/public_search/gemini/`, `management/public_search/logs/GEMINI/`, `management/public_search/packets/GEMINI/`).
   - Không chạm vào `management/tasks.json`, board chính hay bất kỳ checkout nào khác.
   - Do terminal/RunCommand bị policy deny trong môi trường headless, toàn bộ thay đổi được thực hiện bằng native file tools. Các lệnh cần thực thi được đánh dấu rõ là `NOT_RUN` kèm câu lệnh chi tiết để coordinator chạy và commit thay.

---

## 2. Findings & Các điểm đối chiếu đã xử lý (P0..P3)

- **Finding P1 (Tên trường Request):** Trong fixture provisional cũ, tham số ngân sách mỗi nguồn là `per_source_cap`. SOL `SearchRequest` định nghĩa `cap_per_source: Budget` (1..50). Đã đổi toàn bộ request params sang `cap_per_source`.
- **Finding P1 (Tên trường Trạng thái Tổng thể):** Trong fixture provisional cũ dùng `overall_status`. SOL `SearchEnvelope` và `SearchSnapshot` định nghĩa `overall: Literal["success", "empty", "partial_failure", "failed"]`. Đã đổi 1:1 sang `overall`.
- **Finding P1 (Cấu trúc Source Results):** Trong fixture provisional cũ, `source_results` là dictionary keyed theo tên nguồn (`{"openalex": {...}, "arxiv": {...}}`). SOL `SearchSnapshot` định nghĩa `source_results: list[SourceResult]`. Đã chuẩn hóa thành mảng danh sách `list[SourceResult]` với đầy đủ `source`, `status`, `records`, `error`, `source_total`, `elapsed_seconds`, `filter_coverage`, `truncated`, `raw_references`.
- **Finding P1 (Enum Open Access):** Trong fixture provisional cũ dùng `"green"`, `"gold"`, `"preprint"`. SOL `PaperRecord` định nghĩa `open_access_status: Literal["open", "closed", "unknown"] | None`. Đã chuẩn hóa về enum 3 giá trị của SOL (`"open"`, `"closed"`, `"unknown"`).
- **Finding P1 (Filter Coverage):** Trong fixture provisional cũ dùng `"server_and_post_verified"`. SOL `SourceResult` định nghĩa `filter_coverage: Literal["server", "bounded_pool", "none"]`. Đã đổi chuẩn về `"server"`, `"bounded_pool"`, hoặc `"none"`.
- **Finding P1 (Trạng thái Tác giả):** Trong fixture provisional cũ dùng `authors_status: "available"|"missing"`. SOL `PaperRecord` định nghĩa `authors_availability: Literal["known", "missing"]`. Đã đổi 1:1 sang `authors_availability`.
- **Finding P1 (Cấu trúc Phân loại Lỗi):** Trong fixture provisional cũ dùng `error.code` tự do (`"upstream_timeout"`, `"rate_limited"`). SOL `SearchError` định nghĩa `kind: Literal["request", "config", "policy", "auth", "quota", "timeout", "upstream", "schema", "storage"]` và `message: Text`. Đã quy chuẩn toàn bộ lỗi sang `kind` chuẩn của SOL.
- **Finding P1 (Tách loại Contract Type):** Không ép mọi ví dụ thành `SearchEnvelope`:
  - `example_08_tt07_invalid_request_422`: Mô tả `SearchRequest` đầu vào dị dạng kích hoạt `ValidationError` (HTTP 422 trước mạng).
  - `example_10_library_save_idempotent_and_export`: Mô tả thực thể lưu trữ `LibraryEntry` (`canonical_id`, `snapshot_id`, `saved_at`, `hit`, `incomplete_sources`).
  - `example_11_storage_error_500`: Mô tả `SearchEnvelope` lỗi storage với `overall="failed"`, `snapshot=None`, `errors=[SearchError(kind="storage")]`.
- **Finding P1 (Đẳng thức Bộ đếm & Provenance):**
  - Khớp 1:1 đẳng thức `FusionCounts`: `raw = valid + invalid`, `valid = eligible + excluded_by_year`, `eligible = groups + duplicate_excess`, `returned <= groups` (với `returned = len(hits)`).
  - Trong mọi `SearchSnapshot`: `invalid = 0`, và `valid == len([r for s in source_results for r in s.records])`.
  - Khớp 1:1 `missing_fields` với các trường nullable mang giá trị `null`.
  - Khớp 1:1 `field_provenance` với các trường hiện diện, trỏ đúng về `FieldEvidence` của nguồn/ID/raw hash tương ứng.
- **Finding P2 (Cache Invariants):** Cập nhật `SearchEnvelope` với `cached: bool` và `stale: bool`. Case `refresh=true` gặp lỗi trả về `overall="failed"`, `cached=false`, không tự tiện trả cache cũ giả làm thành công.

---

## 3. Danh sách Outputs đã ghi (Owned Deliverables)

1. `docs/public_search/UX_SPEC.md`
2. `tests/fixtures/public_search/gemini/ux_examples.json`
3. `tests/fixtures/public_search/gemini/ux_examples.sidecar.json`
4. `tests/fixtures/public_search/gemini/validate_fixtures.py`
5. `management/public_search/logs/GEMINI/SESSION-20260930-W0-GEMINI-EXT-01C-R1.md`
6. `management/public_search/packets/GEMINI/EXT-01C-R1.md`

---

## 4. Lệnh kiểm chứng dành cho Coordinator (Commands: NOT_RUN)

Do shell/RunCommand bị từ chối bởi runtime security policy, các lệnh sau được đánh dấu là `NOT_RUN` và được chuyển giao để Coordinator thực thi trong môi trường có shell:

```powershell
# Di chuyển tới worktree của GEMINI
Set-Location -Path "D:\Web_mining_20261\scholargraph\.worktrees\public-gemini\scholargraph"

# Đặt PYTHONPATH trỏ vào src của SOL (read-only) và src của GEMINI
$env:PYTHONPATH = "D:\Web_mining_20261\scholargraph\.worktrees\public-sol\scholargraph\src;D:\Web_mining_20261\scholargraph\.worktrees\public-gemini\scholargraph\src"

# Chạy script kiểm chứng typed models và negative tests
& "D:\Web_mining_20261\scholargraph\.venv\Scripts\python.exe" tests\fixtures\public_search\gemini\validate_fixtures.py

# Kiểm tra git status và git diff các tệp owned
git status --short
git diff --check

# Commit owned files
git add docs/public_search/UX_SPEC.md tests/fixtures/public_search/gemini/ management/public_search/logs/GEMINI/ management/public_search/packets/GEMINI/
git commit -m "feat(public_search): reconcile EXT-01C UX fixtures and spec 1:1 with SOL typed contract (R1)"
```

---

## 5. Trạng thái Gate & Bước kế tiếp

- Hoàn thành toàn bộ nội dung reconciliation R1 của `EXT-01C`.
- Dừng mọi thao tác chỉnh sửa để Coordinator chạy kiểm chứng và MUSE thực hiện review snapshot mới.
- Không tự tiện mở các task tiếp theo (`EXT-03`, `EXT-05A`).
