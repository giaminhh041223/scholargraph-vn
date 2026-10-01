# Tài liệu kỹ thuật: Bounded JOSS Site Crawler (EXT-10, Bản R2)

- **Mã nhiệm vụ:** EXT-10 (Giai đoạn B).
- **Tác giả:** Worker GEMINI (Model yêu cầu: Gemini 3.8 Flash High; telemetry thực tế: unknown/runner-provided).
- **Mục tiêu:** Xây dựng trình thu thập HTML chuyên biệt, giới hạn biên (bounded), bảo mật và tuân thủ chính sách cho tạp chí mã nguồn mở Journal of Open Source Software (JOSS) tại `https://joss.theoj.org`.

---

## 1. Tổng quan và phạm vi nhiệm vụ

Trình thu thập JOSS Site Crawler được thiết kế chuyên biệt để thu thập siêu dữ liệu bài báo khoa học đã xuất bản từ JOSS:
- **Phạm vi URL giới hạn:**
  - Trang chính sách robots: `https://joss.theoj.org/robots.txt`
  - Trang điều khoản/chính sách: `https://joss.theoj.org/about`
  - Trang danh sách bài báo đã xuất bản (Seed URL): `https://joss.theoj.org/papers/published.html`
  - Các trang bài báo xuất bản đơn lẻ: `https://joss.theoj.org/papers/10.21105/joss.<digits>`
- **Không tìm kiếm toàn web (No Full-Web Crawling):** Crawler chỉ hoạt động trên domain đã được cấp phép và cấu hình trong `configs/public_site_joss.json`. Mọi liên kết ngoại vi hoặc đường dẫn nằm ngoài danh sách cho phép đều bị từ chối.
- **Không tự động tải PDF:** Siêu dữ liệu liên kết PDF cùng máy chủ (`citation_pdf_url`) được ghi nhận nhưng crawler tuyệt đối không thực hiện tải tệp PDF nhị phân.
- **Tách biệt schema:** Dữ liệu đầu ra sử dụng schema độc lập `JossPaperRecord`, không làm thay đổi hoặc tác động đến contract v1 (`PaperRecord`) của hệ thống tìm kiếm công cộng đã đóng băng trước đó.

---

## 2. Kiến trúc và các cơ chế bảo vệ cốt lõi (Bản sửa R2)

### 2.1. Cấu hình nghiêm ngặt và giới hạn biên (`JossConfig`)
Cấu hình crawler được nạp từ tệp JSON do Coordinator quản lý (`configs/public_site_joss.json`):
- `schema_version`: Phải là số nguyên `1`.
- `site_id`: Cố định `"joss"`.
- `origin`: Cố định `"https://joss.theoj.org"`.
- `start_url`: Cố định `"https://joss.theoj.org/papers/published.html"`.
- `robots_url`: Cố định `"https://joss.theoj.org/robots.txt"`.
- `conditions_url`: Cố định `"https://joss.theoj.org/about"`.
- `user_agent`: Chuỗi không rỗng, không chứa ký tự điều khiển hay xuống dòng.
- `min_interval_seconds`: Trong khoảng `[3.0, 60.0]` giây giữa hai yêu cầu liên tiếp.
- `max_pages`: Trong khoảng `[1, 100]` (mặc định 5 trang).
- `max_papers`: Trong khoảng `[1, 50]` (mặc định 3 bài).
- `max_depth`: Cố định `1` (Listing -> Paper).
- `max_body_bytes`: Trong khoảng `[1024, 10485760]` (1 KB đến 10 MB, mặc định 1 MB).
- `timeout_seconds`: Trong khoảng `[0.5, 120.0]` giây.
- `parser_version`: Cố định `"joss-citation-1.0.0"`.
- `data_root`: Bắt buộc là `"data/public_search/joss"` hoặc thư mục con cháu bên trong không gian tên công cộng này. Cấm tuyệt đối đường dẫn tuyệt đối (ổ đĩa `D:/...`), dấu gạch chéo ngược (`\\`), hoặc path traversal (`..`, `%2e%2e`).

### 2.2. Ràng buộc không gian lưu trữ và chống Symlink/Junction Escape
Hàm `guard_confinement_and_symlinks` thực hiện giải quyết (resolve) đường dẫn và kiểm tra nghiêm ngặt:
- `data_root` và `run_dir` bắt buộc phải nằm bên trong `project_root/data/public_search/joss`.
- `run_dir` không được trùng với thư mục gốc dự án hoặc thư mục gốc `data/public_search/joss`.
- Kiểm tra `is_symlink()` đối với `run_dir`, `raw/`, `checkpoint.json`, và `records.json`. Nếu phát hiện liên kết mềm (symlink/junction) sẽ lập tức báo lỗi `SecurityError`.

### 2.3. Ranh giới phân tích cú pháp Robots.txt nghiêm ngặt
Hàm `validate_robots_directives` loại bỏ lỗ hổng diễn giải văn bản rác thành quyền truy cập:
- Chấp nhận tệp robots rỗng hoặc chỉ chứa chú thích (`#...`).
- Kiểm tra từng dòng chỉ thị: Bắt buộc phải có dấu `:` và tên chỉ thị phải thuộc tập hợp chuẩn: `user-agent`, `allow`, `disallow`, `crawl-delay`, `request-rate`, `sitemap`, `host`.
- Mọi nội dung HTML (ví dụ: `<html>...</html>`) hoặc từ khóa lạ đều bị từ chối với lỗi `RobotsDeniedError`.
- Tuân thủ chỉ thị `Crawl-delay`: Nếu giá trị `Crawl-delay` lớn hơn `min_interval_seconds`, bộ điều tốc `RateLimiter` sẽ tự động nâng khoảng thời gian giãn cách lên giá trị lớn hơn này.
- Tải lại và kiểm tra `robots.txt` trên mọi lượt chạy (mới hoặc tiếp tục), đồng thời kiểm tra lại quyền truy cập của toàn bộ bài báo trong kho lưu trữ khi resume complete.

### 2.4. Điều tốc bằng đồng hồ đơn điệu (Monotonic Clock) và giới hạn luồng mạng
- `RateLimiter` sử dụng `time.monotonic` để loại bỏ rủi ro sai lệch do nhảy giờ hệ thống.
- Hàm `stream_bounded_fetch` thực thi:
  - Cưỡng chế `follow_redirects=False` trên mọi yêu cầu HTTP; từ chối các mã 301, 302, 303, 307 với `SecurityError`.
  - Kiểm tra MIME type chính xác (tách bỏ tham số charset): Bắt buộc đúng `text/plain` cho robots và `text/html` cho trang web. Từ chối các chuỗi bắt đầu không hợp lệ như `text/htmlbad`.
  - Kiểm tra tiêu đề `Content-Length` nếu có, từ chối trước khi tải nếu vượt quá `max_body_bytes`.
  - Thiết lập thời hạn tổng thể (`overall response deadline`): Ngắt kết nối và báo lỗi `NetworkFetchError` nếu việc đọc luồng kéo dài vượt quá `timeout_seconds`.

### 2.5. Phân tích cú pháp an toàn với stdlib `HTMLParser`
- **Bộ phân tích danh sách (`JossListingParser`):**
  - Trích xuất các liên kết thẻ `<a href="...">` có định dạng canonical `/papers/10.21105/joss.<digits>`.
  - Loại bỏ fragment `#...`.
  - Kiểm đếm chính xác `links_found` và `duplicate_links`.
  - Phát hiện trôi bộ chọn (Selector Drift): Báo lỗi `ParseError` nếu không trích xuất được bài báo nào.
- **Bộ phân tích bài báo (`JossPaperParser`):**
  - Quét và phát hiện các từ khóa nhạy cảm / rò rỉ phân chia dữ liệu nghiên cứu: `labels`, `qrels`, `dev_labels`, `test_labels`, `heldout`, `split`, `score`.
  - Trích xuất siêu dữ liệu: `citation_title`, `citation_doi`, `citation_publication_date`, `citation_journal_title`, `citation_author`.
  - Đối chiếu DOI trang đích với `citation_doi` khớp 1:1.
  - Kiểm tra định dạng ngày công bố hợp lệ theo lịch (`YYYY/MM/DD`).
  - Kiểm tra bảo mật toàn diện cho cả `citation_pdf_url` và `citation_abstract_html_url`: Bắt buộc giao thức HTTPS, cùng host `joss.theoj.org`, không credentials, không cổng lạ, không traversal. Mọi URL ngoại vi đều bị từ chối với `ParseError`.

### 2.6. Kiểm chứng toàn vẹn Checkpoint và phân tích lại HTML thô khi Resume
Nhằm ngăn chặn việc đầu độc checkpoint (poisoned checkpoint):
- Checkpoint được kiểm tra với Pydantic model nghiêm ngặt (`CheckpointModel`), cấm trường thừa (`extra="forbid"`), cấm khóa trùng lặp, xác minh tính bất biến của bộ đếm (`pages_fetched == len(visited)` và `unique_papers == len(records)`).
- Khi resume, toàn bộ tệp HTML thô trên đĩa được đối chiếu mã băm SHA-256.
- **Phân tích lại HTML thô (Raw Re-parsing):** Từng bản ghi bài báo trong checkpoint được phân tích lại trực tiếp từ tệp raw HTML trên đĩa để đối chiếu `id`, `doi`, `title`, `authors`, `publication_date`, `venue`, `pdf_url`. Nếu phát hiện tiêu đề bị sửa đổi hoặc gắn nhãn giả mạo, crawler lập tức từ chối với `CheckpointIntegrityError`.
- Khi resume trạng thái `complete`, tệp `records.json` bắt buộc phải tồn tại và khớp 1:1 với checkpoint.
- Khi resume trạng thái dở dang/thất bại: Bộ phân tích sẽ phân tích lại trang danh sách thô đã lưu để đảm bảo không bỏ qua lỗi trôi bộ chọn (Selector Drift), và không tự ý chuyển thành công rỗng.
- Tất cả các thao tác ghi checkpoint và `records.json` đều được thực hiện nguyên tử (`.tmp` rồi `os.replace`).

---

## 3. Cấu trúc bản ghi đầu ra minh họa (`JossPaperRecord`)

> **Lưu ý:** Ví dụ dưới đây mang tính chất minh họa cú pháp (synthetic fixture), không tuyên bố là dữ liệu live telemetry thực tế. Trường `meta_fields` phản ánh danh sách tên các thẻ `<meta>` được trích xuất từ mã nguồn HTML của trang bài báo.

```json
{
  "id": "joss:10.21105/joss.09260",
  "doi": "10.21105/joss.09260",
  "title": "eratosthenes: Synchronizing archaeological chronologies with a focus on artifact types",
  "authors": [
    "Stephen A. Collins-Elliott"
  ],
  "publication_date": "2026/10/01",
  "venue": "Journal of Open Source Software",
  "landing_url": "https://joss.theoj.org/papers/10.21105/joss.09260",
  "pdf_url": "https://joss.theoj.org/papers/10.21105/joss.09260.pdf",
  "raw_sha256": "28916e6c412defacc851a24f8fa06fbd299ec0643e139132967d71ca6174b0c1",
  "retrieved_at": "2026-10-01T23:30:30.299120+07:00",
  "parser_version": "joss-citation-1.0.0",
  "provenance": {
    "site_id": "joss",
    "landing_url": "https://joss.theoj.org/papers/10.21105/joss.09260",
    "raw_sha256": "28916e6c412defacc851a24f8fa06fbd299ec0643e139132967d71ca6174b0c1",
    "parser_version": "joss-citation-1.0.0",
    "retrieved_at": "2026-10-01T23:30:30.299120+07:00",
    "meta_fields": [
      "citation_abstract_html_url",
      "citation_author",
      "citation_doi",
      "citation_firstpage",
      "citation_issn",
      "citation_issue",
      "citation_journal_title",
      "citation_pdf_url",
      "citation_publication_date",
      "citation_title",
      "citation_volume",
      "csrf-param",
      "csrf-token",
      "msapplication-tilecolor",
      "msapplication-tileimage",
      "theme-color",
      "twitter:card",
      "twitter:data1",
      "twitter:description",
      "twitter:image",
      "twitter:label1",
      "twitter:site",
      "twitter:title",
      "twitter:url",
      "viewport"
    ]
  }
}
```

---

## 4. Giao diện dòng lệnh CLI (`scripts/crawl_public.py`)

### 4.1. Khởi động độc lập (Standalone Bootstrap)
Tệp `scripts/crawl_public.py` tự động chèn đường dẫn `src/` vào `sys.path` ngay đầu tệp, đảm bảo có thể chạy độc lập trong môi trường tiêu chuẩn mà không cần thiết lập trước biến môi trường `PYTHONPATH`.

### 4.2. Cú pháp sử dụng
```bash
python scripts/crawl_public.py \
  --project-root . \
  --config configs/public_site_joss.json \
  --run-dir data/public_search/joss/runs/pilot-107 \
  [--resume] \
  [--query "archaeological"]
```

### 4.3. Quy tắc xử lý lỗi và thoát mã
- **Trợ giúp (`--help` / `-h`):** Thoát với mã `0` và hiển thị hướng dẫn.
- **Lỗi tham số hoặc lỗi chạy (Mã thoát 1):** In JSON cấu trúc mô tả lỗi ra `stderr`.
- **Độ chính xác của bộ đếm lỗi:** Nếu lỗi xảy ra trước khi crawler được khởi tạo (như thiếu tệp cấu hình, tham số truy vấn rỗng hoặc vượt quá 500 ký tự), trường `"counters"` sẽ là `null` (không tạo dựng số đếm giả tạo `failed_attempted_calls: 1`). Khi crawler đã chạy, giá trị bộ đếm thực tế sẽ được bảo tồn.
- **Lọc cục bộ với `--query`:** Kiểm tra chuỗi truy vấn hợp lệ trước khi gọi mạng. Lọc trên các trường bắt buộc `title` và `authors` của bản ghi, không làm thay đổi các tệp lưu trữ gốc.
