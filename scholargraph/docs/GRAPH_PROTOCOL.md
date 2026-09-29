# Graph Protocol — holdout, cutoff và masking cho thí nghiệm citation (Tuyến B)

- **Task:** SG-014 — Graph feasibility gate. Phiên bản: 1.0.0; ngày: 2026-09-16.
- **Trạng thái:** hợp đồng thiết kế cho `openalex-citation-holdout-v1`; số liệu gate nằm ở [artifacts/reports/graph_feasibility.json](../artifacts/reports/graph_feasibility.json) và [ADR-016](../management/DECISIONS.md).
- **Tính nhất quán:** tài liệu này chuyên mục hóa Phần 4 (B1–B3) của [RESEARCH_PROTOCOL.md](RESEARCH_PROTOCOL.md) và khối `tracks.B` của [configs/protocol_v1.json](../configs/protocol_v1.json) (seed split `20260915`, `heldout_fraction=0.2`, `mask_scope=[all_dev_heldout_edges, all_test_heldout_edges, reverse_counterparts]`). Không thay đổi bất kỳ ngưỡng hay công thức nào; chỉ làm rõ định nghĩa để SG-016 cài đặt và kiểm thử.
- **Ranh giờ chống rò rỉ (Protocol v1 §2):** module đo đạc (`src/scholargraph/graph/feasibility.py`) **không đọc qrels, nhãn hay held-out edge list nào**; chỉ builder/auditor tin cậy của SG-016 được đọc nhãn để tạo/mask/audit split. Cạnh graph chỉ đến từ `referenced_works` (OpenAlex).

---

## 1. Định nghĩa node và cạnh

1. **Canonical ID:** mọi OpenAlex work ID được chuẩn hóa về `openalex:W<digits>` (strip URI, theo manifest snapshot). Snapshot không được có canonical ID trùng; trùng là lỗi fatal (exit 1), không dedup ngầm.
2. **Node hợp lệ của tuyến B:** work có `publication_year` hợp lệ (1900–2100), **không có năm không được dùng** (missing-year bị loại khỏi tuyến B từ đầu, không điền median — Protocol v1 §5.4). Text query của source = title + abstract; source không đủ title/abstract không làm query.
3. **Cạnh trích dẫn:** cạnh có hướng `u→v` khi `v ∈ referenced_works(u)`, với các phép xử lý được đếm và báo cáo 1:1, không bỏ ngầm:
   - **Self-loop** (`v = u`): loại khỏi cạnh (Protocol v1 B2 "khác u"); ghi `self_loop_count` và danh sách work.
   - **Reference entry trùng lặp trong cùng source:** dedup trước khi chia split; ghi `duplicate_reference_entry_count`.
   - **Cạnh ra ngoài snapshot:** không phải cạnh graph; ghi `out_of_snapshot_reference_occurrences`. Không đi node ảo, không tự doạ "expansion ngầm".
   - **Cạnh nghịch (reciprocal):** giữ nguyên tính có hướng trong raw; ghi `reciprocal_edge_pair_count`; bắt buộc mask hai chiều ở mục 4 nếu tồn tại.
4. **Cạnh nội bộ:** cạnh có cả hai đầu trong snapshot. Mọi thống kê graph (degree, component, density, PPR, co-citation, coupling, graph embedding) **chỉ được tính trên cạnh nội bộ đã mask** (mục 4).

## 2. Holdout (observed vs held-out)

Áp nguyên quy tắc Protocol v1 B2, pin seed để tái lập:

1. Với source `u`, tập tham chiếu `R(u)` = các reference nội bộ hợp lệ, đã loại self, đã dedup, thỏa `year(v) ≤ year(u)` và `year(v)` đã biết.
2. Sắp `R(u)` tăng dần theo `SHA-256` của chuỗi UTF-8 `20260915|u|v` (ID chuẩn); bằng hash thì phá hòa theo target ID tăng dần (Unicode code points).
3. `h = min(|R(u)| − 1, max(1, ceil(0.2·|R(u)|)))`. `H(u)` = `h` reference đầu của thứ tự trên; `O(u) = R(u) \ H(u)`.
4. Đây là **một** split deterministic duy nhất; cấm chạy nhiều seed/variant rồi chọn split đẹp (Protocol v1 §6.2 "core deterministic").
5. `H` của **cả dev và test** là qrels binary nhị phân; chỉ evaluator/auditor đọc. Ranker/indexer/feature builder chỉ nhận `O(u)`. Không dùng `H` để lọc ứng viên, chọn query hay tạo seed (Protocol v1 B2/B3).
6. Query selection: cap 100 dev / 200 test bằng thứ tự `SHA-256(seed|canonical_source_id)`; source phải còn ≥100 novel eligible candidates trong universe (B1). Floors 30 dev / 50 test / ≥2 eligible references là ngưỡng định trước; **cấm hạ floor sau khi xem kết quả**.

## 3. Time cutoff

1. Năm tham chiếu là **năm xuất bản của source** `year(u)`, không phải năm chạy máy.
2. Với query năm `y`: mọi graph feature được tính trên **induced graph** của node có `year ≤ y` (sau masking mục 4). Cạnh hay đường đi qua paper có `year > y` (tương lai) phải bị loại trước khi tính; cache/score gắn cặp `(graph_hash, cutoff_year)`.
3. `test_year` là năm hoàn tất mới nhất **trước năm snapshot** có ≥50 eligible source; `dev_year` là năm gần nhất trước `test_year` có ≥30 eligible source (khả dụng trước, không dùng score — Protocol v1 B1). Năm hiện tại chưa kết thúc không được chọn làm test/dev year.
4. Hạn chế công bố: lọc năm trên snapshot chỉ cho phép "publication-year-constrained retrospective experiment"; không tuyên bố strict historical simulation (metadata/references có thể được OpenAlex cập nhật sau năm xuất bản; cùng năm chưa có thứ tự thời gian).

## 4. Masking — chống leakage hai chiều

Citation graph có hướng, nhưng PPR theo Protocol v1 §5.3 truyền theo `Pᵀ` (đi ngược cạnh), degree/co-citation/coupling là đặc tính vô hướng, nên **xóa một chiều là chưa đủ**. Quy tắc bắt buộc cho SG-016:

1. **Tập cạnh bị mask:** `M = H_dev ∪ H_test ∪ {cạnh đảo (v,u) : (u,v) ∈ H_dev ∪ H_test}` — đúng `mask_scope` trong `configs/protocol_v1.json` (`all_dev_heldout_edges`, `all_test_heldout_edges`, `reverse_counterparts`).
2. **Masked graph** `G_mask = (V, E_O ∖ M)` với `E_O` là cạnh nội bộ sinh từ observed references. `M` và `E_O` rời nhau theo cấu tạo, nhưng audit vẫn phải kiểm chứng: `(u,v) ∈ M ⇒ (u,v) ∉ E(G_mask)` **và** `(v,u) ∉ E(G_mask)` cho mọi cặp — kể cả khi input raw có cạnh reciprocal mà pruning trước đó để sót.
3. **Không dùng cạnh test trong adjacency cho PPR:** seed PPR, ma trận chuyển tiếp `P`, dangling vector và mọi số vòng lặp PageRank/PPR phải được tính **trên `G_mask` đúng cutoff** (mục 3.2). Tính PageRank trên graph đầy đủ rồi xóa cạnh sau là vi phạm protocol (Protocol v1 §10: "Xóa sau khi đã tính PageRank không đủ: mọi feature phải được tính lại từ graph đã mask").
4. **Feature suy ra cũng phải mask:** degree, cited_by proxy nội bộ, co-citation, bibliographic coupling, graph embedding — bất kỳ thứ gì dẫn xuất từ adjacency — được recompute từ `G_mask`. Không dùng `cited_by_count` hiện tại của OpenAlex làm feature (Protocol v1 B2).
5. **Kiểm tra rò rỉ hai chiều tại SG-016 (bắt buộc, có test phá hủy):**
   - assert tập cạnh của adjacency đã export không giao `M` theo **cả hai chiều**;
   - reverse-augmentation (nếu có ở variant nào) phải được dựng từ `G_mask` sau masking, không từ raw;
   - mỗi graph artifact lưu `graph_hash = SHA-256(edge list canonical của G_mask)` + `mask_hash = SHA-256(M)` + cutoff; run không khớp hash thì từ chối dùng cache;
   - nhị phân hoá: một cạnh xuất hiện ở `O(u)` của một query nhưng thuộc `H(v)` của query khác thì **vẫn phải bị mask trong cả hai vai trò** (mask scope là toàn cục `H_dev ∪ H_test`, không per-query).
6. **Universe ứng viên:** `U(u)` = mọi canonical node có `year ≤ year(u)`, trừ self/canonical duplicate và `O(u)`; `H` không tham gia lọc (B2). Known references (`O(u)`) bị loại khỏi output mọi baseline trước top-k.

## 5. Quy trình gate và điều kiện mở thí nghiệm

1. **Gate này chặn trước khi tải/thí nghiệm:** chạy CLI `python -m scholargraph.graph.feasibility` (hoặc script tương đương) trên snapshot đóng băng; báo cáo ghi `decision.overall ∈ {GO, NO_GO}` kèm bằng chứng từng tiêu chí.
2. **Nguyên tắc NO-GO:** NO-GO là kết quả đo được (exit 0), không phải run failure; chỉ lỗi tài nguyên/dữ liệu fatal (thiếu file, JSON hỏng, ID trùng, manifest lệch hash, thiếu floor trong config) mới exit 1 với status FAIL và **không đo đạc nào được thay bằng 0** (ADR-013/014).
3. **Cấm tự cứu:** nếu NO-GO thì không hạ floor, không đổi metric, không tự thay nhãn/nguồn khác. Điều chỉnh phạm vi phải qua ADR và cập nhật scope/dependency chính thức (SG-014 → coordinator áp lên board).
4. **Yêu cầu với snapshot kế tiếp (SG-015)** khi gate NO-GO trên pilot:
   - đổi chiến lược sampling sang snapshot có kết nối trích dẫn thật (ví dụ expansion qua `referenced_works`/`cited_by` quanh seed, hoặc cohort venue/năm có mật độ trích dẫn nội bộ cao), pin manifest (filter, seed, sha256, thời điểm) trước khi tải;
   - giữ nguyên toàn bộ floor của `tracks.B.graph_gate`;
   - chạy lại CLI gate này trên snapshot core; `overall=GO` mới được SG-016 dựng masked split;
   - xử lý dị thường raw đúng mục 1 (self-loop/dedup/reciprocal đếm và báo, không bỏ ngầm).
5. **BEIR enrichment:** bị loại khỏi tuyến B — SciFact không có trường reference; SCIDOCS có `metadata.references` nhưng query của nó không phải node trong corpus, qrels của SCIDOCS là dẫn xuất citation (dùng cạnh đó làm graph sẽ trùng cấu trúc với nhãn test — rò rỉ trực tiếp), và Tuyến A cấm thêm metadata/citation. Số đo SCIDOCS chỉ được ghi nhận làm bằng chứng timebox, không dùng làm graph.

## 6. Kiểm chứng và bằng chứng

- Mỗi lần áp protocol này tại SG-016 phải có: mask/audit report, `graph_hash`, `mask_hash`, danh sách query ID đã chọn theo seed, split hash, và các test negative (thiếu file → exit 1; cạnh heldout xuất hiện trong adjacency (cả chiều đảo) → FAIL; feature cũ chưa recompute → FAIL).
- Báo cáo gate (graph_feasibility.json) truy ngược được: sha256 toàn bộ input, lệnh chạy, thời điểm đo, phiên bản module. Mọi con số trong log/report phải khớp 1:1 với biến đếm trong báo cáo máy đọc.
