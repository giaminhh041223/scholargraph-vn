# Gate W0 R1 — kết luận và tạm dừng

Ngày 2026-09-30. User yêu cầu dừng sau đợt song song hiện tại. Ba lượt đã kết thúc;
không giao fixes/re-review hoặc W1. **W0 chưa đạt freeze, cả ba task giữ REVIEW.**

## Đầu ra đã thu

| Việc đã giao | Đầu ra | Kết quả |
|---|---|---|
| SOL high review audit01B | Report/log commit f6582d9 trong checkout SOL | CHANGES_REQUIRED: 1P1 +3P2 |
| MUSE free xhigh review contract01A | Report/log commit 9f70669 trong checkout MUSE | CHANGES_REQUIRED; coordinator bác hai finding sai dưới đây |
| GEMINI Flash High high (cao nhất hỗ trợ) reconcile UX01C | Sáu outputs commit cc51ef8 do coordinator checkpoint trong checkout GEMINI | Native files đã có; agent terminal ERROR/output limit; validator CLI1 |

Report coordinator [UX validation](EXT-01C-R1-VALIDATION.md) ghi 12 typed JSON objects
PASS, 1 invalid request bị reject đúng; validator vẫn cần sửa. Đây không thay MUSE
review UX độc lập. Implementation không nhập vào parent branch ở lượt này.

## Kết luận về review audit MUSE

Giữ F1–F4 trong report SOL: audit JSON SHA arXiv sai 68hex; auth delta không có căn
cứ; retry metadata/time chưa chứng minh; narrative DOI verified khác actual0/2.
Raw/meta 6/6 vẫn khớp manifest theo reviewer. Sau user resume, tác giả MUSE sửa
artifact/narrative + regressions rồi SOL re-review; không đổi raw cho khớp lỗi.

## Triage độc lập các findings của review contract

- **Bác MUSE P1-1 (OpenAlex Bearer)**: premise dựa vào auth delta sai của chính audit
  MUSE. [OpenAlex Authentication](https://help.openalex.org/api/authentication/)
  xác nhận query parameter và Bearer đều được hỗ trợ tương đương. Transport dùng
  Bearer và cấm secret params không phải bug; không yêu cầu user key/keyed probe
  để giải quyết lựa chọn auth scheme. Khả năng keyed runtime/chịu tải vẫn chưa đo.
- **Bác MUSE P1-2 (factories thiếu ở contracts.py)**: CONTRACT.md mục Store ghi rõ
  hai factories được xuất từ module MUSE `store.py`, không phải `contracts.py`.
  EXT-04A chưa triển khai. Reproducer import factories từ contracts.py kiểm sai
  module, không chứng minh vi phạm thiết kế. Exact signatures đã có trong docs;
  PublicStore protocol cũng ghi EXT-04A implements, no runtime imports. Không thêm
  stub implementation/factory abstraction chỉ để vượt finding này.
- **Giữ MUSE P2-1**: not_requested vẫn chấp nhận filter_coverage=server dù không có
  request/observation. SOL phải làm invariant rõ và regression trước freeze.
- **Giữ MUSE P2-2**: docs cần nêu phối hợp requests arXiv trên các process/machine
  thuộc cùng operator; process-local RateState không là distributed lock. Code
  interval/retries đã được reviewer probe đạt, cần ghi limitation cho pilot.
- P3 config_version naming và DOI normalize helper: ghi convention/trách nhiệm
  adapter; không tự coi thiếu helper là blocker. Adapter chịu normalize trước
  validate theo contract hiện có; reviewer/tác giả xét khi resume, không thêm
  abstraction nếu không cần.

Review contract vẫn **CHANGES_REQUIRED vì hai P2 vi phạm acceptance còn mở**, không
đổi sang PASS sau khi bác hai P1. Report gốc được giữ lịch sử; file gate này là
kết luận điều phối có đối chiếu độc lập, không yêu cầu sửa report trong phiên pause.

## Bước executable sau khi user yêu cầu tiếp tục

1. MUSE sửa source audit F1–F4; SOL sửa invariant not_requested và docs arXiv policy;
   GEMINI sửa validator JSON timestamp/negative subprocess/leakage/packet.
2. Lấy snapshots mới, review chéo đúng phạm vi; reconcile policy config evidence
   sau audit đúng. Không tự bật verified để chạy live.
3. Freeze W0 sau acceptance/re-review; khi đó mới authorize EXT-02/03/04A.

Đây là danh sách chờ, chưa được dispatch. Không process agent điều phối nào cần
tiếp tục ở checkpoint này; desktop apps của user không bị đóng.
