# SG-010 — Codex kiểm tra lại correction

**Kết luận: CHANGES_REQUIRED nhẹ hơn vòng trước — P1 đã đóng, còn 2 P2.**

- Snapshot: commit `8fd8c8a`, người dùng yêu cầu kiểm tra lại bản sửa F1–F5.
- Reviewer chính không sửa implementation SG-010; actual model/effort unknown. Subagent `/root/sg010_correction_evidence`, gpt-5.6-sol high, context mới, kiểm độc lập raw/manifests/Data Card; chỉ đọc.
- Bản [review trước](SG-010-CODEX-REVIEW-20260916.md) và [re-review của phiên sửa](SG-010-RE-REVIEW-20260916.md) được giữ nguyên như lịch sử. Report này bổ sung kết quả kiểm thực tế, không sửa lại các verdict cũ.

## Snapshot đã kiểm

| Artifact | SHA-256 |
|---|---|
| src/scholargraph/ingest/beir_audit.py | 21adcb7d3d2f5399441e96dae1da46312ab123ebb7154322b24460ba41b4b3dd |
| tests/unit/test_data_integrity.py | 7b01dbd05884285aee269547ad851286f329c071fa63f2e18f56c35d5ceb8302 |
| artifacts/reports/beir_data_audit.json | 4c223e04fbfd353cbc467f278237e8f4af346884d078ec721b2cda3c2dc22307 |
| docs/DATA_CARD.md | 6367317d3cbbf696a823e9c78ff8ed6a05592445b8e73084ec5e84ab36701876 |

## Những finding đã giải quyết

| Finding cũ | Kết quả kiểm tra lại |
|---|---|
| F1 P1 báo PASS dù integrity lỗi | **Đã đóng phần P1.** Probe cũ nay audit_passed=false, errors có đủ lỗi, summary FAIL và CLI exit1. Phần narrative còn sót được tách thành R1 P2 dưới đây. |
| F2 test chỉ đọc report cũ | **Đóng.** Live fixture chạy auditor thật ra tmp_path. Thay audit_single_dataset bằng hàm ném lỗi trong bộ nhớ làm test_live_audit_gate_passed báo ERROR đúng như mong đợi. |
| F3 bốn SHA-256 sai | **Đóng.** Hash archive/corpus/queries đã khớp raw/manifests; các hash qrels bổ sung cũng khớp. |
| F4 thống kê độ dài sai | **Đóng.** Tính độc lập bằng tokenizer Protocol v1 xác nhận Section4 Data Card khớp các thống kê thật. |
| F5 license sai | **Đóng.** Data Card nay ghi SciFact CC BY4.0 cho claims/evidence và ODC-By1.0 cho abstracts; SCIDOCS CC BY4.0; phân biệt code BEIR Apache2.0. Khớp nguồn sơ cấp đã đối chiếu ở vòng trước và manifests. |

Canonical roundtrip nay kiểm mọi ID theo thứ tự sorted, không lấy mẫu tối đa1.000 ID như trước. Timestamp được tạo lúc chạy, không còn cố định.

## R1 — [P2] Phần explanation vẫn đưa ra phát hiện cố định trái với số đo

**Vị trí:** `src/scholargraph/ingest/beir_audit.py:556-560`; cùng lỗi tại `:548-550`.

Mặc dù numeric counters và gate đã động, `anomalies_summary.scifact_train_test_query_leakage.explanation` vẫn luôn ghi có đúng hai cặp1292/1291 và870/871 cùng relevant docs. `scifact_empty_text_documents.explanation` vẫn luôn ghi toàn bộ5.183 documents có đủ title/abstract. Các chuỗi này chưa được tạo từ kết quả audit.

**Probe độc lập đã chạy:** tạo dataset synthetic hợp lệ, mỗi corpus chỉ một document, SciFact trainq1/testq2 khác ID và khác text. Gọi API với raw_root và output riêng trong thư mục tạm. Kết quả:

- audit_passed=true; query_text_exact_overlap_count=0; overlapping_queries=[].
- explanation vẫn nói `exactly 2 queries` và liệt kê hai cặp query không tồn tại trong fixture.
- Corpus có1document nhưng explanation ghi `All 5,183 SciFact documents...`.

Vấn đề không còn làm gate integrity báo PASS sai, nhưng machine report vẫn có các kết luận đối lập nhau. Nó có thể ghi dị thường hoặc tính chất chưa được đo khi raw_root/snapshot thay đổi; tests mới không kiểm phần này.

**Sửa cần thiết:** tạo explanations từ counts/details/missingness hiện có; bỏ tuyên bố về same relevant documents nếu chưa tính so sánh đó. Nếu cần giữ mô tả snapshot lịch sử, đặt nó thành expected/reference riêng và chỉ áp dụng sau đối chiếu hash, không trình bày như kết quả của lần chạy. Regression cần kiểm cả số và narrative với fixture0/1/n overlap, corpus size và missingness khác snapshot thật.

## R2 — [P2] Số cặp nhãn0 bị gắn nhầm nhóm tài liệu trong Data Card

**Vị trí:** `docs/DATA_CARD.md:91`.

Câu hiện tại: 229 tài liệu còn lại chỉ có nhãn0, kèm `tổng cộng 279 cặp query-doc nhãn 0`. Đếm trực tiếp raw SCIDOCS qrels cho kết quả:

| Nhóm | Documents | Cặp nhãn0 |
|---|---:|---:|
| Documents chỉ có nhãn0 | 229 | **262** |
| Documents có ít nhất một positive và cũng có nhãn0 với query khác | 15 | **17** |
| Tổng nhãn0 trên cả344 empty-text documents | — | **279** |

Số187 positive pairs trên115 documents là đúng. Tổng466 pairs =187 positive +279zero cũng đúng. Nhưng279 không phải số cặp của riêng229 zero-only documents; cách diễn đạt hiện tại phân bổ sai17pairs và làm mất bản chất relevance theo query-document.

**Sửa cần thiết:** ghi nhóm229 docs có262 zero pairs; trình bày279 như tổng trên cả344docs, trong đó17zero pairs thuộc15docs cũng có positive. Hoặc chỉ giữ tổng theo nhãn và số unique documents thành hai câu tách biệt. Thêm kiểm tra cho partition nếu đưa số này vào Data Card.

## Kiểm chứng đã chạy

1. `& .\.venv\Scripts\python.exe -B -m pytest tests/unit/test_data_integrity.py -q -p no:cacheprovider`: **13 passed in20.76s**, exit0; gồm live audit dữ liệu thật ra thư mục tạm, negative fixtures và manifest checks.
2. Probe cũ: corpus duplicate1, qrels orphan1/duplicate1/conflict1 ở mỗi split, query ID overlap1. Chạy module CLI trong synthetic workspace tạm: **exit1**, audit_passed=false,10errors, overlap statusFAIL; stdout không còn thông báo thành công. Output báo cáo lỗi vẫn tồn tại trong fixture trước khi tự dọn.
3. Probe live-test sensitivity: patch audit_single_dataset trong bộ nhớ thành hàm ném RuntimeError; pytest chọn test_live_audit_gate_passed → **1 ERROR in0.08s**, exit1 như kỳ vọng. Script wrapper xác nhận expected failure và exit0. Đây là kiểm tra độ nhạy của tests, không phải lỗi production mới.
4. Probe synthetic hợp lệ tái hiện R1; root và subagent tính độc lập raw qrels cùng ra262+17=279 cho R2.
5. Subagent kiểm hashes và thống kê Data Card độc lập; không chạy lại full suite trùng việc. Kết quả91tests trong log phiên sửa là evidence của phiên đó; reviewer này chỉ xác nhận13tests SG-010 và các probes nêu trên.
6. Các lượt ghi fixture chạy qua escalation được phép, chỉ temporary directories dưới artifacts hoặc pytest temp; tự dọn, không sửa raw/report nghiệm thu. Không ghi đè report bằng CLI mặc định trong workspace thật.

## Bàn giao

Phần sửa cốt lõi đã đạt; không còn P1 được tái hiện trong phạm vi review. Cần chỉnh R1/R2 rồi kiểm lại trước kết luận PASS toàn bộ. Scope còn lại nhỏ, không cần viết lại auditor hoặc mở thêm task thuật toán. Reviewer chỉ ghi report/log riêng; shared board giữ trạng thái hiện có của coordinator, không tự thay DONE hoặc mở SG-008/011.
