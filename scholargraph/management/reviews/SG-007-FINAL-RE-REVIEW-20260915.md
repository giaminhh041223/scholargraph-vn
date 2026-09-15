# Final re-review SG-007 — Runner và run manifest

- Bắt đầu: 2026-09-15T22:11:26+07:00.
- Reviewer: `/root/sg007_final_rereview`; fresh context.
- Scope chỉ đọc: runner, integrity tests, two correction logs and earlier review reports.
- Must verify all known F2 credential forms are absent from persisted/exported artifacts and F1/F3/F4 continue to pass.
- Kết thúc kiểm tra: 2026-09-15T22:15:29+07:00.
- Verdict: **CHANGES_REQUIRED** — F2 còn **1 P1**; F1/F3/F4 tiếp tục PASS trong phạm vi regression kiểm tra.

## Snapshot và phạm vi

- Runner SHA-256: `96D902B08CF7877D3869DA49BD8F14631C69FBA372FB832F9056758116623EC9`.
- Integrity tests SHA-256: `2B9DB25A1F1A2A666659C410185A02FA1DF34024F8AAF5BC5D835AA6DB051B02`.
- Snapshot khớp SESSION-20260915-015-RUNNER-SECRET-FIX; reviewer mới không tham gia implementation hoặc các lượt review trước.
- Đã đọc AGENTS, state/HANDOFF, SG-007 board/card/routing/registry, chiến lược model, decisions, protocol về final freeze và run evidence, toàn bộ runner/tests, precheck, re-review và cả ba worker logs cùng review log liên quan.
- Git status có các thay đổi đang dở của coordinator/worker và module runner chưa tracked. Reviewer không sửa các file đó.

## F2 — P1 vẫn mở: bỏ sót standalone Bearer và biến thể diagnostic thông thường

Vị trí: `src/scholargraph/evaluation/runner.py:33`, `:37`, `:113`, `:131`.

Hai reproducer gốc và bốn reproducer của re-review đã được che thành công. Tuy nhiên `_redact_text` mới chỉ gọi ba bộ lọc Authorization có `:`/`=`, CLI và key/value; **standalone Bearer không còn được xử lý**. Đây là regression của trường hợp đã được ghi PASS ở re-review trước. Tokenized command cũng chỉ che một phần tử ngay sau `--authorization`, nên có thể che chữ `Bearer` rồi giữ credential ở phần tử tiếp theo.

Kết quả trực tiếp và persistence (mọi credential dưới đây là synthetic):

| Input đưa cùng lúc vào command, append_log, fail | Kết quả sau ghi và export |
|---|---|
| `Authorization: Bearer REVIEW_SECRET` | PASS, không còn credential |
| `--api-key REVIEW_SECRET` | PASS |
| `Authorization=Bearer REVIEW_SECRET` | PASS |
| `Authorization: Basic REVIEW_SECRET` | PASS |
| `--password="prefix REVIEW_SECRET"` | PASS |
| `{'api_key': 'REVIEW_SECRET'}` | PASS |
| `aUtHoRiZaTiOn = bEaReR REVIEW_SECRET` | PASS |
| `{"API_KEY": "REVIEW_SECRET"}` | PASS |
| `Bearer REVIEW_SECRET` | **LEAK** |
| `bEaReR REVIEW_SECRET` | **LEAK** |
| `--PASSWORD = REVIEW_SECRET` | **LEAK**; CLI filter che dấu `=` và giữ giá trị sau đó |
| `--AUTHORIZATION Bearer REVIEW_SECRET` | **LEAK**; CLI text filter thiếu authorization |
| `Authorization: Digest username="REVIEW_SECRET"` | **LEAK**; chỉ che scheme Digest |

Đã tạo **13 synthetic runs** qua API; với từng case gọi `create(command=["python", "run.py", message])`, `append_log(message)`, `fail(message)`, `export(destination)`, rồi quét **tất cả file nguồn và file export bằng casefold**. Với cả năm dòng LEAK, credential xuất hiện trong **manifest.json, run.log và error.json ở cả nguồn lẫn bản export**. Với tám dòng PASS, không file nào chứa credential. Seal không chứa credential trong các case này.

Kiểm tra command tách token riêng:

```text
_redact_command(['run', '--authorization', 'Bearer', 'REVIEW_SECRET'])
=> ['run', '--authorization', '<redacted>', 'REVIEW_SECRET']
```

Yêu cầu sửa vẫn thuộc F2: bảo toàn trường hợp standalone Bearer đã hỗ trợ trước; xử lý cả Authorization option ở dạng text/tokenized command; không dừng ở scheme hoặc dấu `=` trong diagnostic. Với scheme Authorization chưa hỗ trợ, cần che toàn giá trị header hoặc từ chối ghi giá trị đó, thay vì chỉ che từ đầu. Regression cần quét command/log/error và mọi file export bằng so sánh không phân biệt hoa/thường, cùng negative case metadata khoa học đã có. Không có bằng chứng secret thật đã rò rỉ.

## F1/F3/F4 và acceptance đã kiểm lại

| Finding | Bằng chứng và kết quả |
|---|---|
| F1 freeze binding | Các negative tests artifact thiếu/hash sai/track-dataset-split sai/audit FAIL/unresolved/boolean gate vẫn PASS; bổ sung bốn ca thay đổi riêng config, data_source, split_definition, model sau freeze, cả bốn bị FinalTestGateError do binding lệch. |
| F3 verify-before-seal | Test tamper ranking và xóa per-query trước complete đều bị từ chối; tamper giữ RUNNING và không seal. Đã đọc `complete()` gọi `verify_integrity()` trước transition và sealing. |
| F4 code provenance | Test complete/export giữ commit, dirty=True, source_snapshot, source_digest khớp code_hash PASS. Chỉ chứng minh giữ metadata caller cung cấp, không xác nhận snapshot tham chiếu tồn tại hay caller khai đúng Git state. |
| Lifecycle | Smoke manifest/raw rankings/per-query, immutable terminal, export collision, run collision/resume, failed error, artifact/manifest tampering và deterministic hashes đều PASS qua fallback tests. |

## Kiểm tra thực sự đã chạy

Runtime: `C:/Users/ADMIN/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`, cwd ScholarGraph, `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`.

1. `Get-Content`, `rg`, `git status --short`, `Get-FileHash -Algorithm SHA256`: đọc và xác định snapshot trên.
2. `python -m pytest tests/unit/test_run_integrity.py -q`: **exit 1**, `No module named pytest`. Chưa chạy pytest chính thức và không cài dependency.
3. Python stdin direct sanitizer probes: **exit 0**, tái hiện standalone Bearer, mixed case, authorization CLI và Digest như trên; confirmed quoted CLI/JSON key/mixed case header được che.
4. Python stdin nạp test qua runpy, shim tối thiểu chỉ `pytest.raises` có kiểm loại exception và regex message: **17 test functions PASS**, **4 post-freeze mutation assertions PASS**, **13 persistence/export cases** cho kết quả bảng trên; **exit 0**. Đây là fallback assertions, không phải pytest chính thức.
5. Fixture đặt ở `artifacts/sg007-final-review-*` bằng TemporaryDirectory, tự dọn sau lượt kiểm tra; không sửa data/raw hoặc implementation. Lượt fixture dùng escalation được cho phép dựa trên sandbox mkdtemp hang đã được hai review trước xác minh.
6. `powershell -ExecutionPolicy Bypass -File ./scripts/check_project.ps1`: **exit 0**, 50 tasks/routes, 198 local links, 20 sessions; DONE=8, REVIEW=2, TODO=36, DEFERRED=4 tại lúc chạy.

## Bàn giao

F2 chưa đủ điều kiện đóng vì có regression và bypass dễ tái hiện. Coordinator tiếp nhận report để phân công correction tiếp; reviewer không thay trạng thái task hoặc tự DONE. Giữ F1/F3/F4 đã PASS và thêm regression còn thiếu. Sau correction cần review snapshot mới; pytest chính thức vẫn là hạn chế môi trường được ghi rõ.
