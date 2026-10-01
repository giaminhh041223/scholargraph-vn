# Phiên 101 — Entry UI và mismatch library envelope

- EXT-06 fresh SOL R3 PASS_EVIDENCE trên `5f16994`; coordinator gate100. Task evidence DONE, operational two-source FAIL và release/human demo PENDING giữ nguyên.
- SOL helper phát hiện/sửa additive `/public/ui`, link từ `/` sang HTML; `/public` readiness JSON giữ contract. 25 targeted tests PASS, exit0. Commit `64c7a1b`.
- Gemini/MUSE fresh smoke qua native runners đều PASS: Gemini session `7c46b55e-f42e-412c-9e28-30fb94f6a42c`; MUSE session `ses_f09f0e16fffeRdCB6d7XhwUHaW`. Effort explicit Gemini high/MUSE xhigh.
- Dùng computer-use browser tool mở local app `127.0.0.1:8011/public/ui` với service thật trỏ pilot store. Trang HTML và assets hiển thị, approved query knowledge graph chọn OpenAlex/top_k3/cap3 đọc cached snapshot `ps-90f9c840e6b1445bb0d90be9f44e7e91`, 3 hits/provenance/counters đúng; không gọi live request mới.
- Browser save action POST library backend200 nhưng UI báo `LibraryEntry chứa trường không được phép: contract_version`. Browser list tab báo `Phản hồi thư viện phải là danh sách (list[LibraryEntry])`. Root trace: save/list UI đang validate bareentry/array trong khi actual backend wire là envelope có contract_version/entry hoặc entries/errors.
- Không gọi browser flow PASS chỉ vì HTTP200. Đã giao Gemini native author sửa JS/library fixtures, strict validation và negative cases trong checkout riêng. Dispatch GEMINI-UI-LIBRARY-FIX-101, runner exec68532, requested high; actual runtime chưa xác minh.
- Worker chỉ vùng UI/fixtures/packet/log, không backend/schema/config/board. Root kiểm tests/browser sau delivery rồi pin snapshot W5; chưa mở audit mutable UI.
- Local demo server exec59235 bind127.0.0.1:8011, không public exposure; service dùng pilot store, không thay default productionconfig. Human demo xác nhận vẫnPENDING.

## Bản sửa và recovery tiếp nối
- Gemini lượt đầu bị runtime từ chối RunCommand; followup file-only cùng conversation 6c34e098-55b1-4f6f-a5b5-2ab5b2576f8c hoàn tất, evidence 8154ca25-7c87-4411-8d0d-510aeef64e14. Worker commands NOT_RUN, không nhận là tests PASS.
- Coordinator nhập đúng UI/fixture/packet. Worker log viết nhầm management/logs/GEMINI; chỉ nhập vào management/public_search/logs/GEMINI. Sidecar parent tính hash thật, không nhập sidecar NOTMEASURED từ checkout cũ.
- Tự kiểm phát hiện fixture metadata synthetic làm positive/negative validation sai mục tiêu; đã bỏ metadata trước wire validation. Node subprocess đọc UTF-8 rõ ràng. HTTP error JSON/schema malformed được báo rõ, không ignore hay message giả rỗng; thêm 4 malformed error probes.
- Browser phát hiện lựa chọn cả hai nguồn bị gửi repeated sources param trong khi API dùng comma-separated. Coordinator sửa serializer và thêm regression đảm bảo một param openalex,arxiv. Browser sau sửa hiển thị cả hai nguồn success, 6 raw/6 valid/5 unique/3 returned trên snapshot ps-1039af03e9134d119997804398d8bade.
- 24 targeted routes/UI pytest PASS, exit0,10.49s. Gồm Node DOM cases và subprocess fixture lỗi exit1. Browser save idempotent thành công, library list 6 entries (pilot cũ5 +1 arXiv mới); không sửa lịch sử pilot5entries. Browser download event bị timeout, chưa nhận là export browser PASS.
- Recovery riêng102: 5 two-source refresh+5 cached replay,10 success/CLI0; n5/mode refresh median1.9916151s/P952.2064683s,cache median0.5140842s/P950.5674156s. Cache500ms target chưa đạt. Historical26 canonical runs=20success/6partialFAIL, arXiv4timeout2quota giữ nguyên. Readiness101 riêng1run không trộn cohort26.
- Verifier W4-RECOVERY-102 CLI0/PASS,7adversarialPASS; cần audit độc lập trước đổi operational gate. Human demo vẫn PENDING.
