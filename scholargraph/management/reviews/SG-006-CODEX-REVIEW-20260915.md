# SG-006 — Review Codex sau triển khai Gemini

**Verdict: CHANGES_REQUIRED — 2 P1, 3 P2.**

- Ngày ghi nhận: 2026-09-15T21:03:36+07:00.
- Người dùng yêu cầu review SG-006 do Gemini hoàn thành. Vai trò phiên này: reviewer; không sửa implementation hoặc shared board/state/HANDOFF/registry.
- Reviewer Codex ở context riêng với phiên Gemini triển khai; không tham gia viết SG-006. Model/effort cụ thể: unknown, không suy từ profile khuyến nghị A_H.
- Snapshot: commit fdad031; 9/9 SHA-256 trong SG-006-REVIEW-PACKET.md khớp file hiện tại. Không có tracked changes trước review; tài liệu root untracked ngoài scope giữ nguyên.
- Đã đối chiếu SG-006 task card, AGENTS, routing/strategy/registry, state/HANDOFF, session009, protocol v1/JSON và ADR-012 đã duyệt.
- Acceptance: bắt ID/score/year sai; ranker không nhận qrels; schemas/interface/namespace/null policy và synthetic fixtures.
- Báo cáo này bổ sung kiểm chứng độc lập, giữ nguyên báo cáo tự kiểm cũ và lịch sử. Board hiện vẫn ghi DONE; đề nghị coordinator mở lại SG-006 để sửa trước khi dựa vào contract này ở SG-007.

## F1 — [P1] TREC serialization làm mất thứ tự đã khóa trong protocol

**Vị trí:** src/scholargraph/data/schemas.py:258–263, đặc biệt dòng262; test_schemas.py:test_to_trec_lines.

to_trec_lines xuất raw score với sáu chữ số thập phân. Cách này giữ nguyên ties, đồng thời tạo thêm ties khi hai score chỉ khác nhau sau chữ số thứ sáu. Protocol §6.1 và JSON evaluation.trec_serialization yêu cầu score thứ tự giảm nghiêm ngặt N−rank+1, raw scores lưu riêng. trec_eval tự sắp theo score và phá ties theo docno giảm dần, không theo thứ tự dòng/cột rank. Vì thế TREC evaluator có thể chấm một ranking khác với RankingResult.

**Tái hiện đã chạy:** tạo sorted ranking a=0.50000004, z=0.50000003, thứ tự đúng [a,z]. Output:
```text
q1 Q0 a 1 0.500000 scholargraph
q1 Q0 z 2 0.500000 scholargraph
```
Sắp theo comparator score/docno của trec_eval cho [z,a]. Nếu chỉ a relevant thì RR đổi từ1 thành0.5 (minh họa toán, không phải benchmark).

**Sửa:** xuất score thứ tự giảm nghiêm ngặt như protocol; giữ raw score trong artifact khác. Bổ sung case equal scores và near-ties, kiểm ordering sau serialization/parser thay vì chỉ so chuỗi sáu chữ số. Sửa mô tả “hoặc” raw score trong ARCHITECTURE §6.2 thành quy tắc thống nhất.

**Nguồn đối chiếu đã mở:** [trec_eval form_res_rels.c](https://raw.githubusercontent.com/usnistgov/trec_eval/main/form_res_rels.c), phần sort và comp_sim_docno; không chạy executable trec_eval trong phiên này.

## F2 — [P1] Guard qrels đặt trong abstract method không bảo vệ ranker triển khai thông thường

**Vị trí:** src/scholargraph/data/interfaces.py:31–51; test_schemas.py:DummyMockRanker.rank.

rank() bắt buộc bị subclass override, nên đoạn kiểm qrels trong abstract method không tự được gọi. Unit test hiện gọi super().rank(...) một cách chủ động, chỉ chứng minh lớp mock hợp tác, chưa chứng minh boundary. Một subclass hợp lệ bỏ lời gọi super sẽ nhận qrels mà không có DataLeakageError; điều này trái acceptance “Ranker không nhận qrels” và mô tả bảo vệ chặt trong ARCHITECTURE.

**Tái hiện đã chạy:**
```python
class PlainRanker(BaseRanker):
    def rank(self, query, candidate_ids=None, **kwargs):
        return kwargs.get("qrels")

PlainRanker().rank(Query(id="q1", text="test"), qrels={"q1": {"a": 1}})
# Trả về {"q1": {"a": 1}}, không bị từ chối.
```

**Sửa:** đặt boundary kiểm tra tại entry point công khai chung và tách hook triển khai (_rank) cho subclass, hoặc wrapper/composition kiểm đầu vào trước dispatch. Giới hạn tham số bằng contract typed/allowlist; không tuyên bố một blacklist hai tên chặn mọi dữ liệu nhãn giấu trong metadata. Test phải dùng subclass chỉ triển khai hook, kiểm forbidden inputs không thể tới logic xếp hạng. Constructor override cũng cần được xem xét theo cùng thiết kế.

## F3 — [P2] CitationEdge bỏ lọt ID và năm sai

**Vị trí:** src/scholargraph/data/schemas.py:126–134.

min_length=1 không chặn chuỗi chỉ có whitespace; source/target không normalize giống Paper.id. year chỉ khai báo Optional[int], không dùng validation range của Paper. Do đó graph có thể chứa node “ ” hoặc “ a ” không khớp Paper.id “a”, và năm ngoài chính sách đang công bố có thể lọt vào cutoff.

**Tái hiện đã chạy:**
```python
CitationEdge(source_id=" ", target_id="b", year=9999)  # được chấp nhận
CitationEdge(source_id=" a ", target_id="b").source_id  # vẫn là " a "
```

**Sửa:** validator ID/year dùng chung hoặc consistent với Paper, giữ None theo null policy; test invalid source/target/year và ID mapping sau chuẩn hóa. Cùng audit còn thấy RankingResult(query_id=" ") và parse_namespace_id(":") được chấp nhận; cần thống nhất validation ID tại các entry points này, không chỉ trong Paper/Query.

## F4 — [P2] RankingResult constructor/deserialize không kiểm canonical order

**Vị trí:** src/scholargraph/data/schemas.py:213–227.

Validator mang tên validate_unique_docs_and_canonical_order nhưng chỉ kiểm duplicate và rank liên tiếp. Constructor/model_validate khi nhận kết quả module hoặc tải JSON vẫn nhận điểm tăng dần hoặc ties doc ID sai thứ tự. Chỉ create_sorted mới sắp, và contract không bắt mọi caller đi qua factory. Khi consumer lấy candidates[0] hoặc cắt top-k, kết quả khác thứ tự theo score mà evaluator có thể tái tạo.

**Tái hiện đã chạy:** RankingResult nhận z(score0.1, rank1), a(score0.9, rank2) và xuất nguyên thứ tự sai; không ValidationError.

**Sửa:** validate thứ tự (-score, normalized_doc_id) trong model validator hoặc normalize tại một constructor duy nhất có contract rõ; thêm test deserialize/khởi tạo trực tiếp với ascending score và tied-ID order sai. Không chỉ test factory.

## F5 — [P2] Run fixture chứa metrics tổng hợp nhưng không có cờ synthetic máy đọc được

**Vị trí:** src/scholargraph/data/schemas.py:266–276 và tests/fixtures/synthetic_manifest.json:1–8.

RunManifest không có trường synthetic trong khi extra="forbid". Manifest fixture đang khai dataset=scifact, status=COMPLETED và metrics minh họa, nhưng thiếu synthetic=true. Việc đặt suffix “synth” trong run_id hoặc nằm thư mục fixtures không thay thế cờ bắt buộc theo AGENTS §7. Sau serialize/copy sang runner/report, dữ liệu này không có trường đáng tin để phân biệt với completed research run; báo cáo cũ cũng khẳng định không đúng rằng mọi fixture có synthetic=True.

**Tái hiện đã chạy:** manifest fixture nạp thành công, status COMPLETED, synthetic=MISSING. Thêm synthetic=True làm ValidationError extra_forbidden.

**Sửa:** đưa provenance synthetic vào run contract, gắn rõ cho fixture và kiểm roundtrip; consumer research reports về sau phải loại synthetic runs. Không gọi các giá trị minh họa 0.685/0.892/0.65 là số đo retrieval thật.

## Kiểm tra đã thực hiện và giới hạn

| Kiểm tra | Kết quả thực tế |
|---|---|
| Git snapshot và packet hashes | commit fdad031; 9/9 hashes khớp; reviewed artifacts không sửa |
| Python ad hoc reproductions | Chạy thành công bằng bundled Python3.12.14/Pydantic2.13.5; xác nhận F1–F5 như trên |
| pytest tests -q -p no:cacheprovider | Không chạy được trong bundled runtime: No module named pytest |
| Python3.11 đã đăng ký trên máy | Thử gọi runtime WindowsApps; Access denied, không dùng để tuyên bố suite PASS |
| scripts/check_project.ps1 | PASS exit0, 50 tasks/routes, 194 local links, 7 lanes/8 sessions; đây là continuity checker, không chứng minh runtime contracts đúng |
| trec_eval source comparator | Đã đọc primary source; chỉ mô phỏng thứ tự comparator trong Python, chưa chạy compiled evaluator |

Kết quả “28/28” và “34/34” nằm trong log Gemini là bằng chứng do phiên trước ghi, **chưa tái xác minh ở runtime review này**. Các test có sẵn đã đọc cho thấy chưa bao phủ subclass không gọi super, near-tie export, CitationEdge invalid year/whitespace, direct noncanonical RankingResult hoặc synthetic run flag.

Không đòi SG-007 runner, SG-008 evaluator, dataset ingestion hoặc graph experiments phải được triển khai ngay để review SG-006. Findings trên nằm trong code/fixtures hiện có của task. Không sửa code hay tự chạy downstream.

## Bước bàn giao

### Phân công kiểm chứng bổ sung theo yêu cầu người dùng

- Người dùng yêu cầu dùng subagent phù hợp để tối ưu token trong khi review. Đã giao `/root/sg006_schema_checks` bằng công cụ spawn_agent: gpt-5.6-terra, medium, fork_turns=none.
- Phạm vi chỉ đọc và tái hiện F3/F4/F5, không sửa code/board/report; root tiếp tục đối chiếu F1/F2 và tổng hợp. Không mở thêm task backlog hay app task. Đây là kiểm chứng bổ sung, không thay thế trách nhiệm kết luận của reviewer chính.
- Kiểm tra bổ sung ở root: cả equal scores và near-ties đều xuất scores không giảm nghiêm ngặt; subclass có gọi super vẫn nhận heldout_edges vì blacklist chỉ kiểm qrels/labels. Chưa thêm finding mới vì thuộc phạm vi F1/F2.
- Subagent đã hoàn tất và xác nhận độc lập cả F3/F4/F5 bằng các reproducer tương ứng. Kết luận không đổi: CHANGES_REQUIRED (2 P1, 3 P2). Không dùng suy đoán về tác động để nhận đã có leakage/metric lỗi trên dataset thật; đây là lỗi contract đã tái hiện trước downstream.
- Kết thúc review: chỉ report mới này được ghi; reviewed implementation, tests và shared board giữ nguyên. Không còn subagent đang làm hoặc benchmark process do phiên review khởi chạy. Bước tiếp là sửa findings và re-review snapshot mới.

1. Coordinator mở lại SG-006 (REVIEW/IN_PROGRESS tùy người nhận sửa), gắn report này làm evidence thay vì coi PASS cũ là kết luận cuối.
2. Worker sửa F1–F5 cùng regression tests trên runtime project đã xác minh; cập nhật ARCHITECTURE/packet đúng hành vi.
3. Gửi snapshot/hash mới để reviewer kiểm lại vùng ảnh hưởng. SG-006 human_approval_required=false; cần fresh-context technical review, không tự thêm human gate.
4. Review cũ tự mô tả “coordinator/reviewer kiêm nhiệm trong phiên đơn lẻ”; đó là self-check, không phải evidence của fresh-context review bắt buộc. Phiên này độc lập với context triển khai Gemini nhưng verdict là CHANGES_REQUIRED, chưa đủ closeout.
