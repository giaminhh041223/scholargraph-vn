# Nhật ký Phiên `SESSION-20260929-074-GEMINI` — G4 (`GM-6` Bản thảo Báo cáo, Slides, Q&A & Checklist Nộp bài)

- **Phiên:** `SESSION-20260929-074-GEMINI`
- **Lane:** `W` (Báo cáo, slides & chuẩn bị bảo vệ)
- **Task liên quan:** `SG-043`, `SG-044`, `SG-045` (bản thảo phía Agent theo [MERGE_AND_FINISH_PLAN.md](../../docs/MERGE_AND_FINISH_PLAN.md) mục 4.5 & 6.7; giữ trạng thái `TODO` trên board chờ các cổng con người `H-1`, `H-2`, `H-3`).
- **Workspace:** `D:\Web_mining_20261\scholargraph`

---

## 1. Các tài liệu đã soạn thảo và đối chiếu 1:1 với `evidence_index.json`

1. **Báo cáo học thuật & Danh mục khẳng định (`SG-043`):**
   - [final_report.md](../../reports/final_report.md): Đầy đủ 10 mục (Tóm tắt, RQ1–RQ4, Dữ liệu & Chống rò rỉ, Phương pháp, Kết quả chính Track A/B/C, Ablation & Robustness, Phân tích thống kê & 24 ca lỗi, Kiến trúc & Hiệu năng, Giới hạn, Tái lập, và Khai báo sử dụng AI).
   - [CLAIMS_CHECKLIST.md](../../docs/CLAIMS_CHECKLIST.md): Bảng ánh xạ 1:1 toàn bộ 8 khẳng định (`CLM-001`..`CLM-008`), 7 `run_id` của Track A và 2 nhánh Track B sang [evidence_index.json](../../artifacts/reports/evidence_index.json).
   - Nêu bật trung thực 3 kết quả âm (`Hybrid RRF < Dense` ở `nDCG@10`; `Seeded PPR vs Global PageRank` có 95% CI `[-0.0198, +0.0021]` chứa 0; `Age decay` $\lambda > 0$ làm giảm đơn điệu `nDCG@10`), các phép đo độ trễ vượt ngân sách 500ms (`SCIDOCS BM25 P95 = 1510.9ms`, `Track B C100+PPR Mean = 1683.5ms`), và trạng thái Track C VN (`chưa đo — chờ nhãn người SG-033`).
2. **Bộ Slide bảo vệ, 18 câu hỏi phản biện & Khung nhật ký diễn tập (`SG-044`):**
   - [defense_slides.md](../../reports/defense_slides.md): 12 slides phân bổ theo thời lượng 15 phút trình bày + 5 phút demo trực tiếp/offline.
   - [DEFENSE_QA.md](../../docs/DEFENSE_QA.md): 18 câu hỏi và câu trả lời chi tiết về chống rò rỉ, công thức toán học, lý giải kết quả âm, input/output/assumption/error của từng module và cơ chế demo mất mạng.
   - [rehearsal_notes.md](../../artifacts/reports/rehearsal_notes.md): Khung biên bản cho 2 lần diễn tập đổi vai của hai thành viên con người.
3. **Danh mục kiểm tra nộp bài & Kiểm toán phát hành (`SG-045`):**
   - [SUBMISSION_CHECKLIST.md](../../docs/SUBMISSION_CHECKLIST.md): Tổng hợp toàn bộ hạng mục đã PASS và hướng dẫn từng lệnh cho hai thành viên hoàn tất `H-1`, `H-2`, `H-3`.
   - [release_audit.md](../../artifacts/reports/release_audit.md): Biên bản kiểm toán kỹ thuật gói phát hành tại kho chính.

---

## 2. Kết quả Kiểm chứng Tự động

- `.\.venv\Scripts\python.exe scripts\verify_claims.py`: **`PASS`** (`verified_claims = 8`, `verified_primary_numbers = 9`, `track_c_status = chua_do`, exit code `0`).
