# DEMO_SCRIPT — Kịch bản demo 5 phút chạy offline (SG-038)

**Điều kiện tiên quyết:** đã cài môi trường `scholargraph` (`.venv`), dữ liệu frozen đã có (SciFact corpus, OpenAlex core, graph masked, dense indexes). Toàn bộ demo **không cần mạng** — model bge-base chạy từ cache local, UI không tham chiếu CDN, không có synthetic substitution.

Chạy từ thư mục `scholargraph` trong repo (Git Bash):

```bash
export PYTHONPATH=src
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ./.venv/Scripts/python.exe -m uvicorn scholargraph.api.app:app --port 8080
```

Mở `http://127.0.0.1:8080` trong trình duyệt.

## Phút 0–1: Tìm kiếm 3 phương thức

Dùng tập 5 query đã pin trong `configs/demo.json` (đã được kiểm chứng 2 lần độc lập ở SG-036); demo trực tiếp 3 query dưới đây:

1. `diabetes treatment options` — **BM25** → chú ý điểm BM25 (thang ~10) và method ID trên mỗi card.
2. `cancer immunotherapy` — **Hybrid RRF** → điểm RRF (thang ~0,03 — khác thang BM25, giải thích khi demo).
3. `insulin resistance obesity` — **Dense** → điểm cosine 0–1.

**Điểm nhấn trung thực:** thang điểm khác nhau giữa các method được ghi `method` ngay trên card; metadata thiếu (năm/DOI với corpus SciFact) hiển thị "không có", không bịa.

## Phút 1–2: Chi tiết + gợi ý liên quan

- Bấm tiêu đề kết quả đầu của query 3 (`beir:scifact:195352`) → chi tiết title/abstract; năm/DOI hiển thị "không có" (SciFact frozen không có metadata này — policy null).
- Mục "Tài liệu liên quan": 5 gợi ý cosine loại chính nó (self-exclusion đã test).

## Phút 2–3: Đồ thị trích dẫn

- Mở `http://127.0.0.1:8080/graph` (mode **evaluated** — chỉ cạnh observed sau masking, KHÔNG chứa cạnh held-out).
- Nhập node hub demo: `openalex:W1678356000` (Gradient boosting, 2001) → thấy neighborhood 5.341 node vượt cap=30, UI hiện thông báo cắt + 30 node bậc cao nhất; legend phân biệt **cites/cited-by**.
- Nhập node isolated: `openalex:W1003264260` (Preface) → fallback "không có láng giềng" hiển thị rõ, không vẽ trống im lặng.

## Phút 3–4: Xuất tham khảo (missing policy)

```bash
./.venv/Scripts/python.exe scripts/export_references.py \
  --doc-ids beir:scifact:195352 beir:scifact:32909242 openalex:W1678356000 openalex:W1003264260 \
  --output artifacts/reports/demo_references.json
```

- Chỉ ra: 2 bản ghi OpenAlex có DOI + URL thật; 2 bản ghi SciFact **không có năm/DOI** → structured field là `null`, citation line dùng `[không có]` — **không bịa author/citation**.
- Đếm trong file: `counts` ghi rõ `with_doi=2, missing_doi=2, missing_year=2`.

## Phút 4–5: Chứng minh offline + số liệu thật

```bash
./.venv/Scripts/python.exe scripts/offline_smoke.py
```

- Kết quả kỳ vọng: **13/13 PASS** (`artifacts/reports/offline_smoke.md`) với `HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1` — chứng minh không request mạng nào (model từ cache, UI không CDN).
- Mọi số liệu trong demo truy ngược về run/manifest có hash (snapshot pins trong `configs/demo.json`).

## Lưu ý khi thuyết trình

- "Evaluated mode" của graph = G_mask (26.186 cạnh sau mask) — không chứa cạnh held-out; đây là bằng chứng chống leakage (ADR-016, GRAPH_PROTOCOL).
- Snapshot date/ID hiển thị trên UI lấy từ manifest, không hard-code.
- Nếu bị hỏi "tại sao SciFact không có năm?": corpus BEIR gốc không mang metadata này — chính sách dự án là hiển thị thiếu thay vì bịa.
