# Phiên 101 — Entry UI và mismatch library envelope

- EXT-06 fresh SOL R3 PASS_EVIDENCE trên `5f16994`; coordinator gate100. Task evidence DONE, operational two-source FAIL và release/human demo PENDING giữ nguyên.
- SOL helper phát hiện/sửa additive `/public/ui`, link từ `/` sang HTML; `/public` readiness JSON giữ contract. 25 targeted tests PASS, exit0. Commit `64c7a1b`.
- Gemini/MUSE fresh smoke qua native runners đều PASS: Gemini session `7c46b55e-f42e-412c-9e28-30fb94f6a42c`; MUSE session `ses_f09f0e16fffeRdCB6d7XhwUHaW`. Effort explicit Gemini high/MUSE xhigh.
- Dùng computer-use browser tool mở local app `127.0.0.1:8011/public/ui` với service thật trỏ pilot store. Trang HTML và assets hiển thị, approved query knowledge graph chọn OpenAlex/top_k3/cap3 đọc cached snapshot `ps-90f9c840e6b1445bb0d90be9f44e7e91`, 3 hits/provenance/counters đúng; không gọi live request mới.
- Browser save action POST library backend200 nhưng UI báo `LibraryEntry chứa trường không được phép: contract_version`. Browser list tab báo `Phản hồi thư viện phải là danh sách (list[LibraryEntry])`. Root trace: save/list UI đang validate bareentry/array trong khi actual backend wire là envelope có contract_version/entry hoặc entries/errors.
- Không gọi browser flow PASS chỉ vì HTTP200. Đã giao Gemini native author sửa JS/library fixtures, strict validation và negative cases trong checkout riêng. Dispatch GEMINI-UI-LIBRARY-FIX-101, runner exec68532, requested high; actual runtime chưa xác minh.
- Worker chỉ vùng UI/fixtures/packet/log, không backend/schema/config/board. Root kiểm tests/browser sau delivery rồi pin snapshot W5; chưa mở audit mutable UI.
- Local demo server exec59235 bind127.0.0.1:8011, không public exposure; service dùng pilot store, không thay default productionconfig. Human demo xác nhận vẫnPENDING.
