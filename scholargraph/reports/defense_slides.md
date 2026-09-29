# Bộ Slide Bảo vệ Đồ án — ScholarGraph VN (SG-044)

> **Trạng thái:** Bản thảo bộ slide chuẩn bị bởi `GM-6` (đối chiếu 1:1 với [evidence_index.json](../artifacts/reports/evidence_index.json) và [final_report.md](final_report.md)). Chờ hai thành viên cập nhật điểm Track C sau khi xong `SG-033`/`SG-034` và thực hiện 2 lần diễn tập đổi vai (`H-3`).
> **Tổng thời lượng mục tiêu:** 15 phút trình bày (12 slides) + 5 phút Demo trực tiếp/offline ([DEMO_SCRIPT.md](../docs/DEMO_SCRIPT.md)).

---

## Slide 1 — Tiêu đề & Định vị Đồ án (0:00 – 1:00)
- **Đề tài:** ScholarGraph VN — Hệ thống Tìm kiếm Văn bản Học thuật, Tái xếp hạng Đồ thị Trích dẫn và Truy vấn Xuyên ngữ Việt–Anh có Kiểm toán Thực nghiệm.
- **Mục tiêu cốt lõi:**
  1. Xây dựng đường ống truy hồi kết hợp từ vựng (`TF-IDF`, `BM25`), biểu diễn dày đặc (`BAAI/bge-base-en-v1.5`) và hợp nhất thứ hạng (`RRF k=60`).
  2. Tái xếp hạng trên đồ thị trích dẫn có hướng (`Seeded PPR` vs `Global PageRank`) và điều chỉnh độ tuổi bài báo (`Age Decay`) dưới giao thức cắt theo thời gian chống rò rỉ (`temporal holdout`).
  3. Đánh giá trung thực cả **kết quả dương** và **kết quả âm** bằng khoảng tin cậy paired bootstrap 95% ($B=10.000$).

---

## Slide 2 — Bốn Câu hỏi Nghiên cứu & Thiết kế 3 Nhánh Đánh giá (1:00 – 2:15)
- **Track A (Text Retrieval — BEIR):** SciFact (`5.183` bài, `300` test queries) & SCIDOCS (`25.657` bài, `1.000` test queries).
- **Track B (Citation Graph Reranking — OpenAlex):** `18.251` nút đồ thị (`18.250` bài có văn bản sau khi loại tường minh 1 bài rỗng `W126924136` theo `ADR-017`), `200` truy vấn dev + `200` truy vấn test xuất bản năm $\ge 2025$.
- **Track C (Cross-Lingual Vietnamese Pilot):** `30` truy vấn tiếng Việt (`10` dev / `20` test) trên kho `18.250` bài tiếng Anh; pool mù top-10 (`662` cặp) ẩn nguồn phương pháp.

---

## Slide 3 — Giao thức Chống Rò rỉ và Đóng băng Trước Test (`SG-016`, `SG-027`) (2:15 – 3:30)
- **Chống rò rỉ đồ thị (Track B):**
  - Toàn bộ cạnh trích dẫn đi ra từ các bài truy vấn năm $\ge 2025$ bị tách làm nhãn ẩn (`held-out edges`), không nằm trong ma trận kề khi tính PageRank/PPR.
  - Cấm tuyệt đối cạnh trích dẫn ngược thời gian và tự khớp (`self-match`).
- **Đóng băng cấu hình (`configs/frozen_main.json`):**
  - Khóa SHA-256 của 33 tệp dữ liệu, chỉ mục và manifest (`sha256 = 34159fb1...7557`) tại commit `e959f68` **trước khi** mở tập `test`.
  - Chọn siêu tham số Track B ($\gamma=0.3, \lambda=0.0$) hoàn toàn trên tập `dev` (`SG-026`, 20 cấu hình).

---

## Slide 4 — Kiến trúc Đường ống Truy hồi & Tái xếp hạng (3:30 – 4:45)
- **Tầng 1 (Candidate Generation):**
  - Từ vựng: `BM25` ($k_1=1.5, b=0.75$) & `TF-IDF`.
  - Ngữ nghĩa: `BAAI/bge-base-en-v1.5` ($d=768$, chuẩn hóa $L_2$, `ExactDenseIndex`).
  - Hợp nhất: $\text{RRF}(d) = \frac{1}{60 + r_{\text{BM25}}(d)} + \frac{1}{60 + r_{\text{Dense}}(d)}$.
- **Tầng 2 (Graph Reranking trên tập ứng viên `C100`):**
  - Chuẩn hóa min-max theo từng truy vấn: $S(q,d) = (1-\gamma)\tilde{s}_{\text{text}} + \gamma\tilde{s}_{\text{graph}} + \lambda\tilde{s}_{\text{age}}$.
  - Xử lý suy biến minh bạch ở API (`dcca385`): Khi một nhánh rỗng, trả về nhánh còn lại kèm nhãn `hybrid+fallback-dense-only` hoặc `hybrid+fallback-lexical-only` (không che giấu, không lỗi 500).

---

## Slide 5 — Kết quả Track A: Dense vượt BM25, nhưng Hybrid RRF < Dense (4:45 – 6:15)
- **Bảng kết quả chính (`artifacts/reports/main_results.md`):**
  - **SciFact Test ($n=300$):** `TF-IDF = 0.6327` | `BM25 = 0.6647` | **`Dense = 0.7404`** | `Hybrid RRF = 0.7204`.
  - **SCIDOCS Test ($n=1000$):** `BM25 = 0.1521` | **`Dense = 0.2172`** | `Hybrid RRF = 0.1976`.
- **Ý nghĩa thống kê (`B=10.000` paired bootstrap):**
  - `Dense vs BM25`: `+0.0757` trên SciFact (`CI [+0.0405, +0.1115]`) và `+0.0652` trên SCIDOCS (`CI [+0.0558, +0.0748]`).
  - **Kết quả âm 1 (`Hybrid vs Dense`):** `-0.0200` trên SciFact (`CI [-0.0469, +0.0066]`, chứa 0) và `-0.0197` trên SCIDOCS (`CI [-0.0246, -0.0148]`).
  - **Lý do:** RRF trọng số bằng nhau đẩy các bài khớp từ khóa bề mặt ở top-3 của BM25 vượt lên trên các bài đúng ngữ nghĩa ở hạng 4–10 của Dense.

---

## Slide 6 — Kết quả Track B: Seeded PPR vs Global PageRank trên OpenAlex (6:15 – 7:45)
- **Kết quả trên 200 truy vấn kiểm tra (`test200`):**
  - `ppr_age_best_g0.3_l0.0` (Seeded PPR): `nDCG@10 = 0.1004`, `Recall@100 = 0.2325`, `MRR@10 = 0.0890`.
  - `global_pagerank_control` (Đối chứng): `nDCG@10 = 0.1082`, `Recall@100 = 0.2325`, `MRR@10 = 0.0991`.
- **Kết quả âm 2 (`CLM-004`):**
  - Chênh lệch `PPR - Global PR` là `-0.0078` với 95% CI `[-0.0198, +0.0021]` **chứa 0**.
  - **Giải thích:** (1) Trần ứng viên `C100` chỉ giữ được `23.25%` bài trích dẫn thật; (2) `145/200` truy vấn có bài đích bậc vào bằng 0 trên đồ thị huấn luyện; (3) Hạt giống văn bản nhiễu làm PPR lan truyền xác suất ra vùng lân cận sai, trong khi Global PageRank ưu tiên ổn định các bài báo kinh điển.

---

## Slide 7 — Nghiên cứu Cắt bỏ (Ablation A1 & A3) và Độ bền vững (7:45 – 9:15)
- **Ablation A1 — Điều chỉnh tuổi bài báo ($\lambda \in \{0.0, 0.01, 0.03, 0.1\}$ tại $\gamma=0.3$):**
  - **Kết quả âm 3 (`CLM-005`):** `nDCG@10` của PPR giảm đơn điệu: `0.1004` ($\lambda=0$) $\to$ `0.0977` ($\lambda=0.01$) $\to$ `0.0883` ($\lambda=0.03$) $\to$ `0.0673` ($\lambda=0.10$).
  - Tăng điểm cho bài mới làm tụt hạng các bài báo nền tảng được trích dẫn nhiều.
- **Ablation A3 — Độ nhạy hằng số RRF $k \in \{30, 60, 100\}$ (`CLM-006`):**
  - SciFact `nDCG@10`: `0.7224` / `0.7204` / `0.7202` — hầu như bất biến.
- **Phân rã bậc đồ thị (Robustness R2):**
  - Ở nhóm bài đích bậc thấp (`low_deg`, $n=27$), PPR nhỉnh hơn nhẹ Global PR (`0.0680` vs `0.0642`), nhưng thua ở nhóm bậc cao (`high_deg`, $n=28$: `0.3881` vs `0.4226`).

---

## Slide 8 — Phân tích 24 Ca Lỗi Điển hình (`SG-030`) (9:15 – 10:30)
- **3 nhóm nguyên nhân lỗi chính từ 24 Error Packets (`docs/ERROR_ANALYSIS.md`):**
  1. *Đa nghĩa từ vựng (Lexical Polysemy):* BM25 bắt trúng từ chung (`"cell"`, `"treatment"`, `"network"`) nhưng sai ngữ cảnh sinh học/mạng máy tính.
  2. *Rớt ứng viên từ vòng 1 (`Candidate Pool Miss`):* Bài báo trích dẫn thực tế dùng thuật ngữ thế hệ cũ nên rớt khỏi top-100 văn bản (`C100`), khiến tầng đồ thị không bao giờ nhìn thấy.
  3. *Nút cô lập trong đồ thị cắt theo thời gian:* Bài báo đích mới xuất bản sát mốc cắt chưa kịp tích lũy cạnh vào (`in-degree = 0`).

---

## Slide 9 — Track C: Truy vấn Tiếng Việt Xuyên ngữ (`SG-031`..`SG-034`) (10:30 – 11:30)
- **Thiết kế chống thiên lệch:**
  - `30` truy vấn tiếng Việt thực tế (10 dev / 20 test) chia theo 10 nhóm chủ đề.
  - 3 phương pháp tạo pool top-10: `translated_bm25` (dịch bằng `Helsinki-NLP/opus-mt-vi-en`), `multilingual_dense` (`intfloat/multilingual-e5-base`), và `vn_hybrid_rrf`.
  - Pool mù `662` cặp (`219` dev / `443` test) xóa sạch tên phương pháp và điểm số (`vn_pool.json`).
- **Trạng thái hiện tại (`CLM-008`):** Đang chờ 2 thành viên hoàn tất gán nhãn độc lập (`SG-033`) trước khi chạy `scripts/run_vn_eval.py` để khóa cấu hình trên dev và chấm test 1 lần (`SG-034`).

---

## Slide 10 — Hồ sơ Hiệu năng Thực tế & Chi phí Hệ thống (`SG-040`) (11:30 – 12:45)
- **Môi trường đo:** CPU Intel 12 luồng, RAM cục bộ, không dùng GPU (`performance.json`).
- **Bộ nhớ & Khởi động lạnh:** Peak RSS tiến trình lạnh `895.0 MB`; nạp stack độc lập `~14.6s` (`/health` live sau `~28.2s`).
- **Độ trễ Warm Per-Query so với ngân sách mục tiêu `500ms`:**
  - **SciFact (`5.183` bài):** Đạt mục tiêu (`BM25 P95 = 40.2ms`, `Hybrid P95 = 41.5ms`).
  - **SCIDOCS (`25.657` bài):** `Dense search P95 = 9.1ms`, nhưng `BM25 P95 = 1510.9ms` (vượt 500ms do danh sách đảo Python thuần).
  - **Track B (`C100 + PPR`):** Trung bình `1683.5ms` (`P95 = 2380.4ms` — vượt ngân sách 500ms, báo cáo trung thực).

---

## Slide 11 — Đóng gói Tái lập, Kiểm thử Phá hủy & Minh bạch AI (`SG-041`..`SG-052`) (12:45 – 14:00)
- **Tái lập một lệnh:**
  - `requirements.lock` (80 gói khóa cứng), `python scripts/verify_release.py` (kiểm 33 SHA-256), `scripts/run_demo.ps1` (13/13 kiểm tra offline PASS).
- **746 kiểm thử tự động (`pytest`):**
  - Bao gồm kiểm thử phá hủy chống nuốt lỗi ngầm (`exit 1` khi thiếu dữ liệu/split/nhãn) và cô lập tuyệt đối dữ liệu đã freeze (`SG-052`).
- **Minh bạch AI:** Công khai rõ phần code/audit do AI hỗ trợ và các cổng bắt buộc do hai thành viên con người thực hiện (`H-1`, `H-2`, `H-3`).

---

## Slide 12 — Tổng kết & Kịch bản Demo 5 Phút (14:00 – 20:00)
- **3 bài học cốt lõi:**
  1. Dense (`BGE-base`) vượt xa BM25 trên văn bản khoa học, nhưng ghép RRF không trọng số với BM25 yếu hơn sẽ làm giảm `nDCG@10`.
  2. Trên đồ thị trích dẫn thưa cắt theo thời gian, Seeded PPR trên `C100` bị giới hạn bởi `Recall@100 = 0.2325` và không vượt Global PageRank.
  3. Cộng điểm ưu tiên bài mới ($\lambda > 0$) đánh đổi trực tiếp với việc làm tụt hạng các bài báo nền tảng.
- **Chuyển sang Demo trực tiếp (5 phút theo [DEMO_SCRIPT.md](../docs/DEMO_SCRIPT.md)):**
  1. Truy vấn tiếng Anh trên SciFact (`Dense` vs `Hybrid`).
  2. Truy vấn tiếng Việt không trùng từ khóa tiếng Anh $\to$ quan sát nhãn trung thực `hybrid+fallback-dense-only`.
  3. Khám phá đồ thị trích dẫn lân cận (`SG-037`) và xuất trích dẫn BibTeX/JSON khi ngắt mạng (`SG-038`).
  - *Phương án dự phòng mất sự cố máy:* Mở trực tiếp các báo cáo tĩnh `artifacts/reports/offline_smoke.md`, `ui_smoke.md`, `graph_ui_smoke.md` và chạy `python scripts/export_references.py` trên CLI.
