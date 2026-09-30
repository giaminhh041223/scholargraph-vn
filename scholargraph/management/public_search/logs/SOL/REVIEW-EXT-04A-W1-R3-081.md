# Log review SOL EXT-04A R3 081

- Thời điểm: 2026-09-30T15:57:54.131095+07:00; role reviewer độc lập context mới `/root/review_storage_r3_081`; requested SOL6.1/high, actual runtime model unknown.
- Quyền ghi: chỉ report/log này ở parent; target immutable HEAD `6b33c8fe1f5817d38960ac6db29ac62af899da3b`. Đã đọc parent AGENTS/state/HANDOFF/tasks/routing/registry/strategy, EXT task card/contract/config/W0, ADR-020, Gemini R1/R2 và coordinator R2 close gate; target AGENTS/code/tests/fixture metadata.
- Trước/sau: HEAD exact, git status sạch, 8/8 scoped hashes không đổi và 14/14 W0 pins khớp; hashes đầy đủ tại [report](../../reviews/SOL/EXT-04A-W1-R3-081.md).

## Lệnh thực chạy và output

PowerShell; cwd pytest là target nested scholargraph, collector là parent. Dùng runtime parent, nguồn target, không pytest cache/bytecode write:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='D:/Web_mining_20261/scholargraph/.worktrees/public-muse/scholargraph/src'
& 'D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe' -m pytest -p no:cacheprovider tests/unit/test_public_store.py tests/unit/test_public_export.py -q
& 'D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe' 'D:/Web_mining_20261/scholargraph/data/public_search/control/w1-081/storage-close-fault-081.py'
```

- pytest tool chunk `54ae19`: exit0, `43 passed in 4.92s`, không failed/skipped.
- exact fault collector chunk `6b3b3a`: exit0, close structured failure / closed_flag false / cli_exit 1 / cli_stdout empty / evidence structured failure. Collector exit0 không phải CLI exit0.

Supplemental SOL chunk `25c23f`: chạy Python stdin bằng `@' ... '@ | & 'D:/Web_mining_20261/scholargraph/.venv/Scripts/python.exe' -`; dùng TemporaryDirectory `sg-sol-r3-*`, seed initialize_store + close thật, rồi subprocess boot gọi main. Boot giữ original open_existing, wrap connection thật bằng FaultConnection forwarding __getattr__ và close raises OSError. Mode primary-and-close thêm list_library raises structured storage trước cleanup. Từng subprocess dùng runtime/PYTHONPATH trên, args `--check-storage --config <parent configs/public_search.json> --project-root <temp project>`. Assert exit1/stdout rỗng/stderr đúng FAIL.

```json
{"sol_integrated_fault_subprocesses":[{"mode":"close-only","exit":1,"stdout":"","stderr":"FAIL: storage check failed"},{"mode":"primary-and-close","exit":1,"stdout":"","stderr":"FAIL: storage check failed"}]}
```

- 2/2 assertions PASS, Python collector exit0; DB/files/subprocess boot chỉ system temp, cleanup sau subprocess kết thúc. Không fixture hoặc artifact data mới trong repo.
- Git readonly: rev-parse HEAD, status --short/--porcelain, log -5, diff R2..R3 trên store/tests. SHA256 kiểm bytes trước/sau; freeze JSON có đúng 14 keys, scope có đúng 8 files.
- Review R3 3 test assertions: close storage error + closed false + retry/idempotence; CLI subprocess1/FAIL/noVALID; initialize enumeration error + sentinel bytes + DB/marker absent. R2 regression 6 cases nằm cùng focused suite, không tuyên bố chạy Gemini NOT_RUN probes.

## Kết thúc và bước tiếp

Verdict **PASS** scoped R3. Coordinator nhập đúng bytes MUSE6b33c8f, chạy combined parent gate rồi chốt board/freeze W1. Reviewer không cập nhật shared state, không commit và không dispatch W2. Không finding còn mở trong scope; live quota/production orchestration/core human gates chưa được review này kiểm định.

Closeout checker thực chạy: `& D:/Web_mining_20261/scholargraph/scripts/check_project.ps1`, cwd parent, chunk eb3479, exit0: 53 tasks/acyclic/cards-state consistent; 487 local Markdown links; 53 routes/7 lanes/79 sessions. WARN SG-034 awaits SG-033 là human dependency đang giữ nguyên.
