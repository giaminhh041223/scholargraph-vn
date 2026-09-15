# Bản đồ yêu cầu chấm điểm — ScholarGraph VN

Phiên bản: `rubric-map-v1-tracked`  
Ngày: 2026-09-15  
Task: SG-001  
Trạng thái: **scope nội bộ đã duyệt; rubric chính thức vẫn chưa được cung cấp**.

## 1. Tuyên bố nguồn và giới hạn

Workspace hiện có lecture L01–L09 và tài liệu kế hoạch ScholarGraph, nhưng chưa tìm thấy rubric, trọng số điểm, ngày nộp chính xác, format nộp hoặc chính sách AI/pretrained/external data. Vì vậy:

- Không có cột phần trăm điểm tự đặt.
- Các tiêu chí bên dưới là checklist chất lượng để hướng tới bài làm mạnh, không được gọi là yêu cầu chính thức của giảng viên.
- Khi nhận rubric thật, thêm nguyên văn ngắn/đường dẫn hoặc mã tiêu chí chính thức, owner và mapping; không sửa kết quả để “khớp điểm”.
- Mục chưa biết được phép giữ OPEN/PARTIAL để đóng SG-001 vì task yêu cầu ghi rõ unknown và owner. Chúng vẫn chặn tuyên bố “đã đáp ứng rubric chính thức” và phải được kiểm tra lại trước SG-045.

## 2. Requirements register chính thức

| ID | Yêu cầu cần lấy | Giá trị đã xác minh | Nguồn | Owner | Ảnh hưởng nếu thiếu | Trạng thái |
|---|---|---|---|---|---|---|
| OFF-01 | Ngày/giờ nộp và timezone | Người dùng cho phép linh động trước tháng 12/2026; target nội bộ 2026-10-31, buffer đến 2026-11-30; deadline môn vẫn chưa rõ | Xác nhận người dùng ngày 2026-09-15; chưa có LMS/rubric | Thành viên 1 | Phải cập nhật nếu lịch môn sớm hơn mốc nội bộ | PARTIAL |
| OFF-02 | Rubric và trọng số từng tiêu chí | Chưa có | Chưa cung cấp | Thành viên 1 | Không thể chứng minh tối ưu theo điểm chính thức | OPEN |
| OFF-03 | Deliverables bắt buộc | Chưa rõ report/source/slides/video/demo bắt buộc đến mức nào | Chưa cung cấp | Thành viên 1 | Nguy cơ thiếu đúng format nộp | OPEN |
| OFF-04 | Giới hạn report/slide/video và template | Chưa có | Chưa cung cấp | Thành viên 1 | Có thể phải tái cấu trúc bản nộp muộn | OPEN |
| OFF-05 | Chính sách AI/agent và yêu cầu khai báo | Chưa có | Chưa cung cấp | Cả hai | Ảnh hưởng cách dùng agent và phần declaration | OPEN |
| OFF-06 | Cho phép pretrained models/external datasets/API | Chưa có | Chưa cung cấp | Cả hai | Ảnh hưởng OpenAlex, dense encoder và model cards | OPEN |
| OFF-07 | Quy định nhóm và khai báo đóng góp | Thực tế có 2 thành viên; quy định môn chưa rõ | Người dùng; chưa có quy định | Cả hai | Ảnh hưởng eligibility và contribution statement | OPEN |
| OFF-08 | Cách chấm demo/reproducibility/oral defense | Chưa có | Chưa cung cấp | Cả hai | Ảnh hưởng ưu tiên UI, video và rehearsal | OPEN |

Evidence hợp lệ để đóng một mục: file/ảnh rubric rõ nguồn, link LMS/course announcement được người dùng cung cấp, hoặc ghi chú xác nhận từ giảng viên có ngày. Lời suy đoán của agent không hợp lệ.

## 3. Ma trận chất lượng provisional

| QP | Tiêu chí chất lượng | Cơ sở môn/project đã thấy | Bằng chứng dự kiến | Task tạo bằng chứng | Gate trước khi đưa vào bài |
|---|---|---|---|---|---|
| QP-01 | Bài toán rõ, thực tế và có người dùng | L01 nhấn mạnh pattern đúng, hữu ích, hiểu được | [SCOPE](SCOPE.md), user flow, demo narrative | SG-001, SG-036, SG-043 | Hai người nói được problem/value trong 2 phút |
| QP-02 | Bám sát kiến thức Web Mining | Lecture L02–L09 trong workspace | Mapping IR/ML/link/recommendation/visualization; thuật toán có giải thích | SG-001, SG-003, SG-043 | Mỗi thuật toán nối với câu hỏi nghiên cứu và evidence |
| QP-03 | Dữ liệu có provenance và chất lượng | Pipeline Web Mining cần preprocessing/integration | Snapshot manifest, checksum, schema/dedup/license audit | SG-006, SG-009–016 | Không dùng dataset/run không truy nguồn được |
| QP-04 | Baseline và phương pháp hợp lý | L04 IR; L05 PageRank/citation analysis | TF-IDF/BM25/dense/RRF/PageRank/PPR, model cards | SG-012, SG-017–025 | Cùng universe/split/budget; baseline mạnh không bị bỏ |
| QP-05 | Thiết kế đánh giá đúng | Research protocol đã tách ba tuyến | Pre-registered comparisons, evaluator tests, metrics phù hợp | SG-004, SG-008, SG-011, SG-027 | Test labels không vào ranker; config freeze trước final |
| QP-06 | Đóng góp được kiểm chứng | ADR-005 cấm claim novelty/SOTA chưa chứng minh | Related work, ablation, paired uncertainty, error analysis | SG-003, SG-021, SG-029, SG-030 | Claim chỉ dựa trên completed run và comparison hợp lệ |
| QP-07 | Link/graph mining có chiều sâu | L05 có graph ranking, PageRank và citation analysis | Graph audit, masked edges, PageRank/PPR toy tests, ablation | SG-014, SG-016, SG-022–024 | Qua feasibility; graph score không giả làm official BEIR |
| QP-08 | Tính thực tế và trải nghiệm demo | Mục tiêu giúp sinh viên VN tìm/khám phá paper | API/UI offline, source metadata, cited/citing, export | SG-035–040 | Demo dùng snapshot thật; failure/missing data minh bạch |
| QP-09 | Khả năng tái lập | NFR và protocol nội bộ | Environment lock, configs, manifests, run IDs, clean-run audit | SG-007, SG-028, SG-041, SG-042 | Người còn lại thực sự chạy lại; ghi rõ nếu không độc lập |
| QP-10 | Tiếng Việt có đánh giá thật | Mục tiêu người dùng VN không được suy từ English benchmark | Query guide, two-person labels, agreement, VN results | SG-031–034 | Hai người chấm độc lập; LLM không thay nhãn người |
| QP-11 | Phân tích và trình bày trung thực | L01 yêu cầu knowledge correct/useful/understandable | Results, limitations, negative findings, citations và defense Q&A | SG-030, SG-043, SG-044 | Bảng truy về run; không che negative result/limitation |
| QP-12 | Quản lý phạm vi 7 tuần | 2 người, 142 giờ core, free GPU trước | Task logs, decisions, cut order, contribution statement | Toàn bộ; SG-045 tổng hợp | Không mở stretch trước core; không bịa công việc người làm |

## 4. Mapping RQ và yêu cầu sản phẩm tới bản nộp

| Đối tượng | Artifact chứng minh | Vị trí dự kiến trong report/demo | Acceptance cấp dự án |
|---|---|---|---|
| RQ1 — lexical/dense/hybrid | Run files, aggregate + per-query metrics, significance/error analysis | Methods + Results: Text Retrieval | So sánh cùng protocol; không tune test |
| RQ2 — graph value | Masking audit, graph stats, PageRank/PPR ablation | Methods + Results: Graph Experiment | Qua SG-014; nhãn/cạnh giữ lại không lọt feature |
| RQ3 — age adjustment | Config, exposure/relevance analysis, limitations | Analysis: Temporal/Popularity Bias | Không dùng “nhiều bài mới hơn” làm bằng chứng relevance |
| RQ4 — VN → EN | Query set, annotation guide/labels/agreement, VN metrics | Results: Vietnamese Evaluation | Hai rater độc lập, split/freeze rõ |
| FR-01/02 — search/recommend | API tests + UI demo trên snapshot | Demo flow 1–2 | Metadata/source đúng; loại self |
| FR-03/04 — filter/graph | Integration tests + bounded graph visualization | Demo flow 3 | Filter đúng; cited/citing rõ; missing được báo |
| FR-05/06 — explanation/VN | Explanation fields + VN queries/results | Demo + report | Text/graph signals tách biệt; không bịa causal explanation |
| FR-07/08 — offline/export | Offline smoke + exported reference validation | Demo fallback + appendix | Không gọi mạng; không điền metadata giả |
| NFR-01/03/04 — reproduce/continuity/transparency | Manifests, configs, logs, handoff, declarations | Reproducibility + appendix | Clean rerun, status/run traceability |
| NFR-02 — performance | P50/P95/cold start/RAM/index report | Engineering evaluation | Ghi hardware/corpus; mục tiêu không được báo như kết quả |

## 5. Definition of A+-quality nội bộ

Không thể bảo đảm điểm A+ khi chưa có rubric chính thức. Trong dự án này, “A+-quality” chỉ dùng như tiêu chuẩn nội bộ gồm:

1. Có câu hỏi nghiên cứu rõ và mỗi claim có bằng chứng thực nghiệm truy ngược được.
2. Baseline công bằng, evaluator đúng, split/leakage được audit trước final runs.
3. Có giá trị thực tế qua demo offline dùng dữ liệu thật.
4. Có chiều sâu qua graph protocol, ablation, uncertainty và error analysis; không chỉ ghép thư viện.
5. Báo cáo kết quả âm và giới hạn trung thực.
6. Hai thành viên hiểu, tái lập và bảo vệ được phần mình; agent assistance được khai báo theo quy định thật khi có.
7. Bản nộp đúng toàn bộ OFF-01–OFF-08 sau khi nhận yêu cầu chính thức.

Nếu rubric thật mâu thuẫn checklist này, rubric thật được ưu tiên và thay đổi phải ghi ADR/task impact, không sửa lịch sử bằng chứng.

## 6. Checklist review SG-001

- [x] Phạm vi core phù hợp 7 tuần/2 người được viết rõ.
- [x] Core, stretch và out-of-scope tách riêng.
- [x] RQ/FR/NFR được nối với artifact và task.
- [x] Liên hệ môn dựa trên lecture có thật trong workspace.
- [x] Không tạo trọng số/metric kết quả/rubric chính thức giả.
- [x] Project owner xác nhận task đã được review; không có report model riêng trên đĩa nên không gọi đây là independent model audit.
- [x] Project owner chấp thuận đóng SG-001 và triển khai scope; thành viên còn lại vẫn phải đọc/hiểu trước khi khóa protocol ở SG-004.
- [x] OFF-01–OFF-08 được giữ OPEN, có owner/ảnh hưởng/cách đóng; chưa giả lập câu trả lời chính thức.

SG-001 được chuyển DONE sau acceptance audit và xác nhận trực tiếp của project owner ngày 2026-09-15. OFF-01–08 tiếp tục được theo dõi; không có mục nào được ngầm coi là yêu cầu chính thức.
