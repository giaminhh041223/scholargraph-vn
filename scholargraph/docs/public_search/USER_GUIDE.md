# Hướng dẫn tìm kiếm bài báo công khai

Module tìm metadata qua API OpenAlex và arXiv, hợp nhất thứ hạng, lưu snapshot, lưu bài vào thư viện cục bộ và xuất JSON/BibTeX. Truy cập giao diện tại `/public/ui`; `/public` là readiness JSON. Đây là phần mở rộng trên nhánh `codex/public-paper-search`.

## 1. Chuẩn bị

Môi trường đã kiểm: Windows, Python 3.12.14. Dự án khai báo Python >=3.10 trong [pyproject.toml](../../pyproject.toml); chưa xác nhận chạy trên mọi phiên bản/hệ điều hành. Cài mới phụ thuộc trong đợt này: **NOT_RUN**.

Mở PowerShell trong thư mục dự án:

```powershell
Set-Location D:/Web_mining_20261/scholargraph
$env:PYTHONPATH = 'src'
```

Nếu máy chưa có `.venv`, có thể tạo và cài bản khóa dưới đây. Đây là hướng dẫn cài đặt, chưa phải kết quả kiểm thử cài mới:

```powershell
py -3.12 -m venv .venv
& .venv/Scripts/python.exe -m pip install -r requirements.lock
```

Các lệnh bên dưới gọi trực tiếp Python trong `.venv`, không cần kích hoạt môi trường. Không ghi API key vào tài liệu/chat.

## 2. Cấu hình và khởi tạo lưu trữ

[configs/public_search.json](../../configs/public_search.json) đang dùng `data/public_search/sol`, TTL 86400 giây, deadline 30 giây. Hai nguồn trong cấu hình đã audit dùng `auth_mode=anonymous`, `key_env=null`; không cần thiết lập biến API key cho cấu hình này. Bằng chứng chính sách tại [SOURCE_AUDIT](SOURCE_AUDIT.md) là audit đã lưu, không chứng minh chính sách hoặc quota luôn giữ nguyên.

Khởi tạo trước khi dùng API/CLI:

```powershell
& .venv/Scripts/python.exe scripts/search_public.py --project-root . --config configs/public_search.json init-storage
```

Thành công trả `{"status":"INITIALIZED","contract_version":"1.0.0"}`, mã 0. Store gồm `library.sqlite3`, marker `store.json` và thư mục `raw/`: raw bytes nằm trong tệp, SQLite giữ dữ liệu/các tham chiếu và hash. Thiếu hoặc hỏng store phải FAIL; không xóa marker/DB để che lỗi hay tái tạo bằng chứng.

API xây public service khi nhận request cần dữ liệu, không phải ngay khi Uvicorn khởi động. Vì vậy `/public/ui` có thể mở được trước khi store sẵn sàng, còn readiness/search/library sẽ trả lỗi rõ. Public service độc lập với service benchmark; trang core `/` cần tài nguyên core riêng.

## 3. Tìm kiếm, xem nguồn và lưu bài

Chạy một server, một worker:

```powershell
& .venv/Scripts/python.exe -m uvicorn scholargraph.api.app:app --host 127.0.0.1 --port 8000
```

Mở [giao diện cục bộ](http://127.0.0.1:8000/public/ui). Chọn OpenAlex và arXiv, đặt **Hiển thị (top_k)=3**, **Ngân sách/nguồn (cap)=3** để bắt đầu.

1. Nhập query, bấm **Tìm kiếm**: dùng cache còn hạn nếu có, nếu không sẽ gọi nguồn.
2. Bấm nút **Làm mới từ nguồn** để bỏ qua cache và gọi nguồn. Giãn các lượt làm mới ít nhất 3 giây; không chạy nhiều CLI/server process cùng gọi nguồn.
3. Đọc trạng thái từng nguồn, snapshot ID/thời điểm, bộ đếm và nhãn cache. Bấm **Xem chi tiết & Provenance** để đọc nguồn của metadata.
4. Bấm **Lưu vào thư viện**. Lưu lại cùng canonical ID không tạo bản ghi trùng; entry có thể giữ snapshot đã lưu trước đó.
5. Mở **Thư viện cá nhân**, phân trang và bấm **Xuất JSON** / **Xuất BibTeX**. Không có bộ lọc thư viện riêng trong MVP.

Thư viện lưu metadata và provenance, không lưu PDF. Nút mở trang bài báo chuyển tới nguồn. `oa_unknown` trên UI nghĩa chưa xác nhận quyền truy cập mở; trường contract là `open_access_status` (`open`/`closed`/`unknown` hoặc null). Không suy quyền tải PDF từ một URL.

## 4. Lệnh CLI

Tham số toàn cục `--project-root`, `--config` đặt trước subcommand. Các ví dụ này dùng store mặc định, khác store pilot trên preview 8011:

```powershell
& .venv/Scripts/python.exe scripts/search_public.py --help
& .venv/Scripts/python.exe scripts/search_public.py search --query 'knowledge graph' --sources openalex,arxiv --top-k 3 --cap-per-source 3 --refresh
& .venv/Scripts/python.exe scripts/search_public.py library --offset 0 --limit 50
```

`search` trả SearchEnvelope; đọc `snapshot.snapshot_id` trong kết quả rồi thay `SNAPSHOT_ID_THAT` ở lệnh sau. ID phải thuộc store đang dùng, không lấy ID từ store pilot để tra trong store mặc định:

```powershell
& .venv/Scripts/python.exe scripts/search_public.py results SNAPSHOT_ID_THAT
```

`results` cũng trả SearchEnvelope. `library` trả object gồm `contract_version`, `entries`, `errors`; mỗi entry theo [LibraryEntry](../../src/scholargraph/public_search/contracts.py) có `hit`, không phải object `record` tự rút gọn. Không có subcommand CLI `save`; dùng UI hoặc POST `/public/library` với `snapshot_id`, `canonical_id` từ snapshot thật.

Xuất ra stdout:

```powershell
& .venv/Scripts/python.exe scripts/search_public.py export --format json
& .venv/Scripts/python.exe scripts/search_public.py export --format bibtex
```

JSON export là **list LibraryEntry**, chứa `hit.display`, source records và provenance. BibTeX hiện dùng **`@misc`**, bỏ trường thiếu và escape ký tự đặc biệt; không suy loại ấn phẩm hay tạo trường giả.

Để lưu bytes UTF-8 đúng trên cả PowerShell có cơ chế chuyển mã khi redirect, có thể dùng đoạn dưới. Nó không ghi đè tệp cũ và dừng nếu CLI lỗi. Chạy sau khi store đã khởi tạo:

```powershell
@'
from pathlib import Path
import subprocess, sys
out = Path('data/public_search/user_exports')
out.mkdir(parents=True, exist_ok=True)
targets = [('json', out/'library.json'), ('bibtex', out/'library.bib')]
if any(p.exists() for _, p in targets):
    raise FileExistsError('Export targets already exist; choose new output names')
for fmt, path in targets:
    result = subprocess.run([sys.executable, 'scripts/search_public.py',
                             'export', '--format', fmt], capture_output=True)
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stderr)
        raise SystemExit(1)
    with path.open('xb') as stream:
        stream.write(result.stdout)
'@ | & .venv/Scripts/python.exe -
```

Library/list/export cục bộ không cần gọi mạng; liên kết mở trang nguồn vẫn cần mạng. Ví dụ xuất tệp này đã được coordinator kiểm trên project/store tạm riêng; xem [bằng chứng lệnh105](../../artifacts/reports/public_search/sol/doc-commands-105.json).

## 5. Trạng thái và xử lý lỗi

| Trạng thái | Ý nghĩa / hành động |
|---|---|
| `overall=success` hoặc `empty` | Các nguồn hoàn tất; empty là không có hits, không phải số đo lỗi bị thay bằng 0. |
| `cached=true`, `stale=false` | Cache/snapshot lịch sử còn hạn; UI gọi `cached_fresh`. Thời gian từng nguồn trong snapshot là thời gian lúc thu thập, không phải thời gian request cache hiện tại. |
| `cached=false` | Lượt search gọi nguồn, UI gọi `live`; đọc thêm overall/errors. |
| `overall=partial_failure` | Có nguồn lỗi; vẫn giữ hits hợp lệ của nguồn tốt. HTTP có thể non-2xx, CLI mã1; UI đọc envelope, giữ cảnh báo, paging/save trên snapshot đó. |
| `overall=failed` | Không có kết quả search sử dụng được hoặc lỗi request/config/store; đọc errors, không coi là thành công. Snapshot có thể null. |
| `stale=true` khi đọc `results` | Snapshot hết hạn vẫn được đọc có nhãn rõ. Search không tự dùng cache hết hạn khi nguồn lỗi. |

CLI lỗi tham số, thiếu tài nguyên hoặc partial trả **1**; `--help` trả **0**. `search` trả 0 khi không có errors; `results` trả 0 cho success/empty. Đọc cả stdout và stderr vì partial envelope có thể nằm ở stdout dù CLI1. Không bỏ qua exit code.

Ví dụ lỗi an toàn không gọi mạng:

```powershell
& .venv/Scripts/python.exe scripts/search_public.py --config configs/khong_ton_tai.json library
$LASTEXITCODE # kỳ vọng 1
```

RateState chỉ phối hợp trong một tiến trình. Nhiều CLI process hoặc nhiều Uvicorn worker không có khóa rate chung. Khi timeout/quota, giữ lỗi và hits nguồn còn lại nếu có, không giả định OpenAlex luôn thành công.

## 6. Giới hạn và bằng chứng

- Truy vấn được gửi nguyên văn sau chuẩn hóa request; chưa dịch Việt–Anh. Chưa đo relevance hoặc độ bao phủ tiếng Việt bằng nhãn.
- Title-only hợp lệ nếu các trường bắt buộc khác đầy đủ; thiếu title/định dạng sai phải FAIL. Metadata thiếu được ghi null/nhãn thiếu theo contract.
- RRF k=60 hợp nhất **thứ hạng nguồn**, không là điểm chất lượng khoa học. Số trích dẫn không đo độ đúng đắn.
- Fusion có hỗ trợ alias arXiv; adapter OpenAlex hiện chưa populate `arxiv_id`. Vì vậy DOI-less cross-source có thể chưa được gộp. Enrichment này được hoãn; không tự triển khai EXT-09/10.
- Recovery102: 5 refresh +5 cache hai nguồn thành công; lịch sử 26 unique runs gồm 20 success +6 partial_failure (arXiv4 timeout+2 quota). Readiness101 đứng riêng. Đây là pilot ngắn, không bảo đảm mọi query/availability; query Ontology từng trả504 ngoài cohort này.
- n=5 mỗi chế độ, P95 nearest-rank CLI wall time: refresh2.2064683s đạt đề xuất15s; cache0.5674156s **chưa đạt đề xuất500ms**. Chưa tách startup nên chưa quy nguyên nhân; đây không phải độ trễ browser.
- Cài mới và tệp được lưu qua download browser chưa xác nhận trong đợt này. API export bytes/Node download harness đã kiểm; human demo vẫn PENDING.

Xem [kịch bản demo](DEMO.md), [gói bàn giao](RELEASE_PACKET.md) và [contract](CONTRACT.md).
