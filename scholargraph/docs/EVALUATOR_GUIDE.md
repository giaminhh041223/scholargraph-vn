# Evaluator Protocol v1 — SG-008

## Phạm vi

Implementation: [metrics.py](../src/scholargraph/evaluation/metrics.py), class `ProtocolEvaluator`, revision `sg008-1.0.0`. Đây là evaluator cho [Protocol v1 §6.1](RESEARCH_PROTOCOL.md), không phải thí nghiệm chất lượng retrieval. Fixtures đều synthetic.

## Metric convention

| Output key | Cách tính trên một query |
|---|---|
| nDCG@10 | Tổng `rel/log2(rank+1)` ở top 10, chia DCG lý tưởng từ **toàn bộ qrels**; gain linear 0/1/2 |
| Recall@100 | Số positive ở top 100 / tổng positive qrels |
| MRR@10 | `1/rank` của positive đầu tiên ở top 10; không tìm thấy thì 0 |
| MAP@100 | Tổng precision tại mỗi vị trí positive trong top 100 / **tổng positive qrels**, kể cả positive ngoài top 100 |
| P@5 | Số positive ở top 5 / **5**, kể cả chỉ trả 1–4 kết quả |

Positive là nhãn ≥1. Không có positive/IDCG=0 thì điểm 0. Aggregate là trung bình trên mọi ID trong `query_ids` đã khóa; query thiếu ranking hoặc qrels vẫn được giữ. Split rỗng bị từ chối vì không có mẫu số macro có nghĩa.

Ví dụ synthetic: ranking `[không liên quan, liên quan]` có MRR@10 = 1/2. Nếu qrels có 4 positive nhưng chỉ tìm thấy một positive ở rank 2 thì AP@100 = (1/2)/4 = 0,125. nDCG còn xét độ liên quan 1 hay 2 và so với thứ tự lý tưởng; cùng một positive ở đầu danh sách có ích hơn ở cuối.

Đối chiếu với [mã nDCG của NIST](https://github.com/usnistgov/trec_eval/blob/main/m_ndcg_cut.c) và [MAP cutoff của NIST](https://github.com/usnistgov/trec_eval/blob/main/m_map_cut.c). Bộ kiểm chứng dùng package `pytrec-eval-terrier` (C trec_eval), pin version và binary digest trong report. MRR dùng `recip_rank` sau khi cắt ranking xuống top 10; không dùng RR toàn ranking để thay thế.

## Input và audit

```python
from scholargraph.data.schemas import RankingResult
from scholargraph.evaluation.metrics import ProtocolEvaluator

run = RankingResult.create_sorted(
    "fixture:q", [("fixture:b", 0.5, None), ("fixture:a", 0.5, None)]
)
result = ProtocolEvaluator().evaluate(
    {"fixture:q": run},
    {"fixture:q": {"fixture:a": 2, "fixture:b": 0}},
    query_ids=["fixture:q", "fixture:missing"],
    corpus_ids=["fixture:a", "fixture:b"],
    track="A",
)
# result['per_query']: hai query; result['aggregate']['MRR@10'] == 0.5
```

- `runs`: mapping query ID → `RankingResult`, đã sắp score giảm dần/doc ID tăng dần theo Unicode. Evaluator kiểm tra lại cả mutable candidates và run được tạo bằng `model_construct`; không tự sắp/loại lỗi để cải thiện điểm.
- `qrels`: mapping query → doc → grade hoặc sequence các `Qrel`. Sequence giúp phát hiện duplicate/mâu thuẫn trước khi tạo dict. Mapping không thể giữ lại duplicate đã bị loader ghi đè, nên ingestion phải audit dòng gốc. ID và grade không được chuẩn hóa tại evaluator.
- `corpus_ids`: snapshot corpus hợp lệ. Tất cả qrel IDs (cả nhãn 0) phải thuộc corpus; run/query ngoài split, duplicate IDs, grade ngoài 0/1/2, score NaN/Inf bị từ chối trước aggregate.
- `eligible_ids`: nếu truyền, phải có đúng mọi query, mỗi tập là toàn bộ universe hợp lệ cho query, không phải danh sách C100. Positive qrel hoặc ranking ngoài tập này gây lỗi. Các qrel 0 trong corpus nhưng ngoài eligible có thể giữ lại cho provenance.
- `query_document_ids`: ánh xạ query sang source paper để kiểm tra self-match khi query ID khác namespace document ID. Tuyến A còn cấm literal `query_id == doc_id` theo BEIR. Positive qrel self-match gây lỗi, không âm thầm sửa nhãn.
- Tuyến B bắt buộc có cả hai mapping đầy đủ. Caller dựng universe từ năm, observed references và canonical duplicates theo split policy; evaluator chỉ xác minh membership, không có dữ liệu để tự chứng minh temporal/graph leakage.
- Tuyến C trả `pooled Recall@100` và `pooled MAP@100`; không gọi pooled recall là recall toàn corpus.
- `audit.unjudged_counts` đếm trên toàn bộ kết quả thực trả; unjudged chấm gain 0 nhưng không đồng nhất với nhãn negative. `judged_zero_counts` giữ số nhãn 0 riêng. `missing_ranking_count` là query không có entry trong runs; `empty_ranking_count` chỉ đếm entry có danh sách rỗng. Hai loại cùng có điểm 0.

## Ties, raw scores và runner

`RankingResult.to_trec_lines()` xuất scores thứ tự giảm nghiêm ngặt `N-rank+1`. Reference evaluator có thể tự sắp equal-score runs, vì vậy chỉ truyền output này để giữ đúng thứ tự canonical. Raw scores nằm trong `rankings.jsonl`, không bị thay bằng scores xuất TREC.

Sau khi evaluate thành công, truyền `result['per_query']` vào `RunHandle.record_per_query()` và `result['aggregate']` vào `RunHandle.complete()`. Ghi revision cùng SHA-256 implementation vào resolved config/code provenance trước tạo run. Report kiểm chứng evaluator không thay freeze evidence SG-027 hoặc audit leakage SG-011. Xem [runner guide](RUNNER_GUIDE.md).

## Kiểm chứng và giới hạn

Bộ kiểm chứng có fixtures tính tay, đối chiếu C trec_eval, cutoff 10/100, graded labels, tie order, short/empty/missing runs, no positives, invalid inputs và synthetic randomized queries. Sai số cho phép được ghi trong report; không làm tròn trước aggregate.

Chạy từ thư mục ScholarGraph bằng môi trường riêng:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements/sg008-verification.txt
.venv/Scripts/python.exe -m pytest tests/unit/test_metrics_reference.py tests/unit/test_metrics_runner.py -q
.venv/Scripts/python.exe scripts/validate_metrics.py
```

Không dùng `query_ids=list(runs)` vì sẽ bỏ query không trả kết quả. Evaluator không tự biết split/universe có thực sự được freeze đúng hay không; caller phải cung cấp artifact đã audit, pin hashes và giữ ranh giới labels/ranker. Chưa có benchmark thật nào được đo trong SG-008.

**Câu hỏi hiểu bài:** Vì sao relevant đầu tiên ở rank 11 có MRR@10 bằng 0, nhưng vẫn có thể đóng góp Recall@100 và MAP@100?
