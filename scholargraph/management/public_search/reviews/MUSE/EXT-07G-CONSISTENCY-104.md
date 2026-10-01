# EXT-07G Third-worker consistency — MUSE cross-check — Verdict PASS

- **Vai trò:** third-worker (MUSE) kiểm evidence/attribution/math của 2 report SOL, không review reviews vô hạn, không sửa production/board/Git.
- **Inputs (parent absolute, read-only):** `management/public_search/reviews/SOL/EXT-07G-W5-102.md` (CHANGES_REQUIRED, 1×P1+2×P2, target `7726c83`, blob JS `e26866cd...`, arxiv `3fa86fc7...`), `management/public_search/reviews/SOL/EXT-07G-W5-R2-103.md` (PASS 3 closed findings trên `6a5d4e139b85fb67641a612ce4a21f595a10abd2`, independent 12 cases + 1 persistent pytest, JS `9b628b68...`).
- **Target consistency:** `7726c83 → 6a5d4e1 → 66264a7`. JS `6a5d4e1` byte-unchanged tại `66264a7` (R2-103 `§UI` chỉ thêm paging sequence/identity guards; `66264a7` chỉ sửa `service.py + search_public.py + tests`, không chạm `ui/static/public_search.js`/`arxiv.py` theo `git log --oneline` đã xác minh ở R2-104). Audit backend R2-104 vẫn đúng `66264a7`.

## 1. Đối chiếu R1 → R2

| Finding R1 | Expected R2 | Evidence R2 | Kết luận |
|---|---|---|---|
| G-102-01 P1 non-2xx paging (JS:1687-1690 throw trước đọc JSON) | Đọc/validate non-2xx body, giữ warning + paging hits partial | 2 cases HTTP 503+504 snapshot 25 hits → Trang 2/3, 10 cards, giữ `partial_failure` | CLOSED, đã thực thi |
| G-102-02 P2 page/history race (seq chung, historical cùng render) | Page token riêng, invalidate display cũ | Trang 3→1 về đúng 1; pending A + render B thì A không đè B | CLOSED |
| G-102-03 P2 identity/null mutation (nhận wrong-id, null → TypeError) | Guard snapshot/ID/overall trước assignment/render | Wrong-id từ chối giữ state; HTTP200 failed/null báo structured không TypeError, giữ 10 cards; save sau dùng original ID success | CLOSED |
| Guards bổ sung | Không swallow own render, không stale banner, JSON hỏng giữ page | Sentinel active-render báo banner; stale sau xong không banner/đổi view; decode lỗi giữ page 1 + save gốc success | Đạt |

- Independent: `node probe_ui_r2.js` **12/12 PASS exit 0** (JS lấy bằng `git show 6a5d4e1:...`, SHA `9b628b68...`, results `node_results_r2.json`, mock DOM/fetch, không live). Persistent: `pytest -q tests/unit/test_public_ui_paging.py` **1 PASS exit 0 0.34s** (5 scenario groups, không cộng thành unique với 12). Coordinator `25 targeted PASS` là execution coordinator, R2-103 ghi attribution đúng, không nhận thành auditor run. Lượt probe đầu exit 1 do detached button (guard `isConnected` đúng) đã gắn DOM và rerun đạt, không sửa production để pass. Đủ đóng 3 findings.

## 2. Giới hạn giữ nguyên (không claim human PASS)

- Export/download: Node Blob exact text, 1 click, 1 revoke; thiếu Blob/createObjectURL/throwing click báo lỗi theo harness. **NOT_RUN xác minh file download browser** (coordinator `waitForEvent(download)` timeout, không local path) — R2-103 ghi đúng, không suy banner thành proof. Human demo PENDING.
- Cache/latency/live lineage/relevance giữ như R1: P95 cache `0.5674156s n5` vượt proposal, refresh `2.2064s`, recovery 10 vs 6 partial, 26 unique, library 5+frozen + browser 6th, không sustained availability.

## 3. EXT-07M consistency (read-only, không đổi verdict/board)

- 7/7 file storage/export/verifier/tests giữa `7726c83` và `6a5d4e1` byte identical (R2-103 đã kiểm). UI delta không mất target storage audit.
- R1 số startup `~0.35-0.40s` / SQLite `<50ms` chưa đo đã được R2 bỏ, giữ R1 làm lịch sử. Probe R1 `SearchResultRecord`/dict vs `PaperRecord`/list là lỗi fixture auditor, R2 nhận đúng. GEMINI `NOT_RUN` tại thời điểm viết là attribution trung thực; summary R2 `eb84bf30...` có `parent_pytest_suites PASS exit 0` + corrupt DB PASS là execution coordinator, không bịa cases/elapsed. Recovery/library/human khớp recount.
- Còn 1 câu wording (`EXT-07M-W5-R2-102.md:130` quy vượt ngưỡng do startup) chưa đủ phép đo tách chi phí — đề nghị sửa thành “bao gồm startup; chưa đo riêng nên chưa quy nguyên nhân; P95 0.567s vẫn vượt proposal”. Sửa bằng read-only append, không cần rerun suites. Không tự đổi EXT-07M verdict.

## 4. Verdict consistency

- **PASS** consistency: evidence/attribution/math của R1→R2 đúng, 3 findings đóng bằng thực thi độc lập, JS hash/lineage rõ, giới hạn browser/download/human được giữ. Không mở review vô hạn.
