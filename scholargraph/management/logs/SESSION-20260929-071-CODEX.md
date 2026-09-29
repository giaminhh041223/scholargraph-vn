# SESSION-20260929-071-CODEX — CX-2: Tái lập môi trường sạch và kiểm chứng REPRODUCE.md tại bản chính

- **Thời gian bắt đầu:** 2026-09-29T13:04:00+07:00
- **Thời gian kết thúc:** 2026-09-29T13:27:00+07:00
- **Session ID:** `SESSION-20260929-071-CODEX`
- **Lane / Role:** `D` / `W` (`implementation_worker`)
- **Snapshot:** `2d01b70bec5e`
- **Tasks:** `SG-051`, `SG-041`
- **Trạng thái:** `completed`

## 1. Tạo mới `.venv` với `include-system-site-packages = false` (Mục 1 & 2 — Prompt 6.2)
- Máy hiện tại không có `py -3.12` cài riêng ởระดับ hệ thống, nên sử dụng bộ thông dịch Python 3.12.14 tại `C:\Users\ADMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` với cờ mặc định `include-system-site-packages = false` (không chép `.venv` cũ từ `bn`).
- Nội dung `.venv\pyvenv.cfg`:
  ```ini
  home = C:\Users\ADMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python
  include-system-site-packages = false
  version = 3.12.14
  executable = C:\Users\ADMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
  ```
- Cài đặt từ khoá môi trường:
  - `.venv\Scripts\python.exe -m pip install -r requirements.lock` $\rightarrow$ **`exit_code = 0`** (cài đặt thành công toàn bộ 80 gói bao gồm `torch==2.14.0+cpu` qua `--extra-index-url https://download.pytorch.org/whl/cpu`).
  - `.venv\Scripts\python.exe -m pip check` $\rightarrow$ **`exit_code = 0`** (`No broken requirements found.`).

## 2. Chạy Nguyên văn Từng Lệnh trong `docs/REPRODUCE.md` (Mục 3 & 4 — Prompt 6.2)
1. **Kiểm tra khoá môi trường (`python scripts/verify_release.py`):**
   - Lệnh: `.venv\Scripts\python.exe scripts/verify_release.py`
   - Kết quả: `status: PASS`, `freeze_files: 33`, `git_head: 2d01b70bec5e`, **`exit_code = 0`**.
2. **Kiểm thử toàn bộ test suite (`pytest tests -q`):**
   - Lệnh: `$env:PYTHONPATH='src'; .venv\Scripts\python.exe -m pytest tests -q`
   - Kết quả: **`734 passed, 2 warnings in 280.84s`**, **`exit_code = 0`**.
   - Ghi chú nhỏ cho `REPRODUCE.md`: bình luận trong `docs/REPRODUCE.md:32` đang ghi `# Kiểm thử toàn suite (kỳ vọng 722 passed)` (con số trước khi bổ sung các bài test của `SG-041` và `SG-052`; thực tế hiện tại là `734 passed`).
3. **Kiểm tra registry final runs (`scripts/run_final.py --only registry`):**
   - Lệnh: `$env:PYTHONPATH='src'; .venv\Scripts\python.exe scripts/run_final.py --only registry`
   - Kết quả: `track_A_runs: 7`, **`exit_code = 0`**. Đối chiếu `track_A_runs` với bản niêm phong gốc khớp 100% bit-identical; sau khi kiểm chứng đã khôi phục timestamp gốc của tệp báo cáo.
4. **Tái lập thống kê paired bootstrap (`scripts/run_statistics.py`):**
   - Lệnh: `$env:PYTHONPATH='src'; .venv\Scripts\python.exe scripts/run_statistics.py`
   - Kết quả: `comparisons: 24, packets: 24, elapsed_s: 54.9`, **`exit_code = 0`**. Đối chiếu toàn bộ 24 hàng `comparisons` trong `statistics.json` khớp 100% bit-identical; sau khi kiểm chứng đã khôi phục timestamp gốc của tệp báo cáo.
5. **Chạy kịch bản demo 5 phút offline (`scripts/run_demo.ps1`):**
   - Lệnh: `powershell -ExecutionPolicy Bypass -File scripts/run_demo.ps1`
   - Kết quả: `[1/4] Python 3.12.14` $\rightarrow$ `[2/4] verify_release PASS (33 files)` $\rightarrow$ `[3/4] offline smoke: 13/13 PASS` $\rightarrow$ `[4/4] DEMO OK`, **`exit_code = 0`**.
