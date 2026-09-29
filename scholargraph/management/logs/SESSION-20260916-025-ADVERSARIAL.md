# SESSION-20260916-025-ADVERSARIAL — Phá thử SG-010 trên fixture tạm

- Checkpoint: 2026-09-16T14:17:28+07:00.
- Worker: `/root/sg008_reference_tests`, nhận subtask từ coordinator `/root` cho review/sửa SG-010.
- Model/effort runtime: không xác minh được, không suy từ routing.
- Chỉ ghi `tests/unit/test_beir_audit_adversarial.py` và log này; không sửa auditor, shared board, benchmark thật.
- Phạm vi được giao: missing/malformed resources, type/ID/score sai, self-positive, leakage query IDs qua split, title/text missingness và sparsity. Tất cả fixtures nằm trong temp directory, có dấu synthetic.

## Kết quả tái hiện đầu tiên, chưa phải nghiệm thu

Lệnh `.venv/Scripts/python.exe -m pytest tests/unit/test_beir_audit_adversarial.py -q -p no:cacheprovider --basetemp=artifacts/runs/SG010-ADVERSARIAL-025-before` (quyền escalated cho ghi fixture tạm) trả **exit1; 16 failed, 17 passed in10.16s**.

Coordinator sửa auditor song song với phép chạy này; đây là kết quả intermediate, không coi như snapshot toàn bộ mã trước sửa. Báo cáo CLI từng case nằm trong `artifacts/runs/SG010-ADVERSARIAL-025-before`.

Các lỗi được tái hiện:

1. Qrel SCIDOCS ` qtest\td1\t1` có khoảng trắng đầu query ID vẫn được CLI báo thành công (exit0); normalization âm thầm làm dữ liệu sai thành hợp lệ.
2. Positive self qrel `qtest\tqtest\t1` với cả document/query tồn tại vẫn CLI exit0, `audit_passed=true`.
3. Corpus/query/qrel thiếu hoặc malformed được báo FAIL nhưng trường tổng số vẫn0 thay vì null cho phép đo không thực hiện. Split bắt buộc thiếu chưa có component FAIL rõ trong `splits_audit`.
4. Các qrel score ngoài0..2, số thực, NaN, dư cột hoặc ID whitespace chưa đồng bộ raw component/null contract; global gate có thể FAIL do loader nhưng raw counts chưa phản ánh lỗi đúng.

17 case đã pass lúc đó gồm corpus/query strict type/ID probes, query ID leakage, title-only/text-only hợp lệ với shared relevant document qua hai split, và zero-positive sparsity. Không tuyên bố đây là lỗi trước sửa đã tái hiện vì parent có thể đã sửa trong thời gian worker viết tests.

## Checkpoint tiếp theo

- Đã bổ sung empty corpus/query/qrel resources, missing cả hai trường với mixed counts, một trường text hợp lệ dù thiếu key còn lại: tổng39 cases.
- Chờ coordinator báo auditor ổn định rồi chạy lại temp directory mới, ghi kết quả cuối ở cuối log. Không sửa previous failure evidence.

## Bổ sung kiểm tra snapshot vắng hoàn toàn

- Đã thêm case snapshot root vắng và xác nhận dependent qrels không bịa orphan counts khi corpus/query chưa đọc được; tổng hiện tại40 cases.
- Lệnh cùng môi trường, temp `artifacts/runs/SG010-ADVERSARIAL-025-extra`, filter `-k 'empty_required or one_valid_text or both_text or missing_entire'`: **1 failed, 6 passed, 33 deselected in1.95s**, exit1.
- Lỗi còn tái hiện: root vắng hoàn toàn vẫn corpus total_documents0. Sáu tình huống empty resource/mixed missingness/one valid text field đã pass.
