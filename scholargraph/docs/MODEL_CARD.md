# Model Card — Dense encoder cho track A — ScholarGraph VN

- Task: SG-017. Phiên bản: `dense-encoder-v1`. Ngày: 2026-09-16.
- Trạng thái: **đã chốt encoder core + shortlist** theo gate `selection_gate=SG-017` của [protocol v1](../configs/protocol_v1.json) (block `retrieval.dense`). Config máy đọc: [configs/models/dense_encoder.json](../configs/models/dense_encoder.json).
- Phạm vi task này: **lựa chọn + tài liệu**. KHÔNG chạy encoding, KHÔNG tải model weights, KHÔNG đo benchmark (encoding/index thuộc SG-019; chọn cấu hình trên SciFact dev thuộc SG-026). Tài liệu này không chứa bất kỳ điểm số benchmark nào do dự án tạo ra.
- Quy tắc trung thực: mọi fact về model phải có nguồn URL + ngày truy cập; không tra được thì ghi `unknown`. Không bịa tham số/hash/benchmark (AGENTS.md §6; ADR-013/014).

## 1. Mục đích

Chọn một pretrained dense encoder "nhỏ/base" cho truy hồi văn bản khoa học tiếng Anh (tuyến A: BEIR SciFact và SCIDOCS), ghi rõ revision/pooling/prefix/adapter/license và **công bố nguy cơ overlap** giữa dữ liệu huấn luyện của encoder với benchmark. Cấu hình dense phải khớp protocol: similarity cosine trên vector L2-normalized; `missing_embedding=fail_not_drop_document`.

## 2. Ứng viên đã khảo sát

Ký hiệu bảng: N/A = không có; "unknown" = không xác minh được từ nguồn đã truy cập, không suy đoán.

| Thuộc tính | all-MiniLM-L6-v2 | bge-small-en-v1.5 | bge-base-en-v1.5 **(chốt core)** | specter2_base |
|---|---|---|---|---|
| model_id | `sentence-transformers/all-MiniLM-L6-v2` | `BAAI/bge-small-en-v1.5` | `BAAI/bge-base-en-v1.5` | `allenai/specter2_base` |
| revision (sha main, truy cập 2026-09-16) | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` | `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a` | `3447645e1def9117997203454fa4495937bfbd83` |
| Kiến trúc | MiniLM-L6-H384 (BERT-based, base `nreimers/MiniLM-L6-H384-uncased`) | BertModel (họ BGE v1.5) | BertModel: hidden 768, 12 layers, 12 heads, max_pos 512 (config.json) | bert-base-uncased + adapters, finetuned từ `allenai/scibert` |
| Số tham số | 22.713.728 (safetensors, HF API) | 33.4M (card) | ~0.1B (Safetensors size trên card; số tensor chính xác unknown) | unknown (không công bố trong nguồn đã truy cập) |
| Pooling | mean (card) | CLS (1_Pooling/config.json) | CLS (1_Pooling/config.json + card) | unknown (không ghi trên card) |
| Normalization | F.normalize(p=2) trong ví dụ card | normalize embeddings (card) | normalize embeddings (card) | card không ghi rõ |
| max_seq_length | 256 (card: truncate > 256 word pieces; training chỉ 128 tokens) | 512 | 512 | 512 (card hyperparameters) |
| Kích thước vector | 384 | 384 | 768 | unknown (không ghi trên card) |
| Prefix / instruction | Không có | "Represent this sentence for searching relevant passages: " cho **query**; document không dùng | như small | adapter riêng theo task (`specter2_adhoc_query` cho query ngắn) |
| Adapter | N/A | N/A | N/A | Bắt buộc (`adapters` library, load_adapter + set_active) |
| License | Apache-2.0 | MIT | MIT | Apache-2.0 |
| Dữ liệu training chính | >1B cặp câu (tổng 1.170.060.424 tuples theo card): Reddit, **S2ORC citation pairs** (116,3M abstract + 52,6M title + 41,8M title–abstract), WikiAnswers, PAQ, StackExchange, MS MARCO, **SPECTER**, NLI, NQ, … | Card: retromae pre-training + contrastive learning trên "large-scale pairs data"; danh mục dataset tiếng Anh **không được liệt kê** (unknown) | như small | Card: >6M citation triplets khoa học (dataset `allenai/scirepeval`); "base model is trained on citation links between papers" |
| Nguy cơ overlap (§3) | trung bình–cao (có tài liệu) | unknown | unknown | cao (có tài liệu) |
| Trạng thái trong dự án | shortlist (baseline compute) | shortlist (phương án nhẹ hơn) | **chốt core** | cân nhắc, không shortlist |

Nguồn từng ô: mục 7; bản chi tiết đủ URL + ngày truy cập cho từng ứng viên nằm trong `candidates[].sources` của [dense_encoder.json](../configs/models/dense_encoder.json).

## 3. Công bố nguy cơ overlap (bắt buộc theo AGENTS.md §6 và protocol §5.1)

Benchmark tuyến A: SciFact 5.183 docs (claims + evidence abstracts khoa học) và SCIDOCS 25.657 docs (homepage BEIR dẫn về SciDocs evaluation suite của SPECTER, repo có các tác vụ cite/co-cite) — xem [DATA_CARD](DATA_CARD.md). Encoder được pretrained trước khi chấm benchmark, nên corpus/queries **có thể** đã nằm trong dữ liệu huấn luyện.

| Ứng viên | Mức nguy cơ | Bằng chứng (nguồn đã truy cập 2026-09-16) | Điều KHÔNG được suy diễn |
|---|---|---|---|
| all-MiniLM-L6-v2 | **trung bình–cao, có tài liệu** | Card liệt kê rõ S2ORC citation pairs và dataset SPECTER trong training mix. S2ORC/SPECTER là dữ liệu văn bản khoa học quy mô lớn; SciFact/SCIDOCS là corpus abstract khoa học công khai cùng loại dữ liệu, nên một phần văn bản corpus có khả năng đã xuất hiện trong cặp training (mức trùng cụ thể chưa được audit). | Không có bằng chứng qrels/nhãn relevance SciFact–SCIDOCS nằm trong training; không có bằng chứng danh sách query test bị lộ. |
| bge-base-en-v1.5 | **unknown** | Card chỉ ghi "large-scale pairs data", không liệt kê dataset; FlagEmbedding README không liệt kê; bài C-Pack trên card mô tả họ tiếng Trung. Không xác minh được thành phần → không xác nhận cũng không loại trừ overlap. | Không khẳng định có overlap bằng suy đoán; không khẳng định không overlap. |
| bge-small-en-v1.5 | **unknown** | Như bge-base-en-v1.5. | Như trên. |
| specter2_base | **cao, có tài liệu** | Card: train trên >6M citation triplets khoa học (SciRepEval); base train trên citation links giữa các paper. SCIDOCS là benchmark citation-based (homepage BEIR dẫn về SciDocs suite của SPECTER) → nguy cơ trùng ngữ cảnh citation cao nhất trong các ứng viên. | Không có bằng chứng qrels SCIDOCS cụ thể nằm trong tập train. |

Hệ quả cách xử lý:

1. Overlap được công bố **trước** mọi run retrieval (SG-019/026/027) và được lặp lại trong limitation của báo cáo cuối.
2. Không dùng điểm dense để tuyên bố chất lượng "tổng quát" khi encoder có overlap đã biết với benchmark; so sánh chính của RQ1 là hybrid_rrf − bm25, dense không phải tín hiệu duy nhất.
3. Dự án **không có khả năng audit từng văn bản** corpus có nằm trong tập training của model hay không (các model không công bố per-document membership). Mức nguy cơ báo cáo ở đây là cấp độ "theo tài liệu model card", không phải số đếm chính xác — ghi rõ để không dẫn narrative quá mức.
4. Encoder có overlap cao nhất (SPECTER2) không nằm trong shortlist core; nếu mở sau phải qua ADR và bảng kết quả riêng.

## 4. Quyết định: encoder core track A

**Chốt: `BAAI/bge-base-en-v1.5`, revision `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a` (sha main tại 2026-09-16), CLS pooling, L2-normalize, max_length 512, không adapter, prefix `"Represent this sentence for searching relevant passages: "` chỉ áp dụng cho query.**

Lý do theo tiêu chí (không dùng điểm benchmark chưa đo):

1. **Chất lượng dự kiến từ literature (chưa đo):** BGE v1.5 được xây cho embedding retrieval với cơ chế query instruction được tài liệu hóa trên card; card ghi v1.5 có "more reasonable similarity distribution" và "we improve its retrieval ability when not using instruction". MiniLM là sentence/short-paragraph encoder nhẹ, tổng quát. Tài liệu này không đưa ra con số; chất lượng thực tế được SG-026 đo trên SciFact dev nDCG@10 theo protocol §8.1.
2. **Kích thước/chi phí:** ~0.1B params, vector 768 — nằm trong ngân sách compute đã lập: COMPUTE_PLAN §7 đã dự trù lưu trữ 20K × 768 × 4B ≈ 61,4 MB; T4 16GB free. SG-002 chỉ smoke MiniLM (1.065,48 docs/s trên T4, fixture tổng hợp); COMPUTE_PLAN §5 cấm ngoại suy tốc độ MiniLM sang model khác, nên **SG-019 bắt buộc chạy compute pilot riêng với bge-base-en-v1.5** trước full encode.
3. **License:** MIT — card ghi "The released models can be used for commercial purposes free of charge"; phù hợp nghiên cứu/học phần.
4. **Kích thước vector/dims:** 768 (1_Pooling/config.json + bảng MTEB trên card); dung lượng index trong budget (mục 2 trên).
5. **Truncation:** max_length 512 so với 256 của MiniLM giảm mức cắt title+abstract; đây là thuộc tính cấu hình, không phải claim chất lượng đã đo.
6. **Pin được cấu hình inference:** pooling/kiến trúc/max_position xác minh được trong repo (config.json, 1_Pooling/config.json), phục vụ tái lập.

Không chốt các ứng viên khác vì:

- **all-MiniLM-L6-v2:** giữ trong shortlist làm baseline compute (đã smoke ở SG-002, Apache-2.0, 384-dim) nhưng 256-token truncation cao hơn cho title+abstract và card định vị encoder câu/đoạn ngắn tổng quát; không phải ứng viên mạnh nhất cho retrieval theo cấu trúc tài liệu card.
- **bge-small-en-v1.5:** giữ trong shortlist như phương án nhẹ hơn (33,4M, 384-dim) nếu compute pilot của SG-019 cho thấy bge-base vượt ngân sách; chất lượng giữa hai size không được suy đoán, để dev selection quyết.
- **specter2_base (không shortlist):** (a) pretraining citation-based đã tài liệu sẽ đưa tín hiệu graph vào dense baseline của track A, làm suy yếu phép so sánh có kiểm soát RQ1 (giá trị graph được đo riêng ở RQ2/3 với masking); (b) cần hệ adapter (thư viện `adapters`, chọn adapter theo task) vượt ngân sách "nhỏ/base"; (c) card không công bố embedding dimension/pooling — thiếu metadata bắt buộc để pin trung thực. Có thể mở lại như một nhánh "citation-informed" qua ADR ngoài scope v1.

## 5. Shortlist cho chọn cấu hình (protocol §8.1: tối đa 3)

Chọn cuối giữa các cấu hình được thực hiện trên **SciFact dev nDCG@10** (SG-026); trước đó SG-019 phải qua compute pilot với model được chọn.

| config_id | model_id | pooling | normalize | max_length | prefix | Dự kiến vai trò |
|---|---|---|---|---|---|---|
| `dense-a-bge-base-en-v1.5` | BAAI/bge-base-en-v1.5 | CLS | true | 512 | query_only | **core** |
| `dense-a-bge-small-en-v1.5` | BAAI/bge-small-en-v1.5 | CLS | true | 512 | query_only | phương án nhẹ hơn |
| `dense-a-minilm-l6-v2` | all-MiniLM-L6-v2 | mean | true | 256 | không | baseline compute |

Ghi chú prefix: FAQ của card bge-*-v1.5 khuyến nghị thêm instruction cho **short query tìm passage dài** và khẳng định document/passages không cần instruction; với v1.5 việc không dùng instruction chỉ làm giảm nhẹ. Track A có query ngắn (claim/title) và corpus title+abstract dài → pin `query_only`.

## 6. Giới hạn (bắt buộc đọc trước khi diễn giải kết quả)

1. **English encoder không tự chứng minh hiểu tiếng Việt:** encoder core là model tiếng Anh. Với query Việt → corpus Anh (tuyến C), phải dùng multilingual encoder được chốt riêng ở SG-032; không suy từ điểm English sang cross-lingual.
2. **Cosine/pooling là một phần của cấu hình:** cosine chỉ có nghĩa trên cùng một không gian vector của một model; pooling (CLS vs mean) và normalization tạo không gian khác nhau giữa các model, điểm cosine không so sánh chéo giữa các encoder. Mọi so sánh dự án là giữa *rankings* trên cùng corpus/query, không phải giữa giá trị cosine.
3. **Truncation:** input dài hơn max_length bị cắt; phần abstract phía sau mất tín hiệu. Tỷ lệ truncation thật của corpus phải được báo cáo ở SG-019 (chưa đo).
4. **Revision có thể di chuyển:** các sha ghi ở đây là của nhánh `main` tại ngày truy cập; SG-019 phải re-verify hash khi tải weights và ghi revision thực tế vào manifest shard/run evidence (protocol §9).
5. **Chưa đo throughput/VRAM của model được chốt:** mọi ước tính tốc độ phải chờ pilot của SG-019; không dùng số MiniLM thay thế.
6. **Chưa đo chất lượng:** tài liệu này chứa không điểm số nào; dense có thể kém hơn BM25 (kết quả âm vẫn được báo theo protocol).
7. **Overlap không đếm được per-document:** xem §3.4.

## 7. Nguồn (tất cả truy cập ngày 2026-09-16)

| Nguồn | Nội dung đã xác minh |
|---|---|
| [HF card all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | kiến trúc, 384-dim, truncation 256 word pieces, mean pooling, F.normalize, license Apache-2.0, bảng >1B cặp training (S2ORC, SPECTER, Reddit, …) |
| [HF API all-MiniLM-L6-v2](https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2) | sha `1110a243…`, lastModified 2026-06-01, safetensors 22.713.728 params, tags dataset:s2orc, dataset:embedding-data/SPECTER |
| [HF card bge-base-en-v1.5](https://huggingface.co/BAAI/bge-base-en-v1.5) | mô tả BGE v1.5, FAQ instruction + text đầy đủ, Dimension 768 / Sequence Length 512, retromae + large-scale pairs data, license MIT |
| [HF API bge-base-en-v1.5](https://huggingface.co/api/models/BAAI/bge-base-en-v1.5) | sha `a5beb1e3…`, lastModified 2024-02-21, license:mit |
| [config.json bge-base-en-v1.5](https://huggingface.co/BAAI/bge-base-en-v1.5/raw/main/config.json) | BertModel, hidden 768, 12 layers, 12 heads, max_position_embeddings 512 |
| [1_Pooling/config.json bge-base](https://huggingface.co/BAAI/bge-base-en-v1.5/raw/main/1_Pooling/config.json) | pooling_mode_cls_token=true, word_embedding_dimension 768 |
| [HF card bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) | 33.4M params, Dimension 384 / Sequence Length 512, FAQ, license MIT |
| [HF API bge-small-en-v1.5](https://huggingface.co/api/models/BAAI/bge-small-en-v1.5) | sha `5c38ec7c…`, lastModified 2024-02-22 |
| [1_Pooling/config.json bge-small](https://huggingface.co/BAAI/bge-small-en-v1.5/raw/main/1_Pooling/config.json) | pooling_mode_cls_token=true, word_embedding_dimension 384 |
| [HF card specter2_base](https://huggingface.co/allenai/specter2_base) | 6M citation triplets, SciRepEval, adapters (proximity/adhoc_query/…), max length 512, license Apache-2.0, base scibert |
| [HF API specter2_base](https://huggingface.co/api/models/allenai/specter2_base) | sha `3447645e…`, lastModified 2024-12-04, tags dataset:allenai/scirepeval |
| [FlagEmbedding README](https://github.com/FlagOpen/FlagEmbedding) | license MIT; không liệt kê dataset training tiếng Anh |
| [compute_pilot.json](../artifacts/reports/compute_pilot.json) | SG-002: MiniLM resolved revision `1110a243…` (run 2026-09-15, khớp sha API 2026-09-16); T4 1.065,48 docs/s trên fixture tổng hợp |
| [protocol_v1.json](../configs/protocol_v1.json) / [RESEARCH_PROTOCOL](RESEARCH_PROTOCOL.md) | block dense: cosine, l2_normalize, missing_embedding, selection_gate SG-017; §5.1; §8.1 shortlist ≤3 |
| [COMPUTE_PLAN](COMPUTE_PLAN.md) | §4 kết quả T4; §5 cấm ngoại suy tốc độ; §7 storage budget 768-dim |
| [RELATED_WORK](RELATED_WORK.md) | RW04 SPECTER, RW06 SciRepEval/SPECTER2 (adapter theo task), RW11 Multilingual E5 |
| [DATA_CARD](DATA_CARD.md) | counts/license SciFact, SCIDOCS; 344 docs SCIDOCS thiếu abstract |
| [github.com/allenai/scidocs](https://github.com/allenai/scidocs) | homepage BEIR SCIDOCS redirect về đây: "SciDocs - The Dataset Evaluation Suite for SPECTER", có tác vụ cite/co-cite; README không mô tả cách dựng corpus |
| [github.com/beir-cellar/beir](https://github.com/beir-cellar/beir) | bảng datasets: SCIDOCS test-only 1.000 queries / 25K corpus, homepage allenai.org/data/scidocs; không có mô tả provenance |
| [HF dataset allenai/scifact](https://huggingface.co/datasets/allenai/scifact) | "1.4K expert-written scientific claims paired with evidence-containing abstracts"; các trường provenance để trống "[More Information Needed]" — do đó MODEL_CARD không khẳng định corpus SciFact S2ORC-derived |

## 8. Ghi chú yêu cầu cho track VN (SG-032 — không chốt thay)

- Encoder phải multilingual hỗ trợ query tiếng Việt → corpus khoa học Anh; đây là yêu cầu, chưa là lựa chọn.
- Pin đúng một config (model_id/revision/prefix/license/overlap) tại SG-032 theo `tracks.C.multilingual_dense` của protocol; một fixed config trước relevance pooling; không relevance grid; technical dev pilot không cần nhãn relevance.
- RELATED_WORK RW11 đã ghi nhận Multilingual E5 (Wang et al., 2024) là ứng viên tham khảo — **không phải cam kết**.
- Cross-lingual capability phải được chứng minh qua đánh giá tuyến C với nhãn người; điểm multilingual tổng hợp trên web không thay thế.

## 9. Kiểm tra đi kèm

- `tests/unit/test_model_config.py`: config load được (parser nghiêm: chặn duplicate key/NaN), đủ trường bắt buộc, nhất quán protocol (cosine/l2_normalize/missing_embedding/selection_gate), revision là sha 40-hex hoặc ghi unknown tường minh, mọi candidate có overlap disclosure + nguồn URL + ngày truy cập, cross-check revision MiniLM khớp `compute_pilot.json`, và **adversarial tests** trên fixture hỏng trong thư mục tạm (thiếu trường, revision rỗng, normalize=false, similarity sai, JSON lỗi, duplicate key, NaN) với validator FAIL rõ và subprocess exit code 1.
- Kết quả chạy thật: xem [log phiên](../management/logs/SESSION-20260916-030.md).

## 10. Bàn giao tiếp theo

- **SG-019:** compute pilot với `BAAI/bge-base-en-v1.5` revision `a5beb1e3…` (re-verify hash khi tải), rồi encode shard theo manifest; báo truncation rate.
- **SG-026:** chọn cấu hình dense A trên SciFact dev nDCG@10 trong shortlist §5; pin resolved config trước SCIDOCS test (transfer frozen).
- **SG-032:** chốt multilingual encoder cho track C theo §8.
