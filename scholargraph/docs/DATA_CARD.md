# Data Card — ScholarGraph VN (Tuyến A: BEIR SciFact & SCIDOCS)

- **Mã task:** SG-010 — Audit chất lượng dữ liệu.
- **Ngày biên soạn:** 2026-09-15.
- **Phiên bản:** 1.0.0 (Đóng băng sau SG-009 và audit SG-010).
- **Hợp đồng nghiên cứu liên quan:** [RESEARCH_PROTOCOL.md](RESEARCH_PROTOCOL.md) (Giao thức v1), [configs/protocol_v1.json](../configs/protocol_v1.json).
- **Báo cáo máy đọc:** [artifacts/reports/beir_data_audit.json](../artifacts/reports/beir_data_audit.json).
- **Manifests nguồn:** [data/manifests/beir_scifact.json](../data/manifests/beir_scifact.json), [data/manifests/beir_scidocs.json](../data/manifests/beir_scidocs.json).

---

## 1. Tổng quan và Mục đích

Data Card này tài liệu hóa chi tiết hai tập dữ liệu benchmark thuộc **Tuyến A** (Text Benchmark IR) của dự án ScholarGraph VN: **SciFact** và **SCIDOCS**, được phân phối chính thức qua benchmark BEIR (Benchmarking Information Retrieval).

Mục đích sử dụng: Đánh giá khả năng tìm kiếm thông tin khoa học (Scientific Information Retrieval) của các phương pháp xếp hạng: Lexical (TF-IDF, BM25), Dense Retrieval (Pretrained text embeddings), và Hybrid Rank Fusion (RRF).

---

## 2. Nguồn gốc, Bản quyền và Tính toàn vẹn (Provenance & Hashes)

### 2.1 Nguồn dữ liệu
- **Đơn vị công bố:** UKP Lab, Technische Universität Darmstadt (BEIR Benchmark).
- **URL lưu trữ chính thức:**
  - SciFact: `https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip`
  - SCIDOCS: `https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scidocs.zip`
- **Bản quyền:**
  - SciFact: CC BY-SA 4.0 (Wadden et al., EMNLP 2020).
  - SCIDOCS: CC0 / Open Academic Data (Cohan et al., ACL 2020).
  - BEIR: Apache-2.0 License (Thakur et al., NeurIPS 2021).

### 2.2 Đóng băng và Checksums
Dữ liệu thô được tải về, kiểm tra mã băm và giải nén bất biến tại thư mục `data/raw/beir/`:

| Dataset | Kích thước archive | Archive MD5 (Catalog) | Archive SHA-256 | Corpus SHA-256 | Queries SHA-256 |
|---|---:|---|---|---|---|
| **SciFact** | 2.816.079 B | `5f7d1de60b170fc8027bb7898e2efca1` | `4ba436eb46ef27945d8b28cf99fe25cb4812f86236bca487ce5a21dbbc5f891a` | `dec31c8182f3d744c7d2c09423756fd1d17cbef75808db13ba01cc0aab4d1ac6` | `8ff84a7c903f722981cd8d595c022660140c51867b27608a6d4910db86080313` |
| **SCIDOCS** | 142.471.588 B | `38121350fc3a4d2f48850f6aff52e4a9` | `105faeb49e29a8a7db3005a76e7373ae4e84b8061d4791530e386866b8e8f81e` | `142aa7ce0ee0b9eeceec17e3f8be35ebba05459378120b08080ee11db9d2ba94` | `da7ad2a25528f8fbf4c86beee2ca3930a0827289ee761a29f8f2e46b0a8807d9` |

---

## 3. Quy mô và Phân bố dữ liệu (Dataset Composition)

### 3.1 Bảng tổng hợp số lượng

| Dataset | Split | Vai trò nội bộ | Số Corpus | Số Queries | Số dòng Qrels | Phân bố nhãn (Score) |
|---|---|---|---:|---:|---:|---|
| **SciFact** | `train` | Internal Dev | 5.183 | 809 | 919 | Nhãn 1: 919 (100%) |
| **SciFact** | `test` | Official Test | 5.183 | 300 | 339 | Nhãn 1: 339 (100%) |
| **SCIDOCS** | `test` | Official Test | 25.657 | 1.000 | 29.928 | Nhãn 0: 25.000 (83,53%)<br>Nhãn 1: 4.928 (16,47%) |

> **Chính sách phân chia (Split Policy - ADR-012 & Protocol v1):**
> - **SciFact:** Official `train` được chỉ định làm **Internal Dev** cho các phép thử tuning/threshold; official `test` được bảo vệ hoàn toàn cho đánh giá cuối cùng.
> - **SCIDOCS:** Chỉ có official `test`, **không có dev**. Mô hình áp dụng trực tiếp cấu hình đã chốt từ SciFact dev (zero-shot transfer) để tránh data snooping.

---

## 4. Thống kê độ dài văn bản (Lexical Length Distributions)

Được đo lường bằng chuẩn tokenizer của Giao thức v1 (`(?u)\b\w+\b` trên chuỗi casefold Unicode):

### 4.1 SciFact (5.183 documents, 1.109 queries)
- **Document Title:** Min: 1 | Max: 42 | Mean: 13,57 ± 5,05 | Median: 13 | P90: 20 tokens.
- **Document Abstract (Text):** Min: 30 | Max: 1.556 | Mean: 211,75 ± 90,25 | Median: 200 | P90: 312 tokens.
- **Combined Text (`title + " " + abstract`):** Min: 38 | Max: 1.575 | Mean: 225,33 ± 91,69 | Median: 213 | P90: 328 tokens.
- **Query Text:** Min: 4 | Max: 33 | Mean: 12,98 ± 4,38 | Median: 12 | P90: 19 tokens.

### 4.2 SCIDOCS (25.657 documents, 1.000 queries)
- **Document Title:** Min: 1 | Max: 43 | Mean: 9,38 ± 4,11 | Median: 9 | P90: 15 tokens.
- **Document Abstract (Text):** Min: 0 (344 docs) | Max: 1.189 | Mean: 173,20 ± 84,40 | Median: 164 | P90: 279 tokens.
- **Combined Text:** Min: 1 | Max: 1.199 | Mean: 182,44 ± 84,98 | Median: 173 | P90: 288 tokens.
- **Query Text:** Min: 1 | Max: 29 | Mean: 9,33 ± 3,89 | Median: 9 | P90: 15 tokens.

---

## 5. Kết quả Audit Toàn vẹn & Dị thường (Integrity Audit & Anomalies)

Kết quả kiểm tra tự động chạy bởi `src/scholargraph/ingest/beir_audit.py` và kiểm chứng bởi `tests/unit/test_data_integrity.py`:

### 5.1 Tính duy nhất và Toàn vẹn tham chiếu (Referential Integrity)
- **ID Uniqueness:** 100% ID của corpus và queries là duy nhất, không trùng lặp (SciFact: 5.183 docs, 1.109 queries; SCIDOCS: 25.657 docs, 1.000 queries).
- **ID Namespacing:** Ánh xạ lossless hai chiều `beir:<dataset>:<raw_id>` ↔ `raw_id` đạt 100% chính xác.
- **Orphan IDs:** Zero (0) orphan queries, Zero (0) orphan documents trong toàn bộ qrels.
- **Duplicate / Conflicting Qrels:** Zero (0) cặp `(query-id, doc-id)` trùng lặp hoặc xung đột điểm số.

### 5.2 Dị thường 1: 344 tài liệu SCIDOCS thiếu Abstract (Empty Text Anomaly)
- **Mô tả:** Trong snapshot chính thức của BEIR SCIDOCS, có đúng **344 tài liệu** chỉ có tiêu đề (`title`), còn phần tóm tắt (`text`) là chuỗi rỗng (`""`).
- **Tác động tới Qrels:**
  - Toàn bộ **344 tài liệu này đều xuất hiện trong tập qrels test** của SCIDOCS.
  - Trong đó, có đúng **115 tài liệu mang nhãn liên quan dương tính (`score = 1`)** đối với các câu truy vấn tương ứng.
  - 229 tài liệu còn lại mang nhãn không liên quan (`score = 0`).
- **Xử lý theo Giao thức v1:**
  - **TUYỆT ĐỐI KHÔNG LỌC BỎ:** Theo quy tắc liêm chính học thuật (Protocol v1 Section 2 & Section 3), benchmark thô phải được bảo toàn nguyên vẹn. Việc âm thầm loại bỏ 344 tài liệu này sẽ làm sai lệch không gian tìm kiếm, phóng đại điểm số một cách giả tạo và phá vỡ tính tái lập với các công trình BEIR quốc tế.
  - **Cách thức biểu diễn:** Trình nạp dữ liệu `BeirLoader` biểu diễn các tài liệu này với `title = raw_title`, `abstract = ""`. Khi đánh chỉ mục lexical/dense, văn bản đầu vào là chính tiêu đề của tài liệu.

### 5.3 Dị thường 2: Hai truy vấn trùng lặp văn bản giữa Train và Test trong SciFact (Upstream Split Leakage)
- **Mô tả:** Qua audit đối chiếu chéo (cross-split audit), phát hiện trong benchmark SciFact chính thức có **2 câu truy vấn trong tập test trùng văn bản 100% với 2 câu truy vấn trong tập train**:
  1. `Test 1292` và `Train 1291`: *"There is no association between HNF4A mutations and diabetes risks."*
     - Cùng trỏ tới tài liệu liên quan duy nhất: `56893404` (score = 1).
  2. `Test 870` và `Train 871`: *"Obesity decreases life quality."*
     - Cùng trỏ tới tài liệu liên quan duy nhất: `195689316` (score = 1).
- **Nhận định:**
  - Không gian ID truy vấn hoàn toàn phân tách (`query_id_overlap_count = 0`).
  - Sự trùng lặp văn bản này tồn tại sẵn trong dữ liệu gốc của nhóm tác giả SciFact / BEIR.
  - Vì dự án áp dụng mô hình Zero-shot / Pretrained Retrieval (không fine-tune tham số mạng nơ-ron trên train split), hiện tượng này không gây rò rỉ trọng số mô hình nhưng cần được lưu ý khi phân tích lỗi per-query.

---

## 6. Tuân thủ Giao thức Nghiên cứu (Research Protocol Compliance)

1. **Không lọc dữ liệu ngầm (No Silent Filtering):** Toàn bộ 5.183 văn bản SciFact và 25.657 văn bản SCIDOCS được đưa vào candidate universe của mọi retriever (TF-IDF, BM25, Dense, RRF).
2. **Không rò rỉ nhãn (No Label Leakage):** Qrels chỉ được cung cấp cho Evaluator để tính toán metric (nDCG@10, Recall@100, MRR@10, MAP@100, P@5). Bộ tìm kiếm (Indexers / Retrievers) hoàn toàn không được tiếp cận qrels.
3. **Tính tái lập (Reproducibility):** Mọi mã nguồn xử lý và đánh giá đọc dữ liệu offline từ snapshot đã đóng băng, không tải lại qua mạng.

---

## 7. Trích dẫn học thuật (Citations)

```bibtex
@inproceedings{thakur2021beir,
  title     = {{BEIR}: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models},
  author    = {Nandan Thakur and Nils Reimers and Andreas R{\"u}ckl{\'e} and Abhishek Srivastava and Iryna Gurevych},
  booktitle = {Thirty-fifth Conference on Neural Information Processing Systems Datasets and Benchmarks Track},
  year      = {2021}
}

@inproceedings{wadden2020fact,
  title     = {Fact or Fiction: Verifying Scientific Claims},
  author    = {David Wadden and Shanchuan Lin and Kyle Lo and Lucy Lu Wang and Madeleine van Zuylen and Arman Cohan and Hannaneh Hajishirzi},
  booktitle = {Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing (EMNLP)},
  pages     = {7534--7550},
  year      = {2020}
}

@inproceedings{cohan2020specter,
  title     = {{SPECTER}: Document-level Representation Learning using Citation-informed Transformers},
  author    = {Arman Cohan and Sergey Feldman and Iz Beltagy and Doug Downey and Daniel S. Weld},
  booktitle = {Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics (ACL)},
  pages     = {2270--2282},
  year      = {2020}
}
```
