# Bàn giao ScholarGraph

NEXT_TASK: SG-003

- Phiên gần nhất: SESSION-20260915-005.
- Múi giờ làm việc: Asia/Saigon, UTC+07:00.
- Giai đoạn: M1 — SG-002 đã hoàn tất phần local và đang BLOCKED ở phép đo GPU cloud; SG-003 là task tiếp theo không phụ thuộc blocker này.

## Bối cảnh đã chốt

ScholarGraph VN có 2 thành viên, dùng agent hỗ trợ triển khai, mục tiêu hoàn thành core trước 2026-10-31 và giữ tháng 11 làm buffer. GPU dự kiến dùng Kaggle/Colab; chỉ thuê GPU sau khi pilot thực tế chứng minh cần thiết. Deadline/rubric chính thức của môn vẫn chưa được cung cấp.

## Trạng thái chính

- SG-000, SG-001 và SG-005: DONE.
- SG-002: BLOCKED có chủ đích, không phải lỗi implementation. Local audit, notebook, CPU pilot, dự toán và shard/resume plan đã xong; thiếu một run CUDA thật trên tài khoản Colab/Kaggle.
- CPU pilot SG-002: 1.000 fixture tổng hợp, MiniLM revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, batch 8, 21,99 giây, 45,48 docs/s, embedding `[1000, 384]`; checksum file khớp report.
- GPU local: hệ điều hành thấy MX550 2 GB, nhưng PyTorch hiện tại là CPU-only; GPU throughput/peak VRAM không được suy đoán.
- Bộ test: 5/5 pass. Project checker pass trước checkpoint.

## Cách mở blocker SG-002

1. Mở `notebooks/compute_smoke.ipynb` trên Colab hoặc Kaggle và bật GPU.
2. Run All; chỉ nhận kết quả nếu report ghi `device=cuda` và có GPU name/peak VRAM/docs-second.
3. Đưa `artifacts/reports/compute_pilot.json` về workspace, chạy test/checker và chuyển SG-002 sang review/closeout.
4. Nếu chưa có cloud session, tiếp tục SG-003; không cần chờ SG-002.

## Task tiếp theo

SG-003 — Related work và novelty. Đọc task card/routing, claim lane R, thu thập nguồn học thuật có thể kiểm chứng và tạo synthesis gắn với RQ/scope. Không thay đổi protocol hay claim novelty chỉ dựa trên blog/marketing.

## Tệp cần đọc

- [Compute plan và hướng dẫn GPU](../docs/COMPUTE_PLAN.md)
- [Notebook pilot](../notebooks/compute_smoke.ipynb)
- [CPU report](../artifacts/reports/compute_pilot.json)
- [Nhật ký SG-002](logs/SESSION-20260915-005.md)
- [Master plan](../docs/MASTER_PLAN.md)
- [Task cards](../docs/TASKS.md)
- [Research protocol](../docs/RESEARCH_PROTOCOL.md)
- [Model từng ID](../docs/TASK_MODEL_MATRIX.md)
- [Chiến lược chat](../docs/MODEL_AND_CHAT_STRATEGY.md)

## Lưu ý vận hành

- Cache Hugging Face và embedding `.npy` không commit; report JSON được giữ làm bằng chứng.
- Python local có cảnh báo NumPy 2.4.6/SciPy không tương thích; khóa environment trước thí nghiệm khoa học chính thức.
- Không có run/GPU process ScholarGraph đang chạy.
