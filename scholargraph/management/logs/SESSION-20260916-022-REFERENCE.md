# SESSION-20260916-022-REFERENCE — SG-008 reference và kiểm thử

- Cập nhật: 2026-09-16T02:02:51+07:00.
- Worker: `/root/sg008_reference_tests`, được coordinator `/root` giao trong phiên 022.
- Model/effort thực tế: không xác minh được ID runtime trong worker, không suy từ routing.
- Phạm vi: fixtures tính tay, reference C trec_eval, kiểm thử evaluator và script báo cáo. Không ghi shared board, không chạy benchmark thật, không sửa thay đổi SG-010.

## Đầu ra

- `tests/fixtures/metric_golden.json`: 9 fixtures synthetic gồm graded linear nDCG; ties; short run; empty/missing/no positives; 101 positive qrels; các biên rank10/11/100/101. Có công thức tính tay và expected cố định.
- `scripts/validate_metrics.py`: reference dùng `pytrec_eval_ext` là C trec_eval; parse text từ `RankingResult.to_trec_lines()`, MRR dùng `recip_rank` trên top10. Adapter chỉ giữ zero rows cho qrels rỗng/reference bỏ qua và macro trên locked IDs. Report pin package/version và hash binary/wrapper/source, lưu per-query, macro, absolute errors, synthetic=true.
- `tests/unit/test_metrics_reference.py`: golden/reference, 40 queries randomized seed20260916, strict score tie reversal, 38 negative audit cases, Track B universe/source requirements, Track C pooled labels, macro và unjudged audit.
- `requirements/sg008-verification.txt`: direct dependency pins, không tự nhận full transitive lock.

## Reference đã kiểm chứng

- `pytrec-eval-terrier==0.5.10`, wheel `pytrec_eval_terrier-0.5.10-cp312-cp312-win_amd64.whl`, Python3.12.14.
- C extension `pytrec_eval_ext.cp312-win_amd64.pyd` SHA256: `f209f5818632eb2a22653d1029d59114baed3e2a366127dee94b67811fe8cd0e`.
- Nguồn primary: https://pypi.org/project/pytrec-eval-terrier/0.5.10/ ; https://github.com/usnistgov/trec_eval/blob/main/m_map_cut.c ; https://github.com/usnistgov/trec_eval/blob/main/m_ndcg_cut.c . GitHub main chỉ để đối chiếu contract, provenance thực thi được pin bằng package/version + binary hash, không nhận main là revision đã chạy.

## Lệnh và kết quả

1. `pip index versions pytrec-eval-terrier` trong sandbox: thất bại WinError10013 socket, không suy là package không tồn tại.
2. `.venv/Scripts/python.exe -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: --no-deps pytrec-eval-terrier==0.5.10` với quyền escalated giới hạn: PASS, chỉ cài trong `.venv` ScholarGraph.
3. `.venv/Scripts/python.exe -m pytest tests/unit/test_metrics_reference.py -q -p no:cacheprovider`: **56 passed in1.38s**.
4. `.venv/Scripts/python.exe scripts/validate_metrics.py --output artifacts/reports/sg008-dev/metric_validation.json`: lần đầu tính toán xong nhưng ghi file thất bại WinError5; chạy lại đúng lệnh với quyền escalated: **PASS, 74 comparisons, 38 negative cases; max absolute error=1.6653345369377348e-16**, tolerance1e-12.

## Bàn giao

- Coordinator chạy script lần cuối ra `artifacts/reports/metric_validation.json` sau khi code/review đã chốt để source hashes khớp. Báo cáo worker ở `artifacts/reports/sg008-dev/metric_validation.json` là development evidence.
- Fresh-context review và human approval do coordinator theo dõi; worker không tự nhận hai gate đã đạt.
- Các metric và số kiểm chứng trên là synthetic evaluator validation; không phải retrieval scores trên SciFact/SCIDOCS/OpenAlex.
