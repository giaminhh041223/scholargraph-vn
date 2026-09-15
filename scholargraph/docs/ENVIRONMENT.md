# Hướng dẫn Môi trường và Cài đặt — ScholarGraph VN

Tài liệu thiết lập môi trường phát triển và kiểm thử cho dự án **ScholarGraph VN** (thực hiện tại task [SG-005](TASKS.md#sg-005)).

---

## 1. Yêu cầu Hệ thống và Runtime

* **Hệ điều hành**: Windows (PowerShell 5.1+ hoặc PowerShell Core 7+), Linux, macOS.
* **Python Runtime**: Python 3.10 đến Python 3.13 (máy hiện tại đã xác minh cài đặt **Python 3.13.0**).
* **Bộ quản lý mã nguồn**: Git 2.40+ (đã xác minh cài đặt tại `C:\Program Files\Git\cmd\git.exe`).

---

## 2. Thiết lập Môi trường ảo (Virtual Environment)

Khuyến nghị luôn sử dụng môi trường ảo độc lập trong thư mục `scholargraph/.venv` để không xung đột với các thư viện cũ của E-COMASPECT:

```powershell
# Di chuyển vào thư mục scholargraph
cd d:\Web_mining_20261\scholargraph

# Tạo môi trường ảo .venv
python -m venv .venv

# Kích hoạt môi trường ảo trên Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

*(Lưu ý: Nếu gặp lỗi Execution Policy trên PowerShell, chạy `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` trước khi kích hoạt).*

---

## 3. Cài đặt Thư viện Phụ thuộc (Dependencies)

### A. Cài đặt cho chạy thực thi cơ bản (Core CPU Runtime):
```powershell
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```
Hoặc cài đặt dưới dạng editable package:
```powershell
pip install -e .
```

### B. Cài đặt bổ sung cho kiểm thử và phát triển (Dev & Testing):
```powershell
pip install -r requirements-dev.txt
# hoặc
pip install -e ".[dev]"
```

### Danh mục thư viện cốt lõi:
* **Mô hình dữ liệu & API**: `pydantic>=2.0.0`, `fastapi>=0.110.0`, `uvicorn>=0.28.0`, `jinja2>=3.1.0`.
* **Xử lý số liệu & Đồ thị**: `numpy>=1.26.0`, `scipy>=1.12.0`, `networkx>=3.0`.
* **Truy xuất thông tin (IR)**: `rank-bm25>=0.2.2`.
* **Thu thập & tiện ích mạng**: `httpx>=0.27.0`, `tqdm>=4.66.0`.
* **Kiểm thử tự động**: `pytest>=8.0.0`, `pytest-cov>=4.1.0`.

---

## 4. Lựa chọn Công nghệ Frontend Web Demo

Theo quyết định kỹ thuật tại [ARCHITECTURE.md](ARCHITECTURE.md#1-lựa-chọn-kỹ-thuật-ban-đầu):
* **Kiến trúc**: **FastAPI + Jinja2 Templates + CSS / Vanilla JS**.
* **Trực quan hóa đồ thị trích dẫn**: Sử dụng thư viện JavaScript nhẹ **Cytoscape.js** (hoặc Vis-network) được nhúng sẵn dưới dạng static assets trong `ui/static/vendor/`.
* **Ưu điểm**:
  * Chạy **offline 100%** không cần kết nối Internet khi trình diễn demo.
  * Không phụ thuộc vào môi trường Node.js / npm phức tạp.
  * Trọng lượng siêu nhẹ, nạp nhanh, phục vụ trực tiếp từ chính backend Python.

---

## 5. Phân định Ranh giới Tính toán (Compute Boundary)

1. **Máy Cục bộ (Local CPU)**:
   * Thu thập metadata OpenAlex / BEIR, kiểm tra chất lượng dữ liệu (Data Quality Audit).
   * Lập chỉ mục từ vựng (BM25, TF-IDF).
   * Tính toán PageRank toàn cục và Personalized PageRank (PPR) trên đồ thị snapshot 10.000 – 20.000 tài liệu.
   * Tính toán các chỉ số đánh giá (Evaluator: nDCG@10, Recall@100, MRR).
   * Chạy máy chủ Web Demo cục bộ (`uvicorn scholargraph.api:app`).
2. **Điện toán Đám mây miễn phí (Google Colab / Kaggle GPU)**:
   * Sử dụng GPU T4 / P100 miễn phí cho tác vụ nặng duy nhất: **Mã hóa Batch Text Embeddings** cho tập dữ liệu.
   * Quá trình mã hóa chia thành các shard 1.000 – 5.000 bài báo có lưu checkpoint/manifest.
   * Các file vector hoàn tất được tải về đặt trong `scholargraph/artifacts/indexes/`.

---

## 6. Chạy Kiểm thử (Testing)

Từ thư mục `scholargraph/`:
```powershell
# Chạy toàn bộ unit tests
python -m pytest tests

# Chạy kiểm tra tính nhất quán toàn bộ dự án
.\scripts\check_project.ps1
```

---

## 7. Quản lý Phiên bản Mã nguồn (Git)

* Kho mã nguồn Git được khởi tạo tại thư mục gốc workspace `d:/Web_mining_20261`.
* Cấu hình file `.gitignore` đảm bảo:
  * Không commit các file nhị phân lớn từ dự án cũ E-COMASPECT (như `*.pt` 541MB, các file bài giảng PDF).
  * Không commit dữ liệu thô tải về (`data/raw/`), embeddings lớn (`artifacts/indexes/`) hay môi trường ảo (`.venv/`).
  * Giữ cấu trúc thư mục bằng các file `.gitkeep`.
