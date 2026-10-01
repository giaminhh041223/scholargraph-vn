# EXT-06 — Quyết định về evidence và trạng thái vận hành

Ngày: 2026-10-01. Phạm vi: public search extension; không đổi scope hai nguồn của MVP.

Card EXT-06 yêu cầu mọi ca có PASS/FAIL/NOT_RUN, bảo toàn thất bại và số đo. Vì vậy tách hai trạng thái để tránh biến lỗi upstream thành thành công:

- `evidence_status`: chỉ PASS khi resource/freeze/split, kiểm thử phá hủy, hồi quy, raw pilot, số đếm và phép đo có đủ bằng chứng và review độc lập.
- `two_source_operational`: FAIL khi có lượt hai nguồn thất bại. Run tiếp tục giữ `partial_failure`, CLI 1. Verifier cuối trả status FAIL và exit 1 khi evidence đầy đủ nhưng trạng thái vận hành FAIL.
- EXT-06 có thể DONE **về kiểm chứng/evidence** sau reviewer PASS; điều này chỉ mở audit và tài liệu của snapshot, không cho phép tuyên bố MVP hai nguồn hoàn tất hoặc merge release.
- Final release/merge gate giữ PENDING cho đến khi có pilot hai nguồn hợp lệ và người dùng xác nhận demo. Không tự giảm phạm vi thành một nguồn.

Pilot hiện có: 16 lượt được ghi đủ, gồm 6 hai nguồn `partial_failure`/CLI 1 (4 timeout arXiv, 2 quota arXiv), 5 OpenAlex refresh và 5 cache thành công/CLI 0. OpenAlex được chọn tường minh, không fallback. Có 0 lượt hai nguồn thành công trong cohort này.

Human demo chưa được xác nhận. Việc người dùng xác nhận bộ query không phải xác nhận trải nghiệm lưu/xuất. Các harness lỗi trước cohort chuẩn được giữ riêng; không đưa thời gian chưa đo vào phân vị.

Căn cứ: `docs/PUBLIC_PAPER_SEARCH_TASKS.md` EXT-06, `docs/PUBLIC_PAPER_SEARCH_PLAN.md` mục 8 và điểm dừng hai nguồn; fresh SOL pre-review `/root/review_ext06_gate`. Quyết định này cần được reviewer cuối đối chiếu cùng evidence; chưa tự gán gate PASS.
