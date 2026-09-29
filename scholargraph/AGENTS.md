# ScholarGraph — Quy tắc cho mọi phiên làm việc

## 1. Phạm vi và thứ tự ưu tiên
- Dự án ở `D:/Web_mining_20261/scholargraph`. Không sửa tệp bài giảng ở thư mục gốc trừ khi người dùng yêu cầu rõ.
- Chỉ dẫn hệ thống/developer và yêu cầu mới nhất của người dùng được ưu tiên. Kế hoạch là danh mục công việc; thực hiện phần đã được giao.
- Mỗi task có ID cố định `SG-NNN`. Vai trò trong kế hoạch là vai trò nhóm, không phải lệnh tạo agent hoặc task trong ứng dụng.
- Không tự tạo subagent, task mới, automation, tài khoản, dịch vụ trả phí hay xuất bản chỉ vì backlog có mục liên quan.

## 2. Đọc trước khi sửa
Đọc theo thứ tự:
1. `management/state.json`: trạng thái điều phối, task tiếp theo.
2. `management/HANDOFF.md`: đầu vào, việc dở, bước tiếp tục.
3. `management/tasks.json`: trạng thái và dependency chính thức.
4. `management/model_routing.json`, `management/chat_registry.json` và `docs/MODEL_AND_CHAT_STRATEGY.md`: model/role, giới hạn file và chế độ review.
5. Task card tương ứng trong `docs/TASKS.md`.
6. `management/DECISIONS.md`; `docs/RESEARCH_PROTOCOL.md` khi chạm dữ liệu/mô hình/đánh giá.
7. Các file thật liên quan, môi trường và thay đổi chưa hoàn thành.

Không đọc toàn bộ dataset/log cũ mỗi lần. Tra cứu phiên được dẫn trong HANDOFF rồi mở thêm khi cần.

## 3. Nguồn sự thật
- `docs/MASTER_PLAN.md`: phạm vi, giả định, milestone.
- `docs/TASKS.md`: việc phải làm, đầu ra, điều kiện nghiệm thu.
- `management/tasks.json`: trạng thái từng task, owner, dependencies, bằng chứng.
- `management/state.json`: con trỏ phiên hiện tại, ưu tiên kế tiếp, câu hỏi chưa chốt.
- `management/HANDOFF.md`: hướng dẫn tiếp tục đọc được bởi con người.
- `management/logs/SESSION-*.md`: lịch sử đã làm và đã kiểm tra.
- `management/DECISIONS.md`: quyết định có lý do; thêm mục mới khi thay đổi, không xóa lịch sử.
- `management/model_routing.json`: khuyến nghị model/effort, lane, review và human gate cho từng ID; không phải cấu hình runtime hay lịch sử model đã chạy.
- `management/chat_registry.json`: lane logic và các phiên thật được đăng ký khi mở; không phải scheduler/lock.
- `docs/TASK_MODEL_MATRIX.md` là bảng đọc nhanh của routing; cập nhật cùng JSON khi thay đổi, không sao chép mutable status vào bảng.
- Dữ liệu/metrics/run files mới là bằng chứng thực nghiệm. Báo cáo hay nội dung hội thoại không thay thế chúng.
- Nếu các nguồn mâu thuẫn: kiểm tra artifact, log và yêu cầu mới nhất; ghi reconciliation; không suy ra DONE từ một câu mô tả.

## 4. Vòng đời task
Trạng thái: `TODO → IN_PROGRESS → REVIEW → DONE`; dùng `BLOCKED` khi có vướng mắc cụ thể và `DEFERRED` cho phần ngoài lịch chính.
- Trước khi làm: dependency phải DONE; coordinator đọc lại board, đặt owner/session và phạm vi file đang sửa; cập nhật state. Worker chưa được nhận task chỉ chuẩn bị read-only.
- TODO chưa đủ dependency chỉ là chưa sẵn sàng, không cần gắn BLOCKED.
- Giữ một task IN_PROGRESS cho một người; chỉ mở thêm nếu công việc độc lập và đã được phân công rõ.
- Không coi registry là khóa máy tính nguyên tử. Hai phiên không được cùng sửa board hoặc cùng module; nếu phát hiện overlap, chọn phần độc lập và bàn giao cho người điều phối.
- Không chiếm task của phiên khác dựa vào tuổi timestamp. Xác minh phiên đã dừng hoặc có bàn giao.
- REVIEW nghĩa là đầu ra đã có nhưng kiểm tra chưa xong. Có thể tự kiểm tra rõ ràng nếu chỉ một người; không tự nhận có reviewer độc lập.
- DONE yêu cầu artifact tồn tại, acceptance được đáp ứng, kiểm tra liên quan có kết quả, evidence và log đã cập nhật.
- BLOCKED phải ghi lý do, đã thử gì, cần đầu vào nào và task độc lập nào còn làm được.
- Nếu sửa acceptance/phạm vi sau khi hoàn thành, ghi decision và mở lại task hoặc tạo task ID mới.

### Quyền ghi khi có nhiều chat

- Chỉ một coordinator C được ghi tasks.json, state.json, HANDOFF.md và chat_registry.json. Worker sửa module, log/packet riêng đã được giao; reviewer chỉ ghi report riêng và không sửa implementation được review.
- Khi chỉ một chat làm, có thể kiêm coordinator + worker và ghi rõ trong log. Không suy ra quyền điều phối nếu phiên khác còn giữ vai trò đó.
- Mặc định một worker sửa implementation; thêm worker chỉ khi người dùng phân công rõ, đủ dependency và không trùng file. Registry không phải lock nguyên tử.
- Đăng ký session thực tế và active_assignments khi giao worker; không bịa thread ID/model thực tế. Ghi unknown/null nếu chưa xác minh được.
- Không đổi model bằng cách tự sửa cấu hình app. Routing là đề xuất; nếu cần đổi model/effort, nêu rõ để người dùng chọn hoặc dùng công cụ trong phạm vi được cấp.
- Task có review_mode=fresh_context_required cần report từ phiên/context review mới trước DONE. Task có human_approval_required=true cần xác nhận thật của người phụ trách trong log/verification. Không tự nhận đã có human review. Các gate mới không hồi tố model/approval của SG-000 đã hoàn tất.

## 5. Checkpoint và kết thúc phiên
Ghi checkpoint sau một đầu ra quan trọng, trước khi chuyển task, trước khi chạy dài, trước khi kết thúc phiên hoặc khi biết sắp mất context.
Các bước cập nhật shared state dưới đây do coordinator thực hiện. Worker/reviewer ghi log và packet/report riêng, gửi đề xuất để coordinator cập nhật; không cùng sửa file điều phối.
1. Cập nhật task status và evidence trong tasks.json.
2. Cập nhật state.json: active_tasks, next_task_id, updated_at, last_session_log.
3. Cập nhật HANDOFF: task đang dở, file đã đổi, lệnh kiểm tra, kết quả, vướng mắc, bước kế tiếp cụ thể.
4. Ghi log phiên theo template. Mỗi phiên một file; thêm mục mới, không sửa nội dung lịch sử đã chốt để làm đẹp kết quả.
5. Chạy `scripts/check_project.ps1`; nếu lỗi, sửa phần không nhất quán trước bàn giao.
6. Ghi model/effort thực tế nếu xác minh được, lane/session, review/human gate và file đang có người sửa. Không lấy model khuyến nghị làm bằng chứng model đã chạy.

Timestamp dùng ISO 8601 với múi giờ; ngày làm việc tại Việt Nam UTC+07:00. Nếu bị dừng đột ngột, phiên sau đọc artifact trước, khôi phục phần đã làm rồi ghi log; không chạy lại thí nghiệm dài một cách mù quáng.

## 6. Tính trung thực nghiên cứu
- Không hard-code hoặc chặn ngưỡng dưới cho metric. Thiếu run hợp lệ thì báo “chưa đo”.
- Không dùng test labels/qrels làm feature, graph edge, seed PPR, prompt sinh query hay dữ liệu tune.
- Không xem cạnh trích dẫn bị giữ lại để đánh giá là đầu vào đã biết. Kiểm tra cả chiều đảo và các feature suy ra.
- BEIR text benchmark và OpenAlex graph experiment là hai giao thức khác nhau; không gộp kết quả.
- Không giả sử BEIR có full citation graph. Đồ thị bổ sung phải có provenance, mapping, kiểm tra leakage và nhãn “external data”.
- Embedding được pretrained bằng citation có thể từng thấy benchmark; đọc model/data card, công bố nguy cơ overlap.
- Chỉ tune trên dev. Dataset chỉ có test cần dev khác hoặc cấu hình cố định trước test.
- “Thêm trọng số thời gian” là giả thuyết nghiên cứu; chưa được gọi là mới/SOTA hoặc đảm bảo tăng điểm.
- Kết quả âm và lỗi cũng phải lưu. Không chọn seed đẹp nhất hoặc thay metric chính sau khi xem test.
- Mỗi bảng kết quả truy ngược được về run ID, data hash, model revision, config, code version và evaluator.
- Không gọi citation count/PageRank là độ đúng đắn của một paper.

## 7. Kỹ thuật và dữ liệu
- Dùng môi trường riêng của ScholarGraph; khóa version sau kiểm tra tương thích.
- Không ghi đè benchmark gốc; snapshot bất biến, bản xử lý có manifest riêng.
- Raw corpus/embeddings/checkpoints đặt trong data/artifacts của ScholarGraph; dùng ID có namespace.
- Dữ liệu demo phải có nguồn, snapshot ID; fixture phải đánh dấu `synthetic=true` và không xuất hiện trong kết quả học thuật.
- Log không chứa API key, token hoặc thông tin nhạy cảm. Metadata thiếu phải được hiển thị là thiếu.
- Không ghi đè run hoàn tất; tạo run ID mới. Run dở có trạng thái rõ để tiếp tục hoặc hủy có ghi nhận.
- Thêm test khi cần kiểm tra thuật toán, metrics, split, graph, API, resume/download integrity; không viết test chỉ đếm file hay khớp implementation.
- Chống silent bypass: Không dùng .get() mặc định hay fallback che giấu thành phần bắt buộc thiếu hoặc lỗi. Bắt buộc báo FAIL rõ và CLI thoát mã nonzero (1). Không thay thế phép đo chưa thực hiện bằng 0 hay chuỗi rỗng.
- Bắt buộc Negative / Adversarial Testing: Phải có test cases phá hủy trên fixture dị dạng trong thư mục tạm (thiếu split/file bắt buộc, dữ liệu khuyết thiếu text/title, rò rỉ nhãn, CLI subprocess exit code 1 khi có lỗi).
- Đồng bộ 1:1 Narrative và Dữ liệu: Mọi khẳng định trong log/report/Data Card phải khớp toán học với toàn bộ biến đếm thực tế; không suy đoán một chiều.
- Sau thay đổi tài liệu, kiểm tra liên kết/trạng thái; sau thay đổi mã, chạy test liên quan.
- Khi có Git: kiểm tra diff đầu phiên; commit nhỏ theo task nếu thuộc phạm vi được giao; không đụng file người khác.

## 8. Định nghĩa hoàn thành
Một task chỉ DONE khi: đúng scope, đầu ra có thật, acceptance đạt hoặc deviation được ghi rõ, đã vượt qua cả positive tests lẫn negative/adversarial tests phá hủy, kiểm tra phù hợp hoàn tất, log và HANDOFF đồng bộ. Hoàn tất task planning không đồng nghĩa hoàn tất ứng dụng.
