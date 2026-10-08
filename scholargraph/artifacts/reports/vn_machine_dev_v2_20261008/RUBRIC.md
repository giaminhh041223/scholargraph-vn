# Chấm độc lập bằng máy — dev v2

Chỉ đọc 10 file input/vn2_dev_*.jsonl (227 cặp). Query tiếng Việt là nhu cầu tin chuẩn; không dùng bản dịch máy, tìm kiếm web, nhãn người, qrels, test, provenance hệ thống hoặc kết quả agent còn lại.

- 0: không trả lời bất kỳ phần nào; chỉ trùng từ khóa bề mặt.
- 1: trả lời một khía cạnh, hoặc cùng chủ đề nhưng khác khía cạnh/quy mô.
- 2: trả lời trực tiếp toàn bộ nhu cầu tin với thiết kế/kết quả phù hợp.
- unjudged: thiếu nội dung để kết luận; abstract rỗng/title-only bắt buộc unjudged. Có abstract nhưng thực sự không đủ để kết luận cũng ghi rõ lý do.

Đọc mỗi title + abstract và query trước khi quyết định. Không dùng keyword rules để tự động sinh nhãn, không suy kết quả không có trong abstract. Note tiếng Việt ngắn, nêu cụ thể nội dung trả lời hoặc thiếu so với query; lý do bắt buộc cho mọi cặp. Không chấm lại sau khi xem kết quả agent khác.

Mỗi dòng output có đúng các trường: query_id, doc_id, label, annotator, annotator_type, experimental, round, note. annotator=machine_A hoặc machine_B theo phân công; annotator_type=machine; experimental=true; round=independent. label là số nguyên 0/1/2 hoặc chuỗi unjudged. Không giả danh người A/B. Đây là thử nghiệm tham khảo, không hoàn tất SG-033.
