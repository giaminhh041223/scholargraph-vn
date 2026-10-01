# UI pagination delta — coordinator takeover

- Input immutable `7726c83`; fresh SOL report EXT-07G-W5-102 CHANGES_REQUIRED: G-102-01 P1 partial paging, G-102-02 P2 page/historical race, G-102-03 P2 foreign/null snapshot mutation.
- Coordinator sửa UI trong khi Gemini chỉ đọc storage/evidence, native terminal bị denied. Không sửa backend/contract/pilot artifacts.
- Parse/validate envelope trước HTTP check để partial_failure có snapshot HTTP503/504 vẫn phân trang. Không chấp nhận failed/null hoặc snapshot_id khác trước thay đổi displayed state.
- Sequence riêng cho page action, invalidated khi render display mới, guards cả success/error để response cũ không ghi đè page mới/historical snapshot/query mới. Paging cập nhật TTL badge, giữ warning partial đã hiển thị.
- Persistent regression dùng fixture synthetic sinh trong pytest temp, validated bằng parent models/fusion; Node thực thi 5 cases partial/race/historical/identity/null, save sau failed page vẫn dùng snapshot gốc.
- Actual `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q tests/unit/test_public_ui.py tests/unit/test_public_ui_paging.py tests/integration/test_public_routes.py -p no:cacheprovider`:25 PASS, exit0,4.54s,2deprecationwarnings.
- SOL re-review đúng commit mới còn PENDING; audit backend/storage trên7726c83 không chạm deltaUI. Human demo vẫnPENDING.
