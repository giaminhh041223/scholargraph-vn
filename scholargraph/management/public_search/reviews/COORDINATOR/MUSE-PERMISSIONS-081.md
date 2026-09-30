# Sửa kênh ghi OpenCode — 081

- Hai run `f9390d0d-82c3-4c1a-8803-223dbd4ef86d` và `14db2baa-36ec-4845-bb1b-483ddcc17797` kết thúc process0/STOP, controller cũ ghi PASS. Response và tool events chứng minh thao tác edit/write bị từ chối, không có artifact mới. Kết luận thực tế: required action FAIL; giữ summary cũ như lịch sử, không coi task hoàn tất.
- Nguyên nhân: allowlist cũ chỉ có đường dẫn tuyệt đối, trong khi [OpenCode v1.18.0 edit tool](https://github.com/anomalyco/opencode/blob/v1.18.0/packages/opencode/src/tool/edit.ts#L93-L101) hỏi quyền theo đường dẫn tương đối từ worktree Git. Source được đối chiếu với tool events thực tế, không suy quyền ghi từ exit0.
- Controller bổ sung các đường dẫn tương đối của chính file/thư mục đã được giao. Path được resolve và kiểm containment trước khi tạo rule; unknown paths giữ DENY. Không cấp toàn bộ checkout.
- Controller từ chối permission-denial tool events kể cả response có text và final stop. Read miss có thể được worker sửa bằng đường dẫn đúng, không suy đó là thành công hay bỏ qua required output.
- Kiểm chứng thực chạy: 31 tests PASS/exit0; có phạm vi đúng/sai, traversal/missing ownership và subprocess CLI dùng temp config/credential giả lập, process model giả lập exit0 nhưng denied write -> runner FAIL/exit1. Sentinel credential không xuất hiện stdout/stderr. Không gọi provider trong tests.
- Muse retry run `fe105b60-415b-49c1-b7bd-827f45f66a54`, session `ses_f0ea2fb52ffeXlJNnX5Xk3iiHT`, metadata assistant read-only xác nhận provider opencode/model muse-spark-1.3-contributor-free/variant xhigh. File store/export đã thay đổi; acceptance vẫn chờ suite và Gemini re-review.
- Đây là kiểm chứng coordinator, không nhận là review độc lập controller. Thay đổi nằm ngoài W0 frozen contract/transport/config.
