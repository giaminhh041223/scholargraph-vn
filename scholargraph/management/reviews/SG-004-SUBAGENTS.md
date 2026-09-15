# Phân công subagent — SG-004

- Coordinator: SESSION-20260915-008, lane C/R; chỉ coordinator ghi shared board/state/HANDOFF/registry và protocol/config.
- Người dùng cho phép subagents trong yêu cầu SG-004.
- Support `/root/sg004_source_audit`: gpt-5.6-sol, high; fork_turns=none; nguồn xác minh là tham số công cụ spawn_agent đã thành công. Chỉ được ghi `management/reviews/SG-004-SOURCE-AUDIT.md`; không sửa protocol hoặc board. Nhiệm vụ: kiểm chứng dossier, BEIR split và convention evaluator từ primary sources.
- Support source audit đã hoàn tất, không còn sửa report.
- Reviewer `/root/sg004_final_review`: gpt-6-astra, high; fork_turns=none; công cụ spawn_agent thành công. Chỉ được ghi `management/reviews/SG-004-REVIEW-20260915.md`; snapshot protocol/config ở SG-004-REVIEW-PACKET.md đã ngừng sửa. Đây là fresh-context AI artifact review, không thay human approval.
