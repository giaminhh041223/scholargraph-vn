# Bộ 18 Câu hỏi & Trả lời Phản biện Bảo vệ Đồ án — `DEFENSE_QA` (SG-044)

> **Mục đích:** Trang bị cho cả hai thành viên khả năng giải thích độc lập mọi quyết định thiết kế, công thức toán học, luồng dữ liệu (input/output/assumption/error) của từng module và lý giải trung thực các **kết quả âm** dựa trên [evidence_index.json](../artifacts/reports/evidence_index.json) và [final_report.md](../reports/final_report.md).

---

## Nhóm A — Giao thức Thực nghiệm, Chống Rò rỉ và Đóng băng (`SG-008`, `SG-016`, `SG-027`)

### Câu 1: Làm thế nào nhóm đảm bảo không có rò rỉ dữ liệu (data leakage) khi đánh giá dự đoán trích dẫn trên đồ thị OpenAlex (Track B)?
- **Trả lời:**
  1. **Cắt theo thời gian (Temporal Split):** 100 bài truy vấn dev thuộc năm 2024 và 200 bài truy vấn test thuộc năm 2025; ứng viên của mỗi truy vấn chỉ gồm bài có năm không lớn hơn năm bài truy vấn.
  2. **Ẩn cạnh đích (`Held-out Edges`):** Với mỗi bài truy vấn, khoảng 20% tham chiếu (ít nhất 1, chọn tất định theo băm với seed `20260915`) được tách làm nhãn kiểm tra; tổng cộng 330 cạnh. Các cạnh này và cạnh ngược tương ứng bị xóa khỏi đồ thị trước khi tính Global PageRank hay Personalized PageRank (`src/scholargraph/graph/build.py`); đồ thị còn 26.186 trong 26.516 cạnh.
  3. **Loại tự khớp và tham chiếu đã biết:** Kết quả trùng chính bài truy vấn (`self-match`) và các tham chiếu đã quan sát bị loại khỏi ứng viên, kiểm tra tại ranh giới đánh giá (`ProtocolEvaluator` trong `src/scholargraph/evaluation/metrics.py`).
  4. **Bằng chứng kiểm toán:** `artifacts/reports/graph_audit.json` (`PASS`, 15 kiểm tra) ghi nhận `0` cạnh giữ lại còn sót trong đồ thị đã che ở cả hai chiều.

### Câu 2: Vì sao có sự chênh lệch giữa tổng số nút đồ thị OpenAlex (`18.251` bài) và số bài trong chỉ mục văn bản `openalex_core_text` (`18.250` bài)?
- **Trả lời:** Bài báo `openalex:W126924136` trong dữ liệu gốc khuyết hoàn toàn cả `title` lẫn `abstract` (chuỗi văn bản rỗng). Theo nguyên tắc chống nuốt lỗi ngầm và quyết định kiến trúc `ADR-017`, hệ thống không tạo vector giả cho văn bản rỗng mà loại trừ tường minh bài này khỏi không gian truy hồi văn bản (`18.250` bài), đồng thời ghi nhận rõ ID `openalex:W126924136` trong `data/manifests/openalex_core_text.json` và `artifacts/reports/encoding_profile.json`.

### Câu 3: Thế nào là "đóng băng trước khi mở tập test" (`Main Freeze SG-027`) và làm sao chứng minh nhóm không tinh chỉnh siêu tham số trên tập test?
- **Trả lời:**
  - Trước khi chạy bất kỳ đánh giá nào trên tập `test`, tệp [frozen_main.json](../configs/frozen_main.json) (`sha256 = 34159fb133594633530c08390b259ea6efd7e024a384cb2c25092bf6e4797557`) được tạo tại commit `e959f68`, khóa cứng SHA-256 của 33 tệp dữ liệu, chia tập, chỉ mục và cấu hình.
  - Siêu tham số Track B ($\gamma = 0.3, \lambda = 0.0$) được chọn duy nhất từ lưới 20 cấu hình trên tập `dev` (`artifacts/reports/b_dev_trials.json`).
  - Mọi lần chạy tập `test` đều đi qua cổng niêm phong `src/scholargraph/evaluation/sealed.py`, sinh biên bản `artifacts/final_test/freeze_*.json` lưu chính xác mã băm `34159fb1...7557` và mỗi phương pháp chỉ có đúng 1 thư mục run test trong `artifacts/runs/`.

### Câu 4: Khi merge từ nhánh làm việc sang kho chính trên Windows, làm thế nào bảo toàn chính xác từng byte (SHA-256) của 33 tệp đã đóng băng?
- **Trả lời:** Nếu Git tự động chuyển đổi ký tự xuống dòng `LF` $\leftrightarrow$ `CRLF` (`core.autocrlf`), mã băm SHA-256 của các tệp JSON/JSONL sẽ thay đổi dù nội dung logic giống nhau. Nhóm đã khóa `.gitattributes` với quy tắc `* -text` và chuẩn hóa chỉ mục (`ADR-019`, `SG-051`), sau đó xác minh bằng `python scripts/verify_release.py` đạt `PASS` trên cả 33 tệp.

---

## Nhóm B — Truy hồi Văn bản và Hợp nhất RRF (`SG-017`..`SG-021`, `SG-028`)

### Câu 5: Sự khác biệt cốt lõi giữa TF-IDF và BM25 trong `src/scholargraph/retrieval/` là gì?
- **Trả lời:**
  - **TF-IDF** (`tfidf.py`) tăng tuyến tính (hoặc dưới tuyến tính nhẹ) theo tần suất từ $tf$ và chuẩn hóa độ dài bằng tích vô hướng cosine vector.
  - **BM25** (`bm25.py`) bổ sung hai cơ chế quan trọng: (1) **Bão hòa tần suất từ (Term Frequency Saturation)** điều khiển bởi $k_1 = 1.5$ ($\frac{tf \cdot (k_1 + 1)}{tf + k_1 \cdot (1 - b + b \cdot |d|/\text{avgdl})}$) giúp một từ lặp lại 10 lần trong abstract không áp đảo các từ khóa khác; và (2) **Chuẩn hóa độ dài tài liệu linh hoạt** qua $b = 0.75$. Nhờ đó trên SciFact test, BM25 đạt `nDCG@10 = 0.6647`, cao hơn TF-IDF (`0.6327`).

### Câu 6: Vì sao nhóm dùng Reciprocal Rank Fusion (RRF) thay vì cộng trực tiếp điểm BM25 và điểm Cosine của Dense?
- **Trả lời:** Điểm BM25 không bị chặn trên (thường nằm trong khoảng $[0, 30+]$ tùy độ dài truy vấn và độ hiếm IDF), trong khi điểm tích vô hướng của vector chuẩn hóa $L_2$ từ `bge-base-en-v1.5` nằm trong $[-1, 1]$ (thường tập trung hẹp quanh $[0.55, 0.85]$). Cộng trực tiếp raw score sẽ khiến BM25 hoàn toàn lấn át Dense; còn chuẩn hóa min-max trên top-k lại rất nhạy cảm với một điểm ngoại lai (outlier). RRF chỉ dùng thứ hạng $r(d) \in \{1, 2, \dots\}$ thông qua $\sum \frac{1}{k + r(d)}$ ($k=60$), nên bất biến với phép biến đổi đơn điệu của thang điểm.

### Câu 7: Tại sao trên cả SciFact và SCIDOCS, kết quả thực nghiệm lại cho thấy Hybrid RRF ($k=60$) đạt `nDCG@10` thấp hơn Dense đơn lẻ (`CLM-003`)?
- **Trả lời:**
  - Số liệu thực tế: Trên SciFact test, Dense đạt `0.7404` còn Hybrid đạt `0.7204` ($\Delta = -0.0200$, 95% CI `[-0.0469, +0.0066]`). Trên SCIDOCS test, Dense đạt `0.2172` còn Hybrid đạt `0.1976` ($\Delta = -0.0197$, 95% CI `[-0.0273, -0.0122]`).
  - Tuy nhiên, trên SciFact, `Recall@100` của Hybrid (`0.9693`) vẫn cao hơn cả Dense (`0.9667`) và BM25 (`0.8892`).
  - **Giải thích cơ chế (giả thuyết, chưa có phép đo riêng):** RRF với trọng số bằng nhau rất tốt để **mở rộng độ phủ ứng viên ở độ sâu 100** (`Recall@100`), nhưng ở **top-10 (`nDCG@10`)**, khi bộ truy hồi từ vựng (BM25: `0.6647` / `0.1521`) yếu hơn quá xa so với bộ truy hồi ngữ nghĩa (Dense: `0.7404` / `0.2172`), các tài liệu nhiễu đứng hạng 1–2 của BM25 nhận điểm RRF cao và chen vào top-5, đẩy các tài liệu đúng ngữ nghĩa ở hạng 4–8 của Dense xuống dưới.

### Câu 8: Điều gì xảy ra khi người dùng nhập truy vấn tiếng Việt vào API ở chế độ `hybrid` nhưng BM25 không khớp được từ tiếng Anh nào?
- **Trả lời:**
  - Ở tầng đánh giá nghiên cứu (`hybrid.py`), `rrf_fuse` nghiêm cấm đầu vào rỗng để bắt lỗi đường ống.
  - Ở tầng phục vụ ứng dụng (`src/scholargraph/api/service.py`, commit `dcca385`), nếu một trong hai nhánh (BM25 hoặc Dense) trả về danh sách rỗng, dịch vụ không trả lỗi HTTP 500 và cũng **không giả vờ đã chạy hybrid đầy đủ**, mà chuyển về nhánh còn lại kèm nhãn phương pháp có hậu tố minh bạch: `+fallback-dense-only` (hoặc `+fallback-lexical-only`). Nếu cả hai cùng rỗng, trả về danh sách rỗng `200 OK` với hậu tố `+both-sides-empty`. Cả 3 nhánh đều được kiểm thử trong `tests/integration/test_api.py`.

---

## Nhóm C — Đồ thị Trích dẫn, Personalized PageRank và Điều chỉnh Tuổi (`SG-022`..`SG-025`, `SG-029`)

### Câu 9: Giải thích cơ chế hoạt động của Personalized PageRank (PPR) khởi tạo từ văn bản (`src/scholargraph/graph/ppr.py`) trên một đồ thị nhỏ 4–5 nút.
- **Trả lời:**
  - Giả sử đồ thị có 4 bài báo $A, B, C, D$ với cạnh trích dẫn $A \to C, B \to C, C \to D$.
  - Ở **Global PageRank**, ở mỗi bước nhảy ngẫu nhiên (với xác suất $1 - \alpha = 0.15$), người đi bộ ngẫu nhiên dịch chuyển tức thời (teleport) đều tới mọi nút với xác suất $1/4$.
  - Ở **Seeded PPR**, vector dịch chuyển $\mathbf{v}_q$ chỉ tập trung trọng số dương (chuẩn hóa tổng bằng 1) vào các bài báo hạt giống có điểm tương đồng văn bản cao nhất với truy vấn $q$ (ví dụ $A$ và $B$). Khi lặp công thức $\mathbf{p}^{(t+1)} = \alpha P^\top \mathbf{p}^{(t)} + (1-\alpha)\mathbf{v}_q$, xác suất sẽ chảy từ hạt giống $A, B$ sang bài $C$ (được cả $A$ và $B$ trích dẫn theo chủ đề của truy vấn $q$) mạnh hơn nhiều so với một bài nổi tiếng ở chủ đề khác.

### Câu 10: Vì sao trên Track B OpenAlex (`test200`), Seeded PPR (`nDCG@10 = 0.1004`) lại không vượt được đối chứng Global PageRank (`0.1082`, 95% CI chứa 0 — `CLM-004`)?
- **Trả lời:** Một điều đã đo và hai cách giải thích chưa kiểm chứng:
  1. **Đã đo — nút cổ chai từ tập ứng viên `C100`:** Cả PPR và Global PageRank chỉ tái xếp hạng trên cùng 100 ứng viên đầu do văn bản lấy ra; `Recall@100` trung bình chỉ `0.2325`, nên phần lớn bài được trích dẫn thật đã mất trước khi bước đồ thị chạy.
  2. **Giả thuyết — đồ thị thưa ở biên thời gian:** bài đích có ít hoặc không có cạnh vào trong đồ thị đã che. Hiện chưa có số đo về bậc vào của bài đích; không nêu con số khi trả lời.
  3. **Giả thuyết — nhiễu hạt giống (Seed Noise):** top-k văn bản của bài truy vấn mới có nhiều bài nhiễu; PPR khuếch đại lân cận của các hạt giống này, trong khi Global PageRank ưu tiên ổn định các bài có uy tín toàn cục.
  - **Phân tích thăm dò theo bậc của bài truy vấn** (`robustness.json`, không có CI): nhóm bậc thấp ($n=121$) PPR `0.0807`, Global PageRank `0.0902`; nhóm bậc cao ($n=36$) PPR `0.1276`, Global PageRank `0.1252`. Số liệu này không cho thấy PPR có lợi thế ở nhóm bậc thấp.

### Câu 11: Tại sao việc tăng hệ số suy giảm theo tuổi ($\lambda \in \{0.01, 0.03, 0.10\}$) trong Ablation A1 lại làm giảm đơn điệu `nDCG@10` (`CLM-005`)?
- **Trả lời:**
  - Sau khi trộn điểm văn bản và đồ thị, điểm được nhân với $\exp(-\lambda \cdot \max(0, \text{year}(q) - \text{year}(d)))$. Mốc là năm xuất bản của bài truy vấn, không phải năm hiện tại: bài cùng năm với bài truy vấn giữ nguyên điểm, bài càng cũ càng bị giảm; $\lambda = 0$ là đối chứng không điều chỉnh.
  - Đã đo: khi tăng $\lambda$ từ $0.0$ lên $0.10$ tại $\gamma = 0.3$, `nDCG@10` của PPR giảm từ `0.1004` xuống `0.0673` và của Global PageRank từ `0.1082` xuống `0.0740`.
  - Cách giải thích (giả thuyết, chưa có phép đo riêng): bài truy vấn trích dẫn nhiều công trình cũ hơn nó, nên hạ điểm bài cũ làm các bài được trích dẫn thật rơi khỏi top-10. Kết luận an toàn: **ưu tiên bài mới không đồng nghĩa với tăng độ liên quan hay sự công bằng (fairness)**.

---

## Nhóm D — Thống kê, Truy vấn Tiếng Việt và Hiệu năng Hệ thống (`SG-030`..`SG-040`)

### Câu 12: Vì sao nhóm dùng khoảng tin cậy Paired Bootstrap 95% ($B = 10.000$) thay vì báo cáo $p$-value của kiểm định $t$-test?
- **Trả lời:**
  1. Phân phối của các chỉ số xếp hạng như `nDCG@10` và `MRR@10` trên từng truy vấn thường lệch mạnh, có nhiều giá trị 0 hoặc 1 (không chuẩn).
  2. Khoảng tin cậy phần trăm paired bootstrap ($B = 10.000$, `seed = 20260915`) lấy mẫu lại có hoàn lại các cặp hiệu số $d_i = m_{\text{treat}}(q_i) - m_{\text{ctrl}}(q_i)$ trên cùng một truy vấn, vừa không đòi hỏi giả định phân phối chuẩn, vừa cho biết đồng thời **biên độ thực tế của hiệu quả** (ví dụ `[+0.0405, +0.1115]`) lẫn việc khoảng tin cậy có chứa 0 hay không, tránh lạm dụng ngưỡng nhị phân $p < 0.05$.

### Câu 13: Tại sao một mô hình nhúng tiếng Anh tốt như `BAAI/bge-base-en-v1.5` không thể dùng trực tiếp cho truy vấn tiếng Việt (Track C)?
- **Trả lời:** Từ điển con (WordPiece/BPE vocabulary) và không gian nhúng của `bge-base-en-v1.5` chỉ được huấn luyện trên văn bản tiếng Anh. Khi đưa câu tiếng Việt có dấu vào, bộ tách từ sẽ băm nhỏ các âm tiết tiếng Việt thành các mảnh ký tự vô nghĩa (`subword fragmentation`), tạo ra vector nằm lệch hoàn toàn khỏi vùng ngữ nghĩa của các bài báo tiếng Anh cùng chủ đề. Do đó, Track C bắt buộc phải so sánh hai hướng tiếp cận xuyên ngữ thực sự: (1) Dịch truy vấn Việt $\to$ Anh bằng `Helsinki-NLP/opus-mt-vi-en` rồi truy hồi (`translated_bm25`), hoặc (2) Dùng bộ mã hóa đa ngữ `intfloat/multilingual-e5-base` (`multilingual_dense`) và hợp nhất RRF của chúng (`vn_hybrid_rrf`).

### Câu 14: Thế nào là thiên lệch đánh giá theo pool (pooled judgment bias) trong `SG-033` và làm sao nhóm giảm thiểu thiên lệch khi hai người gán nhãn?
- **Trả lời:**
  - Khi kho dữ liệu có `18.250` bài báo, con người không thể chấm hết $30 \times 18.250$ cặp mà chỉ chấm tập hợp nhất (pool) top-10 của 3 phương pháp đại diện (`679` cặp duy nhất ở bộ truy vấn v2, `ADR-023`). Các bài báo không lọt vào pool mặc định bị tính độ liên quan bằng 0 khi tính metric (hoặc được theo dõi qua `unjudged_ratio@10`).
  - Để tránh thiên lệch xác nhận (confirmation bias), `scripts/build_vn_pool.py` loại bỏ hoàn toàn tên hệ thống và điểm số khỏi `data/annotations/v2/vn_pool.json` và xáo trộn ngẫu nhiên thứ tự ứng viên với `seed = 20260915`. Hai thành viên chấm hoàn toàn độc lập (`round = independent`), đo hệ số đồng thuận $\kappa$ có trọng số tuyến tính (`scripts/score_vn_agreement.py`) **trước khi** thảo luận phân xử (`round = adjudicated`).

### Câu 15: Trong báo cáo hiệu năng `SG-040`, tại sao một số phương pháp vượt ngân sách `500ms/query` và nhóm xử lý thế nào?
- **Trả lời:**
  - Ngân sách `500ms/query` là mục tiêu đo đạc thực tế, không phải ràng buộc để cắt giảm ngầm chất lượng.
  - Trên SciFact (`5.183` bài), mọi phương pháp đều dưới `500ms` (`Hybrid P95 = 41.5ms`).
  - Trên SCIDOCS (`25.657` bài), tìm kiếm vector `Dense` chỉ mất `P95 = 9.1ms` nhờ phép nhân ma trận NumPy được tối ưu SIMD/BLAS, nhưng `BM25` cài đặt bằng vòng lặp từ điển Python thuần có `P95 = 1510.9ms` ở các truy vấn dài nhiều từ phổ biến.
  - Trên Track B OpenAlex, việc chạy `C100` kèm phép lặp vô hướng `PPR` trên đồ thị mất trung bình `1683.5ms` (`P95 = 2380.4ms`). Cỡ mẫu đo nhỏ: 20 truy vấn SciFact, 10 truy vấn SCIDOCS, 5 truy vấn Track B. Nhóm báo cáo trung thực toàn bộ các con số vượt ngân sách trong `artifacts/reports/performance.md` và Hình 4.

---

## Nhóm E — Chi tiết Module, Kiểm thử Phá hủy và Vận hành Offline (`SG-035`..`SG-052`)

### Câu 16: Hãy nêu rõ Input, Output, Giả định (Assumption) và Chế độ Lỗi (Error Mode) của 4 module cốt lõi trong `src/scholargraph/`.
- **Trả lời:**
  1. **`retrieval/dense.py` (`ExactDenseIndex`):**
     - *Input:* Ma trận nhúng chuẩn hóa $L_2$ kích thước $(N, d)$, danh sách `doc_ids` độ dài $N$, và vector truy vấn chuẩn hóa $(d,)$.
     - *Output:* Danh sách top-$k$ `(doc_id, score)` sắp xếp giảm dần theo tích vô hướng, phá hòa bằng `doc_id` tăng dần.
     - *Giả định:* Vector đầu vào hữu hạn (`isfinite`), chuẩn $L_2 > 0$, kích thước chiều khớp nhau.
     - *Chế độ lỗi:* Ném ngoại lệ ngay lập tức nếu chiều lệch, chứa `NaN`/`Inf` hoặc `doc_ids` trùng lặp.
  2. **`retrieval/hybrid.py` (`rrf_fuse`):**
     - *Input:* Hai danh sách xếp hạng không rỗng (`lexical_ids`, `dense_ids`), hằng số $k > 0$ (mặc định $60$), độ sâu `final_depth`.
     - *Output:* Danh sách từ điển chứa `doc_id`, `rrf_score`, `lexical_rank`, `dense_rank`.
     - *Chế độ lỗi:* Ném `ValueError` nếu một trong hai danh sách rỗng, có ID trùng lặp trong cùng một danh sách, hoặc $k \le 0$.
  3. **`graph/ppr.py` (`build_teleport`, `personalized_pagerank`):**
     - *Input:* Danh sách nút và cạnh ra của đồ thị có hướng (đã che cạnh giữ lại), vector teleport dựng từ tối đa 20 hạt giống `{doc_id, rrf}` có trọng số dương, hệ số cản $\alpha = 0.85$, ngưỡng hội tụ `tol`, số vòng lặp tối đa.
     - *Output:* Bộ ba (`node_id -> ppr_score` chuẩn hóa tổng bằng 1, số vòng lặp, phần dư).
     - *Chế độ lỗi:* Ném `GraphDataError` nếu tập hạt giống rỗng, trùng lặp, nằm ngoài đồ thị đã che hoặc có trọng số không dương/không hữu hạn; nếu $\alpha \notin (0, 1)$; nếu cạnh trỏ tới nút lạ; hoặc nếu không hội tụ trong số vòng lặp cho phép.
  4. **`evaluation/metrics.py` (`ProtocolEvaluator`):**
     - *Input:* Kết quả xếp hạng `runs`, nhãn `qrels`, tập `query_ids` đã khóa, tập `corpus_ids`, tập `eligible_ids`.
     - *Output:* 5 chỉ số (`nDCG@10`, `Recall@100`, `MRR@10`, `MAP@100`, `P@5`) từng truy vấn và trung bình vĩ mô (macro-average), kèm biên bản kiểm toán (`audit`).
     - *Chế độ lỗi:* Ném `ValueError` nếu phát hiện tự khớp (`self-match`), tài liệu ngoài `eligible_ids`, điểm `qrel` ngoài $\{0, 1, 2\}$, hoặc truy vấn nằm ngoài lát cắt đã khóa.

### Câu 17: Thế nào là "Kiểm thử Phá hủy & Chống Lỗi Ngầm" (Anti-Silent-Bypass) đã áp dụng trong dự án?
- **Trả lời:** Hệ thống cấm tuyệt đối việc dùng giá trị mặc định (`.get(..., 0)`) để che giấu tệp thiếu, nhãn `null`, hay cấu hình chưa duyệt. Mọi CLI (`build_openalex_text_subset.py`, `run_final.py`, `score_vn_agreement.py`, `run_vn_eval.py`, `compare_reproduction.py`, `verify_claims.py`) đều được kiểm thử trực tiếp qua `subprocess.run` trong `tmp_path` để xác nhận **mã thoát bằng 1 (`returncode == 1`)** và thông báo `FAIL:` rõ ràng khi dữ liệu đầu vào bị khuyết, sai định dạng hoặc vi phạm ranh giới rò rỉ.

### Câu 18: Nếu tại buổi bảo vệ mất kết nối Internet hoàn toàn, nhóm thực hiện Demo bằng cách nào?
- **Trả lời:** Toàn bộ mô hình (`bge-base-en-v1.5`, `multilingual-e5-base`), chỉ mục `.npy`, dữ liệu văn bản, đồ thị OpenAlex và bộ nhớ đệm dịch máy đều đã được lưu cục bộ trên ổ cứng và kiểm chứng qua `scripts/offline_smoke.py` (`13/13` kiểm tra offline trong `scripts/run_demo.ps1` đạt `DEMO OK`). Nhóm chỉ cần chạy `run_demo.bat` (hoặc `powershell -ExecutionPolicy Bypass -File scripts/run_demo.ps1`) mà không cần mạng Internet.
