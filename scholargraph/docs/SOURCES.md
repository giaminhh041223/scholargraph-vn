# Nguồn tham khảo đã đối chiếu

Truy cập ngày 2026-09-15. Khi tải dữ liệu ở SG-009/SG-013 phải lưu revision/checksum và kiểm tra điều kiện hiện hành. Chưa tải dataset trong bước lập kế hoạch.

| Nguồn | Dùng cho | Điều đã xác minh |
|---|---|---|
| [OpenAI: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Quy tắc giữa các phiên | Codex đọc chỉ dẫn theo đường dẫn project/current directory; đặt entry point ở root và child |
| [OpenAI model catalog](https://developers.openai.com/api/docs/models) | Phân vai coding assistant | Astra cho việc khó; Sol cho professional work; Terra cân bằng năng lực/chi phí; Luna cho cost-sensitive workloads. Mapping task là khuyến nghị dự án, không phải benchmark đã đo |
| [BEIR repository](https://github.com/beir-cellar/beir) | Benchmark chính | Corpus/queries/qrels, official splits và evaluator |
| [BEIR SCIDOCS](https://huggingface.co/datasets/BeIR/scidocs) | Citation-related retrieval | English corpus khoảng 25,7K; không mặc định có complete citation graph |
| [BEIR SciFact](https://huggingface.co/datasets/BeIR/scifact) | Pilot/search evidence | Scientific claim → bài báo; không phải hỏi đáp tổng quát |
| [BEIR metrics](https://github.com/beir-cellar/beir/wiki/Metrics-available) | Chấm retrieval | nDCG, MAP, Recall, Precision và MRR |
| [SciDocs](https://github.com/allenai/scidocs) | Nguồn benchmark lịch sử | Suite gốc khác BEIR subset; tác giả hướng người dùng đến SciRepEval |
| [SciRepEval](https://github.com/allenai/scirepeval) | Stretch evaluation | Tác vụ khác nhau có metadata/labels/config riêng |
| [SciRepEval paper](https://aclanthology.org/2023.emnlp-main.338/) | Related work | Scientific representation nhiều loại tác vụ |
| [OpenAlex API](https://help.openalex.org/api/) | Graph + demo corpus | API lọc/search/select metadata; kiểm tra quota trước tải nhiều |
| [OpenAlex works](https://help.openalex.org/data/works/) | Data contract | Works liên kết với metadata học thuật và citations |
| [OpenAlex snapshot](https://help.openalex.org/access/snapshot/) | Snapshot strategy | Full snapshot rất lớn; dự án ưu tiên tập con |
| [OGB citation2](https://ogb.stanford.edu/docs/linkprop/) | Tham khảo protocol | Citation link prediction và MRR; quy mô quá lớn cho core |
| [Colab FAQ](https://research.google.com/colaboratory/faq.html) | GPU và khôi phục notebook | Tài nguyên/quota thay đổi, runtime có thể bị đóng; cần lưu output bền vững |
| [Kaggle notebooks](https://www.kaggle.com/docs/notebooks) | GPU notebook thay thế | Trang đã mở nhưng không trích xuất được nội dung; quota của tài khoản chưa xác minh |

## Cần khảo sát ở SG-003/SG-017

- Paper gốc BM25, PageRank, Personalized PageRank, Reciprocal Rank Fusion.
- Scientific embedding: SPECTER/SPECTER2, SciNCL; model card/revision/adapter.
- Graph reranking, bibliographic coupling, temporal/popularity bias trong scholarly recommendation.
- Training-data overlap của từng model với benchmark.
- Công cụ/metric gán nhãn tiếng Việt và cách xử lý unjudged documents.
- License riêng của corpus, model, code và metadata; không suy license dữ liệu từ license code.

Không sử dụng điểm số trong câu trả lời hội thoại trước làm kết quả chạy của dự án.
