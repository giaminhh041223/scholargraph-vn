# REPRODUCE — Tái lập ScholarGraph trên máy mới (SG-041)

Máy tham chiếu: Windows 11, 12 CPU, Python 3.12.14, CPU-only (xem `docs/RELEASE_MANIFEST.md`
để biết pin đầy đủ). GPU không bắt buộc: mọi số liệu học thuật trong repo đều chạy CPU
trừ pilot T4 ở SG-002 (ghi riêng).

## 1. Chuẩn bị môi trường sạch

```powershell
cd scholargraph
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.lock
```

Kiểm tra khoá môi trường: `python scripts/verify_release.py` phải in `status: PASS`.
Lệnh này kiểm tra Python, packages, toàn bộ hash freeze (data/split/graph/model/config),
snapshot models, notebooks, CLI modules và file demo — thiếu gì báo FAIL + exit 1.

## 2. Dữ liệu và models cần có (không tải lại nếu đã đúng hash)

- Raw BEIR snapshots: `data/raw/beir/{scifact,scidocs}/` (hash trong `configs/frozen_main.json`).
- OpenAlex processed: `data/processed/openalex/works.jsonl` + `works_text.jsonl`.
- Snapshots HF trong `artifacts/cache/` (bge-base-en-v1.5, multilingual-e5-base,
  opus-mt-vi-en, MiniLM fallback). Máy offline: copy cả thư mục `artifacts/cache/`.
- Dense indexes trong `artifacts/indexes/` (90MB SciFact/SCIDOCS/OpenAlex + multilingual).

## 3. Tái chạy các mốc (đọc, không ghi đè run đã seal)

```powershell
$env:PYTHONPATH='src'
# Kiểm thử toàn suite (kỳ vọng 734 passed)
.venv\Scripts\python.exe -m pytest tests -q
# Final runs đã seal — KHÔNG chạy lại để "cải thiện số"; chỉ kiểm tra registry:
.venv\Scripts\python.exe scripts/run_final.py --only registry
# Thống kê tái lập bit-identical (cùng seed protocol 20260915):
.venv\Scripts\python.exe scripts/run_statistics.py
```

Mọi run COMPLETED không bao giờ bị ghi đè (RunStore cấp run ID mới).

## 4. Demo 5 phút offline

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_demo.ps1
```

Xem kịch bản trong `docs/DEMO_SCRIPT.md` (5 query đã kiểm chứng, export tham khảo,
graph UI). API/UI chạy local, không CDN, không gọi mạng (xem SG-038 offline smoke).

## 5. Track C (tiếng Việt) — cần nhãn người

Pool mù ở `data/annotations/vn_pool.json` (662 cặp). Hai thành viên chấm theo
`docs/ANNOTATION_GUIDE.md`, chạy `scripts/score_vn_agreement.py` TRƯỚC thảo luận,
rồi SG-034 mới chạy được. Agent không gán nhãn thay người.
