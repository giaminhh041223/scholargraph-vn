# Nhật ký quyết định

Mỗi thay đổi phương pháp/phạm vi quan trọng thêm ADR mới. Không ghi đè quyết định cũ; ghi mục thay thế và lý do.

## ADR-001 — 2026-09-15 — Khu vực ScholarGraph độc lập

**Trạng thái:** accepted for planning.
**Bối cảnh:** workspace có E-COMASPECT, lecture files, checkpoints và dữ liệu cũ; chưa có Git.
**Quyết định:** đặt dự án tại `scholargraph/`; root AGENTS dẫn sang đây.
**Hệ quả:** môi trường/data/results riêng; không dùng kết quả cũ làm benchmark mới.

## ADR-002 — 2026-09-15 — Lịch dựa trên giả định

**Trạng thái:** provisional.
**Quyết định:** 12 tuần, 3 người × 10 giờ/tuần; các task ghi giờ-người và role.
**Chưa biết:** deadline, nhân sự, GPU, rubric.
**Cập nhật khi:** người dùng cung cấp thông tin hoặc SG-001/SG-002 xác minh.
**Hệ quả:** tuần tương đối, không tự đặt deadline lịch.

## ADR-003 — 2026-09-15 — Tách text benchmark và graph evaluation

**Trạng thái:** accepted for planning; graph protocol chọn ở SG-014.
**Lý do:** BEIR qrels không phải graph features; bổ sung citation có nguy cơ chứa đáp án.
**Quyết định:** tuyến A benchmark text nguyên bản; tuyến B OpenAlex custom protocol có masking; bảng external enrichment nếu có phải riêng.
**Hệ quả:** không tuyên bố score graph là official BEIR khi inputs khác.

## ADR-004 — 2026-09-15 — Registry và bàn giao trên đĩa

**Trạng thái:** accepted.
**Quyết định:** task specs ở TASKS.md; mutable status/evidence ở tasks.json; state.json chỉ điều phối; mỗi phiên có log và HANDOFF.
**Hệ quả:** đọc bằng chứng trước tiếp nối, một người điều phối board; kiểm tra tự động read-only.

## ADR-005 — 2026-09-15 — Định nghĩa đóng góp nghiên cứu

**Trạng thái:** accepted for planning.
**Quyết định:** kiểm nghiệm hybrid retrieval + graph + tuổi paper; chưa claim novelty/SOTA hay tăng 3–5%.
**Hệ quả:** kết quả âm vẫn có giá trị nếu protocol chặt và phân tích đầy đủ.

## ADR-006 — 2026-09-15 — Tiếng Việt có đánh giá riêng

**Trạng thái:** accepted for planning.
**Quyết định:** VN nghĩa giao diện và query Việt → corpus Anh; cần model/cách dịch phù hợp và pooled human labels.
**Hệ quả:** English benchmark không chứng minh khả năng cross-lingual; 50 query là mục tiêu timebox, giảm quy mô phải ghi rõ.

## Mẫu ADR tiếp theo

ID: ADR-015
Ngày:
Trạng thái: proposed / accepted / superseded
Task liên quan:
Bối cảnh:
Các lựa chọn:
Quyết định và bằng chứng:
Hệ quả:
Thay thế ADR nào (nếu có):

## ADR-007 — 2026-09-15 — 7 tuần, 2 người, agent hỗ trợ

**Trạng thái:** accepted; thay thế giả định lịch ở ADR-002.
**Nguồn:** người dùng xác nhận còn khoảng 7 tuần, có 2 người, dùng Kaggle/Colab và sẽ cân nhắc thuê GPU nếu cần.
**Quyết định:** 7 tuần với tuần 7 dự phòng/bảo vệ; 10–20K OpenAlex core; pretrained inference, fine-tune để stretch. Dự trù 12–15 giờ/người/tuần, cần theo dõi tải công việc thực tế.
**Cộng tác:** agent hỗ trợ module/checks; hai người chịu trách nhiệm nhãn, insight, review và nội dung bảo vệ. Không coi phân vai là đã tạo task/agent hay cấp quyền chi tiền.
**Hệ quả:** GPU profiling/resume vào tuần 1–2; chưa thuê; kết quả âm vẫn được báo cáo.

## ADR-008 — 2026-09-15 — Giới hạn annotation và bỏ phụ thuộc GPU khỏi scaffold

**Trạng thái:** accepted for planning; thu gọn mục tiêu annotation ở ADR-006.
**Quyết định:** core VN khoảng 30 query, 10 dev/20 test, pool top-10 từ 3 phương pháp, mục tiêu khoảng 600 cặp unique. SG-033 dự trù 16 giờ-người, cập nhật từ pilot 5 query. Có thể tăng 50 query nếu còn nguồn lực; luôn báo hạn chế cỡ mẫu/pooling.
**Lý do:** hai người cần đọc paper và gán nhãn thật trong 7 tuần; agent không thay thế được nhãn người.
**Phụ thuộc:** SG-005 cần SG-001, không chờ toàn bộ GPU pilot SG-002; setup local có thể bắt đầu độc lập. Encoding SG-019 vẫn cần compute pilot hoàn tất.
**Hệ quả:** tổng core 142 giờ-người có agent hỗ trợ; tiếp tục việc local được nếu tài khoản notebook chưa sẵn.

## ADR-009 — 2026-09-15 — Model routing và bàn giao theo lane

**Trạng thái:** accepted for workflow; không phải quyền chạy toàn bộ backlog.
**Nguồn:** người dùng yêu cầu gán model cho các ID và chiến lược cửa sổ chat; đối chiếu OpenAI Docs và model catalog của host hiện tại.
**Quyết định:** routing đủ SG-000–049 với primary/review profile, reasoning, lane và human gate. Astra cho phương pháp/gates/thống kê, Sol cho pipeline khó/điều phối, Terra cho triển khai rõ spec; Luna chỉ hỗ trợ cơ học. Chưa có benchmark model trên dự án.
**Cửa sổ:** 7 lane logic, chỉ mở khi cần; thường C + một worker + V. Mỗi phiên 1–3 task liên quan, bàn giao trên đĩa trước đổi context. Review học thuật dùng context mới và snapshot xác định; nhãn và nghiệm thu con người không được thay bằng AI.
**Quyền ghi:** làm rõ ADR-004: coordinator duy nhất ghi shared board/state/HANDOFF/chat registry. Worker/reviewer có log/report riêng. Một phiên độc lập có thể kiêm điều phối nếu không có coordinator khác.
**Hệ quả:** thêm routing/matrix, chiến lược, templates, tra cứu task và validator. Không đổi dependency/lịch core, không mở thread/agent, không đổi model runtime, không mua compute. Actual model/session chỉ ghi khi xác minh được.

## ADR-010 — 2026-09-15 — Chấp thuận scope và đẩy mốc hoàn thành sớm

**Trạng thái:** accepted.
**Task liên quan:** SG-001; ảnh hưởng lịch toàn bộ core.
**Nguồn:** người dùng xác nhận task đã được review, yêu cầu đánh giá/hoàn tất và cho phép thời hạn linh động miễn trước tháng 12/2026, ưu tiên làm sớm để dành thời gian cho học phần khác.
**Quyết định:** chấp thuận problem, 4 RQ và core/non-core trong SCOPE để triển khai. Đặt target nội bộ 2026-10-31; giữ 2026-11-01–2026-11-30 làm buffer cho lỗi, rubric mới, tái lập và bảo vệ. Không mở stretch chỉ vì có buffer.
**Minh bạch review:** không có review report riêng tồn tại trước closeout; ghi xác nhận trực tiếp của project owner là human review confirmation và thực hiện acceptance audit. Không gọi đó là independent model audit.
**Yêu cầu còn mở:** deadline chính thức, rubric/weights, format nộp, chính sách AI/pretrained/external data và quy định nhóm vẫn OPEN/PARTIAL; phải cập nhật khi có nguồn và trước SG-045.
**Hệ quả:** SG-001 có thể DONE; next SG-002. Nếu lịch chính thức sớm hơn target, lịch chính thức ưu tiên và phải cập nhật state/ADR.

## ADR-011 — 2026-09-15 — Miễn hoạt động đọc sâu của SG-003

**Trạng thái:** accepted.
**Task liên quan:** SG-003; mở dependency SG-004.
**Nguồn:** project owner yêu cầu bỏ qua hoạt động hai thành viên đọc sâu RW02, RW06 và RW10, chuyển SG-003 thành DONE và mở SG-004 nhưng chưa triển khai.
**Quyết định:** chấp nhận fresh-context review PASS làm gate kiểm tra artifact. Miễn phần đọc sâu ba paper của hai thành viên như một deviation có chủ ý; không ghi hoặc suy rằng hoạt động này đã hoàn tất.
**Hệ quả:** SG-003 chuyển DONE. SG-004 đủ dependency và là task kế tiếp ở trạng thái TODO, chưa owner/session/claimed paths. Rủi ro còn lại là hai thành viên có thể chưa giải thích sâu RRF, SciRepEval và time-balanced centrality khi bảo vệ; có thể đọc bù sau nếu cần.

## ADR-012 — 2026-09-15 — Thiết kế protocol v1 và tiếp nhận dossier SG-004

**Trạng thái:** accepted; project owner xác nhận “Duyệt protocol v1”, ghi nhận lúc 2026-09-15T17:40:52.6906333+07:00, sau fresh-context review và re-review PASS. Trước xác nhận này ADR ở trạng thái proposed.
**Phạm vi:** SG-004, không thực thi các task downstream hoặc freeze final run.
**Nguồn:** scope SG-001 đã duyệt, literature SG-003, protocol dự thảo và bản pre Gemini do người dùng cung cấp. Source audit bằng Sol High kiểm chứng BEIR/trec_eval từ primary source; pre chỉ là đề xuất, không phải bằng chứng thực nghiệm.
**Lựa chọn v1:** giữ A/B/C riêng; mỗi RQ có nhãn/method/metric/comparison; A dùng toàn bộ official SciFact train làm internal dev vì core không train model (thay bản nháp tách một phần train), SCIDOCS dùng cấu hình transfer đã khóa. B giữ warm-start observed/heldout 20%, mask cả dev/test và reverse, graph theo cutoff, rerank cùng C100; graph go/no-go và years chờ SG-014. Tuổi dùng một post-fusion exponential freshness variant, loại missing-year khỏi B; không nhận là tái lập CiteRank/time-balanced centrality. C pool ba method, 30 query, 10/20 split, hai người chấm; 600 cặp là dự trù, upper bound 900 trước dedup.
**Evaluator:** nDCG linear gain theo trec_eval; MAP cutoff chia tổng relevant; MRR@10 có adapter đúng cutoff và total order khi ties. Paired percentile CI 95%, 10.000 bootstrap theo query group; không tự suy p-value hoặc formal significance từ CI chưa điều chỉnh nhiều so sánh.
**Sửa sau review vòng 1:** bỏ relevance-grid C 3×3 vì dev pool của cấu hình đã chọn tạo vòng phụ thuộc chọn config/nhãn và thiếu coverage cho trial khác. Core pin 1 translation + 1 encoder trước relevance pooling bằng technical dev pilot; chấm 10 dev trước, chọn default method trong 3 fixed methods, giữ nguyên cấu hình/primary comparison rồi freeze trước chấm 20 test. Upper bound vẫn 300 dev + 600 test = 900 unique pairs; mở grid sau cần ADR và ngân sách dev pool riêng.
**Cấu hình:** protocol_v1.json là machine-readable design contract, runnable=false. Model, hashes, cohort years, resolved tuning và freeze evidence phải chốt ở các gate tương ứng; không điền giả. Thay phương pháp sau thiết kế cần amendment có lý do trước test.
**Hệ quả:** chỉ đánh dấu SG-004 DONE khi acceptance, fresh-context artifact review và xác nhận của project owner có bằng chứng. Không coi lời yêu cầu thực hiện task là đã đọc/duyệt lựa chọn cụ thể vừa được tạo.

## ADR-013 — 2026-09-16 — Tiêu chuẩn chống Silent Bypass và Bắt buộc Adversarial/Negative Testing

**Trạng thái:** accepted.
**Phạm vi:** Toàn bộ các module ingest, audit, retrieval, evaluation, graph và webapp (áp dụng bắt buộc từ SG-010 trở đi).
**Nguồn:** Đúc kết từ các vòng review độc lập của Codex (SG-006, SG-007, SG-010 L1/L2) và phản ánh trực tiếp từ Project Owner về chất lượng thực thi.
**Bối cảnh:** Các task trước đây thường chỉ pass trên "happy path" (dữ liệu chuẩn), nhưng dễ mắc lỗi silent bypass (dùng `.get()` mặc định làm trôi qua lỗi khi thiếu split bắt buộc), thiếu kiểm tra biên (boundary), hoặc narrative suy đoán sai lệch so với dữ liệu thực tế.
**Quyết định kỹ thuật:**
1. **Chống Silent Bypass (No Silent Bypass):** Tuyệt đối không dùng `.get()` mặc định hoặc giá trị fallback để che giấu việc thiếu tài nguyên, thiếu split, hoặc thiếu trường bắt buộc. Khi có lỗi, hệ thống phải báo FAIL rõ ràng, ghi nhận error chi tiết và CLI bắt buộc phải thoát với mã nonzero (1). Tuyệt đối không thay thế phép đo chưa thực hiện bằng 0 hay chuỗi rỗng.
2. **Bắt buộc Adversarial / Negative Testing:** Mọi module trước khi được nghiệm thu DONE bắt buộc phải có test cases phá hủy trong thư mục tạm:
   - Thiếu tài nguyên bắt buộc (missing files/splits).
   - Dữ liệu khuyết thiếu/dị dạng (text-only, title-only, format sai, score ngoài biên).
   - Kiểm tra rò rỉ nhãn (leakage across splits).
   - Kiểm tra thực tế CLI subprocess exit code 1 khi có lỗi.
3. **Đồng bộ 1:1 Narrative và Dữ liệu:** Mọi câu văn trong log/report/Data Card phải xuất phát từ logic toán học chặt chẽ trên toàn bộ biến đếm thực tế; không suy đoán một chiều.
4. **Tự phản biện trước khi bàn giao:** Đóng vai trò "adversary" để tự tìm cách bẻ gãy mã nguồn trước khi báo hoàn tất.
**Hệ quả:** Mọi task downstream (bắt đầu từ SG-012 BM25) chỉ được xem là đạt điều kiện hoàn thành khi đã vượt qua cả positive tests và negative/adversarial tests.

## ADR-014 — 2026-09-16 — Report SG-010 phân biệt chưa đo và quan sát bằng 0

**Trạng thái:** accepted; triển khai ADR-013 theo yêu cầu review/sửa SG-010 của người dùng.
**Phạm vi:** SG-010 mở lại để review và khắc phục; không đổi metric, benchmark raw hoặc split policy.
**Bằng chứng:** Adversarial CLI trong session025 tái hiện positive self-qrel/ID whitespace được chấp nhận, failed resources ghi số 0 giả; thống kê positive-per-query bỏ query toàn nhãn 0.
**Quyết định:** Auditor revision `sg010-2.0.0`, report `schema_version=2`. Component có `status=PASS/FAIL`; khi không thể đo thì scalar/group measurements là `null` và có `error`. Required split thiếu vẫn có entry FAIL. Count 0 chỉ dùng cho tập quan sát thực; thống kê rỗng có count 0 nhưng mean/percentile null. Query toàn nhãn 0 thuộc split vẫn tham gia thống kê positive count.
**Kiểm soát:** Parser không coercion ID/type lỗi, chặn JSON duplicate keys/NaN và score ngoài 0/1/2. Gate chặn positive self-qrel; cross-split ID overlap FAIL, normalized-text overlap báo anomaly với mọi cặp khớp, không tự đổi raw/split. Output không được trỏ vào raw; hash input trước/sau kiểm tra không đổi. Narrative không suy provenance chính thức từ counts hoặc nhận đã kiểm chứng retriever khi mới audit data.
**Tương thích:** Consumer report phải kiểm tra version/status trước đọc measurements, không dùng `null` như 0. Không hồi tố sửa lịch sử report cũ; bản trước session025 được giữ ở `artifacts/reports/sg010_pre_session025.json`. Chỉ DONE sau tests, fresh-context review và continuity checker đạt.

## ADR-015 — 2026-09-16 — Môi trường làm việc độc lập `bn` (bản clone ScholarGraph)

**Trạng thái:** accepted; thực hiện theo yêu cầu trực tiếp của người dùng.
**Phạm vi:** Chỉ workspace `D:/Web_mining_20261/bn`; không sửa bất kỳ file nào ngoài `bn/`. Không đổi trạng thái board, metric, protocol hay raw data.
**Bối cảnh:** Người dùng yêu cầu một folder riêng tên `bn` để làm việc độc lập, clone `scholargraph/` và `AGENTS.md` vào đó, set up môi trường giao task/nhận task theo đúng chuẩn đã thiết lập của ScholarGraph.
**Quyết định kỹ thuật:**
1. Clone toàn bộ `scholargraph/` bằng robocopy (6.227 file, 548,23 MB, FAILED=0), loại trừ `.venv/`, `.pytest_cache/`, `__pycache__/`, `tmp/`, `*.pyc` — là thành phần môi trường/tạm, không phải dự án.
2. `AGENTS.md` gốc (workspace và scholargraph) được clone nguyên văn trừ mục Scope: workspace của môi trường này là `D:/Web_mining_20261/bn`, mọi phiên chỉ làm việc trong `bn/`. Mọi quy tắc chống silent bypass, adversarial testing, checkpoint, review giữ nguyên hiệu lực.
3. Venv bn tạo mới bằng đúng runtime Python 3.12.14 của bản gốc với `--system-site-packages` (venv không relocatable nên không copy); cài `requirements-dev.txt` + `pytrec_eval-terrier==0.5.10` để đạt parity với SG-008. `rank-bm25` sẵn sàng cho SG-012.
4. Copy thêm `SCHOLARGRAPH.md` và 8 file bài giảng được `docs/SCOPE.md` dẫn link vào `bn/` để continuity checker xanh mà không phải sửa nội dung docs (giữ 1:1 narrative với bản gốc).
5. Git local riêng cho `bn` (không nhúng vào repo workspace gốc); board 50 task và lịch sử quản trị được giữ nguyên như snapshot gốc.
**Bằng chứng:** `pytest tests -q` trong bn: 214/214 passed (97.31s, exit 0); `scripts/check_project.ps1` trong bn: PASS (263 links, 50 routes, 7 lanes, 34 sessions). Chi tiết trong [log SESSION-20260916-026](logs/SESSION-20260916-026.md).
**Hệ quả:** Các phiên trong `bn` tiếp tục ScholarGraph từ trạng thái hiện có (next SG-012) trong phạm vi thư mục `bn` only; kết quả thí nghiệm của `bn` không được gán cho workspace gốc và ngược lại, trừ khi được người dùng đồng bộ rõ ràng.

## ADR-016 — 2026-09-16 — Gate khả thi graph Tuyến B: NO-GO trên pilot OpenAlex 2K; chốt holdout/cutoff/masking; loại BEIR enrichment

**Trạng thái:** accepted; kết quả gate NO-GO là kết quả đo được trên snapshot pilot, không phải run failure. Thực hiện theo task SG-014 (lane D, SESSION-20260916-029).

**Phạm vi:** SG-014 và các điều chỉnh scope/dependency chính thức cho SG-015/SG-016 nêu dưới đây. Không tải thêm dữ liệu OpenAlex (thuộc SG-015), không đổi floors của Protocol v1, không đổi raw snapshot, không đụng Tuyến A và Tuyến C.

**Bối cảnh:** SG-013 để lại pilot 2.000 works (topic T10286, seed 20260915) với báo cáo tham chiếu 190 cạnh nội bộ, 1.779 isolated nodes, venue 1.627/2.000 (đã sửa). SG-014 phải tái đếm toàn bộ từ raw, audit mapping OpenAlex↔BEIR, timebox BEIR enrichment, và chốt holdout/cutoff/masking bằng ADR trước khi SG-015 mở rộng.

**Quyết định kỹ thuật:**
1. **Tái đếm độc lập khớp module:** toàn bộ số liệu được đếm lại từ `data/raw/openalex/works.jsonl` (sha256 `3f301e4fc6c9b0de1fa95f736d0ceff2fa6fac137c086e0716fc3afe761c4980`, bất biến) bằng một script đếm riêng rồi đối chiếu với module mới `src/scholargraph/graph/feasibility.py` — khớp 100%. Kết quả: 2.000 works/2.000 canonical ID; 20.102 reference entries; **190** cạnh nội bộ có hướng (0,9452% occurrences); 19.908 occurrences ngoài snapshot; **1.779/2.000 isolated (88,95%)**; 1.819 weak components, largest 71; directed density 4,7523762e-05. Số cũ 190/1.779 được xác nhận; phát hiện mới báo cáo cũ không có: **4 self-loops** (W1511283908, W2915731794, W2153150702, W2741603249), 0 entry reference trùng lặp, 0 cặp cạnh đảo, 3 năm ngoài biên 1900–2100 (1885/1895/1899), 22 thiếu năm, min/max năm hợp lệ 1902/2026 (251 works năm 2026).
2. **Cohort Protocol v1 B1 → NO-GO:** chỉ 21 eligible source tổng cộng, tối đa **2 source/năm** (nhiều năm 1990–2024), trong khi floor định trước là ≥50 test / ≥30 dev → `test_year = null`, `dev_year = null`. Tiêu chí novel-candidates đạt (min 162 ≥ 100 candidates/source trên 21 source) nhưng hai floor cohort là ràng buộc: **overall = NO_GO**.
3. **Mapping OpenAlex↔BEIR:** hai corpus BEIR không expose trường DOI (0/5.183 SciFact, 0/25.657 SCIDOCS) trong khi OpenAlex có 1.202/2.000 (60,1%) → **DOI join bất khả thi**. Exact-title probe (casefold, thu gọn whitespace): SciFact 0 match, SCIDOCS 8 match — chỉ là probe thăm dò, không xây quyết định mapping trên đó.
4. **BEIR enrichment bị loại khỏi Tuyến B:** SciFact không có bất kỳ trường reference nào. SCIDOCS có `metadata.references` (24.504/25.657 docs; 218.316 entries; 20.825 occurrences nội bộ; 20.811 cạnh unique; 197.491 ngoài corpus) nhưng query SCIDOCS không phải node trong corpus và qrels SCIDOCS là dẫn xuất citation — dùng reference graph đó làm cạnh sẽ trùng cấu trúc với nhãn test (rò rỉ trực tiếp kiểu "test citation trong adjacency") và vi phạm ranh giới Tuyến A (cấm thêm citation/metadata). Số đo chỉ được giữ làm bằng chứng timebox.
5. **Chốt holdout/cutoff/masking** tại [docs/GRAPH_PROTOCOL.md](../docs/GRAPH_PROTOCOL.md) v1.0.0, chuyên mục hóa Protocol v1 §4: cạnh masked `M = H_dev ∪ H_test ∪ cạnh đảo tương ứng` (đúng `mask_scope` trong protocol_v1.json); mọi graph feature (PPR/PageRank, degree, co-citation, coupling, graph embedding) phải được tính lại trên `G_mask` đúng cutoff `year ≤ year(u)`; adjacency cho PPR không được chứa cạnh held-out theo **cả hai chiều** (PPR truyền theo Pᵀ nên xóa một chiều là chưa đủ); mask scope là toàn cục, không per-query; cache gắn `(graph_hash, mask_hash, cutoff)`; `H` không dùng để lọc ứng viên hay chọn query; không chạy nhiều split rồi chọn split đẹp.
6. **Contract CLI:** lỗi tài nguyên/dữ liệu fatal (thiếu file, JSON hỏng, ID trùng, sai kiểu, manifest lệch sha256, thiếu floor trong config) → exit 1, status FAIL, không đo đạc nào bị thay bằng 0 (ADR-013/014); NO-GO đo được → exit 0 với `decision.overall = NO_GO` và bằng chứng từng tiêu chí.
7. **Yêu cầu đối với SG-015** (điều chỉnh scope/dependency chính thức): đổi chiến lược sampling từ seeded random topic sample sang snapshot có kết nối trích dẫn thật (ví dụ expansion qua `referenced_works`/`cited_by` quanh seed works, hoặc cohort venue/năm có mật độ trích dẫn nội bộ cao), pin manifest (filter, seed, sha256, thời điểm) trước khi tải; **giữ nguyên mọi floor** (50/30/2/100); chạy lại CLI gate này trên snapshot core và chỉ `overall = GO` mới mở SG-016; SG-016 đứng trước gate GO là blocked.

**Bằng chứng:** [artifacts/reports/graph_feasibility.json](../artifacts/reports/graph_feasibility.json) (sha256 `e0f29a347f5a04c8e241e9dc8964615e211b863122df2888f8c9389752ee00b5`, status MEASURED, provenance gồm sha256 + bytes của 5 input, lệnh chạy, thời điểm đo, `qrels_used=false`); module `src/scholargraph/graph/feasibility.py` (sha256 `54eaadf801333181abbfd1d0cbf1f11570ec084d5be62f57f87ab9d3626bf3ed`); tests `tests/unit/test_graph_feasibility.py` (sha256 `4889b393c2800e5df11c095c56ad1dd39c0cc41d9774744e8af6a98be31b40e4`): **37/37 passed** gồm adversarial (thiếu 5 loại file bắt buộc, JSONL hỏng, ID trùng, ID sai, thiếu `referenced_works`, năm sai kiểu, manifest lệch hash, manifest chưa COMPLETED, snapshot rỗng, corpus BEIR rỗng/ambiguous/duplicate ID) và 3 CLI subprocess kiểm chứng exit code (1 khi lỗi, 0 khi NO-GO đo được); full suite `pytest tests -q`: **321/321 passed** (162,55s). Hash raw trước/sau không đổi: works.jsonl `3f301e4f…`, scifact corpus `dec31c81…`, scidocs corpus `328bb388…`, manifest `83039135…`.

**Hệ quả:** Tuyến B chưa thể tạo masked split trên dữ liệu hiện có; không hạ floor, không thay nhãn, không tự đổi protocol sau khi xem kết quả. SG-015 giữ dependency `SG-013, SG-014` nhưng phạm vi được điều chỉnh như mục 7; SG-016 chỉ bắt đầu sau gate GO trên snapshot core. BEIR enrichment bị loại vĩnh viễn khỏi Tuyến B trừ khi có ADR mới với evidence mapping/leakage riêng. Tuyến A và Tuyến C không bị ảnh hưởng; Tuyến C vẫn tiếp tục khi có snapshot text hợp lệ theo Protocol v1 §7.

**Thay thế ADR nào (nếu có):** không thay thế; chuyên mục hóa và bổ sung chi tiết thi hành cho ADR-003/ADR-012 (quyết định graph protocol và go/no-go trước đó giao cho SG-014).

## ADR-017-DRAFT — 2026-09-17T22:29:57+07:00 — Works không text bị loại khỏi dense universe (đề xuất ban đầu, đã được thay thế bởi ADR-017 chính thức bên dưới)

**Trạng thái:** superseded by ADR-017 (2026-09-17 accepted).
**Task liên quan:** SG-026 (B trials), SG-019 (follow-up additive).
**Bối cảnh:** `dense encode --corpus openalex_core` FAIL đúng thiết kế tại work `openalex:W126924136` (dòng 29): không title lẫn abstract. Rà toàn snapshot: chỉ **1 work** textless (6 works thiếu title còn lại vẫn có abstract_inverted_index). Policy `missing_embedding=fail_not_drop_document` cấm drop ngầm.
**Các lựa chọn:** (a) giữ FAIL — B-track dense vĩnh nhiễn không chạy được; (b) encode chuỗi rỗng — vi phạm L2/cosine và policy; (c) loại tường minh 7 works khỏi DENSE universe, giữ guard fail trong encoder (chọn).
**Quyết định (đề xuất):** dense universe OpenAlex = 18.250 works có text; 1 work textless bị loại khỏi dense candidate universe với counts/ID ghi trong manifest + report (không im lặng); lexical vẫn phủ qua empty-string policy; encoder giữ nguyên fail-loud; thay đổi code cộng thêm (spec entry + subset builder + tests), không sửa hành vi hiện có; SG-019 mở lại review delta trước khi encode production.
**Hệ quả:** B-dev trials chạy được sau khi human duyệt ADR này.


## ADR-017 — 2026-09-17 — Mở lại SG-019 và chính sách loại tường minh cho work thiếu text

**Trạng thái:** accepted; người dùng phê duyệt trực tiếp (chuyển quyền coordinator + duyệt mở lại SG-019). Thay thế bản nháp ADR-017-DRAFT ở trên.
**Phạm vi:** SG-019 (đóng DONE trước đó chỉ phủ SciFact); encoding corpus OpenAlex; không đổi protocol hay raw data.
**Bối cảnh:** Acceptance SG-019 yêu cầu encode theo từng corpus manifest, nhưng bản DONE trước chỉ có SciFact 5.183 docs. Encode OpenAlex bị chặn bởi `missing_embedding=fail_not_drop_document` tại work `openalex:W126924136` (thiếu cả title lẫn abstract). Session trước đã tạo text-subset `data/processed/openalex/works_text.jsonl` (18.250 = 18.251 − 1) kèm manifest `openalex_core_text.json` (counts: parent 18.251, text_works 18.250, excluded 1) và đề xuất ADR này; encode dừng ở 2/19 shards. SCIDOCS chưa encode.
**Quyết định:** (1) Mở lại SG-019 về IN_PROGRESS; hoàn tất encode OpenAlex text-subset (19 shards) và SCIDOCS (26 shards; work thiếu abstract dùng title — combined text không rỗng, không vi phạm fail_not_drop_document), rồi review lại trước khi DONE mới. (2) Chính sách loại tường minh: work không có sự kết hợp title+abstract nào bị LOẠI KHỎI encoding corpus với exclusion list + count trong manifest (hiện 1/18.251); đây là recorded transformation theo ADR-013 — không phải silent drop; mọi consumer phải đọc exclusion từ manifest. (3) Không hạ điều kiện protocol `missing_embedding=fail_not_drop_document`.
**Bằng chứng:** manifest `data/manifests/openalex_core_text.json` (fingerprint, counts); shard manifests namespace `openalex_core_text`; `data/processed/openalex/works.jsonl` sha256 `04e7008e...` bất biến.
**Hệ quả:** Vector dense cho OpenAlex chỉ phủ 18.250/18.251 works; consumer (SG-020/023/025/026) phải đối chiếu exclusion khi mapping doc-ID. SG-026 phần B tiếp tục chờ encode đầy đủ như note đã ghi.


## ADR-018 — 2026-09-19T22:22:02+07:00 — Main Freeze trước final runs

**Trạng thái:** accepted; freeze manifest tạo bởi SG-027, đã được owner human-approve trước SG-028.
**Phạm vi:** Toàn bộ data, split, graph, model configs, evaluator, selection được khóa trong `configs/frozen_main.json` (32 hash + git HEAD); narrative trong `docs/MAIN_FREEZE.md`.
**Bối cảnh:** Card SG-027 + chỉ thị người dùng yêu cầu khóa hash trước final runs; SG-026 selection đã human-approve; SG-033 prerequisite (OpenAlex-e5 index 18.250 docs) đã encode xong 19:22 cùng ngày.
**Quyết định:** (1) Primary comparison chốt: track A (bm25/tfidf/dense/hybrid), track B (control + PPR best gamma=0.3/lambda=0.0), track C VN (translated_bm25/multilingual_dense_e5/vn_hybrid_rrf; original_vi_bm25 diagnostic). (2) Ablations định sẵn cho SG-029. (3) Quy tắc sau freeze: mọi thay đổi phải bump schema_version + ADR; tuning trên test cấm vĩnh viễn; final runs phải dẫn freeze sha256 trong run manifest.
**Bằng chứng:** `configs/frozen_main.json` (32 hash); `tests/unit/test_main_freeze.py` đối chiếu freeze↔file thật (phát hiện drift); encode OpenAlex-e5 18.250 docs hoàn tất 19:22 (sha256 trong freeze).
**Hệ quả:** SG-028 final runs chỉ chạy trên freeze này; kết quả test từ đây có giá trị học thuật "chưa từng thấy test".


## ADR-019 — 2026-09-29 — Hợp nhất `bn` → bản chính, vệ sinh test (SG-051/SG-052) và review hồi tố độc lập (SG-027/028/029/040)

**Trạng thái:** accepted; triển khai theo `docs/MERGE_AND_FINISH_PLAN.md` được người dùng phê duyệt.
**Task liên quan:** SG-027, SG-028, SG-029, SG-030, SG-040, SG-041, SG-051, SG-052.
**Bối cảnh:** Toàn bộ công việc từ SG-012 đến SG-041 đã được thực hiện trong môi trường độc lập `bn/` (ADR-015). Để hoàn tất dự án tại bản chính `D:/Web_mining_20261/scholargraph`, cần giải quyết: (1) nguy cơ lệch byte EOL khi git checkout/merge (`core.autocrlf=true`); (2) nối lịch sử git của `bn` (`e959f68`, `dcca385`) vào repo chính; (3) cô lập `test_text_subset.py` để không ghi đè dữ liệu freeze thật khi chạy pytest, bổ sung test cho 2 nhánh fallback còn thiếu của hybrid API (`dcca385`), và sửa header bảng A2 trong `ablation.md` (SG-052); (4) thực hiện review hồi tố độc lập cho SG-027, SG-028, SG-029, SG-040 (vốn trước đó mới tự kiểm + owner duyệt).
**Quyết định kỹ thuật:**
1. Thêm `.gitattributes` (`* -text`) và chạy `git add --renormalize .` trong `bn` trước khi merge; sao lưu dự phòng `.tmp/backups/bn_scholargraph_backup_20260929.zip` (sha256 `eec6e7eca74bb84c2682f491ffdaceea94199ee8cd464cca127f03bd9ebc9ccc`).
2. Lưu nhánh cũ của bản chính vào `archive/pre-merge`; dùng `git fetch ./bn master:bn-import` và `git merge --allow-unrelated-histories` để giữ nguyên toàn bộ commit SHA của `bn` (`e959f68`, `dcca385`) trong lịch sử bản chính.
3. Chuyển nguyên trạng các thư mục ngoài git (`artifacts/`, `data/`) sang bản chính mà không qua git text checkout, giữ `bn` làm bản dự phòng.
4. Thực hiện đầy đủ SG-052, sửa lỗi đóng gói SG-041 (`run_demo.bat`, `requirements.lock`, đường dẫn tương đối trong `REPRODUCE.md`/`DEMO_SCRIPT.md`), và bổ sung báo cáo review độc lập cho SG-027, SG-028, SG-029, SG-030, SG-040, SG-041, SG-052.
**Hệ quả:** Bản chính `D:/Web_mining_20261/scholargraph` trở thành nguồn sự thật duy nhất có đầy đủ lịch sử git, 33/33 file freeze khớp byte-exact SHA-256, và bộ kiểm thử không chạm vào dữ liệu đã đóng băng.


## ADR-020 — 2026-09-30 — Phạm vi boundary và XML của public arXiv (EXT-03)

**Trạng thái:** accepted trong public search extension; không đổi human gates SG.

**Căn cứ:** fresh SOL review EXT-03-W1-081 trên head74df8db: 53 tests pass nhưng 3P1/4P2 được chứng minh bằng temp reproducers.

**Quyết định:**

- CLI module arxiv là validator payload/optional SearchRequest schema, chưa phải production search; không xem CLI0 là live search pass. Duplicate JSON keys và lỗi arguments phải FAIL/exit1, error messages không stringify raw request/ValidationError. Query grammar mismatch giữa validator và adapter phải nêu scope rõ; không sửa schema frozen để che lệch semantics.
- Chỉ claim hỗ trợ encoding có positive evidence: UTF8/UTF16 có/không BOM. UTF32 được nhận diện để từ chối rõ unsupported, bao gồm payload hợp lệ và DTD; không claim positive support từ negative-only tests. Không thêm dependency.
- Source IDs/version, Atom root/singleton và raw-field link provenance phải validate đúng. Không nhận arbitrary related link là license, không dùng keyword đầu title/abstract như Error correction để kết luận upstream error.

**Bước thực thi:** Gemini R4 author fixes + regression, coordinator chạy thật, independent SOL re-review trước EXT-03 DONE. W0 contract/config/schema giữ nguyên; W1 chưa tích hợp khi quyết định này được ghi.

## ADR-021 — 2026-10-01T23:10:58.246939+07:00 — Tích hợp Public Paper Search MVP vào master local

Người dùng đã xác nhận demo/save/mở JSON-BibTeX và đồng ý tích hợp. Coordinator fast-forward nhánh đã review sau hash/continuity gates, không push/publication.14tasks phaseA DONE; EXT09/10DEFERRED; main research human gates giữ nguyên. CacheP95.5674156s n5 chưa đạt đề xuất500ms là giới hạn công bố; pilot không đo relevance/availability dài hạn. Download xác nhận bởi người dùng, không là proof công cụ agent.


## ADR-022 — Mở giai đoạn B public search

- 2026-10-01T23:30:30.299120+07:00; user yêu cầu làm đến hết và cho tự chọn site. Mở EXT09/10 trên nhánh riêng từ master.
- Crossref là sidecar enrichment DOI chính xác, không thêm Source vào v1 search; giữ metadata gốc và ghi conflict/provenance. Public anonymous, không bịa email.
- Chọn JOSS published HTML, robots và policy raw được lưu. Giới hạn một host HTTPS, listing + paper citation, 1 request/3s, concurrency1, không PDF/JS/ngoài host; caps và resume integrity bắt buộc.
- SOL nhận EXT09 do Muse write allowlist chỉ review/log; Gemini file-only nhận EXT10, coordinator chạy tests do terminal native bị denied. Muse xhigh review snapshot thật.
- Scope không thay human research gates SG030/033, không tự mở stretch hoặc push.
