# SESSION-20260929-068-GEMINI — GM-1: Review hồi tố SG-027 (freeze) và SG-028 (final runs)

- **Thời gian bắt đầu:** 2026-09-29T12:44:00+07:00
- **Thời gian kết thúc:** 2026-09-29T12:52:00+07:00
- **Session ID:** `SESSION-20260929-068-GEMINI`
- **Lane / Role:** `V` (`independent_reviewer`)
- **Snapshot:** `914b6ab80aa354a96df6e65faf4355fd6af06987`
- **Tasks:** `SG-027`, `SG-028`
- **Trạng thái:** `completed`

## 1. Công việc đã thực hiện (Prompt 6.3 — GM-1)
1. Kiểm chứng độc lập toàn bộ 33 tệp được ghim trong `configs/frozen_main.json`, 5 manifest index (`index.json` / `index_manifest.json`), `translations_cache.json`, và 7 tệp `artifacts/final_test/freeze_*.json` (`sha256(frozen_main.json) = 34159fb133594633530c08390b259ea6efd7e024a384cb2c25092bf6e4797557`).
2. Kiểm tra thứ tự nhân quả trên đồ thị commit Git (`git log --reverse --oneline e959f68~1..dcca385`): xác nhận commit freeze (`569f08c`, `e4c1a7e`) đứng trước commit chạy final test (`ddc416a`), và kiểm tra `artifacts/runs/*-test*` có đúng 7 run test (1 run duy nhất cho mỗi cặp `(dataset, method)`).
3. Viết và chạy script kiểm chứng độc lập ngoài dự án (không import `scholargraph.evaluation`), tính lại toàn bộ 7 run Track A × 5 metric và 2 nhánh Track B × 5 metric (45 con số) từ `rankings.jsonl`, `qrels/test.tsv`, và `b_trials_test.json`. Độ lệch tuyệt đối tối đa: `0.00e+00` (`< 1e-4`).
4. Rà soát `artifacts/final_test/leakage_A_*.json` và mã nguồn các bộ xếp hạng; ghi nhận 2 lưu ý mức `P2` (không có `P0`/`P1`).
5. Ghi biên bản review tại `management/reviews/SG-027-REVIEW-20260929.md` và `management/reviews/SG-028-REVIEW-20260929.md`.
