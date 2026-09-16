# Review SG-010 — kiểm tra độc lập ngày 2026-09-16

**Verdict: CHANGES_REQUIRED — 1 P1 và 4 P2.** Kết luận áp dụng cho snapshot dưới đây, cùng snapshot đã được report trước đánh dấu PASS. Chưa đủ cơ sở giữ kết luận nghiệm thu PASS sau các reproducer mới.

- Người dùng yêu cầu review, không giao sửa implementation.
- Reviewer chính: Codex/current-session, actual model/effort chưa xác minh; không tham gia implementation SG-010.
- Subagent kiểm chứng số liệu/provenance: `/root/sg010_evidence_review`, gpt-5.6-sol high, fresh context; chỉ đọc, không sửa file.
- Commit đầu vào: `6cbf504` (SG-010), trước đó `e13ee15` (SG-009).
- Giữ nguyên raw dataset, code, tests, Data Card và báo cáo audit đã có. Chỉ tạo report/log review riêng; không sửa shared control files hoặc mở SG-008/011.

## Snapshot

| Artifact | SHA-256 |
|---|---|
| src/scholargraph/ingest/beir_audit.py | 4c7cbd41a92c6a94ff3c5d852aa321c6dbf6998ba347146c4b543805cc86121c |
| tests/unit/test_data_integrity.py | 67f5eef8d9b902b5f50f7b2d1eacfe327d32e5c5702d490ebdfea82f4bffa1e2 |
| artifacts/reports/beir_data_audit.json | 67e9e6a0faef06fd5cfe0cf7e61fccc673011527b515089e74c2dab4126db6c8 |
| docs/DATA_CARD.md | c58f04a311eb854512bdc4b9d73977fb700fdde55e4c6a169b2e2ab6895c910c |

## F1 — [P1] Không được trả kết luận PASS cố định khi audit đã phát hiện lỗi

**Vị trí:** `src/scholargraph/ingest/beir_audit.py:547`; liên quan `:393-397`, `:476-479`, `:540-554`, `:564-568`.

`run_full_beir_audit` luôn ghi `referential_integrity_status = "100% PASS; zero orphan queries, zero orphan documents, zero duplicate qrel rows."`. Nó không suy trạng thái từ duplicate/orphan/conflict counters hoặc `loader_verification=FAIL`. CLI cũng thông báo thành công mà không kiểm gate. `audit_scifact_train_test_overlap` luôn viết verdict 0 ID overlap và đúng 2 query trùng, bất kể số đo.

**Reproducer đã chạy:** tạo hai dataset nhỏ hoàn toàn synthetic trong TemporaryDirectory dưới artifacts, truyền đường dẫn riêng vào `run_full_beir_audit(root, root/'review-output.json')`. SciFact có hai corpus rows cùng ID `doc1`, một query `q1` xuất hiện cả train/test; mỗi split có hai qrels `(q1, missing-doc)` với score 1 và 0. SCIDOCS fixture hợp lệ.

| Kết quả đo | Giá trị |
|---|---|
| duplicate corpus ID | 1 |
| orphan corpus ID trong test qrels | 1 |
| duplicate qrel pair / conflicting score | 1 / 1 |
| loader train/test | FAIL / FAIL |
| query ID overlap / text overlap | 1 / 1 |
| summary trả về | 100% PASS; zero orphan/duplicate |
| overlap verdict trả về | 0 overlapping IDs; exactly 2 queries |
| exit code của probe gọi API | 0 |

Đây là báo thành công sai ở công cụ làm gate cho dữ liệu, có thể cho lỗi dữ liệu đi tiếp vào split/baseline. Snapshot thật hiện không có các lỗi ID này; finding nói về hành vi kiểm chứng, không tuyên bố raw benchmark thật đã hỏng.

**Cần sửa:** tính verdict từ toàn bộ checks, ghi lỗi với bằng chứng; không cho caller/CLI hiểu audit lỗi là PASS. Các narrative/counts, compliance flags và timestamp phải dựa trên lần chạy thật. Thêm negative fixtures cho duplicate/orphan/conflicting qrels, loader failure và overlap thay đổi; vẫn giữ report lỗi và raw input để kiểm tra.

## F2 — [P2] Tests đọc report cũ nên không phát hiện auditor bị hỏng

**Vị trí:** `tests/unit/test_data_integrity.py:34-40`.

Fixture ưu tiên JSON đã commit, chỉ gọi audit nếu file không tồn tại. Vì vậy các kiểm tra số lượng/integrity không chạy implementation audit hoặc đối chiếu hash raw hiện tại.

**Reproducer đã chạy:** trong process Python riêng, thay năm hàm `audit_single_dataset`, `audit_raw_corpus`, `audit_raw_queries`, `audit_raw_qrels`, `audit_scifact_train_test_overlap` bằng hàm luôn ném `RuntimeError('SYNTHETIC_REVIEW_AUDITOR_BROKEN')`; gọi pytest cho `tests/unit/test_data_integrity.py`. **10 passed in 7.23s** dù toàn bộ auditor bị vô hiệu hóa. Không sửa file code nào.

**Cần sửa:** chạy auditor trên synthetic fixtures mới ở temporary output để kiểm cả trường hợp đúng/sai; kiểm raw/report/manifest hashes ở integration test nếu dùng snapshot thật. Tách việc kiểm report lịch sử khỏi regression của implementation và không ghi đè báo cáo nghiệm thu trong tests.

## F3 — [P2] Bốn SHA-256 trong Data Card không trỏ tới snapshot đã đóng băng

**Vị trí:** `docs/DATA_CARD.md:37-38`.

Đối chiếu độc lập file ZIP, thành viên archive, file raw và manifest cho các giá trị đúng sau:

| Artifact | SHA-256 đúng |
|---|---|
| SciFact archive | 536e14446a0ba56ed1398ab1055f39fe852686ecad24a6306c80c490fa8e0165 |
| SCIDOCS archive | 96640201687767c9b1fcc5af7a80b90fb325b37fa25329c2586c25edcfa17ef1 |
| SCIDOCS corpus | 328bb38854179c83ee40d4f49fae2ef7209ede7163785193cbdcd5906b28eecc |
| SCIDOCS queries | 3c85b68419bd579ff52edb58f9e7b32eb3d18bc83435edb71dbb68aaf79531d6 |

Data Card lần lượt ghi `4ba436…`, `105fae…`, `142aa7…`, `da7ad2…`. Manifest và machine audit khớp raw; lỗi nằm ở Data Card, không phải raw bị thay đổi sau review. Người tái lập theo Data Card sẽ kết luận nhầm snapshot đúng là sai.

**Cần sửa:** sinh bảng từ manifests đã xác minh, cập nhật các hash sai và kiểm sự nhất quán tự động giữa tài liệu/report/manifest.

## F4 — [P2] Thống kê độ dài Data Card mâu thuẫn với raw và machine report

**Vị trí:** `docs/DATA_CARD.md:66`, `:69-72`.

Ví dụ card ghi SciFact query min/max là 4/33, thực tế 3/41; SCIDOCS abstract max 1.189, thực tế 1.919. Kết quả độc lập theo tokenizer Protocol v1 khớp machine report:

| Trường | Min | Max | Mean | Std | Median | P90 |
|---|---:|---:|---:|---:|---:|---:|
| SciFact query | 3 | 41 | 12.904 | 5.038 | 12 | 20 |
| SCIDOCS title | 2 | 48 | 9.950 | 3.868 | 9 | 15 |
| SCIDOCS abstract | 0 | 1919 | 172.230 | 118.062 | 156 | 256 |
| SCIDOCS combined | 2 | 1923 | 182.179 | 118.402 | 166 | 267 |
| SCIDOCS query | 2 | 30 | 9.976 | 3.549 | 10 | 14 |

Sai lệch ảnh hưởng mô tả dữ liệu và quyết định độ dài đầu vào/truncation sau này. **Cần sửa:** xuất số liệu tài liệu từ report đã kiểm chứng; giữ nguồn/version của phép đo, không điền thủ công số liệu khác.

## F5 — [P2] Data Card ghi sai giấy phép của cả hai dataset

**Vị trí:** `docs/DATA_CARD.md:28-29`.

Card ghi SciFact CC BY-SA 4.0 và SCIDOCS CC0. Nguồn sơ cấp của SciFact ghi claims/evidence là CC BY 4.0, abstracts là ODC-By 1.0; SCIDOCS LICENSE ghi CC BY 4.0. Những thông tin này cũng khớp manifests SG-009. [SciFact LICENSE](https://github.com/allenai/scifact/blob/master/LICENSE.md), [SCIDOCS LICENSE](https://github.com/allenai/scidocs/blob/master/LICENSE).

**Cần sửa:** ghi theo thành phần dữ liệu, dẫn license upstream, phân biệt giấy phép code BEIR với dataset. CC0 không tương đương CC BY; card hiện tại có thể khiến người dùng bỏ sót yêu cầu ghi nguồn.

## Các phần đã xác nhận đúng

- Hash raw corpus/queries/qrels trong machine audit khớp manifests; archive MD5 khớp catalog theo kiểm tra độc lập snapshot local.
- SCIDOCS có 344 document với abstract chuỗi rỗng; cả 344 ID xuất hiện trong qrels; 115 ID có ít nhất một positive judgment, 229 ID chỉ có nhãn 0.
- Có 466 query-document pairs liên quan đến 344 ID này: 187 positive, 279 zero. Trong 115 ID có positive, 15 ID cũng có nhãn 0 với query khác. Relevance là theo cặp query-document, không phải nhãn toàn cục của document.
- SciFact có đúng hai cặp query trùng nguyên văn: train1291/test1292 cùng positive doc56893404; train871/test870 cùng positive doc195689316. Query IDs train/test không giao nhau.
- Không thấy thao tác lọc hoặc sửa raw benchmark trong code audit được review.

## Kiểm tra và giới hạn

1. Pytest chính thức trên snapshot nguyên bản: `& .\.venv\Scripts\python.exe -B -m pytest tests/unit/test_data_integrity.py -q -p no:cacheprovider` → **10 passed in 5.26s**, exit0. Không suy kết quả này thành tính đúng của auditor vì F2.
2. Probe thay auditor trong bộ nhớ → **10 passed in7.23s**, exit0, chứng minh F2.
3. Probe synthetic lỗi → tái hiện F1. Lượt đầu thiếu thư mục tmp; lượt kế trong sandbox không hoàn tất nên đã dừng. Lượt escalation được phép, tạo/xóa fixture riêng dưới artifacts, hoàn tất exit0. Không tác động raw hoặc report chính thức; không còn thư mục probe sau chạy.
4. Subagent Sol kiểm độc lập raw/archive/manifests/report/Data Card; root kiểm implementation/pytest/negative probes và đối chiếu license upstream bằng web ngày2026-09-16.
5. Không chạy lại full suite vì scope review tập trung SG-010; không lặp CLI mặc định ghi đè audit report.
6. Code chỉ thử canonical roundtrip trên tối đa1.000 corpus IDs và1.000 query IDs từ set, không phải toàn bộ như mô tả 100%. Nên kiểm hết IDs và dùng thứ tự deterministic khi sửa audit. Chưa có bằng chứng ID thật bị lỗi.
7. Các phát biểu trong Data Card §6 về mọi retriever đã dùng full corpus nên được ghi là yêu cầu protocol cho đến khi có run evidence; không coi SG-010 là bằng chứng retrieval/evaluator đã hoàn thành.

## Bàn giao

Đề nghị coordinator chuyển SG-010 về REVIEW, giao sửa F1–F5, chạy negative regressions và tái review snapshot mới trước nghiệm thu. Shared board hiện vẫn giữ trạng thái DONE từ phiên020; phiên này là reviewer chỉ ghi report/log, chưa nhận quyền sửa control files. Giữ lịch sử review PASS cũ và chỉ rõ report mới này khi tiếp nhận; không sửa lịch sử hoặc mở SG-008/011 trong phiên review.
