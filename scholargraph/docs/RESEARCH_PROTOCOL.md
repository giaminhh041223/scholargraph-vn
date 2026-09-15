# Giao thức nghiên cứu v1 — ScholarGraph VN

- Task: SG-004. Phiên bản: 1.0.0; ngày thiết kế: 2026-09-15.
- Trạng thái: hợp đồng nghiên cứu trước thí nghiệm; **chưa phải cấu hình được phép chạy final test**.
- Cấu hình máy đọc: [protocol_v1.json](../configs/protocol_v1.json). Phạm vi: [SCOPE](SCOPE.md); cơ sở nghiên cứu: [RELATED_WORK](RELATED_WORK.md).
- Quyết định phương pháp của v1 nằm ở [ADR-012](../management/DECISIONS.md). Phê duyệt của người phụ trách và review được ghi riêng trong board/log, không suy từ việc có file.
- Chưa thu thập benchmark tại SG-004, chưa đo retrieval quality, chưa chọn model cuối. Giá trị mặc định dưới đây là lựa chọn của dự án, không phải kết quả tốt nhất đã đo.

## 1. RQ, dữ liệu, nhãn và phép so sánh

| RQ | Tuyến và nhãn | Phương pháp / so sánh định trước | Metric và cách kết luận |
|---|---|---|---|
| RQ1: hybrid có thêm giá trị ngoài từng retriever? | A: BEIR SciFact và BEIR SCIDOCS; qrels chính thức | Chính: hybrid_rrf − bm25, riêng từng dataset. Phụ: hybrid_rrf − dense; TF-IDF là baseline bổ sung | nDCG@10 chính; Recall@100, MRR@10, MAP@100, P@5 phụ; chênh lệch theo query |
| RQ2: PPR bổ sung gì ngoài text? | B: OpenAlex citation holdout, nhãn citation proxy | Chính: hybrid_ppr − hybrid_rrf. Đối chứng: global_pagerank; hybrid_global cùng trọng số fusion | nDCG@10; candidate Recall@100 và oracle nDCG@10; cùng tập ứng viên cho rerank |
| RQ3: ưu tiên bài mới đánh đổi relevance–exposure thế nào? | B: cùng qrels/split của RQ2 và năm xuất bản quan sát được | Chính: hybrid_ppr_age − hybrid_ppr; lambda=0 là đối chứng bắt buộc | nDCG@10 và exposure theo nhóm tuổi; không suy debiasing hoặc quan hệ nhân quả |
| RQ4: truy vấn Việt tìm paper Anh tốt đến đâu? | C: query Việt do người viết, hai người chấm 0/1/2 | Chính: vn_hybrid_rrf − translated_bm25. Phụ: multilingual_dense và original_vi_bm25 | pooled nDCG@10; P@5, MRR@10 và coverage nhãn; Recall/MAP chỉ trên positive đã chấm |

Đây là các giả thuyết có thể không được ủng hộ: fusion/PPR/age có thể không cải thiện hoặc làm giảm relevance. RQ4 đo chất lượng tuyệt đối và khác biệt giữa các phương án xử lý cùng query Việt; không ước lượng mức suy giảm Việt so với Anh nếu chưa có cặp query song ngữ tương đương.

Không gộp ba tuyến hoặc hai dataset A thành một điểm “accuracy”. BEIR SCIDOCS khác full SciDocs/SciRepEval; SciFact ở đây chỉ là evidence retrieval, không đánh giá support/refute hay fact verification. [BEIR](https://github.com/beir-cellar/beir), [SciFact](https://aclanthology.org/2020.emnlp-main.609/)

## 2. Hợp đồng dữ liệu và ranh giới evaluator

1. Snapshot thô bất biến; manifest ghi nguồn, license, revision/checksum, thời điểm tải, preprocessing và ID namespace. Namespace nội bộ ánh xạ lossless về ID BEIR khi xuất TREC run.
2. Ranker được đọc corpus, query text và observed inputs đúng tuyến. Ranker/indexer không nhận qrels, held-out edge list, nhãn người hoặc feature được tạo từ các nhãn đó. Tuning chỉ nhận metric dev từ evaluator.
3. Split builder/auditor là thành phần tin cậy riêng: có thể đọc nhãn để tạo/mask/audit split; không xuất nhãn, số positive bị giữ lại hoặc danh sách ứng viên chọn theo test labels cho ranker.
4. Trước test, chỉ audit cấu trúc, hash, counts, duplicate/mapping và feasibility; không đọc test scores để sửa query, model, split, threshold hoặc chọn corpus.
5. Duplicate DOI/canonical-paper groups, query trùng/paraphrase và model training overlap được audit ở SG-010/011/017. Shared corpus giữa dev/test là bình thường trong retrieval; shared query intent gần như trùng phải được kiểm tra.
6. Fixture được gắn synthetic=true và không nằm trong bảng học thuật. Không tạo nhãn bằng agent rồi gọi là nhãn người.

## 3. Tuyến A — benchmark text

### A1. Dataset, split, candidate universe

- SciFact: dùng test chính thức. **Toàn bộ official train được khai báo là internal dev** cho core pretrained inference; không fit model bằng nhãn này. Đây là lựa chọn v1 thay bản dự thảo “tách một phần train làm dev”; tránh bỏ phí dev khi không có bước huấn luyện. Manifest vẫn giữ tên split nguồn train và role nội bộ dev.
- SCIDOCS: dùng official test; không tạo official dev. Dùng model/cấu hình text đã chọn trên SciFact dev và khóa trước khi đọc điểm test của cả hai dataset. Báo rõ cross-dataset transfer của cấu hình.
- SG-009 xác minh splits và counts trong archive, pin checksum. Các con số phổ biến 5.183/300 và 25.657/1.000 chỉ là dự trù từ BEIR, không điền vào manifest như số đã tải.
- Index toàn bộ title + abstract/text của corpus chính thức. Không thêm metadata ngoài, citation, tuổi, venue, author hay translated/expanded queries vào bảng A.
- Candidate universe là full official corpus; áp dụng chính sách BEIR loại identical query/document ID khi có self-match. Kiểm tra qrels mâu thuẫn với self-removal ở SG-009/011, không âm thầm sửa qrels.
- Giữ nguyên văn bản/ID/qrels thô; text normalization chỉ ở derived index và ghi cấu hình. Không lọc corpus theo relevant labels hoặc theo việc dense có embedding.

### A2. Retrieval budget

TF-IDF, BM25 và dense trả top 100 từ cùng universe. RRF nhận hai danh sách top 100 BM25/dense, union tối đa 200 rồi trả top 100. Nêu rõ hybrid dùng hai retriever; không gọi chi phí tính toán bằng một baseline. Báo latency/compute riêng, không cắt corpus để làm baseline yếu đi.

## 4. Tuyến B — custom citation holdout và graph gate

Tên: openalex-citation-holdout-v1. Kịch bản **warm-start citation recommendation**: đã biết một phần references của source paper; hệ thống tìm citations chưa biết. Text query là title + abstract của source. Citation là proxy relevance, uncited paper chưa phải negative đã được con người xác nhận.

### B1. Feasibility ở SG-014, trước khi mở rộng/chấm điểm

Pilot 1.000–3.000 paper, core mục tiêu 10.000–20.000 nếu qua gate. SG-014 phải ghi số đo thật về title/abstract/year/reference coverage, DOI/ID mapping, tỷ lệ cạnh ra ngoài corpus, isolated nodes, degree/components, cohort support, chi phí tải và graph computation.

Quy tắc lựa chọn trước khi xem retrieval scores:

- Chỉ node có năm hợp lệ; source có title và abstract, ít nhất 2 references nội bộ hợp lệ để giữ được ≥1 observed và ≥1 held-out.
- Chọn test_year mới nhất đã kết thúc trước năm snapshot có ≥50 source hợp lệ; dev_year là năm trước test_year gần nhất có ≥30 source hợp lệ. Không dùng năm hiện tại chưa hoàn tất. Đây là quy tắc availability, không dùng score.
- Mỗi source phải có ≥100 novel eligible candidates. Cap 100 dev queries và 200 test queries bằng thứ tự SHA-256 của seed + canonical source ID; không chọn query dễ.
- Nếu pilot không chứng minh đủ cohorts/support hoặc không xác minh được masking/provenance: ghi no-go và quyết định scope tại SG-014. Không giảm floors sau khi xem điểm; không tự thay bằng một bộ nhãn khác.
- Floors 30/50 là mức thực dụng cho pilot, không phải đảm bảo statistical power. SG-014 ghi chính xác years, query IDs, split hash, graph policy và kết luận go/no-go vào GRAPH_PROTOCOL/ADR trước chạy chính thức. Mọi thay đổi v1 có version và lý do trước test.

### B2. Tạo observed và held-out inputs

Với source u, lấy references R(u) ánh xạ vào snapshot, khác u/canonical duplicate và có year(v) ≤ year(u). Loại duplicate references trước split. Sắp R(u) theo SHA-256 của chuỗi UTF-8 “20260915|u|v” (ID chuẩn); hash bằng nhau phá hòa theo ID tăng dần. Giữ lại h = min(|R|-1, max(1, ceil(0.2|R|))) references đầu làm H(u); O(u)=R(u) trừ H(u). Đây là một split deterministic đã khai báo, không chạy nhiều split rồi chọn kết quả đẹp.

- Builder giữ H của **cả dev và test** làm qrels binary, chỉ evaluator/auditor đọc; ranker nhận O.
- Xóa mọi cạnh trong H_dev ∪ H_test và cạnh đảo tương ứng trước mọi graph feature; kể cả reverse augmentation, co-citation, coupling, degree và graph embedding. Không dựng graph từ qrels.
- Với query năm y, dùng induced graph của node year≤y sau masking chung. Tất cả cạnh và đường đi qua paper tương lai đều bị loại. Các cached scores/index phải gắn graph hash + cutoff.
- Core dùng directed, unweighted citation edges u→v, không thêm reverse edges. Việc cấm cạnh đảo vẫn phải được audit để phòng input có reciprocal edge/biến đổi sau.
- Universe U(u): tất cả canonical papers trong snapshot có year≤year(u), trừ self/canonical duplicate và O(u). Không dùng H để lọc/chọn ứng viên. Known references bị loại ở mọi baseline trước top-k.
- Ghi số references unmapped, future-dated, missing-year và bị loại; nhãn chỉ phủ citations trong universe này. Không dùng negative sampling trong core.
- Mọi prior/degree/PageRank chỉ tính từ graph hợp lệ. Không dùng cited_by_count hiện tại hoặc raw degree làm feature.

Ví dụ synthetic: u có references a,b,c,d,e; nếu b thuộc H thì u→b và b→u bị xóa trước tính graph. a,c,d,e vẫn là observed và bị loại khỏi danh sách citation mới. b nằm trong full eligible universe cùng các paper khác; ranker không được nhận thông tin “b là đáp án”.

Lọc năm trên snapshot hiện tại chỉ hỗ trợ **publication-year-constrained retrospective experiment**. Không khẳng định strict historical simulation: metadata/references có thể cập nhật sau năm xuất bản, cùng năm cũng chưa có thứ tự thời gian chính xác.

### B3. Seeds, tập rerank và expansion

BM25/dense retrieve top 100 trên U(u); hợp RRF rồi chốt C100=top 100 của hybrid_rrf. Tất cả hybrid_rrf, hybrid_global, hybrid_ppr, hybrid_ppr_age rerank **đúng C100**. Seeds là top 20 của hybrid_rrf trong C100, không lấy từ labels; graph propagation được đi trong graph hợp lệ nhưng final output vẫn C100.

Global PageRank độc lập xếp hạng full U(u), chỉ là popularity diagnostic. hybrid_global dùng global scores trên C100 và cùng gamma của hybrid_ppr để đối chiếu personalization. Candidate expansion tắt trong core; nếu mở sau phải có ADR và bảng riêng.

## 5. Công thức và quy ước triển khai

Các phương thức thực thi ở SG-018/020/022–025; SG-004 chỉ đặt hợp đồng, không cài ranker.

### 5.1 Lexical và dense

Tokenizer lexical: Unicode casefold; token regex (?u)\b\w+\b; không stopword removal hoặc stemming. Corpus text=title + một dấu cách + abstract; thiếu field dùng chuỗi rỗng và báo coverage. Dùng cùng tokenizer cho TF-IDF/BM25.

- TF-IDF: tf=1+ln(f) nếu f>0, idf=ln((N+1)/(df+1))+1; vector L2 normalize, cosine; vector rỗng cho score 0.
- BM25: k1=1.5, b=0.75; idf=ln(1+(N-df+0.5)/(df+0.5)); score cộng trên **unique query tokens**, nhân tf factor f(k1+1)/(f+k1(1-b+b|d|/avgdl)). Nếu corpus/tokenizer rỗng: lỗi input. Đây là positive-IDF variant được chọn, không mặc định implementation/package nào cũng dùng công thức này.
- Dense: cosine trên vectors L2 normalized; model/revision/adapter/prefix/truncation/max length chờ SG-017. Không tự chọn E5/BGE/SPECTER từ dossier. Model cho paper→paper và query→paper phải có justification/task adapter; overlap pretrained phải công bố.
- Ties: score giảm dần, canonical doc ID tăng dần theo Unicode code points. NaN/Inf, duplicate IDs hoặc missing embeddings không được âm thầm làm thay đổi universe.

### 5.2 RRF

RRF(d)=Σ_m 1/(60+rank_m(d)), rank bắt đầu từ 1. Document không có trong danh sách top 100 của m đóng góp 0. Hai retriever có trọng số bằng nhau; tie rule dùng ở từng danh sách và sau fusion. k=60 là default định trước, không đảm bảo tối ưu. [Nguồn RRF](https://cormack.uwaterloo.ca/cormack/cormacksigir09-rrf.pdf)

### 5.3 PageRank/PPR

P có hàng chuẩn hóa theo out-degree trên graph hợp lệ. Hàng dangling (không cạnh ra) được thay bằng v. p(t+1)=0.85 Pᵀp(t)+0.15v; p(0)=v.

- PPR: v(d)=RRF(d)/Σ_seed RRF trên top 20 text seeds, còn lại 0.
- Global PageRank: v uniform trên tất cả nodes hợp lệ.
- Converge khi ||p(t+1)-p(t)||₁ < 1e-8, tối đa 200 iterations. Ghi iterations/residual; không hội tụ thì run failed, không dùng iterate cuối làm kết quả.
- Graph/candidate không rỗng là điều kiện input; nếu không có seeds do mọi query token/text rỗng thì báo input failure, không tạo seeds bằng qrels.
- Nếu dùng NetworkX, truyền tol=1e-8/|V| để đúng global L1 threshold của dự án; default thư viện dừng theo |V|×tol. [NetworkX implementation](https://networkx.org/documentation/stable/_modules/networkx/algorithms/link_analysis/pagerank_alg.html)

### 5.4 Fusion và age variant

Với C100, normalize s thành (s−min)/(max−min); vector hằng số thành toàn 0, graph score thiếu thành 0 nhưng phải báo count và lý do. F=(1−gamma)×norm(RRF)+gamma×norm(PPR), gamma∈{0,0.1,0.2,0.3}; chọn trên B dev. hybrid_global thay PPR bằng global score và giữ gamma.

Age variant duy nhất: F_age(d)=F(d)×exp(−lambda×max(0,year(u)−year(d))), lambda∈{0,0.01,0.03,0.05,0.1}. Năm tham chiếu là năm source, không phải năm máy tính chạy. Missing-year bị loại khỏi tuyến B từ đầu; **không điền median**. Demo vẫn có thể giữ metadata thiếu, ghi missing rõ.

SG-024 xác nhận công thức/đơn vị/năm và phân tích dev, SG-026 chọn lambda sau khi gamma đã khóa. Nếu đổi họ công thức, phải amendment trước final test và giữ đối chứng không age. Đây là post-fusion freshness adaptation, không phải tái lập CiteRank hoặc time-balanced centrality. [Cơ sở phân biệt](RELATED_WORK.md)

## 6. Evaluator và thống kê

### 6.1 Metric contract

| Tên báo cáo | Định nghĩa / mapping |
|---|---|
| nDCG@10 (chính) | DCG@10=Σ_{i≤10} rel_i/log2(i+1); IDCG là thứ tự giảm dần tất cả qrels của query, cắt 10. Gain **linear rel**, không dùng 2^rel−1. Mapping trec_eval: ndcg_cut_10 |
| Recall@100 | Số unique relevant ở top 100 / tổng positive qrels; relevant khi rel≥1. Mapping recall_100 |
| MRR@10 | 1/rank relevant đầu tiên nếu rank≤10, ngược lại 0. BEIR evaluate_custom với MRR@10; hoặc trec_eval recip_rank trên **run đã cắt top 10**, không giả định tên recip_rank_10 |
| MAP@100 | AP@100=Σ_{i≤100} Precision@i×I(rel_i≥1) / tổng positive qrels; macro AP. Mapping map_cut_100 |
| P@5 | Số relevant trong top 5 / 5, kể cả run ngắn. Mapping P_5 |

- Macro arithmetic mean trên **toàn bộ query IDs của split đã khóa**. Query thiếu ranking có điểm 0. Query không có positive qrels/IDCG=0: ghi điểm 0, giữ trong macro và báo số lượng; không âm thầm bỏ.
- Unjudged nhận gain 0 khi chấm, nhưng giữ trạng thái unjudged riêng; không gọi đó là negative đã xác minh. VN dùng nhãn 0/1/2 và linear gain để đồng nhất contract.
- Reject duplicate ranking IDs, duplicate/mâu thuẫn qrels, nonfinite score, ID ngoài universe và qrel positive ngoài eligible universe. Fail audit trước aggregate; không loại query lỗi để tăng điểm.
- Canonical order là score desc/doc ID asc. trec_eval có thể tự sắp lại equal-score runs; SG-008 phải xuất score thứ tự giảm nghiêm ngặt (N−rank+1), giữ raw scores ở artifact riêng, rồi kiểm tra thứ tự cùng evaluator. Không dựa vào cột rank của TREC khi scores bằng nhau.
- SG-008 pin evaluator/library revision; toy fixtures graded relevance, MAP denominator, MRR cutoff, ties, short/empty runs, no positives, duplicates và self-match phải khớp công thức tay/primary evaluator trước real run.
- A/B báo candidate Recall@100 của C100 và oracle nDCG@10 (sắp positive trong C100 tốt nhất, IDCG vẫn từ full qrels); B rerank không thể tăng Recall@100 khi giữ C100.
- Tuyến C đổi tên Recall/MAP thành pooled Recall@100/pooled MAP@100; không so với full-corpus recall.

Nguồn contract cần đối chiếu tại SG-008: [trec_eval nDCG](https://github.com/usnistgov/trec_eval/blob/main/m_ndcg_cut.c), [MAP cutoff](https://github.com/usnistgov/trec_eval/blob/main/m_map_cut.c), [BEIR evaluation](https://github.com/beir-cellar/beir/blob/main/beir/retrieval/evaluation.py). Convention do v1 chọn phải được pin vào run; không thay gain sau khi nhìn test.

### 6.2 Chênh lệch và uncertainty

Với mỗi primary comparison §1: lưu per-query difference, mean difference và paired bootstrap percentile CI 95%, 10.000 resamples, seed=20260915. Resample query_group có hoàn lại; group là canonical source/query family không trùng giữa dev/test, singleton nếu không có nhóm liên quan. Mỗi lần lấy toàn bộ queries của group được chọn và tính macro trên queries của mẫu đó; cùng mẫu cho hai hệ thống. Lưu group membership hash và thuật toán/quantile method (linear interpolation).

CI là **pointwise, chưa điều chỉnh multiple comparisons**; protocol v1 không báo p-value hoặc kết luận formal statistical significance. Không chuyển CI không chứa 0 thành bằng chứng thắng trên mọi dataset/chủ đề. Secondary comparisons và bucket analysis là exploratory; muốn kiểm định family-wise phải preregister phép thử/điều chỉnh trước test.

Báo delta tuyệt đối; phần trăm tương đối chỉ khi baseline khác 0, nếu không ghi undefined. Ví dụ synthetic 0.40→0.42 là +0.02 và +5%; không phải số đo dự án. CI bootstrap phản ánh bất định theo query/group, không bao gồm model overlap, annotation bias hoặc mọi lựa chọn split. Core deterministic không lặp seed để tạo CI giả; nếu thêm thành phần stochastic, tối thiểu 3 seed được định trước và tách variance giữa seeds.

### 6.3 Exposure theo tuổi cho RQ3

Buckets theo tuổi năm: 0–2, 3–5, 6–10, ≥11. Với mỗi query, exposure_b@10 = Σ_{i≤10} I(age_i∈b)/log2(i+1), chia tổng discount của số kết quả thực trả (empty list →0); báo số kết quả/query để thấy missing outputs. Macro theo query.

Báo song song: share bucket trong U(u), C100 và top 10; số positive qrels theo bucket, recall theo bucket khi mẫu có support; unknown-year và exclusions ở audit. Bucket không có positive ghi undefined cho recall bucket, kèm support thay vì điền 0. Exposure thay đổi mô tả ưu tiên tuổi, không chứng minh giảm bias có điều kiện hoặc tăng chất lượng paper.

## 7. Tuyến C — mini-benchmark Việt → Anh

- Cùng snapshot corpus English của OpenAlex đã pin, không dùng citation qrels B làm nhãn C. Nếu graph no-go, C chỉ tiếp tục khi có snapshot text hợp lệ và scope quyết định ở SG-014.
- Core 30 queries: 10 dev, 20 test. Hai người viết query từ nhu cầu/intent, không sinh từ test qrels/citation đáp án. Chia theo query family/intent trước tuning; paraphrases cùng nhóm, không nằm hai split.
- Pilot gán nhãn 5 query **thuộc dev** để đo thời gian, chỉnh hướng dẫn trước test. Không chạm test labels để chọn dịch/encoder/pooling.
- Baselines: original_vi_bm25; translated_bm25; multilingual_dense; vn_hybrid_rrf fusion translated_bm25 + multilingual_dense. SG-032 chốt đúng một cấu hình dịch và một multilingual encoder dựa trên task fit, license, tài nguyên và technical dev pilot (thuật ngữ/code-switching), trước khi tạo pool nhãn. Cache/hash, ngôn ngữ đích, prefix/revision và term handling phải pin. Core không phụ thuộc paid LLM; không mặc định Google Translate. Không chọn từ nhiều trial bằng relevance khi chưa có dev judgments.
- Pool là union top 10 của **translated_bm25, multilingual_dense, vn_hybrid_rrf**, khử trùng; thứ tự ẩn danh/xáo trộn seed cố định, không hiển thị method/score. Hai người chấm độc lập từng cặp. Đây là blinded system provenance, không gọi là double-blind nghiên cứu.
- Trần toán học 30×3×10=900 cặp unique trước dedup (1.800 judgments nếu hai người), khoảng 600 là ước tính workload, không bảo đảm 500–600. Nếu quá budget, thay depth/query count đồng đều trước test annotation bằng ADR; không bỏ riêng tài liệu bất lợi.
- Nhãn: 0 không liên quan, 1 liên quan một phần, 2 đáp ứng trực tiếp intent. Thiếu thông tin không tự thành 0: để unjudged và xử lý theo hướng dẫn/adjudication đã khóa.
- Lưu original labels của cả hai trước hòa giải. Agreement: linearly weighted Cohen kappa, weights=1−|a−b|/2 trên cặp có đủ hai nhãn; kèm count, raw agreement và confusion matrix. Degenerate denominator → undefined; không bịa kappa=1.
- SG-031 khóa query/split/instructions; SG-032 pin các cấu hình và chạy technical dev pilot không cần nhãn relevance. SG-033 tạo pool 10 dev bằng ba phương pháp cố định và chấm dev trước (5 query pilot nằm trong 10 này); dùng pooled dev nDCG@10 để chọn phương pháp mặc định trong ba phương pháp, giữ nguyên cả ba cấu hình/rankings và primary comparison. Ghi quyết định cùng config hash trước khi tạo/chấm 20 test queries. SG-033 giữ test labels embargo; SG-034 xác nhận freeze/hash/pool/qrels rồi evaluator mới mở nhãn test. Không đổi model/prompt/parameters sau khi xem dev judgments trong core v1; mở tuning grid cần ADR với dev pool đủ phủ toàn bộ trials và ngân sách annotation riêng trước test.
- Ghi judged@5/@10/@100 và unjudged rate mỗi phương pháp. Main pooled methods phải giữ đúng cấu hình đã tạo pool; original_vi_bm25 hoặc hệ thống thêm sau có thể chưa đủ judgments, chỉ báo kèm giới hạn coverage.
- PPR trên query Việt là optional diagnostic nếu coverage/gate cho phép và được đăng ký trước pool; không cần để trả lời so sánh chính RQ4. Không thêm nhãn/citations từ B vào query C.
- Cỡ test 20 nhỏ, pooled judgments không đầy đủ; không gọi là benchmark chuẩn quốc tế hoặc claim recall toàn bộ corpus.

## 8. Ngân sách tuning, ablations và freeze

### 8.1 Chọn cấu hình

| Thành phần | Dev / ngân sách định trước | Quy tắc chọn |
|---|---|---|
| Lexical, RRF | Các defaults §5 cố định; không grid search | Thay tokenizer/IDF phải amendment trước final test |
| Dense cho A/B | SG-017 shortlist tối đa 3 model/task-adapter configurations; pilot compute trước full encode | Chọn A trên SciFact dev nDCG@10; B có thể chọn adapter phù hợp paper query trên B dev; pin riêng và dùng chung giữa baselines trong một comparison |
| B gamma | 4 giá trị §5.4 | Max dev nDCG@10; ties chính xác → gamma nhỏ hơn |
| B lambda | 5 giá trị, giữ gamma đã chọn | Max dev nDCG@10; ties → lambda nhỏ hơn; không tune theo exposure để ép claim relevance |
| C | Một translation config + một multilingual config pin ở SG-032; không relevance-grid. Ba fixed methods tạo dev pool trước chấm | Chọn default method bằng pooled dev nDCG@10 sau dev annotation, ties → method ID lexicographic; không đổi configs hoặc primary comparison |

Tuning log giữ tất cả trials/lỗi và chi phí; không dùng test leaderboard để chọn. Dense ties dùng config ID định trước. Không tự mở fine-tune/cross-encoder. SG-026 chốt resolved settings A/B, SG-027 freeze trước main test; VN có freeze riêng như §7.

### 8.2 Ablations và fairness

- A: TF-IDF, BM25, dense, hybrid_rrf trên cùng full corpus/split.
- B: hybrid_rrf, hybrid_global, hybrid_ppr, hybrid_ppr_age trên cùng C100 và graph cutoff; global_pagerank standalone là diagnostic khác candidate-generation.
- B giữ gamma của hybrid_ppr cho hybrid_global và age; lambda=0 khôi phục hybrid_ppr. Không retune từng ablation để đổi nhiều thành phần cùng lúc.
- C: original_vi_bm25, translated_bm25, multilingual_dense, vn_hybrid_rrf trên cùng corpus/query/split, main pool cố định.
- Optional expansion/different seed strategies/time families chỉ mở bằng ADR trước test; không coi kết quả hậu kiểm là primary.

### 8.3 Những mục còn chờ, không được điền số giả

| Gate | Giá trị cần chốt | Task chịu trách nhiệm |
|---|---|---|
| A data | archive revision/hash, query IDs, source train→dev mapping, duplicates/self policy audit | SG-009–011 |
| B graph | topic/filter/snapshot, coverage, years, query IDs/groups, observed/heldout masks, hashes, go/no-go | SG-013/014/016 |
| Model | ID/revision/license, adapters/prefixes, overlap, dimensions/truncation, compute pilot | SG-017 |
| Evaluator | package/revision, fixture equivalence, tie serialization | SG-008 |
| Final A/B | full resolved configs/trial registry, ranking depth, hashes/environment/code, planned comparisons | SG-026/027 |
| C | query groups/labels guide, translation/encoder, pool provenance, agreement/labels and embargo | SG-031–034 |

JSON v1 có runnable=false và unresolved_gates. Runner SG-007 phải từ chối final test khi chưa có resolved run config + freeze evidence theo tuyến, không chỉ bỏ các trường null. Các gate được hoàn tất qua manifest/run config riêng, không ghi đè lịch sử v1. SG-004 hoàn thành thiết kế không có nghĩa SG-027 đã freeze.

## 9. Run evidence và xử lý lỗi

Mỗi run có ID duy nhất RUN-YYYYMMDD-HHMMSS-method-dataset-split (thêm suffix nếu trùng); timestamps có timezone. Lưu protocol/config hash và resolved config, data/split/query-group/candidate/masked-graph hashes, model/revision/tokenizer/adapter, translation cache nếu có, code commit + dirty/source hash, hardware/library lock, seed/command, start/end/status, ranking, raw scores, per-query/aggregate metrics và logs không chứa secrets.

Chỉ completed run qua data/evaluator/leakage checks được vào báo cáo. Không ghi đè completed run; rerun tạo ID mới. Lỗi evaluator sau test: giữ run sai, ghi phạm vi ảnh hưởng, sửa có version/ADR và chạy lại công bằng tất cả systems bị ảnh hưởng; không tiếp tục tune theo corrected test score. SG-042 cần người còn lại thực sự tái lập; self-check không thay independent human reproduction.

## 10. Tiếp nhận bản pre và gói hiểu bài

Bản pre của Gemini do người dùng cung cấp giúp dựng khung ba tuyến, RRF/PPR và danh sách công việc. Các tham số gợi ý được xem xét như lựa chọn dự án; công thức/split/claims phải kiểm chứng. Không coi pre là primary source hay bằng chứng đã chạy. Chi tiết sửa ở [source audit](../management/reviews/SG-004-SOURCE-AUDIT.md).

Các điểm đã chỉnh: linear nDCG theo evaluator; MRR@10 đúng cutoff; giữ observed/heldout warm-start; mask cả dev/test và paths tương lai; không impute năm; weighted agreement; trần pool 900 cặp; CI định trước không tự suy p-value; model/translation còn chờ gate; không nhận nguyên config mẫu là run-ready.

**Giải thích ngắn:** A kiểm tra tìm kiếm bằng nội dung trên benchmark. B che một phần references rồi kiểm tra graph giúp tìm lại bao nhiêu, trên cùng ứng viên. C dùng query Việt và nhãn người, với giới hạn nhãn theo pool.

**Ví dụ:** nếu đáp án citation u→b vẫn có trong adjacency, PPR có thể đi thẳng tới đáp án. Xóa sau khi đã tính PageRank không đủ: mọi feature phải được tính lại từ graph đã mask.

**Câu hỏi bảo vệ:** ranker được đọc những gì, và vì sao paper không được trích dẫn chưa thể gọi là không liên quan? Người phụ trách xác nhận protocol sau khi đọc; không ghi hoạt động hiểu bài/gán nhãn là đã làm thay họ.
