# Nhật ký quyết định

Mỗi thay đổi phương pháp/phạm vi quan trọng thêm ADR mới. Không ghi đè quyết định cũ; ghi mục thay thế và lý do.

## ADR-001 — 2026-09-15 — Khu vực ScholarGraph độc lập

**Trạng thái:** accepted for planning.
**Bối cảnh:** workspace có E-COMASPECT, lecture files, checkpoints và dữ liệu cũ; chưa có Git.
**Quyết định:** đặt dự án tại `scholargraph/`; root AGENTS dẫn sang đây.
**Hệ quả:** môi trường/data/results riêng; không dùng kết quả cũ làm benchmark mới.

## ADR-002 — 2026-09-15 — Lịch dựa trên giả định

**Trạng thái:** provisional.
**Quyết định:** 12 tuần, 3 người × 10 giờ/tuần; các task ghi giờ-người và role.
**Chưa biết:** deadline, nhân sự, GPU, rubric.
**Cập nhật khi:** người dùng cung cấp thông tin hoặc SG-001/SG-002 xác minh.
**Hệ quả:** tuần tương đối, không tự đặt deadline lịch.

## ADR-003 — 2026-09-15 — Tách text benchmark và graph evaluation

**Trạng thái:** accepted for planning; graph protocol chọn ở SG-014.
**Lý do:** BEIR qrels không phải graph features; bổ sung citation có nguy cơ chứa đáp án.
**Quyết định:** tuyến A benchmark text nguyên bản; tuyến B OpenAlex custom protocol có masking; bảng external enrichment nếu có phải riêng.
**Hệ quả:** không tuyên bố score graph là official BEIR khi inputs khác.

## ADR-004 — 2026-09-15 — Registry và bàn giao trên đĩa

**Trạng thái:** accepted.
**Quyết định:** task specs ở TASKS.md; mutable status/evidence ở tasks.json; state.json chỉ điều phối; mỗi phiên có log và HANDOFF.
**Hệ quả:** đọc bằng chứng trước tiếp nối, một người điều phối board; kiểm tra tự động read-only.

## ADR-005 — 2026-09-15 — Định nghĩa đóng góp nghiên cứu

**Trạng thái:** accepted for planning.
**Quyết định:** kiểm nghiệm hybrid retrieval + graph + tuổi paper; chưa claim novelty/SOTA hay tăng 3–5%.
**Hệ quả:** kết quả âm vẫn có giá trị nếu protocol chặt và phân tích đầy đủ.

## ADR-006 — 2026-09-15 — Tiếng Việt có đánh giá riêng

**Trạng thái:** accepted for planning.
**Quyết định:** VN nghĩa giao diện và query Việt → corpus Anh; cần model/cách dịch phù hợp và pooled human labels.
**Hệ quả:** English benchmark không chứng minh khả năng cross-lingual; 50 query là mục tiêu timebox, giảm quy mô phải ghi rõ.

## Mẫu ADR tiếp theo

ID: ADR-011
Ngày:
Trạng thái: proposed / accepted / superseded
Task liên quan:
Bối cảnh:
Các lựa chọn:
Quyết định và bằng chứng:
Hệ quả:
Thay thế ADR nào (nếu có):

## ADR-007 — 2026-09-15 — 7 tuần, 2 người, agent hỗ trợ

**Trạng thái:** accepted; thay thế giả định lịch ở ADR-002.
**Nguồn:** người dùng xác nhận còn khoảng 7 tuần, có 2 người, dùng Kaggle/Colab và sẽ cân nhắc thuê GPU nếu cần.
**Quyết định:** 7 tuần với tuần 7 dự phòng/bảo vệ; 10–20K OpenAlex core; pretrained inference, fine-tune để stretch. Dự trù 12–15 giờ/người/tuần, cần theo dõi tải công việc thực tế.
**Cộng tác:** agent hỗ trợ module/checks; hai người chịu trách nhiệm nhãn, insight, review và nội dung bảo vệ. Không coi phân vai là đã tạo task/agent hay cấp quyền chi tiền.
**Hệ quả:** GPU profiling/resume vào tuần 1–2; chưa thuê; kết quả âm vẫn được báo cáo.

## ADR-008 — 2026-09-15 — Giới hạn annotation và bỏ phụ thuộc GPU khỏi scaffold

**Trạng thái:** accepted for planning; thu gọn mục tiêu annotation ở ADR-006.
**Quyết định:** core VN khoảng 30 query, 10 dev/20 test, pool top-10 từ 3 phương pháp, mục tiêu khoảng 600 cặp unique. SG-033 dự trù 16 giờ-người, cập nhật từ pilot 5 query. Có thể tăng 50 query nếu còn nguồn lực; luôn báo hạn chế cỡ mẫu/pooling.
**Lý do:** hai người cần đọc paper và gán nhãn thật trong 7 tuần; agent không thay thế được nhãn người.
**Phụ thuộc:** SG-005 cần SG-001, không chờ toàn bộ GPU pilot SG-002; setup local có thể bắt đầu độc lập. Encoding SG-019 vẫn cần compute pilot hoàn tất.
**Hệ quả:** tổng core 142 giờ-người có agent hỗ trợ; tiếp tục việc local được nếu tài khoản notebook chưa sẵn.

## ADR-009 — 2026-09-15 — Model routing và bàn giao theo lane

**Trạng thái:** accepted for workflow; không phải quyền chạy toàn bộ backlog.
**Nguồn:** người dùng yêu cầu gán model cho các ID và chiến lược cửa sổ chat; đối chiếu OpenAI Docs và model catalog của host hiện tại.
**Quyết định:** routing đủ SG-000–049 với primary/review profile, reasoning, lane và human gate. Astra cho phương pháp/gates/thống kê, Sol cho pipeline khó/điều phối, Terra cho triển khai rõ spec; Luna chỉ hỗ trợ cơ học. Chưa có benchmark model trên dự án.
**Cửa sổ:** 7 lane logic, chỉ mở khi cần; thường C + một worker + V. Mỗi phiên 1–3 task liên quan, bàn giao trên đĩa trước đổi context. Review học thuật dùng context mới và snapshot xác định; nhãn và nghiệm thu con người không được thay bằng AI.
**Quyền ghi:** làm rõ ADR-004: coordinator duy nhất ghi shared board/state/HANDOFF/chat registry. Worker/reviewer có log/report riêng. Một phiên độc lập có thể kiêm điều phối nếu không có coordinator khác.
**Hệ quả:** thêm routing/matrix, chiến lược, templates, tra cứu task và validator. Không đổi dependency/lịch core, không mở thread/agent, không đổi model runtime, không mua compute. Actual model/session chỉ ghi khi xác minh được.

## ADR-010 — 2026-09-15 — Chấp thuận scope và đẩy mốc hoàn thành sớm

**Trạng thái:** accepted.
**Task liên quan:** SG-001; ảnh hưởng lịch toàn bộ core.
**Nguồn:** người dùng xác nhận task đã được review, yêu cầu đánh giá/hoàn tất và cho phép thời hạn linh động miễn trước tháng 12/2026, ưu tiên làm sớm để dành thời gian cho học phần khác.
**Quyết định:** chấp thuận problem, 4 RQ và core/non-core trong SCOPE để triển khai. Đặt target nội bộ 2026-10-31; giữ 2026-11-01–2026-11-30 làm buffer cho lỗi, rubric mới, tái lập và bảo vệ. Không mở stretch chỉ vì có buffer.
**Minh bạch review:** không có review report riêng tồn tại trước closeout; ghi xác nhận trực tiếp của project owner là human review confirmation và thực hiện acceptance audit. Không gọi đó là independent model audit.
**Yêu cầu còn mở:** deadline chính thức, rubric/weights, format nộp, chính sách AI/pretrained/external data và quy định nhóm vẫn OPEN/PARTIAL; phải cập nhật khi có nguồn và trước SG-045.
**Hệ quả:** SG-001 có thể DONE; next SG-002. Nếu lịch chính thức sớm hơn target, lịch chính thức ưu tiên và phải cập nhật state/ADR.

## ADR-011 — 2026-09-15 — Miễn hoạt động đọc sâu của SG-003

**Trạng thái:** accepted.
**Task liên quan:** SG-003; mở dependency SG-004.
**Nguồn:** project owner yêu cầu bỏ qua hoạt động hai thành viên đọc sâu RW02, RW06 và RW10, chuyển SG-003 thành DONE và mở SG-004 nhưng chưa triển khai.
**Quyết định:** chấp nhận fresh-context review PASS làm gate kiểm tra artifact. Miễn phần đọc sâu ba paper của hai thành viên như một deviation có chủ ý; không ghi hoặc suy rằng hoạt động này đã hoàn tất.
**Hệ quả:** SG-003 chuyển DONE. SG-004 đủ dependency và là task kế tiếp ở trạng thái TODO, chưa owner/session/claimed paths. Rủi ro còn lại là hai thành viên có thể chưa giải thích sâu RRF, SciRepEval và time-balanced centrality khi bảo vệ; có thể đọc bù sau nếu cần.
