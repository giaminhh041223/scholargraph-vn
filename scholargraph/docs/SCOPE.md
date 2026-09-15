# Phạm vi dự án — ScholarGraph VN

Phiên bản: `scope-v1-accepted`  
Ngày: 2026-09-15  
Task: SG-001  
Trạng thái: **đã được project owner xác nhận để triển khai ngày 2026-09-15**. Rubric/chính sách môn chưa có vẫn được theo dõi riêng, không được suy đoán.

## 1. Tuyên bố bài toán

Sinh viên thường tìm bài báo bằng từ khóa nhưng khó biết kết quả nào thực sự liên quan, bài nào nối với mạng trích dẫn của chủ đề và vì sao hệ thống đề xuất bài đó. ScholarGraph VN xây một hệ thống tìm kiếm và gợi ý tài liệu khoa học cho người dùng Việt Nam, kết hợp:

1. độ phù hợp từ nội dung văn bản;
2. tín hiệu từ mạng trích dẫn;
3. kiểm nghiệm ảnh hưởng của tuổi bài báo;
4. một giao diện web chạy được trên snapshot offline.

Người dùng chính là sinh viên cần tìm bài tiếng Anh bằng truy vấn tiếng Anh hoặc tiếng Việt. Người dùng phụ là giảng viên/người chấm cần xem được phương pháp, benchmark, bằng chứng tái lập và giới hạn của hệ thống.

## 2. Giá trị thực tế và đóng góp học thuật

### Giá trị thực tế

- Tìm paper theo từ khóa hoặc câu hỏi, có metadata và nguồn.
- Từ một paper, khám phá các paper liên quan và mạng cited/citing.
- Giải thích kết quả bằng tín hiệu text/graph; không coi PageRank hay số trích dẫn là “độ đúng”.
- Chạy demo offline trên snapshot đã định danh; không phụ thuộc API ngoài khi trình bày.
- Hỗ trợ một tập truy vấn tiếng Việt nhỏ để kiểm tra nhu cầu người dùng trong nước.

### Đóng góp học thuật cam kết

- So sánh có kiểm soát TF-IDF, BM25, dense retrieval và hybrid RRF trên benchmark text.
- Trên một protocol graph riêng, đo giá trị bổ sung của PageRank/PPR ngoài tín hiệu nội dung.
- Phân tích đánh đổi relevance–exposure khi hiệu chỉnh theo tuổi bài; không mặc định phương pháp này tốt hơn.
- Đánh giá riêng truy vấn Việt → tài liệu Anh bằng nhãn của hai người.
- Có ablation, uncertainty/error analysis, provenance và kiểm tra leakage.

Đóng góp được mô tả là **tích hợp và kiểm nghiệm có hệ thống**, chưa tuyên bố thuật toán mới, SOTA hoặc mức tăng điểm số khi chưa có dữ liệu chạy.

## 3. Liên hệ học phần đã xác minh

Việc liên hệ dưới đây dựa trên tài liệu có thật trong workspace, không phải rubric chấm điểm:

| Nội dung môn | Cách dự án thể hiện | Bằng chứng dự kiến |
|---|---|---|
| [L01 — Introduction to Web Mining](../../extracted_L01.txt) | Khai phá tri thức hữu ích, đúng và hiểu được từ dữ liệu web không cấu trúc/liên kết | Problem framing, data pipeline, evaluation và visualization |
| [L02 — Machine Learning](../../L02-MachineLearning-01.pdf) | Dense representations; optional learning-to-rank chỉ khi core ổn định | Model card, baseline và overlap disclosure |
| [L03 — Data Visualization](../../L03-Data-visualization.pdf) | Citation graph và bảng kết quả có nguồn | UI/hình minh họa, không che missing data |
| [L04 — Information Retrieval](../../L04-Information-retrieval.pdf) | TF-IDF, BM25, dense và RRF | TREC run, nDCG/Recall/MRR, candidate recall |
| [L05 — Link Analysis](../../L05-LinkAnalysis-01.pdf.txt) | Directed citation graph, PageRank và PPR | Graph audit, masking, toy tests và ablation |
| [L07 — Information Extraction](../../L07-InformationExtraction.pdf) | Chuẩn hóa metadata, DOI và ID mapping | Data quality report và manifest |
| [L08 — Recommendation Systems](../../L08-RecommendationSystems.pdf) | Paper-to-paper recommendation | Protocol/metrics riêng, loại self và known references |
| [L09 — Query Mining](../../L09-OnlineAd-QueryMining.pdf) | Query buckets, VN queries và error analysis | Query set, failure taxonomy và per-query metrics |

## 4. Câu hỏi nghiên cứu

| ID | Câu hỏi | So sánh chính | Bằng chứng tối thiểu |
|---|---|---|---|
| RQ1 | Hybrid retrieval có cải thiện thứ hạng và khả năng tìm đủ bài so với BM25 và dense riêng không? | BM25 vs dense vs RRF, cùng corpus/split/budget | nDCG@10, Recall@100, MRR/MAP khi phù hợp; paired analysis |
| RQ2 | Trong protocol graph đã mask nhãn, PPR bổ sung giá trị gì ngoài nội dung? | Hybrid vs global PageRank vs hybrid+PPR | Graph audit, held-out edge masking, main metric và ablation |
| RQ3 | Hiệu chỉnh tuổi bài tạo đánh đổi relevance–exposure như thế nào? | Không age adjustment vs một biến thể đã khóa trên dev | Relevance metrics + phân bố/exposure theo nhóm tuổi, limitations |
| RQ4 | Chất lượng thay đổi thế nào khi truy vấn Việt hướng tới corpus Anh? | Cách dịch/encoder cross-lingual được khóa trên dev | Bộ query Việt, nhãn người, agreement và error analysis |

RQ và metric chi tiết sẽ được khóa tại SG-004/SG-027. Không xem test để sửa RQ, metric chính hoặc cấu hình.

## 5. Phạm vi core phải hoàn tất

### Dữ liệu và protocol

- Tuyến A: BEIR SciFact và BEIR SCIDOCS theo split/quy tắc đã xác minh; text benchmark giữ nguyên ý nghĩa chính thức.
- Tuyến B: OpenAlex pilot 1.000–3.000 paper; core 10.000–20.000 nếu qua graph feasibility gate. Đây là custom graph experiment, không gộp score với official BEIR.
- Tuyến C: khoảng 30 query Việt, dự kiến 10 dev/20 test; pool top-10 từ ba phương pháp và khoảng 600 cặp unique trước dedup thực tế. Hai người chấm độc lập rồi mới hòa giải.
- Snapshot, checksum/revision, license/provenance, split, qrels và run artifacts phải truy ngược được.

### Phương pháp bắt buộc

- TF-IDF và BM25.
- Một pretrained dense retriever phù hợp được chốt ở SG-017.
- Hybrid Reciprocal Rank Fusion.
- Global PageRank như popularity diagnostic và Personalized PageRank trong tuyến graph.
- Một age-adjustment variant được định nghĩa trước test; baseline không chỉnh tuổi luôn được giữ.

### Sản phẩm bắt buộc

- Search theo query, paper-to-paper recommendation, filter cơ bản và explanation text/graph.
- Citation graph được giới hạn số node, phân biệt cited/citing và hiển thị missing metadata trung thực.
- Snapshot offline; xuất danh sách tham khảo từ metadata thật.
- Báo cáo, source/environment lock, run/config/data manifests, slides và kịch bản demo.

### Đánh giá bắt buộc

- Official text benchmark, custom graph evaluation và VN evaluation ở ba bảng riêng.
- Dev/test discipline; graph label/held-out edges không vào ranker/features.
- Ablation, paired uncertainty hoặc confidence interval phù hợp, error analysis và performance profiling.
- Người còn lại chạy tái lập ít nhất một text baseline và một graph run; nếu không thực sự độc lập phải ghi đúng phạm vi.

## 6. Không thuộc core

Các mục sau bị loại khỏi cam kết 7 tuần, trừ khi có ADR mở lại sau khi core qua gate:

- Cross-encoder reranking, fine-tuning, SciRepEval task và TREC-COVID (SG-046–049 đang DEFERRED).
- Toàn bộ OpenAlex, OGBL-Citation2, corpus trên 20.000 paper khi chưa chứng minh nhu cầu.
- Train language model từ đầu, tạo LLM trả lời/tóm tắt paper, collaborative filtering khi chưa có user history.
- Public deployment, tài khoản cloud/DB/vector service trả phí, mobile app, social network cho researcher.
- Thuê GPU khi chưa có compute pilot, dự toán và quyết định ngân sách của người dùng.
- Tự động tạo nhãn relevance bằng LLM rồi coi là nhãn người.

## 7. Ràng buộc và ngân sách phạm vi

- Mục tiêu nội bộ: hoàn tất core và gói nộp trước **2026-10-31** để dành thời gian cho các học phần khác.
- Vùng đệm: **2026-11-01 đến 2026-11-30** chỉ dành cho lỗi, thay đổi rubric, tái lập và luyện bảo vệ; không chủ động mở stretch trong vùng đệm.
- Ràng buộc người dùng xác nhận: hoàn thành trước tháng 12/2026; ngày/giờ nộp chính thức của môn vẫn chưa được cung cấp. Các ngày trên là mốc quản lý nội bộ, không phải deadline giảng viên.
- Nhân lực: 2 người, dự kiến 12–15 giờ/người/tuần; core ước tính 142 giờ-người có agent hỗ trợ.
- Compute ban đầu: Kaggle/Colab; core ưu tiên pretrained inference, cache/shard/resume; chưa thuê GPU.
- Agent hỗ trợ code, test, phân tích và bản nháp. Hai thành viên chịu trách nhiệm nhãn, quyết định phương pháp, kiểm tra bằng chứng và bảo vệ.
- Chưa có Git/runtime Python ScholarGraph được xác minh; SG-002/SG-005 xử lý, không coi kế hoạch là môi trường đã chạy.

### Quy tắc cắt giảm nếu chậm

Theo thứ tự: giữ SG-046–049 ở DEFERRED → giữ OpenAlex ở khoảng 10K → giảm độ cầu kỳ UI/graph rendering → giảm quy mô VN theo protocol có ghi nhận. Không cắt evaluator correctness, leakage checks, baselines, provenance, freeze, report hoặc khả năng tái lập.

## 8. Điều kiện thành công của dự án

Đây là điều kiện chất lượng nội bộ, không phải ngưỡng điểm giảng viên:

1. Có ít nhất một baseline hoàn toàn tái lập trên benchmark text và mọi bảng kết quả dẫn về completed run.
2. So sánh chính dùng chung data/split/candidate universe/budget và không có leakage đã biết chưa xử lý.
3. Graph experiment chỉ xuất hiện nếu qua SG-014; nếu không qua, báo no-go có bằng chứng và đổi scope sớm.
4. Không ép kết quả phải tăng. Kết quả âm vẫn được báo cáo với phân tích nguyên nhân.
5. Demo offline chạy trên artifact đã đóng băng; thiếu index/model phải báo lỗi, không dùng dữ liệu giả.
6. Hai thành viên giải thích được một query end-to-end, BM25/RRF/PPR, một metric, một lỗi thật và giới hạn nghiên cứu.
7. Mọi claim trong báo cáo truy ngược được tới source, config, data hash và run ID.

Mục tiêu P95 search dưới 500 ms trên corpus/hardware đã ghi là mục tiêu engineering tại SG-040, chưa phải kết quả hay điều kiện bắt buộc để gọi nghiên cứu thành công.

## 9. Cổng xác nhận phạm vi

SG-001 được đóng sau khi project owner xác nhận review và cho phép triển khai scope ngày 2026-09-15. Các mục chính thức chưa biết tiếp tục được theo dõi; chúng phải được cập nhật trước gói nộp cuối nếu giảng viên công bố.

| Mục cần xác nhận | Trạng thái hiện tại | Người chịu trách nhiệm |
|---|---|---|
| Tên dự án và tuyên bố bài toán | Accepted for implementation | Project owner; thành viên còn lại cần đọc lại trước SG-004 |
| Core/non-core và 4 RQ | Accepted for implementation; RQ chi tiết khóa tại SG-004 | Project owner; cả hai cùng chịu trách nhiệm hiểu |
| Mốc hoàn thành nội bộ | Target 2026-10-31; buffer hết 2026-11-30 | Coordinator theo dõi; không phải deadline môn |
| Ngày/giờ nộp chính xác | Unknown | Thành viên liên hệ/đọc LMS |
| Rubric và trọng số chấm chính thức | Unknown | Thành viên cung cấp file/link/ảnh |
| Chính sách dùng AI/agent, pretrained model và external datasets | Unknown | Thành viên xác minh với giảng viên/LMS |
| Format nộp, giới hạn trang/video, yêu cầu source/demo | Unknown | Thành viên xác minh với giảng viên/LMS |
| Quy định số người và khai báo đóng góp | Unknown | Thành viên xác minh với giảng viên/LMS |

Nếu chưa có câu trả lời từ giảng viên, phạm vi kỹ thuật tiếp tục theo core đã duyệt; riêng yêu cầu chính thức vẫn giữ nhãn OPEN/PARTIAL và không được biến thành quy định môn học.

## 10. Bản giải thích 2 phút

> ScholarGraph VN giúp sinh viên tìm và khám phá tài liệu khoa học bằng cả nội dung bài báo và quan hệ trích dẫn. Hệ thống không chỉ làm demo: chúng tôi so sánh TF-IDF, BM25, dense retrieval và hybrid RRF trên benchmark text; sau đó kiểm tra xem PageRank/PPR có bổ sung giá trị trong một graph protocol đã loại các cạnh dùng làm nhãn hay không. Chúng tôi còn phân tích ảnh hưởng của tuổi bài báo và đánh giá một bộ truy vấn Việt → tài liệu Anh do hai người chấm độc lập. Ba tuyến text, graph và tiếng Việt được báo cáo riêng, có split, manifest, run files, ablation và uncertainty. Phần core chạy trên snapshot OpenAlex 10–20 nghìn paper và Kaggle/Colab, kèm web demo offline. Điểm mạnh của dự án là kết nối trực tiếp Information Retrieval, Link Analysis, Recommendation và Data Visualization nhưng vẫn kiểm soát leakage và tái lập. Chúng tôi không tuyên bố SOTA hay ép phương pháp mới phải thắng; giá trị học thuật nằm ở protocol đúng, so sánh công bằng và phân tích trung thực.

Hai thành viên nên tự nói lại nội dung này bằng từ của mình; văn bản trên là khung, không thay thế việc hiểu phương pháp.
