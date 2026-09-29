# Kế hoạch hợp nhất `bn` → bản chính và hoàn tất ScholarGraph

- Lập: 2026-09-29, phiên Claude (coordinator C). Trạng thái: **ĐỀ XUẤT, chưa thực thi.**
- File này là kế hoạch. Trạng thái chính thức vẫn nằm ở `management/tasks.json`, `state.json` và `HANDOFF.md`. Coordinator chỉ ghi các file đó sau khi người dùng duyệt kế hoạch.
- Không mục nào trong file cho phép tự mở agent, lập lịch hay xuất bản ra ngoài. Người dùng tự mở từng phiên Codex/Gemini bằng các prompt ở mục 6.

## 1. Hiện trạng đã kiểm chứng

Kiểm chứng từ ngày 2026-09-23 đến 2026-09-26:

| Hạng mục | Kết quả |
|---|---|
| Board `bn` | 39 DONE · 2 REVIEW (SG-030, SG-041) · 1 IN_PROGRESS (SG-033) · 5 TODO (SG-034, SG-042–045) · 4 DEFERRED (SG-046–049) |
| `scripts/verify_release.py` | PASS: 33 file freeze khớp hash |
| `pytest tests -q` | 730 passed, 0 failed (ngày 2026-09-26; máy đang bị job khác tranh CPU nên chạy mất 71 phút) |
| Tính lại độc lập 4 run SciFact test | Khớp `main_results.md` đến 4 chữ số (chỉ kiểm nDCG@10 và Recall@100) |
| Bản chính so với `bn` | Bản chính không đổi từ lúc clone, `bn` là phần làm tiếp. Raw data giống hệt |

Các vấn đề còn mở:

1. **P0 — ký tự xuống dòng (EOL).** Repo có `core.autocrlf=true`, không có `.gitattributes`, và working tree dùng lẫn CRLF với LF. Checkout hoặc clone lại sẽ làm lệch hash freeze.
2. **P0 — lịch sử git.** `git_head` của freeze (`e959f68`) và của các run (`dcca385`) chỉ tồn tại trong `bn/.git`. Hai repo không có lịch sử chung.
3. **P0 — dữ liệu ngoài git.** Khoảng 7.4GB bị ignore: runs, reports `.md`, indexes, cache… Đây là bản duy nhất và chưa có backup.
4. **P1 — test ghi đè dữ liệu freeze.** `tests/unit/test_text_subset.py:42` ghi đè `data/processed/openalex/works_text.jsonl` và `data/manifests/openalex_core_text.json` thật mỗi lần chạy full suite.
5. **P1 — thiếu review độc lập.** SG-027, SG-028, SG-029, SG-040 bắt buộc review bằng phiên mới (fresh-context), nhưng đã được đóng DONE chỉ bằng owner approval và tự kiểm.
6. **P1 — lỗi cài đặt/chạy.**
   - `requirements.lock:69` ghim `torch==2.14.0+cpu` nhưng thiếu `--extra-index-url`.
   - `run_demo.bat:23` có `>1`, tạo ra file rác `scholargraph/1`.
   - `REPRODUCE.md:10` và `DEMO_SCRIPT.md:5` ghi cứng đường dẫn `bn`.
   - Scope trong AGENTS (gốc và `scholargraph/`) đang trỏ vào `bn`.
7. **P1 — commit `dcca385` (fallback hybrid).** Chưa có session log. Chưa có test cho nhánh lexical-only và nhánh cả hai phía rỗng.
8. **P2 — sổ sách.**
   - `state.last_verification` đã cũ.
   - ADR-017 bị trùng số.
   - `RELEASE_MANIFEST.md` ghi HEAD cũ.
   - Bảng A2 trong `ablation.md` sai số cột.
   - `.venv` đang phụ thuộc Python của Codex runtime (`include-system-site-packages=true`).

## 2. Phân vai

| Bên | Vai trò (lane) | Quyền ghi |
|---|---|---|
| **Claude** (phiên này) | C: điều phối, tích hợp, git và migration | Là bên **duy nhất** ghi `tasks.json`, `state.json`, `HANDOFF.md`, `chat_registry.json`, `DECISIONS.md`. Chạy mọi lệnh git có tính phá hủy hoặc tái cấu trúc |
| **Codex** | Worker (M/P/S/D): sửa code, test, môi trường, script | Chỉ các đường dẫn được giao trong prompt, cộng session log của chính phiên |
| **Gemini** | V: review phiên mới (khác họ model nên độc lập hơn). W: soạn nháp báo cáo và slides | Chỉ file review hoặc file nháp được chỉ định. **Không** sửa implementation |
| **Hai thành viên** | H: human gate, gán nhãn, tái lập chéo, diễn tập | Nhãn SG-033, xác nhận các gate, quyết định phương pháp |

Nguyên tắc phân quyền:

- Agent **không bao giờ** gán nhãn SG-033 và không đóng vai human rater.
- Review của Gemini là "lượt kiểm tra tách biệt bằng model khác", **không** phải review của con người.
- Mọi quyết định phương pháp do hai thành viên chốt.

## 3. Luật chung cho mọi phiên Codex/Gemini

Mỗi prompt ở mục 6 đều dẫn chiếu mục này.

1. **Đọc trước:** `AGENTS.md` (gốc) → `scholargraph/AGENTS.md` → `management/state.json` → `HANDOFF.md` → task card liên quan trong `docs/TASKS.md` → file này.
2. **Phạm vi ghi:** chỉ sửa các đường dẫn trong danh sách "Được ghi" của prompt.
   - Không sửa `management/tasks.json`, `state.json`, `HANDOFF.md`, `chat_registry.json`, `DECISIONS.md`. Đề xuất cho coordinator thì viết trong session log.
3. **Git:**
   - Chỉ `git add <đường dẫn cụ thể>` rồi commit với tiền tố `sg-0NN:`.
   - **Cấm** `git add -A`, `git reset`, `git checkout -- .`, `git stash`, `git clean`, rebase và push.
4. **Vùng bất khả xâm phạm:**
   - `configs/frozen_main.json`, `data/raw/`, `data/splits/`, `artifacts/runs/`, `artifacts/final_test/`, `artifacts/indexes/`.
   - **Cấm chạy lại bất kỳ đánh giá nào trên split test.**
5. **Trung thực:**
   - Ghi đúng lệnh đã chạy, exit code và số liệu thật. Thiếu thì ghi "chưa đo".
   - Không dùng `.get()` với giá trị mặc định để che thiếu dữ liệu. CLI lỗi phải thoát mã 1.
   - Mỗi thay đổi code phải kèm test phá hủy chạy trong `tmp_path`.
6. **Khi gặp finding P0/P1 ảnh hưởng metric, split, leakage hoặc nhãn:** DỪNG, ghi vào log hoặc review và báo coordinator. Không tự sửa. Không "chạy lại test cho đúng". Muốn chạy lại phải có freeze version mới, ADR và người dùng duyệt.
7. **Session log:** `management/logs/SESSION-<YYYYMMDD>-<NNN>-<LANE>.md`. Coordinator cấp NNN khi mở phiên; phiên cuối trong `bn` là 065.
   - Log gồm: phạm vi, file đã đổi, lệnh cùng exit code, kết quả, vướng mắc, đề xuất cập nhật board.
8. **Full pytest:** chỉ chạy khi máy không có job nặng khác (ví dụ `mutants.py` của thư mục `D:\Nghiên cứu sinh`). Sau khi chạy phải kiểm `git status --porcelain`: không được có file ngoài phạm vi bị đổi.
9. Giao tiếp và log bằng tiếng Việt. Định danh trong code dùng tiếng Anh.

## 4. Task mới

Coordinator tạo các task này ở giai đoạn 0 sau khi người dùng duyệt:

| ID | Tên | Lane | Nội dung | Nghiệm thu |
|---|---|---|---|---|
| SG-051 | Hợp nhất `bn` → bản chính | C | `.gitattributes`, merge lịch sử, chuyển dữ liệu, sửa scope, ADR-019 | `verify_release` PASS, full pytest pass và `check_project.ps1` PASS tại `D:/Web_mining_20261/scholargraph`. `git_head` của freeze và các run truy được trong lịch sử |
| SG-052 | Vệ sinh test và phủ fallback API | M/P | Mục 4, 7 và bảng A2 ở mục 1 | Chạy full suite không làm đổi file tracked hay mtime của dữ liệu freeze. Cả 3 nhánh fallback có test |

Phần sửa `run_demo.bat`, lock file và đường dẫn tài liệu thuộc **SG-041**. SG-041 đang ở REVIEW nên sửa trước khi đóng, không cần mở ID mới.

## 5. Các giai đoạn và thứ tự

```
G0 Chuẩn bị (C + người) ──► G1 Sửa và review song song trong bn ──► G2 Chốt bn
      │                          CX-1 ∥ GM-1, rồi GM-2 ∥ GM-3
      └─ H: bắt đầu gán nhãn dev SG-033 ngay (song song, xem G4)
G2 ──► G3 Hợp nhất về bản chính (C, CX-2, GM-4) ──► G4 Hoàn tất dự án tại bản chính
```

### G0 — Chuẩn bị (Claude + người dùng, khoảng 1–2 giờ)

| # | Ai | Việc | Kiểm tra |
|---|---|---|---|
| 0.1 | C | Xác nhận `bn` vẫn ở HEAD `dcca385` và cây sạch (chỉ còn `scholargraph/1`) | Output của `git log -1` và `git status` |
| 0.2 | Người dùng | Chọn nơi backup nằm ngoài `bn` và ngoài bản chính | — |
| 0.3 | C | Nén backup các phần không tái tạo được hoặc tái tạo tốn kém: `artifacts/{runs,final_test,reports,indexes}`, `data/{processed,annotations,manifests,splits}`, khoảng 0.8GB. `data/raw` và `artifacts/cache` tải lại được theo pin nên không bắt buộc | Kiểm tra zip và ghi sha256 của zip |
| 0.4 | C | Ở bản chính: commit các thay đổi đang dở sang nhánh `archive/pre-merge` (người dùng xác nhận trước) | `git status` sạch |
| 0.5 | C | Trong `bn`: thêm `.gitattributes` (`* -text`, tức giữ nguyên byte), chạy `git add --renormalize .`, sau đó `verify_release.py`, rồi commit | verify PASS. Clone thử `bn` vào thư mục tạm và so hash 33 file freeze với bản clone |
| 0.6 | C | Board: tạo SG-051 và SG-052; ADR-019 (hợp nhất và review hồi tố); đánh dấu ADR-017 bản "đề xuất" là superseded; cập nhật `state.last_verification`; viết session log cho `dcca385`; đăng ký các phiên Codex/Gemini và claimed_paths | `check_project.ps1` PASS (người dùng chạy) |

Bước 0.5 phải xong **trước** khi Codex bắt đầu, vì renormalize đụng vào toàn bộ index git.

### G1 — Sửa và review trong `bn` (khoảng 1 ngày)

| Phiên | Ai | Bắt đầu khi | Phạm vi |
|---|---|---|---|
| **CX-1** | Codex | Sau 0.6 | SG-052 và phần sửa của SG-041 (prompt 6.1) |
| **GM-1** | Gemini, phiên mới | Sau 0.6, song song với CX-1 | Review SG-027 và SG-028 (prompt 6.3) |
| **GM-2** | Gemini, phiên mới khác | Sau khi CX-1 commit bảng A2 | Review SG-029 và SG-030 (prompt 6.4) |
| **GM-3** | Gemini, phiên mới khác | Sau khi CX-1 xong | Review SG-040, SG-052 và `dcca385` (prompt 6.5) |

CX-1 và GM-1 không đụng file của nhau: CX-1 sửa `tests/`, `scripts/`, tài liệu và launcher; GM-1 chỉ đọc configs, runs và reports.

### G2 — Chốt `bn` (Claude, khoảng 2 giờ)

1. Đọc review của GM-1, GM-2 và GM-3.
   - Nếu có P0/P1 về metric hoặc leakage: **dừng**, đưa sang người dùng quyết định (freeze version mới hay ghi hạn chế).
   - Nếu chỉ có P2: ghi carry-forward.
2. Cập nhật board.
   - SG-027, SG-028, SG-029, SG-040 giữ DONE, bổ sung evidence review hồi tố. Nếu review FAIL thì mở lại task.
   - SG-030 vẫn REVIEW cho tới khi có human gate (H-1).
3. Chạy full pytest, `verify_release` và `check_project.ps1` (người dùng chạy). Commit rồi tag `pre-merge-bn`.

### G3 — Hợp nhất về bản chính (Claude; người dùng xác nhận từng bước không đảo ngược được, khoảng nửa ngày)

| # | Ai | Việc |
|---|---|---|
| 3.1 | C | Trong repo chính: `git fetch ./bn master:bn-import`, rồi `git merge --allow-unrelated-histories bn-import`. Khi xung đột: lấy bản `bn` cho `scholargraph/`, giữ tài liệu bài giảng ở thư mục gốc. Kiểm tra `git cat-file -t e959f68` và `dcca385` |
| 3.2 | C | Đổi tên các thư mục bị ignore cũ của bản chính thành `*_pre_merge`. Dùng `mv` (cùng ổ D nên gần như tức thì) để chuyển các thư mục bị ignore từ `bn/scholargraph` sang bản chính. Không đi qua git checkout cho các file nhạy cảm về byte |
| 3.3 | C | Trả scope của `AGENTS.md` (gốc và `scholargraph/`) về bản chính. ADR-019 ghi nhận việc hợp nhất. Không tìm-thay hàng loạt chữ "bn": dòng `frozen_by` trong freeze giữ nguyên |
| 3.4 | Codex **CX-2** | Tạo lại `.venv` tại bản chính theo lock và thử REPRODUCE nguyên văn (prompt 6.2) |
| 3.5 | C | Tại bản chính: `verify_release` PASS, full pytest, `run_demo.bat` lên `/health`, rồi `verify_release.py --write-manifest` để tạo lại `RELEASE_MANIFEST` |
| 3.6 | Người dùng | Chạy `scripts/check_project.ps1` tại bản chính |
| 3.7 | Gemini **GM-4** | Review SG-041 tại bản chính (prompt 6.6). Sau đó coordinator đóng SG-041 và SG-051 |
| 3.8 | Người dùng | Giữ `bn` làm bản dự phòng ở chế độ chỉ đọc ít nhất tới khi SG-045 DONE. Việc xoá do người dùng tự làm |

Trong lúc chạy G3 (khoảng nửa ngày), hai thành viên **tạm ngưng ghi** vào `data/annotations/`.

### G4 — Hoàn tất dự án tại bản chính (theo DAG)

| Task | Ai làm | Ai review/duyệt | Ghi chú |
|---|---|---|---|
| SG-030 | H: cả hai đọc 24 error packet (`docs/ERROR_ANALYSIS.md`) | Human gate. Review máy do GM-2 | Ghi ai duyệt, lúc nào, bằng chứng |
| SG-033 | **H**: gán nhãn độc lập. Dev 219 cặp trước, test 443 cặp sau khi SG-034 freeze | C gộp nhãn. Codex chỉ chạy `score_vn_agreement.py` **trước** khi thảo luận | Mỗi người nhãn trên bản sao riêng (ví dụ `vn_labels_A.jsonl` và `vn_labels_B.jsonl`), không xem bản của người kia. C gộp thành `vn_labels.jsonl` (annotator A/B). Có thể bắt đầu nhãn dev ngay từ G0 |
| SG-034 | **Codex CX-3**: chọn default theo pooled dev → `configs/frozen_vn.json` → sau khi có nhãn test thì chạy final VN eval một lần | **Gemini GM-5** review freeze VN trước khi mở test. Người dùng duyệt freeze | Quy tắc tie-break đã có trong `evaluation/tuning.py` |
| SG-042 | **H**: thành viên thứ hai chạy lại baseline và graph run. Codex CX-4 viết `evidence_index.json` và script so sánh theo tolerance | Gemini audit bảng và run ID | Không gọi run của agent là human reproduction |
| SG-043 | **Gemini GM-6** soạn nháp `reports/final_report.md` chỉ từ bảng đã chốt. Codex CX-4 sinh `reports/figures/` từ artifact và script kiểm claims | H sở hữu và sửa. C đối chiếu 1:1 từng con số với run ID | Có mục khai báo AI assistance theo rubric |
| SG-044 | Gemini GM-6 soạn nháp slides và 15–20 Q&A | **H** diễn tập 2 lần, đổi người | Có phương án offline dự phòng |
| SG-045 | C: checklist nộp bài, `release_audit.md`, pin release | Người dùng | Chỉ nộp ra ngoài khi người dùng yêu cầu |

Đường găng là **SG-033** (khoảng 16 giờ-người, cần hai người). Nên bắt đầu nhãn dev ngay, song song với G0–G3.

## 6. Prompt cho từng phiên

Dán nguyên văn vào một phiên mới. `<NNN>` do coordinator cấp. `<SNAPSHOT>` là commit do coordinator cung cấp sau bước 0.6.

### 6.1 CX-1 — Codex: SG-052 và phần sửa của SG-041 (trong `bn`)

```text
Bạn là worker Codex (lane M/P) của ScholarGraph, workspace D:/Web_mining_20261/bn.
Session: SESSION-<YYYYMMDD>-<NNN>-CODEX. Đọc và tuân thủ mục 3 của
scholargraph/docs/MERGE_AND_FINISH_PLAN.md trước khi làm.

Phần A — SG-052 (commit riêng "sg-052: ..."):
1. tests/unit/test_text_subset.py:42 (test_builder_rerun_deterministic) hiện chạy
   scripts/build_openalex_text_subset.py với cwd=PROJECT_ROOT và GHI ĐÈ dữ liệu freeze thật
   (data/processed/openalex/works_text.jsonl, data/manifests/openalex_core_text.json).
   Sửa: thêm tham số output vào builder (hoặc cơ chế sẵn có), để test ghi vào tmp_path;
   assert sha256 của output tmp == hash works_text.jsonl trong configs/frozen_main.json.
   Thêm test phá hủy: thiếu input -> CLI exit 1.
2. Grep toàn bộ tests/ tìm test nào khác ghi vào PROJECT_ROOT (cwd=PROJECT_ROOT, write_text,
   open(...,"w"), subprocess script không có output tmp). Sửa theo cùng cách, liệt kê trong log.
3. src/scholargraph/api/service.py:107-131 (fallback hybrid, commit dcca385): KHÔNG sửa logic.
   Thêm test cho nhánh lexical-only (monkeypatch dense trả rỗng) và nhánh cả hai rỗng; kiểm
   nhãn method trung thực. Nhánh dense-only đã có test trong tests/integration/test_api.py.
4. scripts/run_ablation.py: bảng A2 trong artifacts/reports/ablation.md có header 3 cột nhưng
   dòng 4 cột. Sửa generator để thêm cột run_id vào header; sinh lại CHỈ ablation.md;
   diff phải chỉ đổi bảng A2; mọi file .json đi kèm giữ nguyên sha256 (ghi trước/sau vào log).
Phần B — SG-041 fixes (commit riêng "sg-041: ..."):
5. run_demo.bat:23: chuỗi ">1 phut" đang redirect ra file scholargraph/1 -> sửa thành
   "hon 1 phut" (hoặc escape ^>). Xóa file rác scholargraph/1 (untracked, 67 byte).
6. scholargraph/requirements.lock: torch==2.14.0+cpu không có trên PyPI. Thêm dòng
   --extra-index-url https://download.pytorch.org/whl/cpu ở đầu file; kiểm resolvable bằng
   pip install --dry-run --no-deps "torch==2.14.0+cpu" --extra-index-url ... (ghi exit code).
7. docs/REPRODUCE.md:10 và docs/DEMO_SCRIPT.md:5 đang hard-code D:\Web_mining_20261\bn\...
   -> đổi thành đường dẫn tương đối ("từ thư mục gốc repo: cd scholargraph").
   KHÔNG sửa configs/frozen_main.json hay bất kỳ file nào nhắc "bn" như dấu vết lịch sử.
Được ghi: tests/**, scripts/build_openalex_text_subset.py, scripts/run_ablation.py,
artifacts/reports/ablation.md, run_demo.bat, scholargraph/requirements.lock,
docs/REPRODUCE.md, docs/DEMO_SCRIPT.md, xóa scholargraph/1, session log của bạn.
Nghiệm thu: full pytest pass (ghi số test và thời gian); sau full suite `git status --porcelain`
chỉ còn file bạn sửa; mtime + sha256 của data/processed/openalex/works_text.jsonl không đổi
(ghi trước/sau). Nếu phát hiện bug trong src/ ngoài phạm vi: ghi log, không sửa.
Kết thúc: session log + đề xuất cập nhật board cho coordinator.
```

### 6.2 CX-2 — Codex: môi trường tại bản chính và thử REPRODUCE (G3.4)

```text
Bạn là worker Codex (lane S) của ScholarGraph, workspace D:/Web_mining_20261 (bản chính,
đã hợp nhất từ bn). Session: SESSION-<YYYYMMDD>-<NNN>-CODEX. Đọc mục 3 của
scholargraph/docs/MERGE_AND_FINISH_PLAN.md.
1. Tạo mới scholargraph/.venv bằng Python 3.12 độc lập (ưu tiên `py -3.12`), với
   include-system-site-packages=false. Nếu máy chỉ có Python của Codex runtime thì dùng nó
   nhưng vẫn tắt system site-packages, và ghi rõ vào log. KHÔNG chép .venv cũ từ bn.
2. pip install -r requirements.lock; pip check. Ghi exit code.
3. Làm đúng từng lệnh trong docs/REPRODUCE.md theo nguyên văn; mỗi lệnh ghi exit code và kết quả.
   Lệnh nào hỏng hoặc thiếu bước: ghi vào log dạng "đề xuất sửa REPRODUCE", không tự đoán cho qua.
4. python scripts/verify_release.py (không --write-manifest) -> ghi PASS/FAIL.
Được ghi: scholargraph/.venv, session log. Không sửa docs hay code; đề xuất sửa gửi coordinator.
```

### 6.3 GM-1 — Gemini: review SG-027 (freeze) và SG-028 (final runs)

```text
Bạn là reviewer V (phiên mới, độc lập) của ScholarGraph tại D:/Web_mining_20261/bn/scholargraph,
snapshot commit <SNAPSHOT>. Session: SESSION-<YYYYMMDD>-<NNN>-GEMINI.
Đọc mục 3 của docs/MERGE_AND_FINISH_PLAN.md, task card SG-027/SG-028 trong docs/TASKS.md,
docs/RESEARCH_PROTOCOL.md, ADR-018. Bạn CHỈ ĐỌC và CHẠY LỆNH ĐỌC; chỉ ghi 2 file review.
Bối cảnh: hai task này đã DONE bằng owner approval mà thiếu review phiên mới. Đây là review hồi tố.
Không tin lời log/report; kiểm trên file thật.
Kiểm:
1. Mọi hash trong configs/frozen_main.json khớp file hiện tại; dense_index_pins khớp manifest
   index; translation_pin khớp cache. sha256 của chính frozen_main.json = 34159fb1...7557
   và trùng field frozen_manifest_sha256 trong artifacts/final_test/freeze_*.json.
2. Trình tự theo CHUỖI COMMIT GIT (timestamp không tin được: đồng hồ máy từng nhảy, xem
   management/logs/SESSION-20260921-064.md): freeze có trước mọi run test; mỗi phương pháp
   chỉ có đúng 1 run test (liệt kê artifacts/runs/*-test*); track B dùng đúng g=0.3/l=0.0
   đã chọn trên dev (artifacts/reports/b_dev_trials.json), không có chọn trên test.
3. Viết script ĐỘC LẬP trong thư mục tạm (không import scholargraph.evaluation) tính lại
   TẤT CẢ số trong artifacts/reports/main_results.md: 7 run track A × 5 metric
   (nDCG@10, Recall@100, MRR@10, MAP@100, P@5) từ rankings.jsonl + qrels gốc, và 2 arm
   track B. Tolerance 1e-4. Ghi bảng so sánh đầy đủ.
4. Đọc leakage_A_*.json: kiểm tra những gì, có lọt không; tìm kiểu rò rỉ chưa được kiểm.
Output: management/reviews/SG-027-REVIEW-<YYYYMMDD>.md và SG-028-REVIEW-<YYYYMMDD>.md.
Mỗi finding: mức P0/P1/P2, bằng chứng (file:dòng, lệnh, output), kết luận PASS/FAIL.
Finding P0/P1 về metric/leakage: DỪNG và báo, không sửa gì. Đây không phải review của con người.
```

### 6.4 GM-2 — Gemini: review SG-029 (ablation/robustness) và SG-030 (thống kê)

```text
Bạn là reviewer V (phiên mới, độc lập) tại D:/Web_mining_20261/bn/scholargraph, snapshot
<SNAPSHOT>. Session: SESSION-<YYYYMMDD>-<NNN>-GEMINI. Đọc mục 3 của
docs/MERGE_AND_FINISH_PLAN.md, card SG-029/SG-030, docs/RESEARCH_PROTOCOL.md.
Chỉ đọc; chỉ ghi file review.
Kiểm SG-029: mọi biến thể trong artifacts/reports/ablation.md và robustness.md đã được
định trước trong configs/frozen_main.json (ablations_planned) hoặc ADR, không có biến thể nào
chọn/bỏ dựa trên test; số liệu khớp 1:1 với json nguồn; tự re-fuse một cấu hình RRF k.
Kiểm SG-030: tự viết paired bootstrap độc lập (B=10000, seed=20260915, unit=query_group theo
protocol) tính lại ít nhất 4 dòng của artifacts/reports/statistics.md (có dòng CI chứa 0 và
dòng không chứa 0); cột "CI excl 0" đúng logic; không có claim p-value/significance;
subgroup có n. error_packets.json có 24 packet và docs/ERROR_ANALYSIS.md tồn tại.
Human gate SG-030 (hai thành viên đọc lỗi) chưa xong: KHÔNG ghi là đã duyệt.
Output: management/reviews/SG-029-REVIEW-<YYYYMMDD>.md, SG-030-REVIEW-<YYYYMMDD>.md.
```

### 6.5 GM-3 — Gemini: review SG-040 (hiệu năng), SG-052 và `dcca385`

```text
Bạn là reviewer V (phiên mới, độc lập) tại D:/Web_mining_20261/bn/scholargraph, snapshot
<SNAPSHOT> (sau khi CX-1 commit). Session: SESSION-<YYYYMMDD>-<NNN>-GEMINI.
Đọc mục 3 của docs/MERGE_AND_FINISH_PLAN.md, card SG-040. Chỉ đọc; chỉ ghi file review.
1. SG-040: artifacts/reports/performance.md khớp json nguồn; hardware ghi đủ; chỗ vượt budget
   được nêu, không bị giấu; cold/warm phân biệt đúng; không có số không đo mà vẫn ghi.
2. SG-052 (diff của CX-1): test không còn ghi vào data/ thật — tự kiểm bằng cách đặt thuộc tính
   read-only cho data/processed/openalex/works_text.jsonl và data/manifests/openalex_core_text.json
   rồi chạy pytest tests/unit/test_text_subset.py (phải pass), sau đó gỡ read-only; test mới là
   test phá hủy thật, không chỉ khớp implementation.
3. dcca385 (src/scholargraph/api/service.py:107-131, fallback hybrid khi một phía rỗng): có
   vi phạm "không fallback ngầm" không (nhãn method có đủ trung thực, UI có hiển thị nhãn
   không); 3 nhánh đều có test.
Output: management/reviews/SG-040-REVIEW-<YYYYMMDD>.md, SG-052-REVIEW-<YYYYMMDD>.md.
```

### 6.6 GM-4 — Gemini: review SG-041 (release) tại bản chính

```text
Bạn là reviewer V (phiên mới, độc lập) tại D:/Web_mining_20261/scholargraph (bản chính, đã
hợp nhất). Session: SESSION-<YYYYMMDD>-<NNN>-GEMINI. Đọc mục 3 của
docs/MERGE_AND_FINISH_PLAN.md, card SG-041, log của CX-2. Chỉ ghi file review.
Kiểm: docs/REPRODUCE.md, docs/RELEASE_MANIFEST.md, run_demo.bat/scripts/run_demo.ps1 không còn
đường dẫn bn; RELEASE_MANIFEST ghi đúng HEAD hiện tại; tự chạy python scripts/verify_release.py
và run_demo.bat tới khi /health trả OK (ghi thời gian); đối chiếu log CX-2 xem lệnh nào trong
REPRODUCE thực sự đã thử; checksums/model-data requirements đủ theo nghiệm thu SG-041.
Output: management/reviews/SG-041-REVIEW-<YYYYMMDD>.md.
```

### 6.7 CX-3, CX-4, GM-5, GM-6 (G4)

Coordinator viết prompt chi tiết cho các phiên này khi dependency đã DONE, vì đầu vào cụ thể (nhãn thật, bảng đã chốt) chưa tồn tại. Khung nội dung:

- **CX-3 (SG-034):**
  - Đọc `evaluation/tuning.py` (luật chọn track C) và `configs/vn_methods.json`.
  - Chọn default chỉ trên pooled dev, ghi `configs/frozen_vn.json`, rồi **dừng** chờ GM-5 review và người dùng duyệt.
  - Sau khi có nhãn test: chạy final VN eval **một lần**, ghi `artifacts/reports/vn_results.md` gồm nDCG, P@5, MRR và unjudged ratio.
- **GM-5:** review `frozen_vn.json` trước khi mở test. Kiểm các điểm: chỉ dùng dev, tie-break đúng luật, nhãn có provenance A/B, chưa ai nhìn test.
- **CX-4 (SG-042/043):**
  - Viết `artifacts/reports/evidence_index.json`, trong đó mỗi bảng hoặc con số ứng với một run ID, hash và config.
  - Viết script so sánh kết quả tái lập của thành viên thứ hai theo tolerance.
  - Sinh `reports/figures/` từ artifact.
- **GM-6 (SG-043/044):**
  - Soạn nháp báo cáo, slides và `docs/DEFENSE_QA.md` bằng tiếng Việt, chỉ dùng số trong `evidence_index.json`.
  - Nêu rõ các kết quả âm: hybrid thua dense; PPR không hơn global PageRank vì CI chứa 0.
  - Không claim novelty hay SOTA. Có mục khai báo AI assistance.

## 7. Việc người dùng cần làm

| # | Việc | Khi nào |
|---|---|---|
| U-1 | Duyệt kế hoạch này; chọn nơi backup (bước 0.2) | Trước G0 |
| U-2 | Tạm dừng job nặng khác (`mutants.py`) khi các phiên chạy full pytest | G0–G3 |
| U-3 | Chạy `scripts/check_project.ps1` (Claude không được phép chạy) | Sau 0.6, G2 và 3.6 |
| U-4 | Xác nhận từng bước không đảo ngược được: 0.4, 3.1, 3.2 | G0 và G3 |
| U-5 | Mở các phiên Codex/Gemini theo prompt ở mục 6, báo coordinator model thực tế đã dùng | G1, G3, G4 |
| H-1 | Hai thành viên đọc 24 error packet, ghi duyệt SG-030 | Bất kỳ lúc nào |
| H-2 | Hai thành viên gán nhãn dev (219 cặp mỗi người, độc lập), sau đó test (443 cặp) sau freeze VN | Bắt đầu ngay; test sau SG-034 freeze |
| H-3 | Duyệt freeze VN (SG-034); tái lập chéo (SG-042); sở hữu báo cáo; diễn tập 2 lần (SG-044) | G4 |

## 8. Rủi ro và cách xử lý

| Rủi ro | Xử lý |
|---|---|
| Review hồi tố tìm ra lỗi metric hoặc leakage trong run test đã niêm phong | Không chạy lại ngay. Người dùng chọn: (a) freeze version mới với ADR và chạy lại có ghi nhận, hoặc (b) giữ kết quả và ghi hạn chế trong báo cáo |
| Renormalize hoặc merge làm lệch byte file freeze | Bước 0.5 kiểm bằng clone thử. Bước 3.2 chuyển dữ liệu bằng `mv`. Backup từ bước 0.3 |
| Hai phiên cùng sửa một file | claimed_paths ghi trong prompt và trong board; worker chỉ `git add` đường dẫn cụ thể |
| Nhãn SG-033 trễ | Đây là đường găng: bắt đầu từ G0. Nếu vượt khoảng 600 cặp thì giảm đều số query hoặc độ sâu trước khi nhãn test, kèm ADR (đúng card SG-033) |
| Thiếu Python 3.12 độc lập | CX-2 ghi rõ; người dùng quyết định cài hay chấp nhận ghi hạn chế trong REPRODUCE |
