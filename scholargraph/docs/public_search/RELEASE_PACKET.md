# Gói bàn giao Public Paper Search

Ngày 2026-10-01, nhánh `codex/public-paper-search`. **Phần kiểm tra kỹ thuật agent: PASS trong scope đã kiểm. Human demo và merge master: PENDING.** Đây là gói ứng viên tích hợp, chưa xuất bản bên ngoài. [Hướng dẫn](USER_GUIDE.md) · [Demo/checklist](DEMO.md) · [Handoff](../../management/public_search/HANDOFF.md).

## 1. Phạm vi

Tìm metadata OpenAlex/arXiv qua API, validate/raw provenance, RRF/dedup, cache/snapshot, thư viện SQLite và JSON/BibTeX. Public UI ở `/public/ui`, readiness JSON ở `/public`. Thư viện offline chỉ lưu metadata. Không có crawler HTML publisher, tải PDF, dịch Việt–Anh hay chấm relevance mới trong MVP.

EXT01–07 phần agent đã đóng theo [board](../../management/public_search/tasks.json). EXT-08 là hướng dẫn/demo/review packet; human checklist được giữ PENDING. EXT-09/10 giai đoạn B **DEFERRED**, chưa tự thực hiện. SG-030/SG-033 và các human gate core giữ trạng thái riêng.

## 2. Phiên bản và đầu vào

| Thành phần | Phiên bản / bằng chứng |
|---|---|
| Contract/schema | 1.0.0/schema 1, [CONTRACT](CONTRACT.md) và [contracts.py](../../src/scholargraph/public_search/contracts.py) |
| Config | 1.0.0-audited, [config](../../configs/public_search.json), SHA`1e188af340572a8fc51124fd8bd5b31f615d607a85967a3ee88871374853c4ed` |
| Dependencies | [requirements.lock](../../requirements.lock), SHA`b68fcdc47fdbc67460e8384087e0fde8d62fc8fe820a6cf9b220283e0298d57d`; current Python 3.12.14 trên Windows, fresh install NOT_RUN |
| Source policy | [SOURCE_AUDIT](SOURCE_AUDIT.md), [report](../../artifacts/reports/public_search/muse/source_audit.json); hash được pin trong config, không suy quota/policy luôn giữ nguyên |
| Code library/UI repair | `7726c83`; source serializer/envelope/UI lỗi đã sửa và kiểm |
| Code paging/race/identity | `6a5d4e1` |
| Code service/CLI cuối | **`66264a7`**; target regression 630 |
| Network recovery provenance | **`ca0344d`**, không gán các lượt network này cho code 66264a7 |
| W5 evidence checkpoint | `62f4b4f`; docs draft trước sửa `1023cb9` |

Hash đầy đủ từng resource/code/required split và manifest freeze nằm tại [W5-FINAL-104](../../management/public_search/W5-FINAL-104.json). Manifest gồm 155 tài nguyên bắt buộc; raw/store cục bộ không được đưa hết vào Git. Tái lập verifier cần đủ tài nguyên trong manifest; thiếu phải FAIL, không coi checkout Git đơn thuần là gói dữ liệu đầy đủ.

## 3. Kiểm tra và audit

| Kiểm tra | Kết quả thực tế |
|---|---|
| [Regression cuối104](../../artifacts/reports/public_search/sol/regression-w5-104.json) | Coordinator 630 PASS / 0 failed / CLI 0, 321.284s; public contracts/transport/adapters/fusion/store/export/service/CLI/routes/UI/paging và offline API/UI/graph/export |
| Core freeze | 33 files trước/sau unchanged; manifest SHA`34159fb133594633530c08390b259ea6efd7e024a384cb2c25092bf6e4797557` |
| [Verifier104](../../artifacts/reports/public_search/muse/validation-w5-104.json) | PASS/CLI 0, 7 adversarial PASS; thiếu tài nguyên/splits, dữ liệu dị dạng, leakage và subprocess CLI1 được kiểm trong suite |
| Storage/export audit | Gemini phân tích; coordinator chạy 125 pytest PASS trong 74.75s + probe corrupt DB độc lập PASS; [execution103](../../artifacts/reports/public_search/gemini/ext07m-execution-103.json) |
| Backend re-review | MUSE native 57 test trong scope bản sửa PASS. 4 suites: 63 PASS +1 FAIL do raw path 274 ký tự trong temp sâu trên Windows; chẩn đoán ghi rõ. Coordinator 630 suite ở temp ngắn có case đó PASS. Không đổi lượt native FAIL thành PASS |
| UI re-review | SOL: 12 cases Node độc lập +1 pytest hồi quy PASS; JS của 6a5d4e1 giữ nguyên byte đến 66264a7 |

125/57/7 và 630 có scope chồng nhau, **không cộng thành tổng test duy nhất**. Native MUSE R1 có 51 executions /50 cases riêng biệt, đã được R2 làm rõ. Setup verifier104 từng FAIL do helper path sai/serialization của command; các kết quả FAIL và sửa format report được giữ trong checkpoint, không là lỗi sản phẩm mới.

Audit/cross-check:

- Backend: [MUSE R2](../../management/public_search/reviews/MUSE/EXT-07S-W5-R2-104.md), [Gemini consistency](../../management/public_search/reviews/GEMINI/EXT-07S-CONSISTENCY-104.md).
- UI/arXiv: [SOL R2](../../management/public_search/reviews/SOL/EXT-07G-W5-R2-103.md), [MUSE consistency](../../management/public_search/reviews/MUSE/EXT-07G-CONSISTENCY-104.md).
- Storage/evidence: [Gemini R3](../../management/public_search/reviews/GEMINI/EXT-07M-W5-R3-103.md), [SOL consistency](../../management/public_search/reviews/SOL/EXT-07M-CONSISTENCY-103.md).
- Coordinator: [gate104](../../management/public_search/reviews/COORDINATOR/EXT-07-W5-GATE-104.md). Verdict chỉ bao phủ inputs/scenarios đã kiểm, không bảo đảm mọi deployment.

Yêu cầu SOL/high, Gemini Flash High/high, Muse free/xhigh theo yêu cầu. Gemini terminal bị từ chối ở storage audit, coordinator thực thi probes và ghi attribution; native actual model/effort không có telemetry thì unknown. Không lấy nhãn prompt làm proof runtime.

## 4. Pilot thật và độ trễ

[Recovery102](../../artifacts/reports/public_search/muse/pilot-recovery-102.json):5 query đã xác nhận, top_k=3/cap=3, OpenAlex + arXiv. **5 refresh +5 cache thành công**, mỗi nguồn 3 records. 16 lượt cũ =10 success chỉ OpenAlex +6 partial_failure hai nguồn; lịch sử 26 lượt duy nhất =20 success +6 partial_failure. arXiv: 4 timeout +2 quota. Readiness101 là 1 lượt riêng, không cộng vào 26. Lịch sử FAIL được giữ; query Ontology trả 504 trong server log nằm ngoài cohort chuẩn tắc.

| CLI walltime, mỗi chế độ n=5 | Median | P95 nearest-rank | So đề xuất |
|---|---:|---:|---|
| Refresh | 1.9916151s | 2.2064683s | Đạt đề xuất 15s trong pilot |
| Cache | 0.5140842s | 0.5674156s | **Chưa đạt 500ms** |

CLI timing gồm startup; chưa đo decomposition nên chưa quy nguyên nhân. Không phải latency browser, SLA sản xuất hoặc mẫu đủ kết luận availability/relevance.

Browser đã quan sát 5 query cached hai nguồn/save/library 6 entries; Q1 và library kiểm lại sau restart bản 66264a7. API JSON/BibTeX HTTP200, bytes/hash được kiểm ở [summary102](../../artifacts/reports/public_search/browser-101/summary-102.json). Node Blob/click/revoke kiểm bằng mock. **Tệp được lưu bằng browser: NOT_VERIFIED** do download event timeout; cần human mở hai tệp thật. Hash102 áp dụng export lịch sử 6 entries, không áp cho thư viện sau thêm bài.

## 5. Giới hạn phải giữ khi tích hợp

- Cache P95 vượt proposal 500ms; giữ số đo, không thay bằng 0 hoặc gọi chưa đo là PASS.
- RateState process-local: một server worker; không coi nhiều CLI process có cơ chế phối hợp rate chung.
- Fusion hỗ trợ alias arXiv nhưng adapter OpenAlex hiện để arxiv_id null: cross-source thiếu DOI có thể chưa gộp; enrichment hoãn, không khẳng định EXT-09/10 đã giải quyết.
- Null/metadata thiếu minh bạch; RRF/citation không là chất lượng khoa học; truy vấn nguyên văn/chưa dịch; không đo relevance/coverage tiếng Việt.
- Partial lỗi phải giữ non-2xx/CLI1/cảnh báo/hits của nguồn tốt. Cache hết TTL không fallback ngầm; đọc history stale rõ.
- Human demo/merge/tải PDF/cài mới chưa PASS; không suy từ test tự động.

## 6. Kiểm lại evidence và rollback

Lệnh verifier đúng, ghi report mới ở thư mục report riêng, không ghi đè nguồn/manifest:

```powershell
Set-Location D:/Web_mining_20261/scholargraph
$env:PYTHONPATH = 'src'
& .venv/Scripts/python.exe scripts/verify_public_search.py --project-root . --manifest management/public_search/W5-FINAL-104.json --output-json artifacts/reports/public_search/local-review.json --output-md artifacts/reports/public_search/local-review.md
```

Đây là lệnh cùng cấu trúc đã chạyPASS trên local full evidence; đầu ra phải mới để giữ lịch sử. Nếu thiếu raw/split hoặc hash thay đổi, ghiFAIL và đối chiếu nguồn, không cập nhật hash để che mất bằng chứng.

Rollback cục bộ: dừng **chỉ server do bạn mở** bằng Ctrl+C ở terminal của nó, ghi checkpoint thay đổi chưa commit, kiểm `git status`. Chỉ chuyển nhánh/commit khi các thay đổi đã được giữ an toàn. Checkpoint W5 gồm code+manifest là`62f4b4f`; `66264a7` là code target trước khi thêmmanifest. Có thể dùng `git switch --detach 62f4b4f` để kiểm W5; trở lại bằng `git switch codex/public-paper-search`. Không tự thực hiện rollback, không xóa data/raw/artifacts hoặc dùng reset --hard. Không dừng server khác.

Bước tiếp: human chạy [DEMO](DEMO.md), xác nhận tìm kiếm/save/tệp download và quyền tích hợp. Coordinator cập nhật gate sau xác nhận; nhánh master chưa merge.
