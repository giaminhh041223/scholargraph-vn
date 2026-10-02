# Demo giai đoạn B

Crossref đã nghiệm thu; crawler JOSS đang sửa R3. Tài liệu này chưa xác nhận pilot JOSS hoặc tích hợp master.

## Tra metadata DOI

Từ PowerShell tại `D:/Web_mining_20261/scholargraph`:

```powershell
.venv/Scripts/python.exe scripts/enrich_public.py --project-root . --doi 10.21105/joss.03021 --output-dir data/public_search/phase_b/crossref-demo-moi
```

Chọn output mới cho mỗi lần gọi. `result.json` giữ metadata, provenance và lỗi; `raw.json` giữ response đã nhận, kể cả body lỗi HTTP không phải JSON. `status=success` tương ứng exit 0; lỗi tương ứng exit 1. Lần gọi thật có thể lỗi mạng/quota hoặc dữ liệu nguồn thay đổi.

[Pilot đã lưu](../../artifacts/reports/public_search/phase_b/crossref-live-history-107.json): 5 lượt gọi, 3 thành công và 2 HTTP 404. Bản ghi OpenAlex gốc không đổi; xung đột abstract/citation count lưu riêng. Không đọc sidecar như một bản cập nhật library.

## Quét JOSS

Lệnh dưới đây là cú pháp dự kiến của crawler, **chưa nghiệm thu live**:

```powershell
.venv/Scripts/python.exe scripts/crawl_public.py --project-root . --config configs/public_site_joss.json --run-dir data/public_search/joss/demo-moi
.venv/Scripts/python.exe scripts/crawl_public.py --project-root . --config configs/public_site_joss.json --run-dir data/public_search/joss/demo-moi --resume --query archaeological
```

Crawler lấy metadata từ trang danh sách bài đã xuất bản và tối đa 3 bài theo cấu hình hiện tại. Query lọc cục bộ trên các bài đã thu thập, không tìm toàn bộ JOSS. Resume kiểm raw/checkpoint và robots mới; lỗi thiếu/hỏng dữ liệu phải FAIL, không bỏ qua.

Sau khi crawler nghiệm thu, có thể lấy DOI trong `records.json` rồi dùng `enrich_public.py --doi DOI`. Không truyền `JossPaperRecord` vào `--record-json`, vì tham số này yêu cầu `PaperRecord` v1 đầy đủ.

Crossref/JOSS dùng CLI riêng; giao diện `/public/ui` vẫn tìm OpenAlex/arXiv. Không tải PDF, không quét ngoài host, không có lịch chạy tự động.
