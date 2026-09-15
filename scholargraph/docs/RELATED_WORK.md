# Tổng quan nghiên cứu và định vị đóng góp — ScholarGraph VN

Task: SG-003. Phiên bản: `related-work-v1`. Ngày tra cứu: 2026-09-15.

Trạng thái: bản phục vụ review; chưa có fresh-context review và chưa có xác nhận hai thành viên đọc sâu. Tài liệu tham khảo: [references.bib](references.bib). RQ/phạm vi giữ theo [SCOPE](SCOPE.md); các đề xuất thiết kế dưới đây chuyển sang SG-004, không tự thay [protocol](RESEARCH_PROTOCOL.md).

## 1. Kết luận để định hướng dự án

Định vị phù hợp là **một nghiên cứu thực nghiệm có kiểm soát về text, graph và tuổi bài trong tìm kiếm tài liệu khoa học**, kèm đánh giá Việt → Anh và demo tái lập. Các thành phần đều có tiền lệ. Chưa có cơ sở gọi tổ hợp là thuật toán mới hay SOTA.

Ba phân biệt chi phối thiết kế:

- Graph trong dữ liệu huấn luyện pretrained khác graph đưa vào lúc xếp hạng: cần báo cả hai để diễn giải RQ2.
- Tìm paper liên quan một paper khác, tìm bằng chứng cho một claim, và tìm bằng câu hỏi tự nhiên có nhãn/candidate khác nhau.
- Ưu tiên bài mới và hiệu chỉnh thiên lệch tuổi là hai mục tiêu khác nhau. Cần đo cả relevance lẫn exposure (mức xuất hiện ở các vị trí cao).

Đây là tổng hợp có chọn lọc phục vụ core 7 tuần, không phải systematic review hoặc khảo sát đầy đủ tới năm 2026. Không sao chép số điểm paper thành mục tiêu bắt buộc của dự án.

## 2. Cách chọn và kiểm chứng nguồn

Tra cứu theo năm nhóm: BM25/RRF; personalized/topic-sensitive PageRank; scientific embeddings; citation age bias; query-oriented temporal recommendation. Dùng PDF của tác giả, ACL Anthology, arXiv và trang nhà xuất bản. Metadata tác giả/năm được đối chiếu theo bài, không lấy ngày crawl của kết quả tìm kiếm.

Chọn 12 nguồn cho ma trận: phương pháp nền tảng, benchmark khớp tuyến A/C, và tiền lệ trực tiếp có thể bác bỏ novelty quá rộng. Với 11 nguồn có PDF, đã đối chiếu các phần nêu trong bảng; không khẳng định đã đọc toàn bộ mọi phụ lục. TextTAGC chỉ đọc được abstract/metadata của nhà xuất bản, nên không dùng để nhận xét chi tiết split, leakage, code hay tái lập.

BM25 (2009) là chuyên khảo phương pháp do các tác giả chủ chốt viết, không phải bài công bố đầu tiên của BM25. E5 là technical report/preprint. CiteRank có preprint 2006 và bài journal 2007; bibliography ghi journal 2007 kèm đường dẫn preprint.

### Ma trận 12 primary sources

“Giới hạn/áp dụng” là nhận định của ScholarGraph khi chuyển phương pháp sang scope này, trừ khi chỉ rõ tác giả đã nêu. Mã `RWxx` ánh xạ 1–1 sang BibTeX key trong cột đầu.

| ID / BibTeX key / nguồn | Phương pháp và bằng chứng đã đối chiếu | Giới hạn/áp dụng cho ScholarGraph |
|---|---|---|
| RW01 `robertson2009bm25` — Robertson & Zaragoza, 2009, [BM25 and Beyond](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf) | PRF; BM25 có term-frequency saturation và điều chỉnh độ dài. Đọc §2.1–2.3, §3.4–3.5, §5; chuyên khảo lý thuyết và tham số. | Baseline từ khóa bắt buộc cho RQ1. Phải ghi tokenizer, IDF variant, k1/b; lexical matching không tự giải quyết query Việt trên corpus Anh. SG-018. |
| RW02 `cormack2009rrf` — Cormack, Clarke & Büttcher, 2009, [RRF](https://cormack.uwaterloo.ca/cormack/cormacksigir09-rrf.pdf) | Tổng hợp bằng nghịch đảo thứ hạng; đọc công thức §1 và Tables 1–3 trên TREC/LETOR. k=60 được chọn ở pilot rồi giữ cố định. | Lý do dùng RRF làm hybrid baseline; kết quả nguồn không bảo đảm BM25+dense luôn thắng. Độ sâu danh sách/ứng viên và missing rank phải cố định. SG-020/021. |
| RW03 `haveliwala2002topic` — Haveliwala, 2002, [Topic-Sensitive PageRank](https://www.cse.iitb.ac.in/~soumen/readings/papers/Haveliwala2002topic.pdf) | §2 Eq.5 và §3: vector personalization không đều; tính các vector theo chủ đề để tạo điểm phụ thuộc query. Đánh giá trên Web, §4. | Cơ sở PPR; không phải bằng chứng trực tiếp cho citation recommendation. Query-seeded PPR của dự án là một lựa chọn triển khai khác cơ chế topic vectors của bài. SG-023. |
| RW04 `cohan2020specter` — Cohan et al., ACL 2020, [SPECTER](https://aclanthology.org/2020.acl-main.207/) | §2–4: triplet training dùng quan hệ citation; inference từ text không cần citation. SciDocs gốc gồm bảy tác vụ document-level. | Phân biệt graph pretraining với graph rerank. SciDocs đầy đủ khác BEIR SCIDOCS; pretrained overlap cần audit. SG-011/017. |
| RW05 `ostendorff2022scincl` — Ostendorff et al., EMNLP 2022, [SciNCL](https://aclanthology.org/2022.emnlp-main.802/) | Abstract, §1, phần method và thảo luận sampling: chọn láng giềng trên citation embeddings làm contrastive samples; margin giảm positive/negative collisions. Đánh giá SciDocs. | Paper không trích dẫn nhau vẫn có thể gần về nội dung; citation là nhãn proxy có nhiễu. Chưa chọn SciNCL cho query tự nhiên; SG-017 phải đối chiếu task/model. |
| RW06 `singh2023scirepeval` — Singh et al., EMNLP 2023, [SciRepEval/SPECTER2](https://aclanthology.org/2023.emnlp-main.338/) | §3–4, Table 1 và Appendix A: 24 tasks, bốn format, phân biệt proximity với ad-hoc search; SPECTER2 dùng biểu diễn theo format. | SG-017 cần adapter/query representation phù hợp. Không chuyển điểm giữa SciRepEval, SciDocs và BEIR khi evaluator/candidates khác. Chỉ dùng làm cơ sở chọn model, benchmark SciRepEval vẫn stretch. |
| RW07 `thakur2021beir` — Thakur et al., NeurIPS Datasets and Benchmarks 2021, [BEIR](https://arxiv.org/abs/2104.08663) | §3–5, Appendix B/D: benchmark retrieval đa miền; BM25 là đối chứng mạnh trong thí nghiệm bài. Appendix B chỉ rõ giới hạn English và pure textual search. | Tuyến A giữ input/evaluator chuẩn; thêm graph hoặc recency cần bảng riêng. BEIR không chứng minh RQ4. SG-004/009/028. |
| RW08 `wadden2020scifact` — Wadden et al., EMNLP 2020, [Fact or Fiction](https://aclanthology.org/2020.emnlp-main.609/) | §2–4: SciFact có claim, abstract chứa evidence và rationale; tác vụ gốc gồm retrieval và verification support/refute. | ScholarGraph chỉ đánh giá retrieval theo bản BEIR; nDCG tốt không đồng nghĩa xác minh claim đúng hoặc phát hiện stance. SG-004/009. |
| RW09 `walker2007citerank` — Walker et al., 2007, [CiteRank](https://arxiv.org/abs/physics/0612122) | Preprint pp.1–2, Eq.1: bắt đầu duyệt graph theo prior giảm mũ với tuổi; kiểm tra trên APS/hep-th, dùng citation tăng thêm làm proxy traffic. | Tiền lệ trực tiếp cho graph + freshness; không thể nhận tổ hợp đó là mới. Task global traffic khác query relevance. SG-024 phải nói rõ tuổi tác động ở đâu. |
| RW10 `mariani2016timebalanced` — Mariani, Medo & Zhang, 2016, [Time-balanced network centrality](https://arxiv.org/abs/1608.08414) | §II.D Eq.3: z-score PageRank trong cửa sổ paper gần tuổi; §III/Discussion đối chiếu APS Milestone Letters. | Hiệu chỉnh tuổi khác exponential freshness. Milestone significance khác query relevance; chuẩn hóa theo năm lịch cũng khác cửa sổ theo số bài của nguồn. SG-024/030. |
| RW11 `wang2024multilinguale5` — Wang et al., 2024, [Multilingual E5](https://arxiv.org/abs/2402.05672) | §2–3: contrastive pretraining đa ngôn ngữ rồi supervised fine-tuning; đánh giá retrieval/embeddings, có các kích thước model khác nhau. | Ứng viên cho RQ4; kết quả multilingual chung chưa chứng minh query Việt → abstract khoa học Anh. SG-017/032 cần model card, prompt/prefix và overlap audit. |
| RW12 `liu2026texttagc` — Liu et al., Scientometrics 2026, [TextTAGC](https://link.springer.com/article/10.1007/s11192-025-05518-5) | Abstract nhà xuất bản: query-oriented recommendation kết hợp title/abstract, graph convolution và temporal features; báo thí nghiệm AAN/DBLP. | Tiền lệ gần cho text+graph+time. Full text chưa truy cập; không suy cấu hình, fairness hay code availability. ScholarGraph chọn pretrained inference/PPR theo ngân sách; chưa so thực nghiệm với TextTAGC. |

## 3. Từ công thức đến lựa chọn cần kiểm nghiệm

### 3.1 RRF: hợp nhất thứ hạng

Theo RW02, `RRF(d) = sum_r 1 / (k + rank_r(d))`. Dự án cần quy ước document vắng trong danh sách bị cắt đóng góp 0; thứ hạng bắt đầu từ 1 và xử lý ties ổn định. Đây là chi tiết triển khai phải kiểm thử ở SG-020.

Ví dụ tự tạo: k=60, paper A đứng 1/10 ở BM25/dense có điểm khoảng 0,03068; B đứng 3/2 có điểm khoảng 0,03200. RRF ưu tiên B. Ví dụ chỉ minh họa phép tính; không dùng làm bằng chứng cải thiện retrieval. Hợp nhất bằng rank không đòi BM25 score cùng thang với cosine.

### 3.2 PPR: truyền điểm từ các paper khởi đầu

Ký hiệu của tài liệu này: `p_q = alpha * P^T p_q + (1-alpha) * v_q`, trong đó P có hàng tổng bằng 1 sau xử lý dangling nodes, v_q là phân phối seed từ text retrieval. Alpha ở đây là xác suất đi theo cạnh; đối chiếu ký hiệu khi đọc RW03 vì bài dùng quy ước restart khác.

Ví dụ tự tạo: A→B và A→C; seed tập trung ở A thì điểm có thể đi tới B/C. Nếu A→B là cạnh dùng làm đáp án holdout, phải xóa cạnh trước mọi phép tính graph. Seed phải được tạo từ text/observed inputs được phép; đây là quy tắc protocol ScholarGraph, không phải kết quả mới của RW03.

### 3.3 Ba cách đưa tuổi vào có ý nghĩa khác nhau

- RW09: đưa tuổi vào prior bắt đầu duyệt, dạng `exp(-age/tau)`.
- RW10: biến đổi điểm PageRank đã tính thành `z_i = (p_i - mean_window_i) / std_window_i` theo cửa sổ publication-order.
- Một phương án dự án có thể thử: hiệu chỉnh điểm sau fusion bằng age factor. Đây là adaptation cần chốt, không tự gọi là bản tái lập RW09/RW10.

SG-024 chỉ chọn một variant core sau dev/feasibility; ghi vị trí áp dụng, cutoff, missing-year policy và trường hợp phương sai 0 nếu dùng z-score. Không tăng danh sách ablation bắt buộc chỉ vì đã tìm thấy thêm paper. Graph/age không được thêm vào official text table của tuyến A.

## 4. Đối chiếu novelty và claim được phép

| Ý tưởng | Tiền lệ đối chiếu | Claim hiện có thể dùng |
|---|---|---|
| Kết hợp các danh sách retrieval | RW02 | Áp dụng RRF và đo RQ1 trên corpus/split đã khóa |
| Graph score phụ thuộc query/chủ đề | RW03 | Kiểm tra phần giá trị PPR bổ sung trên cùng candidate set |
| Citation để học biểu diễn nội dung | RW04–06 | Dùng pretrained model; công bố thông tin graph trong training |
| Citation graph cùng tuổi bài | RW09–10 | Phân tích relevance–exposure; chưa claim debiasing tổng quát |
| Text + graph + time cho query-oriented paper recommendation | RW12, ở mức abstract đã truy cập | Mục tiêu ứng dụng đã có tiền lệ; khác biệt của implementation chưa chứng minh novelty |
| Query Việt → paper Anh | RW11 và tuyến C đã định | Đánh giá nội bộ bằng nhãn người; chưa gọi benchmark chuẩn hoặc phương pháp cross-lingual mới |

Tuyên bố đóng góp dự kiến của nhóm:

> ScholarGraph VN kiểm nghiệm giá trị bổ sung của tín hiệu trích dẫn và hiệu chỉnh tuổi bài trên một hệ truy xuất hybrid. Nghiên cứu tách benchmark text chuẩn, thí nghiệm graph có masking và đánh giá truy vấn Việt → tài liệu Anh; báo cáo ablation, độ bất định, exposure và chi phí tái lập trên phạm vi dữ liệu xác định.

Đây là kế hoạch đóng góp thực nghiệm. Chỉ sau các run hợp lệ mới đổi động từ “kiểm nghiệm” thành phát hiện cụ thể. Nếu PPR không tăng nDCG, phân tích theo graph coverage, query intent và candidate recall vẫn trả lời được RQ2. Điểm số giữa dữ liệu khác nhau không dùng để tuyên bố thắng tác giả khác.

## 5. Bàn giao cho SG-004 và các task sau

Các mục sau là đề xuất của ScholarGraph dựa trên đối chiếu; SG-004 sẽ khóa chi tiết, không coi bảng này là config đã duyệt.

| RQ | Đối chứng cần giữ | Nhãn và bằng chứng | Lỗi diễn giải cần tránh |
|---|---|---|---|
| RQ1 | BM25, dense, RRF | Tuyến A; nDCG@10, Recall@100; paired per-query analysis | Gán hiệu quả dense/graph cho fusion khi corpus hoặc candidates đổi |
| RQ2 | Hybrid, global PageRank diagnostic, hybrid+PPR | Tuyến B qua SG-014; masked graph, held-out citations; thêm candidate recall | Nếu dense đã học citation thì đo giá trị graph bổ sung, không phải toàn bộ giá trị graph từ đầu |
| RQ3 | Hybrid+PPR có/không age variant | Tuyến B; relevance và exposure theo tuổi trong cùng eligible universe | Nhiều bài mới hơn chưa chứng minh relevance cao hơn hay giảm bias có điều kiện |
| RQ4 | Dịch query+BM25, multilingual dense, hybrid theo protocol C | Khoảng 30 query Việt, nhãn 0/1/2 của hai người; agreement trước hòa giải | Benchmark English hoặc điểm multilingual tổng hợp không thay thế test Việt |

Candidate expansion phải tách khỏi reranking trên tập ứng viên cố định. Mask held-out edges trước PPR, degree, reverse edges, coupling và các feature suy ra. Corpus hiện tại lọc theo năm chỉ hỗ trợ retrospective experiment; strict historical simulation còn cần metadata khả dụng tại cutoff. Các quy tắc này kế thừa protocol hiện có.

RQ3 nên báo tối thiểu phân bố tuổi trong corpus eligible và trong top-k, kèm relevance theo bucket khi đủ nhãn. Một diagnostic exposure có thể dùng trọng số `1/log2(rank+1)` rồi cộng theo bucket, macro theo query. Đây là đề xuất diagnostic cần chốt ở SG-024, không phải phép kiểm định công bằng hoặc bằng chứng nhân quả. Với bucket nhỏ, báo số query/document hỗ trợ và độ bất định thay vì diễn giải quá mức.

## 6. Citation là proxy relevance — giải thích khi bảo vệ

Citation quan sát hành vi tham khảo của tác giả. RW05 nêu cả khả năng hai bài tương tự mà không có citation lẫn nhiễu của tín hiệu citation. Vì vậy trong tuyến B, “khôi phục citation bị giữ lại” đo một nhiệm vụ cụ thể, chưa bao phủ toàn bộ tài liệu hữu ích cho người dùng. [SciNCL](https://aclanthology.org/2022.emnlp-main.802/)

Ví dụ tự tạo: paper A trích B để giới thiệu phương pháp; C dùng phương pháp tương tự nhưng không nằm trong references của A. Với nhãn holdout, B là positive; C chưa có nhãn liên quan chắc chắn. Hệ thống trả C có thể hữu ích dù evaluator không cộng điểm. Ngược lại, một citation chỉ cung cấp bối cảnh có thể ít hữu ích cho intent hiện tại.

Khi bảo vệ: “Chúng tôi dùng citation làm tín hiệu thay thế có giới hạn cho liên quan; báo riêng kết quả retrieval bằng nhãn benchmark và đánh giá query Việt bằng người chấm.” Không diễn giải citation count/PageRank là độ đúng của nội dung paper.

## 7. Kế hoạch hai thành viên đọc sâu 3 paper

Cả hai đều đọc cùng ba bài. Thời gian dưới đây là timebox đề xuất, không phải giờ đã làm. Agent chuẩn bị câu hỏi; phần hiểu bài cần câu trả lời của chính hai thành viên.

| Paper | Phần nên đọc / thời gian mỗi người | Sản phẩm sau đọc |
|---|---|---|
| RW02 — RRF | Toàn bài 2 trang; 25–35 phút | Tự tính ví dụ A/B ở §3.1; giải thích k, missing rank và vì sao fusion có thể thua |
| RW06 — SciRepEval | §3–4, Table 1, phần phương pháp và limitations; 45–60 phút | Vẽ bảng paper→paper và query→paper; giải thích chọn adapter/task đúng ở SG-017 |
| RW10 — Time-balanced centrality | §II.D, §III và Discussion; 45–60 phút | Phân biệt freshness với age normalization; nêu một tình huống tăng exposure bài mới nhưng giảm relevance |

Sau đọc, mỗi người viết 3–5 câu cho mỗi paper: bài toán, phương pháp, bằng chứng, một giới hạn, liên hệ RQ. Thảo luận chung 20–30 phút và giải thích lại citation proxy bằng một ví dụ khác §6.

| Xác nhận | RW02 | RW06 | RW10 | Ngày / ghi chú của người đọc |
|---|---|---|---|---|
| Thành viên A (chưa gán tên) | PENDING | PENDING | PENDING | Chưa có xác nhận |
| Thành viên B (chưa gán tên) | PENDING | PENDING | PENDING | Chưa có xác nhận |

## 8. Kiểm tra và điều kiện đóng SG-003

- Ma trận 12 nguồn và bibliography đã chuẩn bị; đường dẫn/metadata theo nguồn gốc được tra cứu.
- Đã tách paper findings khỏi đề xuất dự án; không có claim SOTA, điểm số dự án hay novelty thuật toán chưa chứng minh.
- TextTAGC chỉ có abstract/metadata công khai: đủ xác định tiền lệ rộng, chưa đủ so sánh chi tiết. Không cần mua full text để giữ claim thận trọng hiện tại; muốn so thuật toán phải đọc tiếp bản hợp pháp.
- Fresh-context review: PENDING; gói đầu vào tại [SG-003 review packet](../management/reviews/SG-003-REVIEW-PACKET.md).
- Việc hai thành viên đọc sâu ba paper: PENDING. Đây là hoạt động trong task card; `human_approval_required=false` không cho phép tự ghi rằng đã đọc.

SG-003 giữ REVIEW sau bàn giao. SG-004 chỉ được nhận khi coordinator xác minh review và hoàn tất phần còn lại của task card. Khảo sát này định hướng core; trước một claim “đầu tiên/SOTA” cần rà soát rộng hơn và đối chứng thực nghiệm tương ứng.
