# SESSION-20260915-018-RUNNER-SECRET-ESCALATION

- Bắt đầu: 2026-09-15T22:20:20+07:00.
- Worker: `/root/sg007_secret_escalation`; lane M.
- Task: SG-007 escalated P1 secret-sanitization correction.
- Scope: `src/scholargraph/evaluation/runner.py`, `tests/unit/test_run_integrity.py`, và log này only.
- Must replace only the incomplete F2 sanitizer with a robust approach covering all previously reproduced forms and persistence/export. Preserve passing F1/F3/F4 behavior; do not modify control files.

## Triển khai F2

- Thay ba regex thay thế nối tiếp bằng bộ nhận diện exact credential key và parser ranh giới value. Nhận `:` / `=` / khoảng trắng đúng ngữ cảnh, không phân biệt hoa/thường; đọc trọn quoted value, escapes, dấu câu trong unquoted credential và quoted value nhiều dòng.
- Authorization hỗ trợ Basic/Bearer cả dạng quoted và tách scheme/value; Digest và scheme khác được che toàn header tới ranh giới record/option. CLI hỗ trợ giá trị inline, argv riêng, dấu `=` riêng, khoảng trắng quanh `=`, scheme và Digest attributes chia nhiều argv elements. Không chỉ che tên scheme rồi giữ credential phía sau.
- Standalone Bearer được nhận tại đầu field/dòng hoặc với token có hình dạng opaque. Giữ câu văn metadata hiện có (`authorization model for bearer plants...`) và exact-key negatives `token_count`, `tokenizer`, `passwordless`.
- Sanitize recursively tại điểm ghi manifest: ngoài command/log/error còn che credential keys và credential syntax trong metadata lồng nhau của config, environment, model và code provenance. Hashes vẫn là identity của đầu vào gốc; config đã loại secret không phải bản có thể dùng để suy ra secret từ hash. Caller nên cung cấp credential qua môi trường, tách khỏi config học thuật.
- F1 freeze validation, F3 verify-before-seal và F4 code identity logic giữ nguyên; chỉ thêm sanitation vào serialization của manifest.

## Regression và diễn biến kiểm tra

- Bổ sung 3 test functions, tổng **20 functions**. Ma trận sinh từ key × delimiter × case × quote × scheme gồm **612 text cases** và **88 argv cases**; không chỉ hard-code các chuỗi của reviewer.
- Phủ toàn bộ 13 reproducer trong final review, thêm Authorization space/quotes, Digest nhiều thuộc tính, scheme khác, header chia argv, inline scheme + argv credential, credential có comma/punctuation, quoted multiline và unterminated quote. Kiểm sanitizer idempotent; giữ `--seed 42` sau argv credential.
- Persistence: đưa text cases vào command riêng từng item, multiline log và error; 88 argv cases có run/export riêng; quét không phân biệt hoa/thường tất cả files ở cả run gốc lẫn export, gồm manifest/log/error/seal. Thêm completed-run test cho nested metadata, kiểm config hash gốc, giữ token_count/tokenizer/passwordless, commit/dirty identity và integrity seal.
- Trong phát triển đã phát hiện và sửa Authorization dùng khoảng trắng trước quoted scheme, cùng Bearer chữ thường ở đầu dòng sau newline. Lượt full fallback đầu dừng tại persistence test; lượt cuối tất cả tests PASS. Khi thêm multiline quoted-value case, đặt unterminated-quote fixture cuối batch để không ghép nó thành một quoted value khác với case đứng sau; từng case vẫn được kiểm độc lập qua direct sanitizer và command item.

## Kiểm tra đã thực sự chạy

Runtime: `C:/Users/ADMIN/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`; cwd `D:/Web_mining_20261/scholargraph`; `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`.

1. `python -m pytest tests/unit/test_run_integrity.py -q`: **exit 1**, `No module named pytest`. Không cài dependency và không tuyên bố pytest chính thức PASS.
2. Python stdin nạp test file qua `runpy.run_path`; shim chỉ `pytest.raises` bằng context manager kiểm exception type + regex message, mỗi function chạy trong `TemporaryDirectory(prefix='sg007-escalation-', dir='artifacts')`: lượt cuối **20 functions PASS, exit 0**. Ma trận **612 text + 88 argv** PASS, bao gồm persistence/export scans. Fixture tự dọn sau khi hoàn tất; dùng escalation được cho phép vì các review trước đã xác minh sandbox treo ở tạo thư mục tạm.
3. Existing freeze-gate, tamper/missing-artifact, terminal immutability, export collision, deterministic hashing và code-provenance regressions đều PASS trong 20 functions này. Không coi đây là kiểm chứng evaluator SG-008.
4. `powershell -ExecutionPolicy Bypass -File ./scripts/check_project.ps1`: **exit 0**, 50 tasks/routes, 198 links, 21 sessions; board tại lúc đọc DONE=9, IN_PROGRESS=1, TODO=36, DEFERRED=4. Worker không sửa shared board.
5. `git diff --check`: **exit 0** cho tracked working-tree changes. Runner/tests vẫn untracked nên lệnh Git này không thay thế test của hai file đó.

Snapshot hoàn tất implementation lúc `2026-09-15T22:35:42.4375270+07:00`:

| File | SHA-256 |
|---|---|
| src/scholargraph/evaluation/runner.py | F7B1676953CAD645D511D5B54922A5068895091B7665BB0E3F1D0697448AD229 |
| tests/unit/test_run_integrity.py | 156BAE62560F04B426C4778732E6750735C77E172E0B256DD6098F87BA3340B7 |

## Giới hạn và bàn giao

- Chuỗi prose có từ `bearer` rồi một từ chữ thường ngắn không có marker là mơ hồ: không thể phân biệt tuyệt đối credential tùy ý và cụm khoa học như `for bearer plants` chỉ từ nội dung. Bare Bearer ở đầu field/dòng và token opaque đã được che; explicit Authorization/CLI/dict credential được che không phụ thuộc hình dạng secret. Không tuyên bố phát hiện mọi secret tùy ý nằm trong văn xuôi, tên file hoặc dữ liệu khoa học. Phần marker/heuristic này cần reviewer đánh giá rõ; nếu muốn bảo đảm với mọi free-form input thì phải đổi API sang structured logging/explicit sensitive values, nằm ngoài correction hiện tại.
- Known credential forms và all previous review reproducers có regression PASS; cần fresh-context review snapshot mới trước coordinator đóng task. Pytest package vẫn thiếu và phải ghi đúng limitation.
- Chỉ sửa runner, integrity tests và log riêng này. Không sửa board/state/HANDOFF/chat registry/task cards; không tự DONE.
