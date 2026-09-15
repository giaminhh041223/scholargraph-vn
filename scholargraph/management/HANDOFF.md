# Bàn giao ScholarGraph

NEXT_TASK: SG-003

- Phiên gần nhất: SESSION-20260915-005.
- Múi giờ: Asia/Saigon, UTC+07:00.
- Giai đoạn: M1 — SG-002 DONE; SG-003 là task tiếp theo.

## Bối cảnh đã chốt

ScholarGraph VN có 2 thành viên, dùng agent hỗ trợ triển khai, mục tiêu hoàn thành core trước 2026-10-31 và giữ tháng 11 làm buffer. GPU dùng Kaggle/Colab; chỉ thuê khi pilot của model cuối chứng minh cần thiết. Deadline/rubric chính thức của môn vẫn chưa được cung cấp.

## Trạng thái chính

- SG-000, SG-001, SG-002 và SG-005: DONE.
- CPU pilot SG-002: 1.000 fixture tổng hợp, MiniLM, batch 8, 21,99 giây, 45,48 docs/s.
- Colab pilot SG-002: Tesla T4 15.360 MiB, batch 32, 0,9385 giây, 1.065,48 docs/s, peak allocated/reserved khoảng 243,6/292 MiB.
- CPU và GPU dùng cùng input hash và model revision. Cả hai file embedding khớp SHA-256 trong report; GPU nhanh hơn khoảng 23,43 lần.
- Đây là compute feasibility, không phải retrieval-quality evidence. Model cuối tại SG-017 phải pilot lại.
- Không có bằng chứng cần thuê GPU ở thời điểm hiện tại.
- Bộ test: 6/6 pass; project checker phải tiếp tục pass sau mỗi thay đổi registry.

## Task tiếp theo

SG-003 — Related work và novelty. Đọc task card/routing, claim lane R, thu thập nguồn học thuật có thể kiểm chứng và tạo synthesis gắn với RQ/scope. Không thay đổi protocol hay claim novelty chỉ dựa trên blog/marketing.

## Tệp cần đọc

- [Compute plan](../docs/COMPUTE_PLAN.md)
- [Colab GPU report](../artifacts/reports/compute_pilot.json)
- [CPU baseline report](../artifacts/reports/compute_pilot.local_cpu.json)
- [Notebook pilot](../notebooks/compute_smoke.ipynb)
- [Nhật ký SG-002](logs/SESSION-20260915-005.md)
- [Master plan](../docs/MASTER_PLAN.md)
- [Task cards](../docs/TASKS.md)
- [Research protocol](../docs/RESEARCH_PROTOCOL.md)
- [Model từng ID](../docs/TASK_MODEL_MATRIX.md)
- [Chiến lược chat](../docs/MODEL_AND_CHAT_STRATEGY.md)

## Lưu ý vận hành

- Cache Hugging Face và embedding `.npy` không commit; hai report JSON CPU/GPU được giữ làm bằng chứng.
- Python local có cảnh báo NumPy 2.4.6/SciPy không tương thích; khóa environment trước thí nghiệm khoa học chính thức.
- Không có run/GPU process ScholarGraph đang chạy.
