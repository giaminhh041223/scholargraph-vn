# Checkpoint cuối — machine_B dev v2

Đã đọc query_vi, title và abstract của toàn bộ 227 cặp từ đúng 10 file `input/vn2_dev_001.jsonl` đến `input/vn2_dev_010.jsonl`, rồi chấm semantic độc lập theo RUBRIC.md. Các quyết định cùng lý do cụ thể tiếng Việt nằm trong 10 file `decisions_*.tsv`; Python chỉ chuyển các quyết định đã chấm sang schema JSONL và kiểm tra tính toàn vẹn.

## Đầu ra

- File ghép: `../vn2_labels_machine_B_dev.jsonl` — 227 cặp, 10 query, không trùng cặp, coverage khớp chính xác input.
- 10 checkpoint: `vn2_labels_machine_B_001.jsonl` đến `vn2_labels_machine_B_010.jsonl`.
- Phân bố nhãn: 0 = 74; 1 = 113; 2 = 18; unjudged = 22. Tổng 74 + 113 + 18 + 22 = 227.
- Cả 22 cặp thiếu abstract đều unjudged; không có cặp có abstract được chấm unjudged.
- Mỗi dòng có đúng tám trường theo rubric, annotator `machine_B`, annotator_type `machine`, experimental `true`, round `independent`, note không rỗng.
- Kiểm tra chi tiết: `validation.json`. Cả 13 negative cases thực thi CLI qua subprocess đều báo FAIL rõ và exit code 1: thiếu file, JSON sai, thiếu title, text-only, thiếu trường abstract, abstract sai kiểu, score ngoài biên, title-only bị gán nhãn số, note rỗng, cặp trùng, split test giả lập ngoài packet, metadata giả human, thiếu cặp.

## Giới hạn

Đây là nhãn thử nghiệm máy dựa trên nội dung abstract được cấp; không phải nhãn người và không hoàn tất SG-033. Chỉ đánh giá chất lượng/coverage/schema của artifact; chưa đo độ đúng so với người hoặc độ đồng thuận giữa máy. Không đọc nhãn người, qrels, test thật, vn_pool_provenance, output machine_A hoặc web. Không chỉnh official labels, configs, boards/shared state và không commit.

Abstract có thể bị cắt hoặc không nêu baseline/thiết kế/kết quả đủ chi tiết; note ghi rõ phần thiếu, không bổ sung kết luận từ tri thức ngoài packet. Các label 1 phản ánh câu trả lời một phần hoặc cùng chủ đề nhưng khác khía cạnh/quy mô, đúng rubric; không diễn giải là đáp ứng toàn bộ query.

Không xác minh được runtime model/effort từ API của worker nên không coi chỉ dẫn model/effort là bằng chứng runtime thực tế.

Đầu ra phân công đã hoàn tất. Bước tiếp theo thuộc coordinator: kiểm tra artifact và thực hiện so sánh nếu nằm trong yêu cầu người dùng; worker dừng ở đây.
