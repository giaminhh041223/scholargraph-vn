# Model cho từng task — ScholarGraph VN

Ngày thiết lập: 2026-09-15. Đây là **khuyến nghị phân công**, không tự chọn model trong ứng dụng, không ghi nhận model đã chạy và không đổi trạng thái task. SG-000 đã DONE từ trước; SG-046–049 vẫn DEFERRED.

Nguồn chuẩn cho routing: [model_routing.json](../management/model_routing.json). Trạng thái/dependency vẫn ở [tasks.json](../management/tasks.json). Cách mở/đóng chat, fallback và review: [chiến lược chat](MODEL_AND_CHAT_STRATEGY.md).

Astra = GPT-6 Astra; Sol/Terra/Luna = GPT-5.6 tương ứng. High/XHigh là mức suy luận đề xuất, không phải cấp quyền. Cột “người duyệt” là gate bổ sung; không thay thế acceptance sẵn có. “Review riêng” cần phiên/context mới; “tự kiểm” cho phép tự kiểm có log, không được gọi là review độc lập.

| Task và nội dung | Làm chính | Chat | Reviewer | Cách review | Người duyệt | Lý do |
|---|---|---|---|---|---|---|
| [SG-000](TASKS.md#sg-000) — Thiết lập kế hoạch, rules và log | Sol · High | C | Sol · High | Tự kiểm được | Theo checkpoint | Điều phối hồ sơ; mapping không ghi lại model đã dùng ở phiên cũ. |
| [SG-001](TASKS.md#sg-001) — Chốt scope và yêu cầu môn | Sol · High | C | Astra · High | Review riêng | Bắt buộc | Chốt phạm vi vừa sức và đối chiếu rubric thật. |
| [SG-002](TASKS.md#sg-002) — Khảo sát local và GPU pilot | Sol · High | D | Sol · High | Tự kiểm được | Theo checkpoint | Chẩn đoán runtime, đo pilot và phục hồi notebook. |
| [SG-003](TASKS.md#sg-003) — Related work và novelty | Astra · High | R | Sol · High | Review riêng | Theo checkpoint | Đọc nguồn gốc, phân biệt khoảng trống nghiên cứu với tích hợp kỹ thuật. |
| [SG-004](TASKS.md#sg-004) — Protocol nghiên cứu v1 | Astra · XHigh | R | Astra · High | Review riêng | Bắt buộc | Thiết kế câu hỏi, split, metric và giả thuyết có thể bác bỏ. |
| [SG-005](TASKS.md#sg-005) — Package, môi trường và Git local | Terra · High | D | Sol · High | Tự kiểm được | Theo checkpoint | Scaffold và môi trường theo scope; không cần suy luận nghiên cứu dài. |
| [SG-006](TASKS.md#sg-006) — Schema và interface | Sol · High | D | Astra · High | Review riêng | Theo checkpoint | Data contract ảnh hưởng nhiều module và tính tái lập. |
| [SG-007](TASKS.md#sg-007) — Runner và run manifest | Sol · High | M | Sol · High | Tự kiểm được | Theo checkpoint | Runner, provenance và resume phải nhất quán. |
| [SG-008](TASKS.md#sg-008) — Kiểm chứng evaluator | Astra · High | R | Astra · High | Review riêng | Bắt buộc | Evaluator sai làm mất giá trị toàn bộ bảng kết quả. |
| [SG-009](TASKS.md#sg-009) — Tải và đóng băng BEIR | Terra · High | D | Sol · High | Tự kiểm được | Theo checkpoint | Tải theo spec, checksum, license và split gốc. |
| [SG-010](TASKS.md#sg-010) — Audit chất lượng dữ liệu | Sol · High | D | Astra · High | Review riêng | Theo checkpoint | Audit trùng lặp và chất lượng trước khi chạy baseline. |
| [SG-011](TASKS.md#sg-011) — Split và leakage checks | Astra · XHigh | R | Astra · High | Review riêng | Bắt buộc | Leakage trực tiếp và gián tiếp qua text, graph, pretrained. |
| [SG-012](TASKS.md#sg-012) — BM25 pilot thật | Terra · High | M | Sol · High | Tự kiểm được | Theo checkpoint | BM25 pilot theo evaluator đã kiểm chứng. |
| [SG-013](TASKS.md#sg-013) — OpenAlex pilot có resume | Sol · High | D | Sol · High | Review riêng | Theo checkpoint | API ingestion, phân trang, resume và quota có nhiều lỗi biên. |
| [SG-014](TASKS.md#sg-014) — Graph feasibility gate | Astra · XHigh | R | Astra · High | Review riêng | Bắt buộc | Quyết định graph protocol khả thi trước khi đầu tư compute. |
| [SG-015](TASKS.md#sg-015) — Snapshot OpenAlex core | Terra · High | D | Sol · High | Tự kiểm được | Theo checkpoint | Mở rộng pipeline đã qua pilot, không đổi protocol. |
| [SG-016](TASKS.md#sg-016) — Graph và masked split | Sol · High | D | Astra · High | Review riêng | Bắt buộc | Triển khai masking graph; reviewer kiểm tra rò rỉ cạnh/feature. |
| [SG-017](TASKS.md#sg-017) — Chọn dense model | Astra · High | R | Sol · High | Review riêng | Bắt buộc | Trade-off mô hình embedding, overlap, license và GPU. |
| [SG-018](TASKS.md#sg-018) — Lexical baselines | Terra · High | M | Sol · High | Tự kiểm được | Theo checkpoint | Lexical baselines chuẩn với cấu hình cố định. |
| [SG-019](TASKS.md#sg-019) — Encoding shard và dense index | Sol · High | M | Sol · High | Review riêng | Theo checkpoint | Batching GPU, shards, ID alignment, resume và index. |
| [SG-020](TASKS.md#sg-020) — Hybrid RRF | Sol · High | M | Astra · High | Review riêng | Theo checkpoint | RRF cần kiểm tra hợp nhất rank, ties và missing candidates. |
| [SG-021](TASKS.md#sg-021) — Candidate recall | Astra · High | R | Sol · High | Review riêng | Theo checkpoint | Phân biệt lỗi candidate generation với reranking. |
| [SG-022](TASKS.md#sg-022) — Graph baselines | Sol · High | M | Astra · High | Review riêng | Theo checkpoint | Chiều cạnh, coupling và normalization phải có toy tests. |
| [SG-023](TASKS.md#sg-023) — Personalized PageRank | Sol · High | M | Astra · High | Review riêng | Theo checkpoint | PPR cần convergence, dangling-node và seed correctness. |
| [SG-024](TASKS.md#sg-024) — Age adjustment | Astra · High | R | Astra · High | Review riêng | Bắt buộc | Age adjustment phải tách bias, confounding và relevance. |
| [SG-025](TASKS.md#sg-025) — Reranking integration | Sol · High | M | Sol · High | Review riêng | Theo checkpoint | Ghép text/graph và explanation theo interface đã chốt. |
| [SG-026](TASKS.md#sg-026) — Dev tuning có budget | Astra · High | R | Astra · High | Review riêng | Bắt buộc | Tuning budget và kiểm soát lựa chọn trên dev. |
| [SG-027](TASKS.md#sg-027) — Main freeze | Astra · XHigh | R | Astra · High | Review riêng | Bắt buộc | Freeze trước test là mốc học thuật không được bỏ qua. |
| [SG-028](TASKS.md#sg-028) — Final runs | Sol · High | R | Astra · High | Review riêng | Theo checkpoint | Thực thi config frozen; không điều chỉnh từ kết quả test. |
| [SG-029](TASKS.md#sg-029) — Ablation và robustness | Astra · High | R | Astra · High | Review riêng | Theo checkpoint | Ablation phải cô lập thành phần và so sánh công bằng. |
| [SG-030](TASKS.md#sg-030) — Thống kê và error analysis | Astra · XHigh | R | Astra · High | Review riêng | Bắt buộc | Paired bootstrap, uncertainty, effect size và phân tích lỗi. |
| [SG-031](TASKS.md#sg-031) — Query Việt và annotation guide | Astra · High | R | Astra · High | Review riêng | Bắt buộc | Rubric truy vấn Việt và hướng dẫn nhãn cần người xác nhận. |
| [SG-032](TASKS.md#sg-032) — Cross-lingual baselines | Sol · High | M | Astra · High | Review riêng | Theo checkpoint | Baseline cross-lingual có provenance và ngân sách bằng nhau. |
| [SG-033](TASKS.md#sg-033) — Pool và nhãn hai người | Terra · High | R | Sol · High | Review riêng | Bắt buộc | AI chỉ chuẩn bị công cụ/pool ẩn danh; hai người tự gán nhãn. |
| [SG-034](TASKS.md#sg-034) — Freeze và final VN eval | Astra · High | R | Astra · High | Review riêng | Bắt buộc | Freeze VN, giới hạn pooling và đánh giá trên nhãn người. |
| [SG-035](TASKS.md#sg-035) — API search/metadata | Terra · High | P | Sol · High | Tự kiểm được | Theo checkpoint | API theo schema đã duyệt; không tự đổi pipeline. |
| [SG-036](TASKS.md#sg-036) — UI search/recommend | Terra · High | P | Sol · High | Tự kiểm được | Theo checkpoint | UI theo acceptance, trạng thái thiếu dữ liệu và luồng demo. |
| [SG-037](TASKS.md#sg-037) — Citation graph UI | Terra · High | P | Sol · High | Tự kiểm được | Theo checkpoint | Graph UI bounded nodes và phân biệt chiều cited/citing. |
| [SG-038](TASKS.md#sg-038) — Offline và xuất tham khảo | Terra · High | P | Sol · High | Tự kiểm được | Theo checkpoint | Offline/export dùng metadata thật; không điền DOI giả. |
| [SG-039](TASKS.md#sg-039) — Integration checks | Sol · High | P | Sol · High | Review riêng | Theo checkpoint | Kiểm tra tích hợp và failure paths xuyên module. |
| [SG-040](TASKS.md#sg-040) — Performance profiling | Sol · High | P | Sol · High | Review riêng | Theo checkpoint | Đo latency toàn tuyến, cold start, RAM và corpus size. |
| [SG-041](TASKS.md#sg-041) — Packaging và tái lập | Terra · High | W | Sol · High | Review riêng | Theo checkpoint | Đóng gói theo runbook và kiểm tra máy sạch. |
| [SG-042](TASKS.md#sg-042) — Tái lập chéo và audit | Astra · High | W | Astra · High | Review riêng | Bắt buộc | Người còn lại thực sự chạy tái lập; AI chỉ hỗ trợ audit. |
| [SG-043](TASKS.md#sg-043) — Báo cáo học thuật | Astra · High | W | Astra · High | Review riêng | Bắt buộc | Tổng hợp claim từ evidence và nêu giới hạn trung thực. |
| [SG-044](TASKS.md#sg-044) — Slides và diễn tập | Sol · High | W | Astra · High | Review riêng | Bắt buộc | Agent hỗ trợ câu chuyện/Q&A; cả hai người tự diễn tập. |
| [SG-045](TASKS.md#sg-045) — Gói nộp và handoff cuối | Terra · High | C | Sol · High | Review riêng | Bắt buộc | Checklist gói nộp; người dùng duyệt, không tự gửi bài. |
| [SG-046](TASKS.md#sg-046) — Stretch: cross-encoder | Sol · High | M | Astra · High | Review riêng | Bắt buộc | Stretch cross-encoder chỉ mở sau quyết định scope/compute. |
| [SG-047](TASKS.md#sg-047) — Stretch: fine-tuning | Astra · High | M | Astra · High | Review riêng | Bắt buộc | Fine-tuning có rủi ro leakage, budget và quá tải lịch. |
| [SG-048](TASKS.md#sg-048) — Stretch: SciRepEval task | Astra · High | R | Astra · High | Review riêng | Bắt buộc | Benchmark mới có protocol và labels khác; giữ ngoài core. |
| [SG-049](TASKS.md#sg-049) — Stretch: TREC-COVID | Sol · High | R | Astra · High | Review riêng | Bắt buộc | Thêm benchmark chỉ khi còn thời gian và được mở scope. |

SG-033: Terra chỉ hỗ trợ công cụ, randomize/blind pool và tính agreement sau khi chấm; **không phải người gán nhãn thứ ba**. SG-042 phải có bằng chứng người còn lại chạy lại, không chỉ agent tự đọc code. SG-044 cần cả hai bạn tự trình bày, không dùng trả lời của agent làm bằng chứng đã hiểu.

Các mức phân vai ở trên là quyết định thiết kế cho dự án, chưa có thử nghiệm đối chiếu các coding model trên ScholarGraph. Cơ sở phân loại chung: [OpenAI model catalog](https://developers.openai.com/api/docs/models); danh sách model khả dụng được đối chiếu với tool catalog của host hiện tại. Xem lại khi model/khả năng truy cập thay đổi.

