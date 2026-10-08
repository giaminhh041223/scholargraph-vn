# Bàn giao machine_A — dev v2

Đã đọc title, abstract và query_vi của toàn bộ 227 cặp trong 10 input JSONL; tự chấm semantic theo RUBRIC. Các quyết định cụ thể được nhập vào checkpoint bằng write_checkpoint.py; script không phân loại hay sinh quyết định.

- File ghép: ../vn2_labels_machine_A_dev.jsonl
- 10 checkpoint: vn2_dev_001.jsonl đến vn2_dev_010.jsonl trong thư mục này.
- Tổng: 227 cặp duy nhất, 10 query; 0=80, 1=106, 2=19, unjudged=22.
- Cả 22 abstract thiếu được giữ unjudged.
- Verification: verification.json kiểm schema, coverage, tính duy nhất và missing-abstract guard; không xác nhận correctness semantic.
- Adversarial: adversarial_verification.json có 1 happy-path exit 0 và 10 fixture lỗi exit 1 qua CLI subprocess, gồm thiếu file/query/cặp, thiếu title/note, label ngoài biên, title-only có nhãn số, cặp trùng, test-split và label leakage. Fixture tạm được tạo bên trong machine_A/ rồi dọn sau kiểm tra.
- Không đọc human labels, qrels, test corpus, vn_pool_provenance, báo cáo có nhãn, bản dịch máy hoặc output machine_B; không web. Test-split leakage ở đây là trường query_id giả lập trong fixture, không đọc dữ liệu test.
- Đây là machine experiment với annotator_type=machine, experimental=true, round=independent; không hoàn tất SG-033 và không thay human gate.
- Không commit, không sửa official labels/configs/boards/shared state.

Công việc chấm machine_A đã xong. Bước điều phối tiếp theo: coordinator kiểm integrity file và nếu cần so hai máy, giữ nguyên các nhãn independent đã lưu; không coi đồng thuận máy là ground truth.
