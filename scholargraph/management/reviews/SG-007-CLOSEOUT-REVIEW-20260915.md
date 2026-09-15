# Closeout review SG-007 — 2026-09-15

- Reviewer: `/root/sg007_closeout_review`; context mới, không tham gia implementation được kiểm tra.
- Phạm vi ghi: chỉ report này. Không sửa runner, tests hoặc shared control files.
- Kết luận snapshot đầu: **CHANGES_REQUIRED** — còn **1 P1 thuộc F2**. F1/F3/F4 và các credential forms đã có regression tiếp tục PASS.

## Snapshot đầu vào

| File | SHA-256 |
|---|---|
| `src/scholargraph/evaluation/runner.py` | `F7B1676953CAD645D511D5B54922A5068895091B7665BB0E3F1D0697448AD229` |
| `tests/unit/test_run_integrity.py` | `156BAE62560F04B426C4778732E6750735C77E172E0B256DD6098F87BA3340B7` |

Hashes đọc trực tiếp khớp bàn giao `SESSION-20260915-018-RUNNER-SECRET-ESCALATION.md`. Đã đọc AGENTS, state/HANDOFF/board, routing/registry/strategy, SG-007 card, decisions, protocol freeze/run evidence, correction log018, final re-review trước, toàn bộ runner và integrity tests. Git status cho thấy công việc coordinator cùng các file ngoài scope đang dở; reviewer không sửa chúng.

## [P1] F2 — explicit credential có xuống dòng sau delimiter vẫn được ghi nguyên văn

Vị trí: `src/scholargraph/evaluation/runner.py:257` và `:189`.

`_redact_text` chỉ bỏ qua space/tab sau `:` hoặc `=`. Khi value bắt đầu ở dòng tiếp theo, `_scalar_end` dừng ngay tại newline, tạo span rỗng; credential được giữ nguyên. Đây là syntax credential rõ ràng, gồm một JSON object hợp lệ, không phải suy đoán secret trong văn xuôi.

Hai reproducer synthetic (ký hiệu `\n` dưới đây là newline thực):

```text
{"api_key":\n "SYNTH_REVIEW_42"}
password:\n SYNTH_REVIEW_42
```

Cả hai được truyền riêng qua `create(command=["run", message])`, `append_log(message)`, `fail(message)` rồi `export(...)`. Quét case-insensitive tất cả file nguồn và export xác nhận:

| Case | Nguồn có credential | Export có credential |
|---|---|---|
| JSON `api_key` với newline sau colon | `manifest.json`, `run.log`, `error.json` | `manifest.json`, `run.log`, `error.json` |
| `password` với newline sau colon | `manifest.json`, `run.log`, `error.json` | `manifest.json`, `run.log`, `error.json` |

Seal không chứa credential trong hai ca này. Không đọc secret thực hoặc môi trường nhạy cảm; không có bằng chứng secret thực đã rò rỉ.

Yêu cầu sửa: xử lý whitespace hợp lệ quanh explicit key/delimiter/value, gồm LF/CRLF và quoted JSON value ở dòng tiếp theo; regression riêng từng case cần kiểm direct sanitizer, command/log/error và export. Bảo toàn negative scientific metadata. Không yêu cầu phát hiện mọi secret tùy ý trong prose, filenames hoặc scientific data; giới hạn đó được log018 công bố hợp lý.

## Các kiểm tra đã PASS trên snapshot này

- **F2 known forms:** 20 integrity test functions PASS qua fallback assertions, gồm ma trận 612 text cases + 88 argv cases, persistence/export scans, Authorization Basic/Bearer/Digest/unknown scheme, quoted/multiline values, nested manifest metadata và negative scientific metadata.
- **F1:** các negative freeze tests có sẵn PASS; thêm 4 kiểm tra sửa riêng `resolved_config`, `data_source`, `split_definition`, `model` sau tạo freeze evidence đều bị `FinalTestGateError` do binding lệch.
- **F3:** tamper ranking và xóa per-query trước complete bị từ chối; test xác nhận run tampered vẫn RUNNING và chưa seal. Đọc code xác nhận verify trước transition/seal.
- **F4:** commit/dirty/source snapshot reference/source digest được giữ qua complete/export. Đây là provenance caller cung cấp; không xác nhận snapshot tham chiếu tồn tại hoặc Git state caller khai là đúng.
- Lifecycle smoke, terminal immutability, collision/resume, failed error, artifact/manifest tamper và deterministic hashing PASS trong cùng 20 functions.

## Cách kiểm chứng và giới hạn

1. Runtime bundled Python, `-B`, `PYTHONPATH=src`; direct sanitizer probes exit 0, tái hiện hai bypass trên.
2. Python stdin nạp tests bằng `runpy.run_path`, shim chỉ `pytest.raises` kiểm exception type và regex message; **20 functions + 4 mutation assertions PASS**, hai persistence probes cho kết quả LEAK như bảng, exit 0. Đây không phải pytest chính thức.
3. Fixture `TemporaryDirectory(prefix="sg007-closeout-review-", dir="artifacts")`; lượt sandbox không ra output và bị dừng. Lượt escalation được cho phép hoàn tất, fixture tự dọn. Reviewer không cài dependencies.
4. Coordinator thông báo môi trường `.venv` mới chạy pytest thật integrity + schemas **56 passed**. Đây là evidence coordinator báo, chưa phải lần reviewer tự chạy; không thay kết quả reproducer riêng.

## Bàn giao

Đã thông báo P1 sớm và xác nhận persistence cho coordinator. Coordinator tiếp nhận sửa whitespace parsing và regression. Reviewer sẵn sàng kiểm snapshot mới; chưa đủ gate DONE ở snapshot đầu này. Không cần mở rộng scope sang SG-008 hoặc nghiên cứu arbitrary-secret detection.

## Re-review correction cùng phiên — kết luận cuối PASS

Coordinator sửa parsing whitespace và thêm regression; reviewer chỉ kiểm tra và ghi report, không sửa implementation. **Verdict cuối: PASS cho snapshot mới bên dưới**. P1 F2 vừa tái hiện đã đóng; không còn material finding mở trong phạm vi review này. Nội dung CHANGES_REQUIRED ở trên được giữ nguyên như lịch sử snapshot trước.

| File | SHA-256 snapshot cuối đã xác minh trực tiếp |
|---|---|
| `src/scholargraph/evaluation/runner.py` | `5F2D7F76D06D6E7D64C68077CE98108A0A07B897E8CB29D3818DFE1C30171ABA` |
| `tests/unit/test_run_integrity.py` | `FA1A65BFAA1F61EE00DF2202454C2A38BD67DAD826ED1DB66E2D93AF755B4209` |

Thay đổi được đọc lại: whitespace quanh explicit key/delimiter/value và giữa Basic/Bearer với credential được tiêu thụ bằng `isspace()`. Regression mới có LF, CRLF và LF/tab/space, mỗi dạng kiểm bốn syntax cùng nested diagnostic metadata, command, log, error, source và export. Các negative scientific metadata vẫn giữ nguyên.

Kiểm tra reviewer thực sự chạy trên snapshot cuối:

1. `./.venv/Scripts/python.exe -B -m pytest tests/unit/test_run_integrity.py -q -p no:cacheprovider`, `PYTHONPATH=src`: **23 passed in 17.77s**, exit 0. Đây là pytest chính thức, không phải shim. Bao gồm tất cả F1/F3/F4, lifecycle, ma trận 612 text/88 argv và 12 whitespace syntax persistence cases.
2. Python stdin với `.venv` chạy lại **hai reproducer nguyên gốc** và thêm JSON uppercase CRLF quanh colon cùng Authorization Basic CRLF: **4/4 PASS** direct và persistence/export. Quét case-insensitive mọi file nguồn/export; không còn synthetic credential.
3. Trên snapshot cuối, thay riêng config/data/split/model sau freeze: **4/4 assertions PASS**, đều bị FinalTestGateError do binding lệch.
4. Cả hai lượt chạy dùng escalation được cho phép; probes độc lập chỉ tạo `TemporaryDirectory(prefix="sg007-closeout-confirm-", dir="artifacts")` và tự dọn. Reviewer không cài dependency hoặc thay shared control files.

Giới hạn vẫn giữ: parser bảo vệ known/explicit credential syntax, không bảo đảm phát hiện mọi secret tùy ý trong free-form scientific prose hoặc filename. Code provenance bảo toàn khai báo caller; review không xác minh các caller source references. Không tuyên bố SG-008 evaluator hoặc final research run đã được kiểm chứng. Coordinator có thể dùng PASS này cho fresh-context gate SG-007 cùng smoke/full-suite/checkpoint evidence của coordinator.
