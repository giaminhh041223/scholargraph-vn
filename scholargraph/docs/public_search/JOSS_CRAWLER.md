# Tài liệu kỹ thuật: Bounded JOSS Site Crawler (EXT-10)

- **Mã nhiệm vụ:** EXT-10 (Giai đoạn B).
- **Tác giả:** Worker GEMINI (Gemini 3.8 Flash High).
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

## 2. Kiến trúc và các thành phần cốt lõi

### 2.1. Cấu hình nghiêm ngặt (`JossConfig`)
Cấu hình crawler được nạp từ tệp JSON do Coordinator quản lý (`configs/public_site_joss.json`):
- `schema_version`: Phải là số nguyên `1`.
- `site_id`: Cố định `"joss"`.
- `origin`: Cố định `"https://joss.theoj.org"`.
- `start_url`: Cố định `"https://joss.theoj.org/papers/published.html"`.
- `robots_url`: Cố định `"https://joss.theoj.org/robots.txt"`.
- `conditions_url`: Cố định `"https://joss.theoj.org/about"`.
- `min_interval_seconds`: Tối thiểu `3.0` giây giữa hai yêu cầu liên tiếp.
- `max_pages`: Giới hạn tổng số trang tải về (mặc định 5 trang).
- `max_papers`: Giới hạn số bài báo xuất bản được thu thập (mặc định 3 bài).
- `max_depth`: Giới hạn độ sâu duyệt là `1` (Listing -> Paper).
- `max_body_bytes`: Giới hạn dung lượng tải về tối đa `1048576` bytes (1 MB).
- `timeout_seconds`: Thời gian chờ mạng tối đa `30.0` giây.
- `parser_version`: Cố định `"joss-citation-1.0.0"`.
- `data_root`: Thư mục gốc lưu trữ dữ liệu crawler (`data/public_search/joss`).

### 2.2. Kiểm chứng Policy Manifest (`validate_policy_manifest`)
Trước khi thực hiện bất kỳ kết nối mạng nào, crawler bắt buộc phải đối chiếu tệp manifest chính sách (`data/public_search/phase_b/policy-107/manifest.json`):
- Kiểm tra toàn bộ đường dẫn tài nguyên phải nằm bên trong `data/public_search/`.
- Xác minh trạng thái `status == "PASS"`.
- Tính toán mã băm SHA-256 thực tế của từng tệp trên đĩa và đối chiếu với giá trị trong manifest. Nếu tệp bị thiếu, bị sửa đổi hoặc sai lệch mã băm, quá trình khởi tạo sẽ thất bại ngay lập tức (`PolicyViolationError`).

### 2.3. Phòng chống tấn công SSRF và xác thực DNS (`validate_url_and_dns`)
Trước mỗi yêu cầu HTTP, URL và hostname được kiểm tra qua các tầng bảo vệ:
- **Giao thức & Cổng:** Bắt buộc giao thức HTTPS và cổng 443 chuẩn. Không chấp nhận cổng tuỳ ý.
- **Chống thông tin nhạy cảm:** Từ chối URL chứa username/password (`user:pass@`).
- **Chống Path Traversal:** Từ chối URL chứa ký tự điều khiển, khoảng trắng, dấu `\\`, `..` hoặc mã hóa URL traversal (`%2e%2e`, `%2f`).
- **Từ chối Query & Fragment:** Cấm tham số truy vấn (`?`) và fragment (`#`) trên URL đích.
- **Kiểm tra DNS toàn cầu:** Hostname được phân giải thông qua DNS resolver (hỗ trợ dependency injection cho kiểm thử). Mọi địa chỉ IP phân giải thuộc dải riêng tư (RFC 1918), loopback (`127.0.0.1`), link-local, multicast, reserved hoặc unspecified đều bị từ chối với `SecurityError`.

### 2.4. Tải luồng có giới hạn dung lượng (`stream_bounded_fetch`)
- Không tự động theo dõi chuyển hướng (`follow_redirects=False`). Các mã trạng thái chuyển hướng (301, 302, 303, 307, 308) bị coi là lỗi bảo mật (`SecurityError`).
- Kiểm tra tiêu đề `Content-Type`: Bắt buộc `text/plain` cho `robots.txt` và `text/html` cho trang danh sách/bài báo.
- Đọc nội dung theo luồng (chunk streaming): Dừng đọc và ngắt kết nối ngay khi tổng số byte vượt quá `max_body_bytes`, tránh tấn công làm cạn kiệt bộ nhớ.

### 2.5. Phân tích cú pháp an toàn với stdlib `HTMLParser`
- **Bộ phân tích danh sách (`JossListingParser`):**
  - Trích xuất các liên kết thẻ `<a href="...">` có định dạng canonical `/papers/10.21105/joss.<digits>`.
  - Loại bỏ fragment `#...`.
  - Kiểm đếm chính xác số liên kết tìm thấy (`links_found`) và số liên kết trùng lặp (`duplicate_links`).
  - Phát hiện trôi bộ chọn (Selector Drift): Nếu không trích xuất được bất kỳ liên kết bài báo nào từ trang danh sách, báo lỗi `ParseError`.
- **Bộ phân tích bài báo (`JossPaperParser`):**
  - Kiểm tra các từ khóa nhạy cảm/rò rỉ phân chia dữ liệu nghiên cứu: `labels`, `qrels`, `dev_labels`, `test_labels`, `heldout`, `split`, `score`. Nếu xuất hiện trong tên thẻ, thuộc tính hoặc giá trị meta, báo lỗi `ParseError`.
  - Trích xuất siêu dữ liệu theo chuẩn Google Scholar / Highwire Press:
    - `citation_title` (Bắt buộc, singleton không mâu thuẫn).
    - `citation_doi` (Bắt buộc, singleton, phải khớp 1:1 với DOI trên URL trang đích).
    - `citation_publication_date` (Bắt buộc, singleton, định dạng lịch hợp lệ YYYY/MM/DD).
    - `citation_journal_title` (Bắt buộc, singleton).
    - `citation_author` (Bắt buộc, chấp nhận danh sách nhiều tác giả hoặc tên lặp lại).
    - `citation_pdf_url` (Tuỳ chọn, bắt buộc phải cùng máy chủ `https://joss.theoj.org`).
  - Tuyệt đối không fallback ngầm về text-only hay title-only nếu thiếu các trường siêu dữ liệu bắt buộc.

### 2.6. Tuân thủ Robots.txt và giới hạn tốc độ
- Trên mỗi lượt chạy mới hoặc tiếp tục (resume), crawler luôn tải và phân tích lại tệp `robots.txt` trực tiếp (`urllib.robotparser.RobotFileParser`).
- Nếu `robots.txt` trả về mã lỗi (403, 404, 429, 500), chứa ký tự điều khiển hoặc bị lỗi mạng, crawler lập tức dừng lại, không tự ý suy đoán quyền truy cập (`RobotsDeniedError`).
- Kiểm tra phương thức `can_fetch()` cho cả seed URL và từng URL bài báo phát hiện được.
- Đảm bảo thời gian giãn cách giữa các yêu cầu mạng luôn >= 3.0 giây (`RateLimiter`).

### 2.7. Cơ chế lưu trữ nguyên tử và tiếp tục (Resume) an toàn
- **Ràng buộc vị trí lưu trữ:** Thư mục chạy (`run_dir`) bắt buộc phải nằm bên dưới `data_root` được cấu hình. Tuyệt đối không cho phép ghi đè vào các thư mục benchmark hoặc dữ liệu cốt lõi của dự án.
- **Ghi nguyên tử:** Checkpoint được ghi ra tệp tạm `checkpoint.json.tmp`, đồng bộ xuống đĩa (`os.fsync`) rồi đổi tên nguyên tử (`os.replace`) thành `checkpoint.json`.
- **Lưu trữ payload thô bất biến:** Từng trang HTML tải về được lưu tại `raw/{sha256}.html`, đi kèm nhật ký URL, thời gian và phiên bản bộ phân tích.
- **Tiếp tục chạy an toàn (`--resume`):**
  - Kiểm tra khớp mã băm cấu hình (`config_hash`).
  - Kiểm tra sự tồn tại và tính toàn vẹn SHA-256 của từng tệp HTML thô đã ghi nhận trong checkpoint. Nếu bất kỳ tệp nào bị thiếu hoặc sai lệch nội dung, crawler từ chối chạy tiếp (`CheckpointIntegrityError`).
  - Nếu checkpoint đã đạt trạng thái `complete`: Làm mới kiểm tra `robots.txt`, xác minh toàn vẹn dữ liệu và trả về kết quả đã thu thập mà không thực hiện tải lại các bài báo.

---

## 3. Cấu trúc bản ghi đầu ra (`JossPaperRecord`)

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
      "citation_author",
      "citation_doi",
      "citation_firstpage",
      "citation_issn",
      "citation_issue",
      "citation_journal_title",
      "citation_pdf_url",
      "citation_publication_date",
      "citation_title",
      "citation_volume"
    ]
  }
}
```

---

## 4. Hướng dẫn sử dụng CLI (`scripts/crawl_public.py`)

### 4.1. Cú pháp dòng lệnh
```bash
python scripts/crawl_public.py \
  --project-root . \
  --config configs/public_site_joss.json \
  --run-dir data/public_search/joss/runs/pilot-01 \
  [--resume] \
  [--query "archaeological"]
```

### 4.2. Các tham số
- `--project-root`: Thư mục gốc của dự án (mặc định: `.`).
- `--config`: Đường dẫn tệp cấu hình JOSS (mặc định: `configs/public_site_joss.json`).
- `--run-dir` (Bắt buộc): Thư mục lưu trữ kết quả và checkpoint của lượt chạy (bắt buộc nằm trong `data_root`).
- `--resume`: Cờ báo tiếp tục lượt chạy trước đó từ `run_dir`.
- `--query`: Truy vấn chuỗi con cục bộ để lọc các bài báo trong tập kết quả trả về theo tiêu đề hoặc tác giả (vẫn bảo tồn toàn bộ bài báo thu thập được trong `records.json` và checkpoint).

### 4.3. Mã thoát và định dạng kết quả
- **Thành công (Mã thoát 0):** In cấu trúc JSON kết quả ra `stdout`.
- **Thất bại (Mã thoát 1):** In cấu trúc JSON mô tả lỗi (`kind`, `message`, `counters`) ra `stderr`.
- **Trợ giúp (`--help` / `-h`):** Thoát với mã 0 và hiển thị hướng dẫn.

---

## 5. Danh mục các ca kiểm thử phá hủy (Negative & Adversarial Testing)

Bộ kiểm thử tại `tests/unit/test_public_site_crawler.py` bao phủ toàn diện:
1. **Cấu hình:** Thiếu tệp cấu hình, JSON trùng lặp khóa, thiếu trường bắt buộc, giá trị biên sai (`schema_version != 1`, `min_interval < 3.0`, số âm, origin sai, data_root traversal).
2. **Policy Manifest:** Thiếu manifest, trạng thái khác `PASS`, thiếu tệp bắt buộc, sai lệch mã băm SHA-256 của tệp chính sách, thoát khỏi `data/public_search`.
3. **Bảo mật URL & SSRF:** Giao thức không an toàn, chứa credentials, cổng lạ, host lạ, traversal, query/fragment cấm, DNS trả về IP nội bộ / private / loopback.
4. **Mạng & Luồng dữ liệu:** Chuyển hướng 301/302, mã trạng thái HTTP khác 200, Content-Type sai, payload vượt quá giới hạn 1MB.
5. **Robots.txt:** Cấm User-Agent, chứa ký tự điều khiển, lỗi HTTP 403/404/500.
6. **Bộ phân tích:** Trôi bộ chọn (0 liên kết bài báo), thiếu trường meta bắt buộc, sai định dạng ngày, lệch DOI trang đích so với thẻ meta, xung đột thẻ singleton, PDF URL ngoại vi, xuất hiện từ khóa nghiên cứu rò rỉ (`score`, `qrels`, `labels`,...).
7. **Lưu trữ & Checkpoint:** Thư mục chạy đã tồn tại khi chạy mới, thư mục thoát khỏi `data_root`, tệp HTML thô bị sửa đổi mã băm khi resume, checkpoint bị hỏng.
8. **Subprocess CLI:** Kiểm tra thực tế gọi CLI qua subprocess: thiếu đối số bắt buộc (thoát mã 1), sai cấu hình (thoát mã 1), gọi `--help` (thoát mã 0).
