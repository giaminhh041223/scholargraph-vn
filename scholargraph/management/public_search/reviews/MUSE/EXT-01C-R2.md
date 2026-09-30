# Re-review doc lap EXT-01C R2 - UX spec va fixtures (GEMINI working tree)

- Task: EXT-01C, owner GEMINI, reviewer MUSE (REV-W0-01C-R2-MUSE).
- Requested model: muse spark 1.3. Actual model/effort: unknown (khong suy tu nhan).
- Reviewer checkout: D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph, branch codex/public-search-muse, head 9f70669.
- GEMINI checkout: D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph, branch codex/public-search-gemini, head cc51ef8 + 4 modified (UX_SPEC.md, ux_examples.json, ux_examples.sidecar.json, validate_fixtures.py) + 3 untracked (2 log/packet R2 + 1 packet cu). Review tren working tree hien tai.
- SOL contract ref (read-only): checkout SOL, proposed head cb64c59a714085f1c453284fdfba76de3efb086e, code commit 774aeef0bfc42c636779f739c3fb4fbb8e9e37c4, v1.0.0 schema 1.
- Ngay: 2026-09-30. Chi ghi report/log MUSE. Khong sua fixtures/board/raw. Khong live request, khong doc qrels/labels/env.

## Inputs da doc

- docs/public_search/UX_SPEC.md (status PROPOSED_SOL_R2_RECONCILED, head cb64c59a + commit 774aeef0; 9 UI states; truth table TT-01..TT-07; English notice; OA unknown; synthetic notice).
- tests/fixtures/public_search/gemini/ux_examples.json (136021 bytes, root synthetic true + 9 ui_states + 7 tt, 12 example keys: ex01..ex11).
- tests/fixtures/public_search/gemini/ux_examples.sidecar.json (R2, checkpoint 2026-09-30T10:05:00+07:00, SOL head cb64c59, commit 774aeef, v1.0.0, synthetic true x3, khong tu tao content hash).
- tests/fixtures/public_search/gemini/validate_fixtures.py (687 dong: ALLOWED 5 types, map 1:1, coverage equality, recursive leakage, 16 negative subprocess, title-only + benign positive, --sidecar bat buoc).
- management/public_search/packets/GEMINI/EXT-01C-R2.md + logs/GEMINI/SESSION-20260930-W0-GEMINI-EXT-01C-R2.md (claim: 13 typed, 16 negative exit1, NOT_RUN chuyen coordinator).

## Phuong phap (read-only + rerun validator)

- Runtime: D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe. Chay validator tren GEMINI workdir (import SOL contracts read-only, tempfile cho negative, khong ghi repo).
- Grep contract_type/truth_table_id/ui_states_demonstrated trong fixture; grep `\.get\(` trong validator; doc sidecar; doi chieu UX_SPEC vs contracts.py overall_status/error_http_status.

## Evidence that (rerun doc lap, khop claim coordinator)

- `validate_fixtures.py --sidecar ...`: exit 0. Output: 1:1 typed PASS; Envelopes 11, Requests 1, Library entries 1, Total 13; 16/16 negative exit 1; title-only PASS; benign held_out PASS. Khop packet (13 typed, 16 exit1).
- contract_type/payload 1:1: code ALLOWED 5 types + map SearchEnvelope->envelope, StorageError->envelope, CacheScenarios->subcases, ValidationError->invalid_request_payload, LibraryEntry->library_entry; check exactly-one-payload + mismatch reject. Fixture: ex01 SearchEnvelope/envelope, ex02-07 SearchEnvelope/envelope (TT-01..TT-06), ex08 ValidationError/invalid_request_payload (TT-07, query blank + sources rong + top_k 75 + year dao -> ValidationError dung), ex09 CacheScenarios/subcases (3 subcases A/B/C), ex10 LibraryEntry/library_entry, ex11 StorageError/envelope. Negative 10 (Unknown), 15 (multi payload), 16 (mismatch) deu exit 1 that.
- Coverage: root ui_states_covered 9/9 (loading, empty, missing_fields, partial_failure, quota_exceeded, cached_fresh, cached_stale, oa_unknown, save_idempotent) == EXPECTED == observed; root truth_table 7/7 (TT-01..TT-07, hau to mo rong) == EXPECTED == observed; cache ex09 dung 3 subcases (A cached True/stale False, B failed/cached False, C cached True/stale True). Negative 11 (clear root), 12 (clear examples), 13 (thieu C), 14 (thua D) deu exit 1 that.
- Leakage metadata/text boundary: check_leakage_boundary de quy tren dict keys, cam labels/qrels/splits/split/benchmark_input/test_labels/eval_labels (exact + substring qrels/test_labels/eval_labels/benchmark_input), khong chan values text. Negative 9 (injected key qrels) exit 1 that; positive benign (query chua "held_out ... splits") van PASS + envelope validate PASS. Khong false positive tren fixture that (exit 0).
- Sidecar provenance: task EXT-01C/wave W0/iteration R2/owner GEMINI/reviewer MUSE/dispatch DISPATCH-20260930-W0-GEMINI/session SESSION-20260930-W0-GEMINI-EXT-01C-R2/updated_at checkpoint/synthetic+not_live+not_for_production true/reconciled 1.0.0/commit 774aeef/head cb64c59/status PROPOSED_SOL_R2_RECONCILED. Validator bat updated_at + head + commit + version (thieu/sai -> exit 1; negative 1 missing sidecar exit 1 that). Khong tu tao content hash (dung, tranh claim gia).
- No .get default: grep chi 1 `env.get("PYTHONPATH", "")` cho moi truong (khong phai required field); required root/example fields dung `in` + index truc tiep, thieu -> ValueError exit 1 (negative 4, 5 that). Khong silent masking.
- SHA256 working tree (ghi nhan, chua commit): UX_SPEC.md 27464aa3d965725ae672517edbea2f2425394c93304fc5743224190c564eeb14; ux_examples.json 40c69c353e1e2de449e8f1f4771ab7ac23ef05051ae1f2e7f67ccc5767d983c6; sidecar 31625c97c6b0c5498b2d47b7f3e4f7b27ab4c375e4e9be59b1c546c72d433d46; validator 0aa419f032ee24a12882cae40211d17bb72543bfe6c5f31ecc0fcfd87683db19.
- UX_SPEC wording: English notice co dinh; citation_count chi tham khao (khong diem quality); OA unknown an nut PDF; library chi metadata/provenance (khong PDF); non-2xx doc body hien partial hits; truth table + HTTP/CLI khop contracts.py (TT-01..TT-06 + TT-07 422); synthetic/not-live/not-for-production co dinh.

## Findings

- P0/P1: khong co. Khong silent fallback (.get), khong doc labels/qrels, khong hard-code metric, khong dung test labels lam feature, khong goi citation la correctness, secrets khong lien quan (fixtures synthetic, khong key).
- P2/P3 mo: khong co vi pham acceptance EXT-01C. Luu y nho (khong chan): TT-03 validator chi check overall empty + 0 hits (khong phan biet empty+empty vs success-filtered); ex04 mo ta filtered nhung sources deu empty — chap nhan duoc cho UX demo, khong sai contract.
- NOT_RUN: live sources, browser screenshots (ghi ro thieu), production search CLI (validator la fixture validator; recheck CLI that tai EXT-05B/06), offline full regression.

## Verdict: PASS (pham vi R2: 13 typed + 16 negative + title-only/benign + provenance, khong bypass)

- Dieu kien: GEMINI working tree chua commit (4 modified + 3 untracked); contract SOL van PROPOSED chua freeze (cho EXT-01B + freeze W0). Khong claim DONE/freeze/live evidence.
- Next: coordinator giu nguyen 4 files khi nhap (khong tron packet cu); EXT-05A doi chieu backend that + sua UI-owned bugs; re-review neu contract doi version.