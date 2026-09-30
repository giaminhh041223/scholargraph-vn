# SESSION-20260930-076-CODEX — thiết kế task ba worker public search

- Ngày 2026-09-30, UTC+07:00; nhánh `codex/public-paper-search`, base `d7bedc6`.
- Người dùng giao: thiết kế task đầy đủ, chia cho gpt 6.1 sol / gemini 3.8 flash high / muse spark 1.3, có song song/review/sửa.
- Vai trò: lập kế hoạch + điều phối riêng extension; không chiếm coordinator main SG-030/033.
- Actual model/effort/thread ID chưa xác minh; không lấy tên worker đề xuất làm runtime evidence.

## Đã đọc/xác minh

- AGENTS root/con, state/HANDOFF/tasks/DECISIONS/RESEARCH_PROTOCOL, routing/registry/strategy và templates.
- Plan extension, Git branch/status và scope API/ingest/UI đã kiểm trong phiên trước.
- Skill Ponytail/entry: dùng stdlib/native/dependencies có sẵn, tránh giao cùng module cho nhiều writer.
- Gemini/Muse không có công cụ gọi trực tiếp trong phiên; chuẩn bị prompt, không thay bằng model khác hoặc nhận đã chạy.
- Có gọi một subagent `gpt-6.1-sol` để read-only review **tài liệu phân công**; đây không phải dispatch implementation của ba worker. Report [PLANNING-20260930-SOL.md](../public_search/reviews/PLANNING-20260930-SOL.md).

## Đầu ra

- [Task cards](../../docs/PUBLIC_PAPER_SEARCH_TASKS.md): 14 task MVP + 2 DEFERRED B, dependency graph, W0–W6, ownership/checkouts/review→fix→re-review.
- [Board extension](../public_search/tasks.json): đề xuất owner/reviewer, worker actual/session null, active assignments rỗng, 14 TODO + 2 DEFERRED.
- [Handoff extension](../public_search/HANDOFF.md) và ba prompt SOL/GEMINI/MUSE.
- Plan gốc được liên kết sang phân công mới, estimate MVP được cộng đúng 39–62 giờ công dự trù gồm review/sửa.
- Chưa tạo worktree/session/ba worker implementation/code module. Chỉ reviewer tài liệu được gọi; phần triển khai pending.

## Kiểm chứng

- `scripts/check_project.ps1`: exit0, PASS 53 task core và 421 local Markdown links tại lượt kiểm đầu; cảnh báo SG-034 chờ SG-033 giữ nguyên.
- Kiểm board EXT read-only bằng PowerShell: PASS 16 unique cards, DAG không vòng, owner khác reviewer, prompt tồn tại, runtime/session/evidence chưa bị bịa, tổng 14 card MVP 39–62 giờ; active_assignments rỗng.
- `git diff --check`: exit0 ở lượt kiểm đầu; chỉ tài liệu/board kế hoạch thay đổi.
- Reviewer Sol phát hiện ba P2 (refresh, empty truth table, SQLite init). Đã sửa plan/cards/prompts; reviewer re-review trả PASS cho thiết kế, không implementation.
- Kiểm cuối `scripts/check_project.ps1`: exit0, 422 local Markdown links và các gate core PASS; kiểm cuối board/cards/reviewer/estimate PASS, W0 sẵn sàng 01A SOL / 01B MUSE / 01C GEMINI. DAG đã được kiểm tự động và reviewer ở lượt trước; không có thay đổi dependencies sau kiểm.
- Không pytest/module benchmark vì phiên chỉ thiết kế task. Staged whitespace/path diff được kiểm trước commit.

## Bàn giao

- Khởi động có thể làm: coordinator chuẩn bị checkout/session thật, giao đồng thời EXT-01A/01B/01C theo ba prompt, review/pin contract trước W1.
- Chưa kiểm chứng source search/Terms/quota trong phiên này; EXT-01B giải quyết, site B còn thiếu.
- Không push/merge parent, không tự nhận worker đang chạy.
