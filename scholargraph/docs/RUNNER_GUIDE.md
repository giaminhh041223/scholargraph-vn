# Runner SG-007

Runner lưu bằng chứng của một thí nghiệm đã được cấu hình: run ID/status, hashes protocol/config/data/split/code/model, seed, lệnh, phần cứng, ranking và kết quả từng query. Runner không tính metric hay quyết định chất lượng retrieval; phần evaluator thuộc SG-008.

## Sử dụng

1. Tạo `RunStore(Path("artifacts/runs"))`, rồi gọi `create(...)` với nguồn/hash thật, model ID/revision và cấu hình đã chốt. `synthetic=True` chỉ dành cho fixture.
2. Gọi `record_rankings(...)` và `record_per_query(...)`; mỗi artifact chỉ ghi mới một lần. Có thể `append_log(...)` trong khi RUNNING.
3. Khi tiếp tục run dở, dùng `resume(run_id, expected_hashes=...)` để kiểm tra provenance và artifact trước khi làm tiếp.
4. Gọi `complete(aggregate_metrics)` khi thành công hoặc `fail(exception)` khi lỗi. Run COMPLETED/FAILED bất biến qua API, manifest có seal SHA-256, artifact được kiểm tra khi đọc/xuất.
5. `export(new_path)` sao chép cả run sang thư mục mới và từ chối ghi đè. Chạy lại thí nghiệm cần run ID mới.

Ví dụ đầy đủ có thể chạy được: [run_runner_smoke.py](../scripts/run_runner_smoke.py). Chạy từ thư mục ScholarGraph:

```powershell
& .\.venv\Scripts\python.exe -B scripts/run_runner_smoke.py
& .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
& .\scripts\check_project.ps1
```

Script tạo hai run synthetic COMPLETED/FAILED trong một thư mục riêng dưới artifacts/runs, kèm exports. [Smoke report](../artifacts/reports/sg007_smoke_20260915.json) lưu đường dẫn, SHA-256, môi trường và 9 kiểm tra. Mỗi lần chạy tạo thư mục run mới; báo cáo tổng hợp được cập nhật. Run artifacts ở local và bị Git ignore; có thể tạo lại bằng script. Giá trị `synthetic_smoke_value` chỉ thử khả năng lưu, không phải metric học thuật.

## Môi trường đã kiểm tra

- Python 3.12.14; Pydantic 2.13.5; pytest 8.4.2; httpx 0.28.1.
- `.venv` tạo từ bundled Python bằng `venv --system-site-packages`, tái sử dụng Pydantic sẵn có; pytest/httpx được cài riêng vào .venv.
- [Danh sách phiên bản kiểm thử](../requirements/sg007-verification.txt) ghim ba dependency trực tiếp đã dùng. Đây không phải lock transitive hoặc môi trường đầy đủ của ứng dụng.
- Toàn bộ suite: **78 passed**; reviewer độc lập chạy riêng runner: **23 passed**. [Review cuối](../management/reviews/SG-007-CLOSEOUT-REVIEW-20260915.md) ghi hashes và probes bổ sung.

## Ranh giới vận hành

- Run test không synthetic bắt buộc có protocol, freeze artifact và leakage audit hợp lệ, với bindings khớp config/data/split/model/method; chưa thể dùng cấu hình protocol còn unresolved để chạy final test.
- Provenance lưu dữ liệu caller cung cấp. Khi checkout có sửa đổi, cung cấp cả snapshot SHA-256 như smoke script; không chỉ ghi tên commit rồi khai clean.
- Các credential key/options và Authorization Basic/Bearer/Digest đã có regression, gồm JSON nhiều dòng. Parser không bảo đảm nhận diện mọi bí mật tùy ý trong văn xuôi; không đưa credential vào ranking hoặc scientific payload.
- Tính bất biến áp dụng qua API và phát hiện thay đổi bằng hashes; không phải cơ chế chống người có quyền sửa đồng thời cả artifact và seal. Mỗi run có một writer.
