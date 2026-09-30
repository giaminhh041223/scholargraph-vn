# Review độc lập EXT-01B R2 — SOL (re-review F5/F6)

- **Verdict: PASS.** R2 author fixes F1–F6 đã được kiểm tra trên snapshot MUSE hiện tại. Không còn bypass im lặng trong validator ở các trường hợp đã giao.
- Reviewer: SOL, fresh context; implementation model/effort MUSE: unknown. Chỉ đọc worktree MUSE; chỉ ghi report/log này trong worktree SOL.
- Target: `D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph`, branch `codex/public-search-muse`, live HEAD `9f70669` (UNCOMMITTED theo packet). Không sửa implementation, board hoặc raw.
- Audit/session: `ses_f0fc34300ffehYtM193B3KNg56`, generated `2026-09-30T10:16:26+07:00`; correction packet/log ghi chạy lúc `2026-09-30T11:06:48+07:00`, không có live data mới.

## F1–F4 và hash chain

Validator chạy trên raw pilot thật và trả `PASS`, exit 0. Tái băm độc lập khớp 6/6 file MANIFEST ↔ meta ↔ bytes; raw không đổi qua review. Các số chính: arXiv body 4,457 bytes, SHA-256 `e38e577822f80ed9e8555322c5865e34ecc60b604a2af1bd767effa08535254c`; OpenAlex 429 body 253 bytes, SHA-256 `e2853e1081387fb57084d3fbaa427c9e4dc1562c2af5ff09044420a58189aca6`; OpenAlex retry body 101,458 bytes, SHA-256 `8050e77aba06e90709c0ef2006647049ef8306e55f48e2e034bc538764468a0d`.

- **F1 PASS:** audit, meta, MANIFEST và raw hashes/byte counts khớp.
- **F2 PASS:** audit/narrative chỉ mô tả anonymous/keyed access theo official docs; keyed behavior không probe, không tạo account/key; không còn gate `Bearer`, `keyed probe`, `user-created`; quota/runtime sustained và retry metadata thiếu đều ghi `author-reported/unverified`/`not measured`.
- **F3 PASS:** retry provenance có đủ bốn trường author-reported/unverified; narrative phân biệt first-page observed với docs-only và không dựng lại retry URL; retry meta thật không có URL/headers/date.
- **F4 PASS:** đếm độc lập từ payload: arXiv **2 entries, DOI 0/2, totalResults 186833**; OpenAlex retry **3 works, meta.count 976071, page 1/per_page 3**. Audit và narrative khớp; không gọi DOI verified.

## Re-review F5/F6

### F5 — thiếu Atom `opensearch:totalResults` phải FAIL

Validator mới tại `validate_source_audit.py:316-338` yêu cầu trường này trong cả audit và Atom body, từ chối empty/non-integer/missing với `FAIL:` và exit 1. Fixture `adv_no_totalresults` trả:

```text
FAIL: malformed arxiv body: missing required opensearch:totalResults (F5)
exit 1
```

Reproducer độc lập trong thư mục tạm: xóa thẻ Atom khỏi `valid_mini`, cập nhật MANIFEST/meta/audit SHA và byte count nhất quán, giữ audit `totalResults=999`; validator vẫn trả đúng `FAIL ... missing required ... (F5)`, exit 1.

### F6 — counter sai kiểu phải FAIL có context

`parse_int_strict` mới (validator lines 32–50) được dùng cho mọi required numeric counter/byte field. Fixture `adv_nonnumeric_counter` và reproducer tạm với `entries_returned="oops"` đều trả:

```text
FAIL: audit.sources.arxiv entries_returned (F4): must be integer, got 'oops' (F4)
exit 1
```

Không có traceback. Bool, float, empty, non-decimal và kiểu khác đều bị từ chối bằng `FAIL:` contextual.

## Subprocess evidence

Dùng root `.venv/Scripts/python.exe`, không network:

| Case | Exit | Kết quả |
|---|---:|---|
| real raw pilot | 0 | PASS |
| `valid_mini` | 0 | PASS |
| `adv_missing` | 1 | FAIL missing required pilot file |
| `adv_hash_mismatch` | 1 | FAIL hash mismatch |
| `adv_malformed` | 1 | FAIL malformed Atom |
| `adv_narrative_mismatch` | 1 | FAIL narrative DOI counter |
| `adv_missing_key` | 1 | FAIL missing audit `totalResults` |
| `adv_no_totalresults` | 1 | FAIL missing Atom `totalResults` (F5) |
| `adv_nonnumeric_counter` | 1 | FAIL contextual non-integer counter (F6) |

Temporary hash-consistent missing-totalResults and nonnumeric-counter probes reproduced both historical findings and returned exit 1 with a single `FAIL:` line. Raw pilot hash snapshot before/after remained identical.

## Closeout

F1–F6 đạt acceptance trên snapshot đã kiểm. Không sửa implementation/board/raw; không có live request. Có thể chuyển EXT-01B R2 sang bước coordinator closeout theo policy, với điều kiện coordinator dùng đúng snapshot/evidence này.
