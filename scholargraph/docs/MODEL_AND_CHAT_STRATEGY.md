# Chiến lược model và cửa sổ chat

Áp dụng cho ScholarGraph VN: 2 người, 7 tuần, agent hỗ trợ triển khai. Ngày đối chiếu model: 2026-09-15. Mục tiêu là chất lượng có thể kiểm chứng và hai người hiểu được sản phẩm; không có model nào bảo đảm A+.

## 1. Cách dùng ngay

1. Tra ID trong [bảng 50 task → model](TASK_MODEL_MATRIX.md), hoặc chạy `scripts/get_task_brief.ps1 -TaskId SG-001` từ thư mục ScholarGraph.
2. Chat điều phối C xác minh dependencies, task card, phạm vi được người dùng giao và các file đầu vào. Chưa có đầu vào thì không giao worker viết dựa trên giả định.
3. Người dùng chọn model/mức suy luận theo bảng khi mở phiên. Dùng [mẫu bắt đầu chat](../management/templates/CHAT_START.md). Model của task ưu tiên hơn default của lane.
4. Worker làm một phần có acceptance rõ, tự kiểm và lưu [bàn giao](../management/templates/CHAT_HANDOFF.md). Coordinator cập nhật board.
5. Nếu task yêu cầu review riêng, mở phiên V theo [mẫu review](../management/templates/REVIEW.md); xử lý findings rồi người phụ trách xác nhận gate nếu có.

Đây là cấu hình hướng dẫn trên đĩa, **không phải cấu hình runtime của Codex**: chưa mở cửa sổ mới, chưa chuyển model của chat này, chưa khởi chạy agent hay thí nghiệm. Không dùng các ID lane C/R/... làm ID task thật trong ứng dụng. Model routing cho SG-000 chỉ là khuyến nghị nếu có công việc quản trị tiếp nối, không sửa lịch sử model phiên trước.

## 2. Chọn model theo rủi ro

Phân loại chung của OpenAI: Astra cho suy luận/code phức tạp, Sol cho công việc chuyên môn phức tạp, Terra cân bằng năng lực/chi phí, Luna cho tác vụ nhạy cảm chi phí và khối lượng lớn. [Nguồn chính thức](https://developers.openai.com/api/docs/models).

Việc áp dụng vào ScholarGraph dưới đây là **khuyến nghị của dự án**, chưa phải kết quả benchmark giữa các coding model:

| Model | Vai trò đề xuất | Mức suy luận |
|---|---|---|
| GPT-6 Astra | Protocol, leakage, gate graph, thống kê, diễn giải claim và review học thuật | High; XHigh tại SG-004/011/014/027/030 |
| GPT-5.6 Sol | Điều phối chính, pipeline khó, GPU/resume, RRF/PPR, tích hợp và debug xuyên module | High; Medium khi chỉ đọc tiến độ |
| GPT-5.6 Terra | Scaffold, tải snapshot theo spec, baseline chuẩn, API/UI, đóng gói | High cho task chính; Medium cho chỉnh sửa nhỏ đã rõ yêu cầu |
| GPT-5.6 Luna | Trợ lý tùy chọn: chỉnh format, chuẩn hóa tên, tóm tắt log đã xác minh, checklist | Medium; không làm chủ task học thuật/core |

Bảng 50 ID có 18 task Astra, 20 Sol và 12 Terra, bao gồm task setup đã xong và 4 stretch chưa mở. Đây là số task, **không phải tỷ lệ token/chi phí hoặc thời gian**. Không bắt buộc sử dụng đủ 4 model; có thể chỉ dùng Sol + Astra nếu việc chuyển model làm mất thời gian, nhưng phải ghi override và giữ nguyên review/gates.

Không dùng mức max/ultra mặc định. Chỉ tăng suy luận khi bài toán thực sự chưa được giải quyết và có đầu vào đầy đủ. Thiếu rubric, dataset hoặc log lỗi không được giải quyết bằng tăng mức suy luận.

Các model này là trợ lý làm dự án; **không phải embedding/reranking model chạy trên Kaggle/Colab**. Model học thuật được chọn riêng ở SG-017, GPU được đo ở SG-002/019. Đổi coding model không tự tạo thêm GPU, không chứng minh quota notebook đủ.

Không suy API context window, giá API hay benchmark nhà cung cấp thành quota/chi phí thực tế của gói Codex. Khả năng truy cập và giới hạn phải kiểm tra trên tài khoản khi dùng; kế hoạch này không mua dịch vụ.

## 3. Chia cửa sổ: 7 vai trò, mở theo nhu cầu

Một lane là một dòng công việc có thể trải qua nhiều phiên chat, không phải một chat kéo dài cả 7 tuần. [chat_registry.json](../management/chat_registry.json) lưu lane và sau này lưu các phiên thật; hiện chưa liên kết thread nào.

| Lane | Tên gợi ý | Dùng khi nào | Giới hạn context |
|---|---|---|---|
| C | SG · Điều phối · W01 | Chọn việc sẵn sàng, scope, nhận bàn giao, cập nhật tiến độ | Không nhét stack trace dài hoặc toàn bộ paper/code |
| R | SG · Research/Eval · SG-004 | Literature, protocol, leakage, tuning, thống kê, VN | Tách phiên thiết kế protocol với phiên final analysis |
| D | SG · Data · SG-013 | Môi trường, schema, ingestion, audit, graph masking | Tách OpenAlex ingestion với BEIR audit nếu khác đầu vào |
| M | SG · Methods · SG-019 | Encoding, lexical/dense/hybrid, PPR, reranking | Mở phiên mới khi chuyển text retrieval sang graph |
| P | SG · Product · SG-035 | API/UI, offline, integration, profiling | Gói 1–3 task dùng chung module và acceptance |
| W | SG · Writing · SG-043 | Reproduce, report, slides, defense | Chỉ nhập bảng/evidence đã được chốt, không tự đoán kết quả |
| V | SG · Review · SG-027 | Kiểm tra một task khó hoặc milestone | Phiên mới, đọc protocol + artifact; không dựa chỉ vào lời worker |

Tên trên là mẫu để người dùng đặt, không phải những chat đã tồn tại. Một phiên chỉ có một role chính; chuyển worker sang reviewer trong cùng lịch sử không tạo review độc lập.

Mặc định 2–3 chat hoạt động: **C + một worker + V khi có đầu ra để review**. V có thể review snapshot đã chốt của task trước khi worker làm task khác không ảnh hưởng snapshot. Nếu review file đang tiếp tục thay đổi thì dừng worker hoặc chốt snapshot trước.

Chỉ thêm worker thứ hai khi người dùng giao rõ, prerequisites đều DONE và phạm vi file không giao nhau. Trước SG-005 chưa có Git đã xác minh, giữ một worker sửa implementation. Sau khi có Git, checkout/worktree riêng là lựa chọn khi thực sự triển khai song song; vẫn cần tích hợp và xác minh input commit/artifacts. Không coi worktree là tự đồng bộ dataset, environment hoặc bảng trạng thái.

## 4. Một người ghi bảng tiến độ

Coordinator C là bên duy nhất ghi `tasks.json`, `state.json`, `HANDOFF.md`, `chat_registry.json` khi nhiều phiên cùng làm. Worker chỉ sửa file đã giao, log riêng và handoff riêng; không tự claim/DONE task trên shared board. Reviewer không sửa implementation, chỉ ghi review report được chỉ định.

Một chat làm độc lập có thể kiêm coordinator + worker, nhưng phải ghi rõ. Không được có hai coordinator cùng hoạt động. Bàn giao điều phối cần xác nhận bên trước đã dừng hoặc trao quyền; timestamp cũ không đủ để giành quyền.

Khi giao worker, C ghi owner/session/claimed_paths vào task hiện có; đăng ký phiên trong `chat_registry.sessions` và cập nhật `active_assignments`. Đường dẫn log/packet phải tồn tại trước khi dẫn tới. Các trường này là ghi nhận, không phải lock nguyên tử hay scheduler.

Mẫu entry phiên thật (chỉ thêm khi phiên đã được mở và có log):

```json
{
  "session_id": "SESSION-YYYYMMDD-NNN",
  "chat_id": "M",
  "app_thread_id": null,
  "task_ids": ["SG-019"],
  "actual_model": null,
  "actual_reasoning": null,
  "log_path": "management/logs/SESSION-YYYYMMDD-NNN.md",
  "status": "active"
}
```

Để null khi không có ID/model thực tế được công cụ hoặc người dùng xác nhận; không điền model khuyến nghị vào trường “actual”. Các status phiên: active/checkpoint/completed/interrupted. `active_assignments` dùng `task_id`, `session_id`, `chat_id`; chỉ cho task IN_PROGRESS/REVIEW. Kết thúc phiên thì gỡ assignment đã hoàn thành hoặc bàn giao owner đúng phiên mới. Một lane có nhiều phiên lịch sử; `app_thread_id` tại lane chỉ là con trỏ tùy chọn tới phiên hiện tại.

## 5. Vòng đời context để không đứt chuỗi

**Trước phiên:** đọc AGENTS, state, HANDOFF, registry, routing, task card, decisions và đúng phần protocol liên quan. Tiếp đó kiểm tra file thật. Không đọc toàn bộ TASKS 50 card, mọi log hay raw corpus vào chat nếu không cần.

**Trong phiên:** giữ 1–3 task liên quan; task sau chỉ bắt đầu khi task trước đủ dependencies và đã được coordinator chốt DONE. Đây là gợi ý phạm vi, không phải giới hạn kỹ thuật của model. Checkpoint sau đầu ra quan trọng, trước notebook/run dài, trước chuyển task hoặc khi context bắt đầu nhiễu. Có thể rà checkpoint sau khoảng 60–120 phút, nhưng không cắt ngang một thao tác đang ghi artifact.

**Mở phiên mới khi:** chuyển nhóm vấn đề, qua mốc freeze, có quá nhiều nhánh debug không còn hữu ích, agent lặp lại giả định đã sửa, hoặc nhiều lần nén context làm bỏ sót quyết định. Không dựa vào một tỷ lệ token giả định; số context tối đa của API không phải ngưỡng nên dùng hết trong chat dự án.

**Trước khi đóng:** lưu handoff khoảng 400–800 từ nếu đủ, không giới hạn cứng. Gồm task/scope, phiên bản input, file đổi, lệnh và exit code thật, decisions, lỗi còn lại, run/process đang chạy, bước tiếp tục chính xác. Chi tiết dài nằm trong artifact/log có đường dẫn. Không đưa secrets hay toàn bộ dataset vào packet.

**Phiên kế tiếp:** mở lại cùng project, nhận đúng phạm vi, đọc packet và kiểm tra artifact trước khi tiếp tục. Không chỉ dán câu “tiếp tục như trước”. Đổi model không được coi là một biên review/context mới; nếu cần fresh review hãy dùng phiên mới với nguồn đầu vào có kiểm soát.

Nếu notebook bị ngắt: kiểm tra run ID/shard manifest và output đã lưu bền vững; không encoding lại mọi thứ chỉ vì chat trước đã đóng. Cửa sổ chat không phải kho checkpoint GPU.

## 6. Review và trách nhiệm của hai bạn

- Task “tự kiểm được”: test liên quan + evidence + coordinator xem acceptance; không bắt buộc mở V cho từng chỉnh sửa nhỏ. Có thể gom review tại milestone.
- Task “review riêng”: worker tự kiểm trước; V đọc acceptance/protocol, code/data/run thực tế, ghi findings với mức độ và bằng chứng. Cùng model ở context mới vẫn là một lượt kiểm tra tách biệt, nhưng không được gọi là thẩm định con người độc lập hay bảo đảm không có lỗi tương quan.
- Reviewer kiểm tra snapshot xác định: commit nếu có, nếu chưa có thì file list + SHA-256 cho đầu vào quan trọng. Worker không sửa snapshot giữa lượt review. Sửa lỗi xong phải chỉ rõ phiên bản mới và kiểm lại vùng ảnh hưởng.
- Finding ảnh hưởng metric, split, leakage, nhãn, loss dữ liệu hoặc correctness phải được xử lý trước DONE. Bất đồng phương pháp đưa hai bạn quyết định, không “bỏ phiếu” giữa nhiều agent.
- Với `human_approval_required=true`, lưu ai duyệt, thời điểm và bằng chứng xác nhận trong log/verification trước DONE. Agent không tự gán tên thành viên để giả lập approval. Gate mới không hồi tố bắt làm lại SG-000.

Phân công con người đề xuất: bạn A phụ trách câu hỏi nghiên cứu, protocol và báo cáo; bạn B phụ trách data/system, reproducibility và demo. Cả hai cùng gán nhãn SG-033 độc lập trước thảo luận, và đổi vai giải thích mỗi tuần. Đây là phân vai đề xuất, không phải hai tài khoản/agent đã tạo.

Mỗi task xong agent trả “gói hiểu bài”: đã làm gì; thuật toán bằng lời thường; một ví dụ nhỏ; bằng chứng đúng; một hạn chế/câu hỏi bảo vệ. Hai bạn cần tự trả lời lại và tự chạy ít nhất một kiểm tra liên quan. Có thể dùng một phiên R chỉ đọc để học, nhưng không biến câu trả lời của tutor thành nhãn hay kết quả thực nghiệm.

## 7. Lịch dùng chat trong 7 tuần

| Tuần | Chat thường dùng | Mục đích bàn giao |
|---|---|---|
| 1 | C, R, D; V ở gate | SG-001–008: scope, protocol, compute pilot, môi trường, schema/evaluator |
| 2 | D, R, M | SG-009–016 và chuẩn bị SG-017: data, split, BM25 pilot, graph feasibility |
| 3 | M, R; P khi đủ deps | SG-017–021: text/dense/hybrid; SG-031 chuẩn bị query; API khi đầu vào sẵn |
| 4 | M, R, V | SG-022–027: graph, rerank, tune và main freeze |
| 5 | R, P, M | SG-031–039: VN baseline/nhãn và demo; chỉ chạy task đủ prerequisites |
| 6 | R, P, V | SG-028–030/034/040: final eval, ablation, thống kê, hiệu năng |
| 7 | W, C, V | SG-041–045: tái lập, report, diễn tập và gói nộp |

Bảng tuần là định hướng, không thay DAG chính thức. SG-046–049 vẫn DEFERRED. Không mở task vượt freeze chỉ để khai thác một model mạnh hơn.

Trình tự đầu tiên có thể giao sau bước setup hiện tại: SG-001 và SG-002 đều sẵn sàng sau SG-000. Mặc định làm lần lượt; có thể giao song song chỉ khi người dùng yêu cầu và không trùng file. Sau SG-001: SG-003 và SG-005 sẵn sàng. SG-004 cần SG-003; SG-006 cần SG-004 + SG-005. Không chạy SG-019 trước khi compute pilot và corpus/model đầu vào được chốt.

## 8. Khi cần đổi model hoặc tiết kiệm

1. Nếu thiếu dữ liệu/quyền, ghi blocker và lấy đúng đầu vào; không đổi model để né việc xác minh.
2. Nếu sau hai cách thử có bằng chứng vẫn không qua acceptance, dừng vòng lặp, ghi reproducer + failures + hypothesis; đề nghị Terra → Sol → Astra. Hai lần là ngưỡng điều phối, không giới hạn debug cứng.
3. Nếu model được chỉ định không khả dụng: báo người dùng. Có thể đề nghị Sol thay Astra tạm thời để chuẩn bị evidence, nhưng không bỏ review/human gate và không gọi đó là cùng mức bảo đảm.
4. Muốn ít chuyển model: Sol High cho implementation, Astra High/XHigh cho gate; giữ nguyên task IDs/chat lanes. Muốn tiết kiệm thêm: Terra cho task rõ spec; Luna chỉ xử lý phần cơ học, được model chủ task kiểm lại.
5. Log model thực tế, effort nếu biết, số vòng sửa, thời gian người review và lỗi lọt; sau tuần 1–2 dùng số liệu này để điều chỉnh routing qua ADR. Không có số liệu thì nói “chưa đo”; không đặt phần trăm tiết kiệm tùy ý.

Nguồn routing máy đọc: [model_routing.json](../management/model_routing.json). Kiểm tra nhất quán bằng `scripts/check_project.ps1`; checker chỉ xác minh cấu trúc/ràng buộc, không xác nhận model thực tế của ứng dụng hay năng lực khoa học.
