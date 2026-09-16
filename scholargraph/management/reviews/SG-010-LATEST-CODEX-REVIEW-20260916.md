# SG-010 — Review bản sửa e9c0fe2

**Verdict: CHANGES_REQUIRED — còn 1 P1 mới và 1 P2.**

Hai ca R1/R2 cụ thể của vòng trước đã được sửa; R2 đã đóng. Bản sửa R1 bổ sung nhánh mặc định che thiếu split bắt buộc và vẫn suy thiếu chính xác về title. Không tuyên bố raw benchmark hiện tại hỏng: các lỗi dưới đây được tái hiện trên fixtures synthetic riêng.

## Snapshot và phạm vi

- Commit được kiểm: `e9c0fe2`; so sánh với `7b25bab`.
- Reviewer chính: Codex/current-session, actual model/effort unknown, không tham gia implementation SG-010.
- Subagent `/root/sg010_latest_review`, gpt-5.6-sol high, context mới: review diff/narrative và đếm R2 độc lập từ raw; không sửa file hoặc chạy pytest trùng.
- Chỉ ghi report/log mới; giữ nguyên implementation, tests, raw data, Data Card, báo cáo chính thức và shared control files đang có thay đổi SG-008.

| Artifact | SHA-256 |
|---|---|
| src/scholargraph/ingest/beir_audit.py | 428ea67eff42671333dd333fc93007e41a124f81f1b6d5769d98ab1a770f9998 |
| tests/unit/test_data_integrity.py | 45d127269b4e87517adc4023322f3486baa196d4bfa1e42beadfc6a95031418b |
| docs/DATA_CARD.md | 1d9b4264cfb36fb2e9ad0fb7f8cdf63320571ecac67a996b431a798085af40f5 |
| artifacts/reports/beir_data_audit.json | cd85a1a5cd247ada7322077f6ca42f4e2aa8d71fddb12bbf008f066241c23769 |

## L1 — [P1] Thiếu SCIDOCS test qrels vẫn trả PASS và CLI exit0

**Vị trí:** `src/scholargraph/ingest/beir_audit.py:555-556`.

Bản sửa đổi truy cập test split thành `.get("test", {})`, sau đó thay các phép đo thiếu bằng0. `audit_single_dataset` chỉ audit các `*.tsv` thực sự tồn tại, loader cũng chỉ kiểm những split đã tìm thấy. Gate không kiểm SCIDOCS có test split bắt buộc, nên danh sách checks rỗng được xem là không có lỗi. Trước correction, truy cập trực tiếp test split không âm thầm cho qua tình trạng này.

**Probe đã chạy:** tạo SciFact/SCIDOCS synthetic hợp lệ trong thư mục tạm, mỗi corpus1document, SciFact trainq1/testq2 disjoint. Xác nhận baseline PASS. Đổi tên duy nhất `scidocs/qrels/test.tsv` thành `test.tsv.disabled` trong fixture rồi chạy module CLI với cwd là workspace tạm.

| Đầu ra thực tế | Giá trị |
|---|---|
| CLI exit code | **0** |
| audit_passed | **true** |
| errors | [] |
| SCIDOCS splits_audit | {} |
| SCIDOCS loader_verification | {} |
| referential_integrity_status | 100% PASS; zero orphan queries, zero orphan documents, zero duplicate qrel rows. |
| CLI báo Audit finished successfully | true |

Đây là audit thành công sai khi thiếu phần nhãn bắt buộc của benchmark; downstream có thể tiếp nhận snapshot chưa đầy đủ. Đây là hồi quy do xử lý mặc định rỗng trong correction, không phải yêu cầu mở rộng thuật toán.

**Cần sửa:** xác nhận presence và khả năng đọc các split bắt buộc trước kết luận audit: SciFact train/test, SCIDOCS test. Thiếu split phải xuất trạng thái FAIL/error rõ và CLI nonzero; không thay phép đo chưa thực hiện bằng0. Có thể tiếp tục thu thập các lỗi khác để giữ report chẩn đoán.

**Regression tối thiểu:** baseline đầy đủ PASS; thiếu test.tsv, thư mục qrels rỗng và chỉ có split khác đều FAIL/CLI nonzero; output báo cáo ghi rõ split thiếu. Fixtures chỉ trong thư mục tạm, không đổi snapshot thật.

## L2 — [P2] Narrative báo đủ title dù chỉ kiểm abstract

**Vị trí:** `src/scholargraph/ingest/beir_audit.py:558-560`; cùng lỗi tại `:584-587`.

Nhánh `empty_or_missing_text_count == 0` kết luận mọi document có cả title lẫn abstract không rỗng. Điều kiện này không kiểm `empty_or_missing_title_count`. Loader hỗ trợ text-only document, nên đây là đầu vào hợp lệ mà auditor cần mô tả chính xác.

**Probe đã chạy:** khôi phục đủ test.tsv trong fixture trên, thay mỗi corpus bằng1document `{title: "", text: "Synthetic body only"}`. Kết quả:

- audit_passed=true (hợp lệ cho text-only).
- Mỗi dataset có `empty_or_missing_title_count=1`.
- Cả hai explanations vẫn ghi `All 1 ... documents have both non-empty title and abstract...`.

**Cần sửa:** nếu chỉ kiểm abstract thì chỉ nói về abstract; nếu nói cả hai field phải dùng cả hai bộ đếm missingness. Nhánh mô tả title-only cũng cần dựa trên field đã kiểm. Thêm regression text-only, title-only, đủ hai field và thiếu cả hai; narrative phải khớp counters, còn chính sách loader/gate giữ đúng contract.

## Những phần đã xác nhận đạt

- **R1 cũ:** không còn hardcode2query/5.183docs ở các ca thử trước. Fixture không overlap báo0; custom overlap dùng đúng IDs/text; số corpus/abstract thiếu thay đổi theo input. Điểm L2 ở trên là nhánh suy luận còn sót.
- **R2 CLOSED:** phép đếm độc lập từ raw SCIDOCS khớp implementation, report và Data Card:344docs,115cópositive,229zero-only,15mixed;187positivepairs;279zeropairs=262zero-only+17trênmixed; tổng466pairs.
- Tests mới có regression động và kiểm partition R2 từ live audit, không chỉ đọc JSON cũ.
- Các negative tests duplicate/orphan/conflicting qrels và ID overlap trước đây tiếp tục đạt trong lần pytest hiện tại.
- Không có thay đổi F3/F4/F5 trong correction ngoài đoạn R2 của Data Card; kết luận hash/thống kê/license được giữ theo review trước, không nhận đã lặp mọi kiểm chứng upstream lần này.

## Evidence đã chạy trong phiên review

1. `& .\.venv\Scripts\python.exe -B -m pytest tests/unit/test_data_integrity.py -q -p no:cacheprovider` → **15 passed in33.68s**, exit0. Bao gồm live raw audit ra temp path và manifest checks.
2. Probe baseline synthetic, CLI missing split và text-only → exit0 của script chẩn đoán, tái hiện chính xác L1/L2 như trên. Script ghi trong TemporaryDirectory dưới artifacts, tự dọn; không chạy CLI mặc định ở workspace thật.
3. Lượt yêu cầu quyền đầu của probe hết thời gian do automatic approval review không hoàn tất; retry một lần được phép và chạy thành công. Không coi timeout là kết luận action unsafe; không còn kiểm tra bị chặn.
4. Subagent read-only kiểm R2 và diff độc lập; không chạy full suite. Số150tests trong HANDOFF hiện thuộc phiên SG-008, không dùng làm bằng chứng reviewer đã chạy trong phiên SG-010 này.

## Bàn giao

Đề nghị sửa L1/L2, chạy các negative scenarios nêu trên và kiểm lại đúng snapshot mới. Không cần viết lại audit hoặc mở backlog mới. Reviewer không thay trạng thái shared board vì scope chỉ review và coordinator khác đang quản lý SG-008. Bản [resolution](SG-010-CODEX-RECHECK-RESOLUTION-20260916.md) được giữ như lịch sử; report này là kết luận kiểm độc lập mới nhất.
