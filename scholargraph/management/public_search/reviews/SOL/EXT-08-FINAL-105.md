# EXT-08 — Final review 105

**Verdict: PASS trong scope tài liệu.** Không có finding cần sửa. Target `e3a2730f31f9ef6b08807f9cc9f447bfd3088c77`; reviewer SOL `/root/audit_ext07g_102`, requested `gpt-6.1-sol/high`. Kiểm `2026-10-01T15:05:18+07:00`.

Đọc USER_GUIDE/DEMO/RELEASE_PACKET, code và artifacts. Chỉ read-only checks; **không chạy lại tests, CLI demo/verifier, server hoặc network**.

- **Contract:** đúng `partial_failure`, HTTP non-2xx/CLI1, giữ hits hợp lệ; search không tự fallback cache stale. Search/results là SearchEnvelope; library wrapper có entries/errors; JSON export là list LibraryEntry chứa hit, BibTeX `@misc`. Đối chiếu code thật.
- **Store/demo:** đúng `library.sqlite3`, `store.json`, raw bytes trong files. Default `data/public_search/sol` khác pilotstore; snapshot IDs cần cùng store. Preview8011/default8000 rõ; helper tạm có snippet tái tạo. Rollback `62f4b4f` gồm manifest, scoped stop server của người dùng, giữ thay đổi/evidence, không reset/xóa data.
- **Lệnh/export:** verifier đúng `--manifest/--output-json/--output-md` và output guard. Artifact105: **6 executions =4 exit0 +2 expected exit1**. Helper giữ binary stdout, chặn overwrite/CLI lỗi; nội dung khớp documented snippet. JSON temp **4 bytes**, BibTeX **0 bytes** và hash khớp empty initialized store hợp lệ. Helper hash là source UTF-8/LF/bỏ newline cuối; temp hiện CRLF, không claim source byte-identical. Không suy empty-store check thành browser proof.
- **Evidence:** regression **630 PASS**, freeze **33** unchanged; **125/57/7** overlap, không cộng unique. Native MUSE longpath FAIL giữ rõ. Code target `66264a7`; 7 code files và JS giống byte tới target docs; manifest155 resources. Recovery network code `ca0344d`: **10=5 refresh+5 cache** success; history **26=20 success+6 partial** (4 timeout+2 quota); readiness riêng. Cache P95 **0.5674156s**, n=5, vượt proposal500ms; không quy startup nguyên nhân.
- **Giới hạn/checklist:** fusion hỗ trợ alias nhưng OpenAlex arxiv_id null; enrichment hoãn. Browser cache/save/list, CLI recovery, API export và Node mock được tách đúng. Download file **NOT_VERIFIED**; human demo/merge **PENDING**. **39/39** liên kết cục bộ tồn tại, không file URI sai.

PASS không thay human approval/release gate. Coordinator quyết định board và human demo; giữ history R1.
