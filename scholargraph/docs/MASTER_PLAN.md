# Kế hoạch tổng thể — ScholarGraph VN

Phiên bản 1.2 — 2026-09-15, đã điều chỉnh theo thông tin mới của người dùng. Trạng thái: kế hoạch thực thi, chưa có benchmark đã chạy.

Bổ sung điều phối 2026-09-15: [model cho từng ID](TASK_MODEL_MATRIX.md) và [chiến lược chat/context](MODEL_AND_CHAT_STRATEGY.md). Không thay thời hạn, dependency hoặc phạm vi core.

## 1. Mục tiêu và giả định

Xây một hệ thống giúp sinh viên tìm tài liệu khoa học và khám phá các bài liên quan bằng nội dung và mạng trích dẫn. Đầu ra học thuật là so sánh tái lập được giữa lexical retrieval, dense retrieval, hybrid retrieval và graph reranking.

Thông tin đã xác nhận và giả định còn lại:
- 2 người, còn khoảng 7 tuần; agent hỗ trợ code, kiểm thử, phân tích. Dự trù 12–15 giờ/người/tuần, tổng 168–210 giờ-người; phần vượt sức được cắt theo thứ tự ở mục 10.
- Mục tiêu vận hành được chốt sau review SG-001: hoàn tất trước 2026-10-31; tháng 11 là vùng đệm đến 2026-11-30 để sửa lỗi/thay đổi rubric/tái lập/luyện bảo vệ. Đây không phải deadline chính thức của môn.
- Hai bạn chịu trách nhiệm hiểu phương pháp, xác nhận nhãn và diễn giải kết quả. Agent không thay thế trách nhiệm học thuật hoặc người gán nhãn độc lập.
- GPU hiện có: Kaggle/Colab; có thể cân nhắc thuê sau pilot nếu cần. Windows dùng môi trường Python riêng. GPU chủ yếu cho encoding; core không yêu cầu fine-tune.
- Hướng nội dung demo ban đầu: Information Retrieval, NLP, Graph Learning.
- Pilot OpenAlex 1.000–3.000 paper; mục tiêu core 10.000–20.000, chỉ mở rộng 30.000–50.000 khi ingestion/graph/benchmark đã ổn định.
- VN là người dùng/giao diện tiếng Việt và một đánh giá truy vấn Việt → tài liệu Anh. Chưa giả định corpus bài báo tiếng Việt.
- Bộ VN core khoảng 30 query (10 dev/20 test), pool gọn với hai người chấm; chỉ tăng lên 50 khi pilot còn thời gian. Core hiện dự trù 142 giờ-người, còn 26–68 giờ trong tổng dự trù để xử lý phát sinh/điều phối.
- Đã biết thời lượng 7 tuần và số người; còn thiếu ngày nộp chính xác, rubric, quy định dùng AI/pretrained và phần cứng local. SG-001/SG-002 sẽ ghi hoặc cập nhật các điểm này.

Điểm A+ là mục tiêu chất lượng; không có metric hoặc mức tăng nào tự bảo đảm điểm môn học.

## 2. Yêu cầu sản phẩm

| ID | Yêu cầu | Điều kiện nghiệm thu |
|---|---|---|
| FR-01 | Tìm kiếm bằng từ khóa/câu hỏi | Top-k có paper ID, title, snippet, nguồn và điểm; không có ID giả |
| FR-02 | Gợi ý từ một paper | Loại chính paper đầu vào; giải thích liên hệ nội dung/citation |
| FR-03 | Lọc theo năm/chủ đề/OA | Kết quả và thứ hạng tuân thủ filter; missing metadata có quy tắc |
| FR-04 | Khám phá mạng trích dẫn | Phân biệt cited/citing; giới hạn số node và dẫn về nguồn |
| FR-05 | Giải thích kết quả | Tách text relevance, graph signal; thông báo khi graph không có dữ liệu |
| FR-06 | Hỗ trợ truy vấn tiếng Việt | Có baseline và test người gán nhãn riêng, công bố phạm vi |
| FR-07 | Demo offline | Search/recommend trên snapshot, có ngày cập nhật và nguồn |
| FR-08 | Xuất danh sách tham khảo | ID/DOI chính xác, không bịa tác giả hoặc metadata thiếu |
| NFR-01 | Tái lập | Lệnh chạy có config, environment, checksum, run files |
| NFR-02 | Hiệu năng | Đo P50/P95, RAM, index size trên phần cứng và corpus đã ghi rõ |
| NFR-03 | Khôi phục công việc | Task board, state, handoff, session log nhất quán |
| NFR-04 | Minh bạch | Demo, dev, test và external-data experiment được nhận diện rõ |

Mốc hiệu năng đề xuất: P95 local search dưới 500 ms với index đã nạp. Đây là mục tiêu kiểm tra ở SG-040, không phải kết quả đã đạt; phải bao gồm query encoding, retrieval và rerank. Báo cold-start riêng.

## 3. Yêu cầu học thuật và liên hệ môn học

| Nội dung môn trong workspace | Thành phần dự án | Bằng chứng nộp |
|---|---|---|
| L02 Machine Learning | Dense representation; optional learning-to-rank | Baselines, model card, kiểm tra overlap |
| L03 Data Visualization | Citation graph và bảng so sánh | Demo và hình có nguồn |
| L04 Information Retrieval | TF-IDF, BM25, dense, hybrid | Run files + nDCG/Recall/MRR |
| L05 Link Analysis | PageRank, PPR, xử lý đồ thị | Graph audit + ablation |
| L07 Information Extraction | Chuẩn hóa metadata, DOI/ID mapping | Data quality report |
| L08 Recommendation | Paper-to-paper retrieval | Đánh giá recommendation riêng |
| L09 Query Mining | Phân tích query và lỗi truy xuất | Query buckets/error analysis |

Đây là mapping theo tên các tài liệu môn đã thấy, không thay cho rubric chính thức.

Câu hỏi nghiên cứu:
- RQ1: Hybrid có cải thiện thứ hạng và khả năng tìm đủ bài so với BM25/dense riêng?
- RQ2: Trên graph protocol có kiểm soát nhãn, PPR bổ sung giá trị gì ngoài nội dung?
- RQ3: Điều chỉnh theo tuổi bài tạo đánh đổi relevance–exposure như thế nào?
- RQ4: Truy vấn Việt → bài Anh giảm chất lượng bao nhiêu và cách xử lý nào hiệu quả?

## 4. Phạm vi cam kết

**Core:** data ingestion; hai BEIR text benchmarks; OpenAlex pilot/snapshot; graph feasibility gate; các baseline; một graph experiment có giao thức sạch; web demo; đánh giá Việt nhỏ; báo cáo và tái lập.

**Stretch:** cross-encoder, fine-tuning, thêm SciRepEval task, TREC-COVID. Chỉ làm sau khi phần cốt lõi ổn định và có thời gian.

Chưa nằm trong phạm vi: chạy toàn bộ OpenAlex/OGBL-Citation2, train LLM từ đầu, mạng xã hội nghiên cứu, collaborative filtering khi chưa có user history, hệ thống viết toàn bộ literature review, tích hợp thanh toán hoặc triển khai public.

## 5. Thời gian và mốc

| Mốc | Tuần dự kiến | Task | Đầu ra cần kiểm tra |
|---|---|---|---|
| M0 — Hồ sơ điều phối | Trước triển khai | SG-000 | Plan, rules, task board, handoff, log |
| M1 — Phạm vi và môi trường | 1 | SG-001…SG-008 | Research spec, environment, metric checker |
| M2 — Dữ liệu và feasibility | 1–2 | SG-009…SG-016 | Benchmark hợp lệ, OpenAlex pilot, graph go/no-go |
| M3 — Retrieval baseline | 2–3 | SG-017…SG-021 | BM25, dense, RRF, candidate recall |
| M4 — Graph experiment | 3–4 | SG-022…SG-027 | Graph methods, dev results, frozen configs |
| M5 — VN và web demo | 4–5 | SG-031…SG-039 | Human labels, search/recommend UI offline |
| M6 — Kết quả và hiệu năng | 5–6 | SG-028…SG-030, SG-034, SG-040 | Tables, CI, ablation, errors, latency |
| M7 — Đóng gói và bảo vệ | 6–7 | SG-041…SG-045 | Reproduction audit, report, slides, release |
| M8 — Mở rộng tùy nguồn lực | Sau core | SG-046…SG-049 | Thí nghiệm bổ sung riêng |

Các tuần giao nhau vì hai người và agent chia phần độc lập; thứ tự thực tế theo dependency trong task board. Giờ từng task là thời gian con người cần đầu tư với agent hỗ trợ, gồm đọc/review/chạy/xác minh; không phải thời gian tác vụ nền hay một cam kết tốc độ agent.

## 6. Phân vai dự kiến

- Người 1: Research/Evaluation + Coordinator (R/C), quản lý câu hỏi nghiên cứu, protocol, bảng kết quả, log.
- Người 2: Data/Graph + Search/System (D/S), quản lý snapshot, baseline, demo, tái lập.
- H — Human annotators: hai bạn cùng gán nhãn độc lập; chấm ẩn danh hệ thống và lưu nhãn trước hòa giải.
- Agent hỗ trợ: triển khai module có hợp đồng rõ, tạo test, chạy phân tích và viết bản nháp; người sở hữu task đọc diff/bằng chứng và giải thích lại được.
- Một coordinator cập nhật board tích hợp; agent được phân công dùng file riêng và bàn giao artifact/log để tránh đè file.

Một người làm nhiều vai vẫn dùng cùng quy trình. Không mặc định các vai trò đã có người nhận.

## 7. Đường găng và cổng quyết định

1. Metric đúng + split rõ → benchmark loader → BM25 thật.
2. OpenAlex pilot → graph coverage/leakage audit → chốt graph protocol.
3. Dense + BM25 → hybrid → candidate recall → PPR → dev tuning.
4. Freeze cấu hình → final test → ablation/statistics → báo cáo.
5. Snapshot + API/UI → kiểm thử offline → performance → tái lập.

**G0 — Rubric:** yêu cầu chưa biết được ghi “chưa xác nhận”. Tiếp tục việc độc lập, không tự nhận đã được giảng viên duyệt.

**G1 — Data:** ID/qrels hợp lệ, raw data có checksum; không loại tài liệu benchmark để làm sạch rồi vẫn gọi là benchmark nguyên bản.

**G2 — Graph (SG-014):** phải kiểm tra full graph đầu vào có nguồn gốc và phù hợp nhãn. BEIR không mặc định có graph. Không đủ dữ liệu an toàn thì dùng OpenAlex custom graph protocol tách biệt; nếu vẫn không đạt, ghi quyết định giảm claim graph và giữ graph demo, ưu tiên retrieval study hoàn chỉnh.

**G3 — Baseline:** evaluator chính xác, run tái lập, hybrid baseline đủ mạnh trước thử thuật toán mới.

**G4 — Research freeze:** chốt query split, graph snapshot, hyperparameter budget, metric chính và model revision trước final test.

**G5 — Delivery:** mọi bảng liên kết run ID; người đọc khác có thể tái lập phần chính. Không buộc kết quả phải cải thiện; kết luận phải phù hợp bằng chứng.

## 8. Rủi ro và cách xử lý

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| Graph rò nhãn | Test citation xuất hiện trong adjacency/features | Bỏ cạnh và feature suy ra; dựng lại graph; đánh dấu run cũ không hợp lệ |
| Không đủ abstract/ID mapping | Coverage thấp ở pilot | Giữ missingness report; giảm phạm vi demo; tách graph experiment |
| Test-only benchmark | Không có dev đúng chức năng | Dùng dev độc lập/config cố định; không random chia test rồi so trực tiếp leaderboard |
| Pretrained overlap | Model học trên cùng paper/citation | Chọn revision/protocol phù hợp, công bố giới hạn, thêm own test |
| API quota/mạng | Lỗi tải/resume | Cache, rate limit, pilot nhỏ, snapshot bất biến; kiểm tra budget trước mở rộng |
| Thiếu GPU | Encoding chậm/OOM | Model nhỏ hơn, batch nhỏ, encode một lần/cache; ghi đổi model |
| Thiếu người gán nhãn | Pool chưa được chấm độc lập | Thu hẹp bộ VN và giới hạn claim; không thay người bằng LLM rồi gọi nhãn người |
| Graph/recency làm giảm relevance | Dev/query buckets giảm | Ghi kết quả, ablation, giữ cấu hình tốt trên dev; không ép tăng số |
| Mất context/phiên dừng | Task dở, run chưa hoàn tất | HANDOFF + log + artifact; không lặp chạy dài nếu đã có kết quả hợp lệ |

## 9. Gói nộp cuối

1. Báo cáo: motivation, related work, dữ liệu/protocol, methods, results, error analysis, limitations.
2. Source + environment lock + hướng dẫn tái lập.
3. Dataset manifests, split IDs, graph masking audit và annotation guide.
4. Run files, per-query metrics, config/model revisions, thống kê.
5. Demo offline; slides; kịch bản bảo vệ; danh sách đóng góp từng thành viên.
6. Task/log/decision history chứng minh quá trình thực hiện.

Task chi tiết ở [TASKS](TASKS.md); thiết kế đánh giá ở [RESEARCH_PROTOCOL](RESEARCH_PROTOCOL.md).

## 10. Kế hoạch theo tuần cho hai bạn

| Tuần | Người 1 — học thuật/đánh giá | Người 2 — dữ liệu/sản phẩm | Agent hỗ trợ và cổng ra |
|---|---|---|---|
| 1 | Chốt RQ, đọc BM25/PPR, kiểm tra rubric và metrics | Setup, tải benchmark, thử OpenAlex/GPU | Loader/evaluator skeleton; cuối tuần BM25 pilot có log |
| 2 | Chốt splits, kiểm tra overlap và graph masking | Dữ liệu 10–20K, encoding batch có resume | Baselines và graph audit; cuối tuần quyết định graph go/no-go |
| 3 | Đọc lỗi retrieval, xác minh metric/ablation | RRF, PPR, first API | Có bảng dev text/hybrid; giải thích được PPR trên toy graph |
| 4 | Khóa main protocol, viết query VN và hướng dẫn nhãn | Age adjustment, tuning, UI cơ bản | Freeze cuối tuần; agent tạo annotation tool/pool |
| 5 | Hai người chấm nhãn, phân tích test và CI | Hai người chấm nhãn, demo offline, latency | Kết quả chính và VN, không thêm tính năng lớn |
| 6 | Viết report và limitations; người 2 review | Packaging, tái lập; người 1 chạy lại | Evidence bundle, report draft, video/kịch bản demo |
| 7 | Ôn Q&A, sửa diễn giải, kiểm tra trích dẫn | Sửa lỗi cuối, diễn tập demo | Dự phòng lỗi/GPU, đóng gói nộp; không mở RQ mới |

Nếu chậm: bỏ SG-046…SG-049 trước, giữ OpenAlex ở 10K, giảm độ cầu kỳ UI/graph rendering, giảm bộ VN theo protocol đã ghi. Bảo toàn metric đúng, chống leakage, baseline và báo cáo. Cuối tuần 2 không qua graph gate thì sửa phạm vi sớm bằng ADR; không đợi tuần 6.

## 11. Tính toán và GPU

Với pretrained encoder nhỏ/base, chỉ title+abstract và cache embeddings, Kaggle/Colab là phương án bắt đầu hợp lý. Đây là đánh giá khả thi thiết kế, chưa đo trên tài khoản của bạn. Quota/GPU thực tế thay đổi; Colab không bảo đảm tài nguyên. [Colab FAQ](https://research.google.com/colaboratory/faq.html)

- CPU local: ingestion, BM25, graph, metric, API/UI, report.
- GPU notebook: encode batch trên 1.000 mẫu pilot; ghi model, GPU, batch, sequence length, docs/giây và peak VRAM. Ngoại suy thời gian = tổng docs / docs-per-second, cộng thời gian tải/lưu.
- Cache theo dataset hash + model revision + preprocessing config. Chia shard 1.000–5.000 docs, checksum và completion manifest, resume bỏ shard đã xác minh.
- Lưu kết quả sang nơi bền vững được người dùng cấp trước khi runtime đóng. Máy local giữ bản metrics/manifests để tiếp nối.
- Ước lượng dung lượng minh họa: 50.000 vectors × 768 chiều × 4 byte ≈ 154 MB chỉ riêng ma trận embedding; chưa tính model, index, text hoặc batch memory.
- Không dùng nhiều GPU khi chưa cần; core không có fine-tune nên không dự trù thuê ngay.
- Chỉ xem xét thuê khi SG-002/SG-019 đo cho thấy free GPU không đủ trước deadline, OOM sau giảm batch/model hợp lý hoặc cần một run dài ổn định. Khi đó lập dự toán giờ × đơn giá tại thời điểm thuê và mức trần để người dùng quyết định trước chi phí.

Mỗi cuối tuần, cả hai phải giải thích được một query chạy qua hệ thống, một bảng kết quả và một lỗi thật. Agent giúp hoàn thành implementation; hai bạn nắm lý do và bằng chứng bảo vệ.
