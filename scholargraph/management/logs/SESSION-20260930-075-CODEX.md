# Nhật ký SESSION-20260930-075-CODEX — kế hoạch tìm nguồn công khai

- Ngày: 2026-09-30, UTC+07:00.
- Vai trò: lập kế hoạch và chuẩn bị nhánh trong chat hiện tại.
- Model/effort/thread ID thực tế: chưa xác minh, không ghi từ routing khuyến nghị.
- Phạm vi người dùng giao: tạo nhánh mở rộng và lên plan chi tiết; chưa triển khai tìm kiếm/crawler.
- Board hiện tại vẫn có coordinator C và assignments SG-030/SG-033. Không chiếm quyền ghi shared board; handoff riêng là tài liệu này và kế hoạch bên dưới.

## Đầu vào đã đọc và hiện trạng

- Đọc AGENTS con, state, HANDOFF, tasks/task cards liên quan, DECISIONS, routing/registry/strategy và RESEARCH_PROTOCOL.
- Kiểm tra API/service/UI thật: search hiện tại SciFact frozen; downloader OpenAlex theo topic có sẵn.
- Git ban đầu ở master, HEAD `83358a9ec4add841293bc09c419b17c8dbb3bc0f`; không có thay đổi trong scholargraph lúc kiểm tra đầu phiên. Root có các untracked ngoài scope.
- Tạo nhánh `codex/public-paper-search` bằng `git switch -c codex/public-paper-search` thành công.
- Tra tài liệu API chính thức OpenAlex, arXiv và Crossref. arXiv Terms được link từ manual nhưng không lấy được nội dung bằng web tool; ghi gate phải xác minh trước live pilot.

## Đầu ra và checkpoint

- [PUBLIC_PAPER_SEARCH_PLAN.md](../../docs/PUBLIC_PAPER_SEARCH_PLAN.md): MVP hai nguồn, schema, failure contract, API/UI/cache/library, 8 work packages chính và 2 tùy chọn, estimate, adversarial tests và tiêu chí review/tích hợp.
- EXT IDs là đề xuất trong kế hoạch, không nhận là task trên board SG đã đăng ký hoặc DONE.
- Phần triển khai chưa làm; chưa search API thật, chưa có số đo vận hành, chưa test module mới.

## Kiểm chứng

- `scripts/check_project.ps1`: exit 0; PASS 53 tasks, dependency graph, 389 Markdown links, evidence/session paths và routing. Cảnh báo có thật: SG-034 đang chờ SG-033.
- `git branch --show-current`: `codex/public-paper-search`; hai tài liệu mới tồn tại đúng đường dẫn.
- `git diff --check` và `git diff --cached --check`: exit 0; staged diff chỉ gồm kế hoạch và nhật ký riêng của phiên.
- Chỉ thay đổi tài liệu; không chạy pytest hoặc tuyên bố module tìm trực tuyến đã hoàn tất.

## Bàn giao riêng / bước kế tiếp

- Người dùng đọc plan. Khi được giao implementation, coordinator đăng ký task tương ứng; bắt đầu EXT-01 source pilot/config/schema.
- Giữ gate thiếu đầu vào rõ ràng: arXiv Terms/quota chưa kiểm chứng; site HTML thí điểm chưa chọn.
- Không merge/push nhánh trong phiên kế hoạch.
