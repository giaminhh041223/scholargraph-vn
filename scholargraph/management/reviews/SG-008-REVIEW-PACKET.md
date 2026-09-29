# SG-008 — Gói review evaluator

## Phạm vi và trạng thái

- Snapshot chốt 2026-09-16T02:04:05+07:00, session coordinator `SESSION-20260916-022`.
- Đã triển khai [task card SG-008](../../docs/TASKS.md#sg-008): tính tay metrics, đối chiếu evaluator reference, kiểm tra graded labels/ties/duplicates/no results.
- Implementation và tự kiểm xong; fresh-context review và human approval còn chờ. Không phải benchmark thật; toàn bộ validation data synthetic.
- Không sửa protocol thiết kế, runner SG-007 hoặc các thay đổi SG-010/013 có sẵn.

## Artifact và snapshot SHA-256

| File | SHA-256 |
|---|---|
| `src/scholargraph/evaluation/metrics.py` | `ECB7D5A44E7A3A5BDE0D56288EE7CD00398BC4771FEE8DE438CCEA4C78CE2EC0` |
| `tests/unit/test_metrics_reference.py` | `FDDE894503B1DE74AA5AB8C4D4167AC55A59F6EF4D45B0BD86384463DB17C380` |
| `tests/unit/test_metrics_runner.py` | `0730A4C59538E524182A3DECEBC86A5A4B2EFBB824430215674231B93C3EE9B0` |
| `tests/fixtures/metric_golden.json` | `74EC7DD91C680A634DD7CAF437FDEB8112049347C6DDF5DCC34B8DAF2DE6B6CC` |
| `scripts/validate_metrics.py` | `BB3FAFC7BB5F31B7119307C94BDA11CD22DE66F3847AFB48D820E8560726234A` |
| `requirements/sg008-verification.txt` | `B190E198E29EBB07B5679AF9DEB3095C6258AE70F451A3523ECCE0ED5AB35C4F` |
| `docs/EVALUATOR_GUIDE.md` | `4B7E45C00B23D73DFBA412ACFF6A29C9D33793642809AE42A577E0FEBA2E63BB` |
| `artifacts/reports/metric_validation.json` | `55B3444A4049FFCD85BCDFACBC4DB6CABF104B07BD1E5EAFD6F75E154F5F514A` |

## Bằng chứng đã chạy

- `.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp=artifacts/runs/SG008-TEST-20260916-0205`: **150 passed in 32.77s**, exit 0.
- `.venv/Scripts/python.exe -B scripts/validate_metrics.py`: **PASS 74 comparisons + 38 negative cases**, sai số lớn nhất `1.6653345369377348e-16`, tolerance tuyệt đối `1e-12`.
- [Báo cáo máy đọc](../../artifacts/reports/metric_validation.json): 9 golden scenarios/12 query rows, 40 randomized queries, seed 20260916; per-query, macro, hand formulas và hashes source/reference.
- Reference thực thi: `pytrec-eval-terrier==0.5.10`; C extension SHA-256 `f209f5818632eb2a22653d1029d59114baed3e2a366127dee94b67811fe8cd0e`. Không nhận nhánh GitHub main là revision binary đã chạy.
- [Worker log](../logs/SESSION-20260916-022-REFERENCE.md), [coordinator log](../logs/SESSION-20260916-022.md), [hướng dẫn sử dụng/hiểu bài](../../docs/EVALUATOR_GUIDE.md).

## Yêu cầu reviewer

Đọc AGENTS, task card, [Protocol §6.1](../../docs/RESEARCH_PROTOCOL.md) và code/artifacts thực tế. Kiểm tra công thức linear gain, denominator MAP, cutoff MRR và P@5; all-locked-query macro; qrel duplicates/universe/self; serialization ties; khả năng tái lập reference, source hashes, mô tả giới hạn. Chạy tests và probe độc lập nếu hữu ích. Không ghi đè report chính hoặc sửa implementation trong lúc review; nếu tái sinh report dùng `--output artifacts/reports/sg008-review/metric_validation.json`.

Ghi verdict, findings có mức độ, commands/results thực tế và snapshot đã kiểm tra. Chỉ viết report `management/reviews/SG-008-REVIEW-20260916.md` và log `management/logs/SESSION-20260916-022-REVIEW.md`. Review model không thay human approval. Caller vẫn chịu trách nhiệm freeze/universe/leakage; SG-008 không tự hoàn tất SG-011/027.
