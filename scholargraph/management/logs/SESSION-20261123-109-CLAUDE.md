# SESSION-20261123-109-CLAUDE

- Bắt đầu: 2026-11-23 (UTC+07:00); checkpoint/kết thúc: 2026-11-23T17:18:53+07:00
- Owner: Claude Code (desktop), một chat kiêm coordinator + worker; không có phiên nào khác đang chạy được xác minh.
- Model/effort: claude-fable-5-2 theo system prompt của phiên; effort không xác minh (unknown).
- Task IDs: không nhận task mới. Liên quan SG-043 (báo cáo), giữ TODO.
- Phạm vi được giao: (1) người dùng yêu cầu viết progress report môn học (PDF ≤ 3 trang) từ hiện trạng dự án; (2) sau khi được báo các số lệch, người dùng trả lời "Sửa luôn" cho việc sửa `reports/final_report.md` khớp artifact.
- Trạng thái: completed (2 checkpoint; checkpoint 2 ở cuối file).

## Đã đọc và xác minh

AGENTS (gốc + scholargraph), state, HANDOFF, tasks.json, public_search HANDOFF/state/tasks, SCOPE, DATA_CARD, DECISIONS (ADR-017, ADR-023), protocol_v1.json, frozen_main.json, tuning_space.json, age_adjustment.json. Số liệu lấy trực tiếp từ `main_results.md`, `statistics.json`, `ablation.md`, `ablation_rrfk.json`, `robustness.json`, `performance.json`, `graph_audit.json`, `split_audit.json`, `graph_feasibility_core.json`, `error_packets.json`, `data/annotations/v2/*`, `vn_machine_dev_v2_20261008/REPORT.md`. Nhánh `codex/public-search-phase-b`, HEAD `57e2895`, có sẵn 3 file docs phase B chưa commit (không đụng).

## Công việc

1. Tạo `reports/progress/Groupxx_ProgressReport.html` và `.pdf` (3 trang A4, tiếng Anh, in bằng Edge headless). Còn 3 placeholder: số nhóm, tên thành viên, link repo (repo chưa có remote).
2. Sửa `reports/final_report.md` bằng script thay thế có kiểm tra (37 vị trí, mỗi anchor phải khớp đúng 1 lần, sai là exit 1). Các lỗi đã sửa:
   - CI nDCG@10: hybrid−BM25 SciFact `[+0.0297, +0.0819]` → `[+0.0333, +0.0792]`; dense−BM25 SCIDOCS `[+0.0558, +0.0748]` → `[+0.0549, +0.0753]`; hybrid−dense SCIDOCS `[-0.0246, -0.0148]` → `[-0.0273, -0.0122]` (theo `statistics.json`).
   - Số truy vấn dev/test: SciFact 300/300 → 809/300; SCIDOCS 1.000/1.000 → không có dev/1.000; OpenAlex 200/200 → 100/200; năm dev 2024, test 2025 (theo `split_audit.json`, `graph_audit.json`, `graph_feasibility_core.json`).
   - Mô tả che cạnh Track B: không phải "toàn bộ cạnh đi ra" mà là ~20% tham chiếu (ít nhất 1), 330 cạnh giữ lại, che hai chiều (theo `protocol_v1.json`, `graph_audit.json`).
   - Công thức tuổi: bản thảo ghi cộng `λ·s_age` với `t_ref = 2026`; thực tế là nhân `exp(-λ·max(0, year(q) − year(d)))` sau fusion, mốc là năm bài truy vấn (theo `protocol_v1.json`, `age_adjustment.json`). Sửa cả lời văn "thưởng độ mới".
   - Dev nDCG@10 của cấu hình chọn: `0.1297` → `0.1310` (theo `frozen_main.json`).
   - Nhóm bậc Track B: số 145/27/28 và 0.0680/0.3881/0.0642/0.4226 không có trong artifact; thay bằng `robustness.json` (low n=121: PPR 0.0807, global 0.0902; high n=36: PPR 0.1276, global 0.1252; chia theo bậc của bài truy vấn). Kết luận diễn giải đảo chiều theo số thật.
   - Số gói lỗi: 8/8/8 → 12/6/6 (theo `error_packets.json`). Bỏ các ví dụ từ khóa và số 145/200, 76,75% không có nguồn; ba cơ chế lỗi ghi là giả thuyết chờ H-1.
   - Kiểm toán rò rỉ: bỏ tên 3 file không tồn tại và câu "0 trùng lặp văn bản"; ghi 7 file per-run PASS, graph audit 0 cạnh sót, và 2 truy vấn SciFact trùng văn bản dev/test đã được `split_audit.json` ghi nhận.
   - RRF k: "< 0.002" → lệch tối đa 0.0019 so với k=60.
   - Track C: chuyển sang v2 (679 cặp, 227/452, ADR-023), ghi lý do bỏ v1, thêm thử nghiệm máy chấm (thăm dò, không là nhãn).
   - Nguồn gốc truy vấn VN: bản thảo ghi "do con người biên soạn"; manifest v1 và v2 đều ghi agent soạn nháp, chủ dự án duyệt nguyên bản. Sửa bảng dữ liệu, mục 8 và mục 10 (AI disclosure).
   - Link hỏng `docs/DATASET_CARD.md` → `docs/DATA_CARD.md`; số test 746 → 749 (state.json, 29/09); thêm cỡ mẫu đo hiệu năng (n = 20/10/5).
3. Sửa progress report cho khớp các phát hiện trên (nguồn gốc truy vấn VN, công thức tuổi, cỡ mẫu đo hiệu năng) rồi build lại PDF.

## Kiểm tra

| Lệnh/kiểm tra | Kết quả |
|---|---|
| `scripts/verify_claims.py` sau khi sửa | exit 0, PASS (8 claims, 9 primary numbers) |
| `pytest tests/unit/test_claims_verifier.py -q` | 4 passed |
| grep các giá trị sai cũ trong `final_report.md` | 0 dòng |
| Kiểm mọi link `../` trong `final_report.md` và 5 path mới | không link hỏng |
| PDF progress report | 3 trang (pymupdf), đã xem ảnh từng trang |
| `pytest tests --collect-only` | 1609 tests collected trên nhánh hiện tại |

## Chưa làm / chưa kiểm

- Chạy toàn bộ pytest hôm nay (`.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`, KHÔNG đặt `PYTHONPATH=src`, bắt đầu trước khi sửa `final_report.md`): **1588 passed, 21 failed**, 855 s.
  - 20 lỗi ở `tests/unit/test_public_fusion.py` (các test CLI subprocess) do lệnh của phiên này thiếu `PYTHONPATH=src` (`ModuleNotFoundError: No module named 'scholargraph'`). Chạy lại hai file `test_public_fusion.py` + `test_ui.py` với `PYTHONPATH=src`: 107 passed, 1 failed.
  - 1 lỗi thật, có từ trước phiên này: `tests/unit/test_ui.py::test_static_served_offline` cấm chuỗi `http://` trong mọi file `ui/static/*`, nhưng `ui/static/public_search.js` (thêm ở nhánh public search, commit `5dc9fd6`..`6a5d4e1`) có `http://` trong chú thích kiểm tra URL. Chưa sửa (ngoài phạm vi); cần quyết định sửa test hay sửa chú thích.
  - Chưa chạy lại toàn bộ suite với `PYTHONPATH=src`, nên không có số pass toàn suite đã đo cho cấu hình đúng. Progress report vẫn dùng số 749 ghi nhận ngày 29/09.
- `verify_claims.py` chỉ kiểm claim ID, run ID, 9 giá trị nDCG@10 chính và mẫu cấm; nó không kiểm CI hay các số khác. Việc PASS trước đây không chứng minh các số còn lại đúng.
- Các số sai tương tự CÒN trong: `scripts/build_evidence_index.py` (chuỗi `statement_vi` viết tay của CLM-002, CLM-003 có CI sai; CLM-008 và table_3 ghi 662, 219/443) → `artifacts/reports/evidence_index.json`; `docs/CLAIMS_CHECKLIST.md` (CLM-002, CLM-003, CLM-008); `reports/defense_slides.md`; `docs/DEFENSE_QA.md`; `docs/REPRODUCE.md`. Chưa sửa vì ngoài phạm vi được giao; bảng `table_6_paired_bootstrap` trong evidence index thì đúng.
- Các lời giải thích cơ chế trong báo cáo vẫn là giả thuyết, chưa có phép đo.
- Không đối chiếu được với proposal (không có file proposal trong workspace).

## Bàn giao

- Task status: không đổi (42 DONE, SG-030 REVIEW, SG-033 IN_PROGRESS, 5 TODO, 4 DEFERRED). Human gates giữ nguyên.
- Bước kế tiếp: người dùng điền số nhóm/thành viên/link repo vào progress report; quyết định có sửa các file còn lệch ở trên không (cần regenerate `evidence_index.json`).
- Không có process nào còn chạy. Chưa commit.

## Checkpoint 2 — sửa các file còn lệch (người dùng trả lời "Sửa tiếp")

Phạm vi được giao: evidence index, checklist, slides, Q&A (và `REPRODUCE.md` đã nêu cùng nhóm).

- **Gốc lỗi:** `statement_vi` của các claim trong `scripts/build_evidence_index.py` là chuỗi viết tay, lệch với `statistics.json` dù cùng file đã nạp đúng số vào `metrics` và `table_6`.
- **`scripts/build_evidence_index.py`:** CI của CLM-001..004 lấy từ dòng thống kê qua `_ci()`; thêm `_expect_ci_excludes_zero()` (lời văn "chứa 0/không chứa 0" mâu thuẫn với thống kê thì exit 1); số cặp pool VN đếm từ `data/annotations/v2/vn_pool.json` (thiếu file thì exit 1, tổng phải khớp `counts.unique_pairs`); ghi output bằng LF trên mọi nền tảng (trước đó chạy trên Windows sinh CRLF, làm diff toàn file).
- **`artifacts/reports/evidence_index.json` sinh lại.** So nội dung với HEAD: chỉ đổi `claims[1,2,7].statement_vi`, `claims[7].source_file`, `tables.table_3_track_c_vn` (`pending_human_gate`, thêm `pool`, `pool_pairs`) và `generated_at`. Bảng số liệu 1, 2, 4..8 không đổi. Hash file này không được ghim ở đâu trong repo (đã grep).
- **`scripts/verify_claims.py`:** thêm kiểm 5 CI nDCG@10 (CLM-001..004) phải xuất hiện đúng định dạng trong cả `final_report.md` và `CLAIMS_CHECKLIST.md`. Chạy trước khi sửa checklist: exit 1, chỉ đúng 2 CI sai. Docstring ghi rõ phần không kiểm.
- **Tài liệu:** `docs/CLAIMS_CHECKLIST.md` (6 chỗ), `reports/defense_slides.md` (20), `docs/DEFENSE_QA.md` (11), `docs/REPRODUCE.md` (1), `reports/final_report.md` (thêm 1: nhãn fallback). Ngoài CI/pool/số query/công thức tuổi/nhóm bậc/số gói lỗi như ở checkpoint 1, còn sửa: nhãn API thật là hậu tố `+fallback-dense-only` sau method id `hybrid-rrf-k60-bm25-dense` (tài liệu ghi `hybrid+fallback-...`); Q&A câu 16 ghi hàm `seeded_ppr` không tồn tại, hàm thật là `build_teleport` / `personalized_pagerank` ném `GraphDataError`; Q&A câu 1 trích file `leakage_B_openalex.json` không tồn tại; ví dụ từ khóa và các khoảng năm trong phần giải thích không có nguồn đã bỏ; các giải thích cơ chế gắn nhãn "giả thuyết".
- **Test mới:** `test_verify_claims_rejects_stale_bootstrap_ci_exit_1`; `test_evidence_index_claim_text_is_derived_and_lf`, `test_evidence_index_missing_vn_pool_exits_1`, `test_evidence_index_rejects_claim_wording_contradicting_stats` (fixture copy vào `tmp_path`, CLI subprocess).

| Lệnh/kiểm tra | Kết quả |
|---|---|
| `scripts/build_evidence_index.py` | exit 0, 7 run / 24 so sánh / 8 claim |
| `scripts/verify_claims.py` (sau khi sửa checklist) | exit 0, PASS |
| `pytest tests/unit/test_claims_verifier.py tests/unit/test_reproduction_audit.py` (`PYTHONPATH=src`) | 14 passed |
| grep giá trị sai cũ trong 5 tài liệu | chỉ còn 3 dòng nhắc v1 có chủ đích |

Không sửa: `test_ui.py::test_static_served_offline` (lỗi có từ trước, ngoài phạm vi); `reports/figures/*.svg` không sinh lại vì các bảng nguồn không đổi.

## Kết quả chạy toàn suite với `PYTHONPATH=src` (nhận sau checkpoint 2)

`PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`: **1606 passed, 3 failed**, 367 s, trên 1609 test (bắt đầu trước khi thêm 4 test mới).

- `test_ui.py::test_static_served_offline`: lỗi thật có từ trước, chưa sửa.
- `test_claims_verifier.py::test_verify_claims_real_files_pass` và `::test_verify_claims_rejects_p_value_and_sota_exit_1`: fail do chạy đúng lúc `verify_claims.py` đã có kiểm CI mới nhưng `CLAIMS_CHECKLIST.md` chưa sửa. Chạy lại ở trạng thái cuối cùng với `test_reproduction_audit.py` và `test_ui.py`: 22 passed, 1 failed (chỉ còn test_ui).
- Chưa có lần chạy toàn bộ 1613 test nào trên trạng thái cuối cùng. Kết luận được phép nêu: 1606 test không liên quan thay đổi đã pass, 14 test của verifier/generator pass ở trạng thái cuối, 1 test_ui fail.

## Checkpoint 3 — sửa `test_ui.py::test_static_served_offline` (người dùng: "bạn xử lí luôn nhé")

- **Nguyên nhân:** test SG-036 cấm chuỗi `http://`/`https://` ở bất kỳ đâu trong `ui/static/*`. `ui/static/public_search.js` (nhánh public search) có hai dòng chú thích mô tả việc kiểm tiền tố URL (dòng 133–134); không có URL nào trong code. Đây là lỗi dương tính giả của test, không phải tài nguyên mạng.
- **Vì sao sửa test, không sửa JS:** `public_search.js` được ghim SHA-256 `9b628b68…9457` trong `management/public_search/W5-FINAL-104.json` và bằng chứng validation W5; sửa JS sẽ làm lệch các bằng chứng đó. `test_ui.py` không bị ghim ở đâu (đã grep hash).
- **Thay đổi:** thêm `_absolute_urls_outside_comment_lines()` chỉ bỏ qua dòng là chú thích trọn dòng (`//`, `/*`, `*`); URL trong code, chuỗi, `@import`, markup hoặc chú thích cuối dòng vẫn bị bắt. Thêm `test_absolute_url_scan_ignores_only_whole_line_comments` (4 ca phải bắt, 3 ca chú thích bỏ qua) và yêu cầu quét ít nhất 4 file tĩnh. Ý định của acceptance SG-036 (UI offline, không CDN) giữ nguyên; không cần ADR mới.
- **Kiểm tra:** `pytest tests/unit/test_ui.py` 10 passed. Đột biến thật: thêm `@import url(https://fonts.example/a.css);` vào `style.css` → test fail đúng; đã khôi phục file (git status sạch ở `ui/`). Hash `public_search.js` không đổi.
- **Toàn suite trên trạng thái cuối:** `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider` → **1614 passed, 0 failed**, 307,5 s (gồm 4 test verifier/generator của checkpoint 2 và 1 test mới của checkpoint 3).

## Bàn giao cuối phiên

- Task status không đổi; human gates giữ nguyên. Chưa commit (nhánh `codex/public-search-phase-b` còn 3 file docs phase B chưa commit từ trước phiên này, không thuộc phiên 109).
- Progress report: câu về test đổi từ "749 tests (29 Sep)" sang "1,614 tests passed (23 Nov)" theo lần chạy trên; PDF build lại, vẫn 3 trang.
- Bước kế tiếp: người dùng điền placeholder progress report và nộp; commit khi được đồng ý.

## Checkpoint 4 — trình bày lại progress report (người dùng: trông như sinh viên làm, form lịch sự chỉn chu)

- Viết lại `reports/progress/Groupxx_ProgressReport.html` theo khuôn báo cáo môn học: khối tiêu đề (trường/khoa, mã môn, tên báo cáo), bảng thành viên + MSSV, nhóm/giảng viên/repo/ngày, Times New Roman đen trắng, mục đánh số, chú thích bảng/hình, 10 tài liệu tham khảo (lấy từ `docs/references.bib`, thêm OpenAlex, BGE/C-Pack, PageRank). Lời văn ngôi "we" của nhóm, ít thuật ngữ nội bộ. Số liệu không đổi so với bản trước.
- Placeholder tô vàng: tên trường, khoa, 2 họ tên + MSSV, số nhóm, giảng viên, link repo (2 chỗ). Tên trường không có trong tài liệu môn học của workspace nên không tự điền.
- PDF build lại bằng Edge headless: 3 trang A4, đã xem ảnh cả 3 trang.
- Người dùng cung cấp nhóm gồm **4 thành viên** (kèm MSSV), giảng viên Nguyễn Kiêm Hiếu, mã lớp 175886; đã điền vào progress report. Các câu "both members / the second member" đổi thành "two members / the group / a member who did not run the experiments". Lưu ý: `state.json` vẫn ghi `human_members: 2` (giả định lập kế hoạch cũ); chưa sửa board vì không thuộc phạm vi được giao.
- Còn trống: tên trường, khoa, số nhóm, link repo. PDF vẫn 3 trang.

