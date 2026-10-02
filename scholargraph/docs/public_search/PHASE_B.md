# Giai đoạn B — Crossref và quét HTML JOSS

Trạng thái: EXT-09 DONE (98 tests PASS, Muse review độc lập PASS); EXT-10 đang sửa R3, chưa nghiệm thu live. [Demo CLI](PHASE_B_DEMO.md).

## Phạm vi

- **Crossref:** tra metadata theo DOI chính xác. Metadata gốc giữ nguyên; kết quả bổ sung lưu riêng, có nguồn, hash raw và danh sách mâu thuẫn. Không tìm kiếm mơ hồ theo tiêu đề.
- **JOSS:** thu metadata từ trang HTML bài đã xuất bản của một tạp chí, rồi lọc cục bộ theo tiêu đề/tác giả. Không tải PDF hoặc nội dung ngoài host.
- Hai CLI có schema riêng; contract tìm kiếm OpenAlex/arXiv v1 giữ nguyên. Kết quả crawler chưa được nhập tự động vào library của giao diện.

## Nguồn và giới hạn

- [Crossref access and authentication](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/): pool public không cần tài khoản; giới hạn được công bố là 5 request và concurrency 1. Cấu hình dự án dùng tối đa một request/giây trong một process, ghi nhận rate headers thực tế; lỗi quota/HTTP/schema trả FAIL. Không tự thêm email hoặc token.
- [JOSS published papers](https://joss.theoj.org/papers/published.html), [licensing](https://joss.theoj.org/about#content_license), [robots](https://joss.theoj.org/robots.txt): policy được kiểm và lưu raw trong `data/public_search/phase_b/policy-107/`. Robots phải được đọc lại khi chạy. Nội dung công khai ghi CC BY 4.0, trừ nội dung có quy định riêng; khi dùng metadata phải giữ nguồn bài/JOSS.
- Pilot JOSS giới hạn 5 trang HTML và 3 bài, độ sâu 1, 1 MiB mỗi response, cách nhau ít nhất 3 giây, một process tuần tự. Robots, DNS private, redirect, đổi selector hoặc thiếu citation bắt buộc làm run FAIL rõ ràng.
- Không chạy đồng thời nhiều crawler/CLI để nhân giới hạn truy cập. Pilot nhỏ không chứng minh độ phủ hoặc tính sẵn sàng dài hạn.

## Nghiệm thu

Unit tests dùng dữ liệu tổng hợp trong thư mục tạm; live pilot có raw/manifest riêng. Cần kiểm thiếu file/config/raw, payload dị dạng, rò rỉ labels/splits, CLI exit 1, quota/robots/redirect/private IP/body cap, counter/dedup/resume integrity. Reviewer đọc snapshot có hash sau khi tác giả dừng sửa.

Lệnh sử dụng và kết quả thực tế sẽ được ghi sau khi implementation và pilot hoàn tất. SG-030/SG-033 vẫn cần review và nhãn thật từ hai thành viên; giai đoạn B không xác nhận thay các gate này.
