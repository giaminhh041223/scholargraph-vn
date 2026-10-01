# SOL — Sửa findings EXT-07S F-01/F-02, vòng 103

- Thời điểm checkpoint: 2026-10-01T14:15:54+07:00.
- Worker thực tế: `/root/fix_ext07s_103`; dispatch từ coordinator, yêu cầu model `gpt-6.1-sol/high`. Runtime model/effort chưa có metadata độc lập để xác minh.
- Input được giao: parent `6a5d4e1`; báo cáo native MUSE [EXT-07S-W5-102](../../reviews/MUSE/EXT-07S-W5-102.md), snapshot audit `7726c83`.
- Quyền ghi: service, CLI, hai test modules và log riêng này. Coordinator giữ board/state/HANDOFF, commit và dispatch re-review.

## Thay đổi

- **F-01:** Đo thời gian thực của boundary lỗi bằng `time.perf_counter()` độc lập với đồng hồ transport; bắt adapter RuntimeError/OSError và lỗi đồng hồ transport thành source failed có thời gian quan sát được. Giữ snapshot/kết quả nguồn healthy trong `partial_failure`, không ghi elapsed null hoặc gán 0 thay phép đo. Nếu chính đồng hồ đo độc lập lỗi, cho NaN hoặc thời gian âm, phát `ServiceError(config)` rõ ràng và không lưu snapshot/cache.
- Nhánh exception giữ coverage kế hoạch lọc năm: OpenAlex `server`, arXiv `bounded_pool`; không có lọc năm là `none`. Error RuntimeError/OSError dùng message cố định, không stringify exception có secret. TransportError giữ kind đã chuẩn hóa.
- Xóa future fallback từng tạo SourceResult không hợp contract với elapsed null. Future chuyển tiếp ServiceError đo thời gian không hợp lệ để CLI trả FAIL/1.
- **F-02:** Dùng subclass ArgumentParser với `error()` phát ValueError message cố định. Parser con kế thừa; lỗi đối số vào `_failure(request)` và mã 1. `--help` vẫn mã 0.
- Bổ sung 31 ca hồi quy: 17 ca service (12 tổ hợp exception × nguồn × lọc năm, 1 lỗi transport clock, 4 lỗi phép đo độc lập) và 14 ca CLI subprocess (9 parse errors, 4 help, 1 unexpected adapter exception với service thật).
- Thay test CLI cũ cho phép HTTP trực tiếp bằng harness chạy entry point thật, SQLite store trong thư mục tạm và adapter empty synthetic; kiểm overall empty/CLI0 xác định. Harness partial chạy PublicSearchService thật + MemoryStore + RuntimeError/healthy record, không stub envelope.
- **F-03:** Metadata alias arXiv nullable của OpenAlex là limitation tùy chọn ngoài acceptance delta; không đổi adapter/schema. Coordinator ghi quyết định defer trước closeout audit.

## Kiểm chứng thực tế

1. Lượt đầu targeted suite: **14 failed, 43 passed**, 19.62s. Lỗi nằm ở tests mới: 12 healthy fixtures đưa datetime JSON string vào strict Python validator; 2 assertions giả sử nguồn đầu tiên là OpenAlex trong khi contract chuẩn hóa thứ tự sources. Sửa fixture dùng Python model dump và chọn source theo ID; không đổi production để làm tests pass.
2. Chạy lại `.venv/Scripts/python.exe -m pytest tests/unit/test_public_service.py tests/integration/test_public_cli.py tests/integration/test_public_routes.py -q`: **57 passed**, 2 deprecation warnings của dependency hiện có, **15.98s**, exit **0**. Dùng temporary fixtures/storage, synthetic adapters, không HTTP trực tiếp. Assertions kiểm surviving hit/snapshot, elapsed >= thời gian sleep quan sát, coverage, errors, cache không lưu partial, secret không xuất hiện, CLI1/structured FAIL và help0.
3. `git diff --check -- src/scholargraph/public_search/service.py scripts/search_public.py tests/unit/test_public_service.py tests/integration/test_public_cli.py`: exit **0**.
4. `./scripts/check_project.ps1`: exit **1**, **FAIL: Broken link in EXT-07M-W5-102.md: ../../../AGENTS.md**; có WARN SG-034 chờ SG-033. Liên kết hỏng thuộc báo cáo khác, đã báo coordinator, worker không sửa ngoài scope.

## Bàn giao

- Implementation và regression đã có trên checkout chung, chưa commit, chưa tự nhận fresh review PASS hoặc task DONE.
- Bước tiếp theo: coordinator sửa liên kết báo cáo EXT-07M, pin commit chứa delta này và giao MUSE re-review F-01/F-02 trên commit mới; ghi limitation/defer F-03. Human demo/release gate tiếp tục do coordinator quản lý.
