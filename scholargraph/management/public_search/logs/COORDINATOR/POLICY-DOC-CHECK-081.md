# Kiểm tra docs chính thức — phiên 081

Coordinator đọc bằng web tool ngày 2026-09-30, không gọi API works/query và không tạo tài khoản.

- [OpenAlex API](https://help.openalex.org/api/) và [Authentication](https://help.openalex.org/api/authentication/): basic anonymous queries được mô tả; Bearer header cũng được hỗ trợ. Không suy ra quota bền vững từ docs hoặc yêu cầu tạo key để hoàn tất W1 coding.
- [arXiv Terms](https://info.arxiv.org/help/api/tou.html): legacy API tối đa một request mỗi ba giây, một connection; giới hạn tính chung các máy dưới quyền kiểm soát. Transport hiện process-local, MVP phải giữ một owner/process khi live; không có bảo đảm distributed rate.

Đây là kiểm tra tài liệu, không phải live adapter/pilot measurement. Audit raw/hashes cũ giữ nguyên. W1 sẽ dùng mock/synthetic fixtures hoặc parse raw đã có, không request live song song.
