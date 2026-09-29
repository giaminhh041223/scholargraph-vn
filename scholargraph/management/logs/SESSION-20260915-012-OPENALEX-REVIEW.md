# SESSION-20260915-012-OPENALEX-REVIEW

- Bắt đầu: 2026-09-15T21:52:00+07:00.
- Reviewer: `/root/sg013_review`; fresh context, lane V.
- Task: SG-013 — review independent implementation/pilot snapshot.
- Scope ghi: report `management/reviews/SG-013-REVIEW-20260915.md` and this session log only.
- Do not modify implementation, raw snapshot, manifests, reports, shared board/state/HANDOFF/chat registry, or task card.

## Kết quả review — 2026-09-15

- Đã review artifact hash xác định và ghi `management/reviews/SG-013-REVIEW-20260915.md`.
- Verdict: **CHANGES_REQUIRED**, 1 P1 (error response có thể echo secret vào exception), 2 P2 (Retry-After bị cap xuống 60s; venue coverage đếm sai location presence).
- Xác minh độc lập snapshot: 2.000 unique works, 20 pages, tất cả hashes khớp; 190 internal edges, 1.779 isolated nodes; report cohort khớp 21 eligible sources tổng cộng, tối đa 2/năm. Venue có tên chỉ 1.627/2.000 theo định nghĩa source display_name hoặc raw_source_name; report hiện đếm 2.000.
- Probes source trong bộ nhớ: secret echo True; Retry-After 120 → sleep 60; HTTP-date parse → 0; corrupted works/page hash bị reject; repeated-page records dedup giữ 2.000.
- Bundled runtime thiếu httpx/pytest. Không chạy được pytest; kiểm thử trên dùng dependency stub/fake response và stdlib assertions, không phải integration test và không xác nhận lại pytest worker.
- Hai lỗi ở công cụ đọc dữ liệu đã được xử lý: PowerShell object JSON không nhận keys khác casing → dùng AsHashtable; Python splitlines tách Unicode separator trong text → dùng newline JSONL chính xác. Kết quả cuối dựa trên đủ 2.000 records.
- Không sửa implementation/raw/manifests/measured report/shared state; chỉ ghi report và log được giao. Bàn giao coordinator mở vòng sửa F1–F3, giữ raw snapshot và report lịch sử; không tự DONE.
- Closeout: `powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1` exit 0; 50 tasks, 198 links, 50 model routes, 15 registered sessions; board tại thời điểm check: DONE=8, IN_PROGRESS=1, REVIEW=1, TODO=36, DEFERRED=4.
