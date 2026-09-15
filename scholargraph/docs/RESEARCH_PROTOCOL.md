# Giao thức nghiên cứu — bản trước thí nghiệm

Ngày: 2026-09-15. Các lựa chọn dưới đây là kế hoạch; SG-004 và SG-027 sẽ khóa cấu hình có thể chạy sau feasibility. Chưa có kết quả.

## 1. Ba tuyến đánh giá

| Tuyến | Input → output | Corpus/labels | Ý nghĩa |
|---|---|---|---|
| A — Text retrieval | Query → danh sách paper | BEIR SciFact và SCIDOCS, split chính thức | So sánh BM25/dense/hybrid trên benchmark chuẩn |
| B — Graph recommendation | Paper/chủ đề → paper | OpenAlex snapshot + split/labels tự xây có audit | Kiểm tra giá trị graph; công bố là custom experiment |
| C — Việt → Anh | Query tiếng Việt → paper tiếng Anh | OpenAlex corpus cố định + nhãn người | Đánh giá tính hữu ích cho người dùng VN |

SciFact là truy xuất bằng chứng cho phát biểu khoa học; SCIDOCS là truy xuất liên quan citation, không đại diện hoàn toàn cho mọi nhu cầu tìm kiếm. Không gộp score ba tuyến thành một con số “accuracy”. [Nguồn BEIR](https://github.com/beir-cellar/beir)

## 2. Điều chỉnh cần thiết so với ý tưởng ban đầu

- Bộ BEIR tiêu chuẩn cung cấp corpus, queries và qrels. Không được suy ra adjacency graph đầy đủ từ qrels.
- SCIDOCS (BEIR) và bộ SciDocs đầy đủ/SciRepEval có candidate pool, tác vụ và evaluator khác nhau; score không trao đổi trực tiếp.
- PageRank toàn cục là đối chứng mức phổ biến. Điểm trích dẫn cao không bảo đảm phù hợp query.
- Hiệu chỉnh tuổi paper được xem là biến thí nghiệm. Muốn nói giảm thiên lệch phải đo exposure có điều kiện theo relevance/chủ đề; chỉ tăng tỷ lệ bài mới chưa đủ.
- Tăng 3–5% hay P95 dưới 500 ms là mong muốn, không phải điều kiện ép kết quả hoặc bằng chứng A+.
- Ghép PPR với freshness chưa tự chứng minh novelty; SG-003 khảo sát liên quan và mô tả đóng góp ở mức phù hợp.

## 3. Tuyến A: benchmark text

- Tải bản chính thức, pin revision/checksum, giữ nguyên ID, query, corpus và test qrels.
- SG-009 xác minh số lượng/splits thực tế; số trên website chỉ để dự trù.
- SciFact có train/test trong BEIR; tách dev từ phần train theo query group trước tune, không dùng test.
- BEIR SCIDOCS chỉ công bố test trong bảng BEIR: cấu hình cố định trước test hoặc dùng dev độc lập đã kiểm tra không trùng. Không tạo “official dev” giả.
- Raw test labels chỉ evaluator đọc. Indexer/ranker API không nhận qrels.
- Kiểm tra trùng giấy DOI/title/preprint giữa dev, model training data nếu biết, và benchmark.
- Index trên toàn bộ corpus đánh giá là hợp lệ trong retrieval; dùng test relevance để tạo feature là không hợp lệ.
- Kết quả benchmark text chính thức chỉ dùng các field và candidate universe đúng protocol. External graph enrichment phải nằm bảng riêng có disclosure.

## 4. Tuyến B: graph — phải qua SG-014

### B1. Pilot và cổng khả thi

Lấy 1.000–3.000 records đầu tiên, kiểm tra:
- ID, DOI, abstract, năm, referenced works và khả năng mapping.
- Tỷ lệ node cô lập, cạnh ra ngoài corpus, degree distribution, các topic đại diện.
- Có đủ observed graph cho query và labels độc lập hay không.
- Học phí tài nguyên: dung lượng và quota dự kiến khi mở rộng.
- Ghi rõ ngày thu thập khác ngày xuất bản; metadata hôm nay có thể đã được sửa sau đó.

Không đủ graph sạch cho BEIR thì không đặt graph score vào bảng chính thức của BEIR.

### B2. Custom citation holdout được đề xuất

- Đặt tên protocol riêng `openalex-citation-holdout-v1`.
- Chia source papers theo năm thành development và test; mốc năm chọn bằng availability ở pilot, khóa trước xem score.
- Chỉ candidate papers được xuất bản không muộn hơn source query. Paper thiếu năm bị loại khỏi thí nghiệm thời gian, nhưng có thể giữ trong demo với nhãn missing.
- Chia citations của source thành observed (nếu giả định user đã có thư mục tham khảo) và held-out. Công bố rõ đây là warm-start citation recommendation.
- Xóa toàn bộ held-out edges của dev/test khỏi adjacency trước tính PPR, degree, co-citation, bibliographic coupling, embedding graph; nếu thêm reverse edges thì xóa cả bản đảo.
- Ground-truth edge list chỉ evaluator giữ; ranker không đọc list.
- Loại self và các references đã biết khỏi candidate trả về khi đánh giá tìm citation mới.
- Corpus candidate cố định và dùng chung cho các baseline; ưu tiên full eligible corpus. Nếu dùng sampled negatives, ghi cách lấy mẫu và không so score với full-corpus retrieval.
- Positive citation chỉ là proxy liên quan; uncited paper không tự động là negative đã xác minh.
- Recompute graph scores từ graph được phép. Không dùng `cited_by_count` hiện tại để đánh giá kịch bản lịch sử.
- Muốn claim strict historical simulation cần snapshot/thông tin chỉ có tại cutoff. Chỉ lọc năm trên snapshot hiện tại thì gọi publication-year-constrained retrospective experiment và công bố giới hạn thời gian.

Nếu B2 không đủ dữ liệu: chọn neighborhood graph rerank trên một bộ query được người chấm nhãn độc lập; vẫn cần pin snapshot và kiểm tra nhãn không đi vào graph. Quyết định chọn B2 hoặc phương án thay thế phải có ở DECISIONS trước chạy chính thức.

## 5. Baselines và phương pháp

Các cấu hình bắt buộc:
- TF-IDF cosine.
- BM25.
- Một dense model phù hợp query → paper.
- RRF fusion của BM25 và dense; dùng làm hybrid baseline mạnh.
- Global PageRank (chỉ tuyến có graph), popularity diagnostic.
- Hybrid + Personalized PageRank.
- Hybrid + PPR + age adjustment.

SPECTER2/SciNCL là ứng viên paper representation; model dùng cho paper-to-paper không được mặc định tốt cho natural-language query. Đọc model card, task adapter, license, training overlap và version ở SG-017. [SciRepEval](https://github.com/allenai/scirepeval)

RRF trước, rồi thử score fusion có chuẩn hóa. Nếu dùng score fusion:
- Chuẩn hóa per query; ghi rõ cách xử lý score hằng số/missing.
- PPR teleport distribution lấy từ kết quả text, không lấy từ relevant labels.
- Chốt hướng cạnh, dangling-node handling, damping, tolerance, số seeds.
- Tách seed set, graph expansion set và final candidate set.
- Ablation reranking dùng cùng candidate set. Graph candidate expansion, nếu có, là thí nghiệm riêng.
- Freshness/age factor có công thức và mốc thời gian cố định; missing year có policy.

## 6. Metrics và thống kê

Metric chính: nDCG@10. Metric phụ: Recall@100, MRR@10, MAP@100, P@5. Dùng evaluator chuẩn BEIR/trec_eval tương thích và kiểm tra fixture tính tay trước real run. [Metric reference](https://github.com/beir-cellar/beir/wiki/Metrics-available)

- Khóa relevance threshold/gain convention của evaluator; qrels 0 khác relevant 1/2, unjudged khác nhãn negative chắc chắn.
- Tie-break deterministic theo doc ID; kiểm tra duplicate IDs và self-match theo từng protocol.
- Báo macro theo query, không micro theo số document.
- Candidate recall/oracle nDCG giúp tách lỗi retrieve với lỗi rerank.
- Báo chênh lệch tuyệt đối và tương đối riêng: ví dụ 0,40 → 0,42 là +0,02 tuyệt đối, +5% tương đối (minh họa toán, không phải kết quả).
- Paired bootstrap CI 95% trên query cho chênh lệch hai hệ thống, số resamples/seed ghi trong config.
- Nếu kiểm định nhiều so sánh, định trước primary comparison hoặc điều chỉnh multiple comparisons.
- Model deterministic không cần chạy 5 seed giống nhau để tạo CI; chạy lặp chỉ kiểm tra tái lập/latency.
- Khi fine-tune hoặc có sampling, tối thiểu 3 seed; tách độ biến thiên seed với độ bất định theo query.
- Không khai báo CI khác 0 là bằng chứng tổng quát cho mọi chủ đề; nêu kích thước test.

## 7. Tuyến C: mini benchmark tiếng Việt

Kế hoạch core 7 tuần: khoảng 30 query tiếng Việt do người hiểu chủ đề viết; 10 dev, 20 held-out test chia theo intent/topic để tránh query paraphrase rơi cả hai phía. Chỉ tăng lên 50 query nếu pilot gán nhãn cho thấy còn đủ thời gian. Cỡ test nhỏ phải được ghi trong kết luận.
- Corpus cố định, cùng ID giữa các hệ thống.
- Baseline: BM25 trên query gốc; query translation → BM25; multilingual dense; hybrid; graph rerank nếu đủ coverage.
- Kiểm tra model/công cụ dịch và nguồn lực ở SG-032. Dịch tự động không tự trở thành nhãn ground truth.
- Pool top 10 từ 3 phương pháp đại diện đã định trước (dịch query + BM25, multilingual dense, hybrid/PPR), khử trùng. Mục tiêu khoảng 600 cặp query-paper duy nhất, mỗi cặp được hai người chấm. Pilot 5 query để đo thời gian; nếu vượt budget thì giảm số query hoặc depth đồng đều trước chấm test và ghi decision. Không loại riêng kết quả bất lợi cho một phương pháp để giảm workload.
- Hai người gán nhãn độc lập: 0 không liên quan, 1 một phần, 2 liên quan trực tiếp. Người chấm không thấy tên/score của hệ thống.
- Hướng dẫn có ví dụ, cách đọc title/abstract, xử lý thiếu thông tin; adjudicate bất đồng sau khi lưu original labels.
- Báo weighted Cohen's kappa hoặc Krippendorff's alpha phù hợp thang thứ bậc; tính trước adjudication.
- Test labels chỉ mở sau khi khóa VN config; không sửa query test từ lỗi nhìn thấy.
- Đánh giá trong pooled judgments; báo tỷ lệ kết quả chưa được chấm, giới hạn coverage, không claim recall đầy đủ trên toàn corpus.
- Bộ này là benchmark nội bộ, không được gọi là benchmark tiếng Việt chuẩn quốc tế.

## 8. Thiết kế các run

Mỗi run có ID `RUN-YYYYMMDD-HHMMSS-method-dataset-split`:
- config đã resolve;
- dataset manifest/hash, split hash, graph hash;
- model ID/revision, tokenizer/prompt/adapter;
- code commit hoặc source hash nếu chưa có Git;
- hardware, library versions, seed, command;
- status started/completed/failed, timestamp;
- ranking TREC run, per-query metrics, aggregate metrics, log stderr/stdout;
- tuning_trials riêng, bảng kết quả dẫn về run ID.

Chỉ aggregate metrics của completed run hợp lệ mới lên báo cáo/UI benchmark. Chạy lại tạo run ID mới. Không ghi đè lịch sử.

## 9. Freeze và audit cuối

SG-027 khóa text/graph protocol; VN có bước freeze riêng sau dev ở SG-034. Ghi trước danh sách planned ablations và primary comparisons. Nếu phát hiện lỗi evaluator sau test, lưu run lỗi, sửa có log và chạy lại toàn bộ hệ thống bị ảnh hưởng công bằng.

SG-042: người khác tái lập ít nhất một text baseline và một graph run trên dữ liệu/config tương ứng; nếu chỉ một người thì ghi self-reproduction và không nhận là độc lập.
