# Nhật ký Phiên `SESSION-20260929-073-CODEX` — G4 (`CX-3` & `CX-4` Tooling, `evidence_index.json`, `figures/`)

- **Phiên:** `SESSION-20260929-073-CODEX`
- **Lane:** `W` (Báo cáo, tái lập & công cụ đánh giá G4)
- **Task liên quan:** `SG-034`, `SG-042`, `SG-043` (phần công cụ và chỉ mục bằng chứng phía Agent; giữ nguyên trạng thái `TODO` trên board theo DAG chờ cổng con người `SG-030` và `SG-033`).
- **Workspace:** `D:\Web_mining_20261\scholargraph`

---

## 1. Các tạo phẩm đã xây dựng

1. **Công cụ `CX-3` (`SG-034`) — [run_vn_eval.py](../../scripts/run_vn_eval.py):**
   - Hỗ trợ quy trình 2 pha tách biệt:
     - `--phase freeze-dev`: Chỉ đọc các cặp thuộc lát cắt `dev` từ `data/annotations/vn_labels.jsonl`, từ chối mọi nhãn `null`, từ chối bất đồng A/B chưa phân xử (`adjudicated`), tính `nDCG@10`, `P@5`, `MRR@10`, `pooled Recall@100`, `unjudged_ratio@10` cho 3 phương pháp trong pool (`translated_bm25`, `multilingual_dense`, `vn_hybrid_rrf`), chọn cấu hình mặc định qua `scholargraph.evaluation.tuning.select_best` (phá hòa theo thứ tự từ điển `trial_id`), và ghi `configs/frozen_vn.json` với `"human_approved": false`.
     - `--phase eval-test`: Bắt buộc `configs/frozen_vn.json` tồn tại và có `"human_approved": true` (thoát mã lỗi `1` nếu chưa được con người duyệt), chấm điểm tập `test` 1 lần và xuất `artifacts/reports/vn_results.json` + `artifacts/reports/vn_results.md`.
2. **Công cụ `CX-4` (`SG-042` / `SG-043`):**
   - [build_evidence_index.py](../../scripts/build_evidence_index.py) $\to$ sinh [evidence_index.json](../../artifacts/reports/evidence_index.json) nối 1:1 toàn bộ 7 run Track A, 2 nhánh Track B, các bảng Ablation (`A1`, `A3`), Robustness (`R1..R5`), 24 khoảng tin cậy Paired Bootstrap, số đo hiệu năng (`SG-040`), và 8 khẳng định cốt lõi (`CLM-001`..`CLM-008`) với mã băm SHA-256 của tệp nguồn. Track C VN được ghi trung thực `status = "chua_do"`, `metrics = null`.
   - [compare_reproduction.py](../../scripts/compare_reproduction.py): Đối chiếu kết quả chạy lại của thành viên thứ hai với `evidence_index.json` theo ngưỡng dung sai `1e-4`; bắt buộc định danh người tái lập (`--reproducer`) và từ chối tên tác tử AI (`agent`, `codex`, `gemini`, `claude`).
   - [generate_figures.py](../../scripts/generate_figures.py) $\to$ sinh 4 biểu đồ SVG từ `evidence_index.json`:
     - `reports/figures/fig1_track_a_ndcg10.svg`
     - `reports/figures/fig2_track_b_openalex.svg`
     - `reports/figures/fig3_ablation_age_rrf.svg`
     - `reports/figures/fig4_latency_budget.svg`
   - [verify_claims.py](../../scripts/verify_claims.py): Kiểm chứng khớp 1:1 giữa `reports/final_report.md`, `docs/CLAIMS_CHECKLIST.md` và `artifacts/reports/evidence_index.json`.

---

## 2. Kiểm thử Đơn vị & Kiểm thử Phá hủy (Adversarial Tests)

- [test_vn_eval.py](../../tests/unit/test_vn_eval.py): 5 kiểm thử (happy path 2 pha trong `tmp_path`, từ chối `eval-test` khi `human_approved=false`, từ chối nhãn `null`, từ chối bất đồng A/B chưa phân xử, từ chối lộ `system` provenance, từ chối thiếu tệp — tất cả trả về `returncode == 1`).
- [test_reproduction_audit.py](../../tests/unit/test_reproduction_audit.py): 6 kiểm thử (`build_evidence_index.py`, `compare_reproduction.py` trong ngưỡng `1e-4`, từ chối tên AI reproducer `exit 1`, từ chối sai lệch `> 1e-4` và điểm ngoài `[0, 1]` `exit 1`, `generate_figures.py`).
- [test_claims_verifier.py](../../tests/unit/test_claims_verifier.py): 4 kiểm thử (`verify_claims.py` PASS trên tài liệu thật, từ chối thiếu `CLM-ID` `exit 1`, từ chối câu chứa `p < 0.05` hoặc `state-of-the-art` `exit 1`, từ chối sửa số liệu chính `exit 1`).
- Kết quả chạy: `15 passed in 12.12s`.
