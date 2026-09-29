# Data Card — ScholarGraph VN (Tuyến A: BEIR SciFact & SCIDOCS)

- **Mã task:** SG-010 — Audit chất lượng dữ liệu.
- **Ngày biên soạn:** 2026-09-15 (Cập nhật chuẩn hóa: 2026-09-16).
- **Phiên bản:** 1.0.1 (Khắc phục theo review độc lập Codex F1–F5).
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
- **Bản quyền chi tiết theo thành phần dữ liệu:**
  - **SciFact:** Claims và evidence annotations thuộc giấy phép **CC BY 4.0**; corpus abstracts thuộc giấy phép **ODC-By 1.0** (theo [SciFact License](https://github.com/allenai/scifact/blob/master/LICENSE.md); Wadden et al., EMNLP 2020).
  - **SCIDOCS:** Toàn bộ dataset thuộc giấy phép **CC BY 4.0** (theo [SCIDOCS License](https://github.com/allenai/scidocs/blob/master/LICENSE); Cohan et al., ACL 2020). Người sử dụng có nghĩa vụ trích dẫn và ghi nhận tác giả (attribution), không phải CC0 public domain.
  - **BEIR Code Package:** Thuộc giấy phép mã nguồn mở **Apache-2.0** (Thakur et al., NeurIPS 2021).

### 2.2 Đóng băng và Checksums
Dữ liệu thô được tải về, kiểm tra mã băm và giải nén bất biến tại thư mục `data/raw/beir/` (đối chiếu hoàn toàn khớp với manifests nguồn):

| Dataset | Kích thước archive | Archive MD5 (Catalog) | Archive SHA-256 | Corpus SHA-256 | Queries SHA-256 | Qrels SHA-256 |
|---|---:|---|---|---|---|---|
| **SciFact** | 2.816.079 B | `5f7d1de60b170fc8027bb7898e2efca1` | `536e14446a0ba56ed1398ab1055f39fe852686ecad24a6306c80c490fa8e0165` | `dec31c8182f3d744c7d2c09423756fd1d17cbef75808db13ba01cc0aab4d1ac6` | `8ff84a7c903f722981cd8d595c022660140c51867b27608a6d4910db86080313` | `train`: `a53f2114831916c096b6c37d9e54da68cef4efdcdbd5ed46533601af972acf1d`<br>`test`: `0864bb985e0ca2367ba217977e72004d549054b2b06666ed9d4825ac7c21284c` |
| **SCIDOCS** | 142.471.588 B | `38121350fc3a4d2f48850f6aff52e4a9` | `96640201687767c9b1fcc5af7a80b90fb325b37fa25329c2586c25edcfa17ef1` | `328bb38854179c83ee40d4f49fae2ef7209ede7163785193cbdcd5906b28eecc` | `3c85b68419bd579ff52edb58f9e7b32eb3d18bc83435edb71dbb68aaf79531d6` | `test`: `dcd3d7f77417294bb6f338537f3c28d8a5ea72b30fe6633f407fa85528767e35` |

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

Được đo lường chính xác bằng tokenizer chuẩn của Giao thức v1 (`(?u)\b\w+\b` trên chuỗi casefold Unicode, không stemming, không bỏ stopword) và lưu trữ đồng bộ trong báo cáo máy đọc [artifacts/reports/beir_data_audit.json](../artifacts/reports/beir_data_audit.json):

### 4.1 SciFact (5.183 documents, 1.109 queries)
- **Document Title:** Min: 1 | Max: 42 | Mean: 13,572 ± 5,049 | Median: 13,0 | P25: 10,0 | P75: 17,0 | P90: 20,0 tokens.
- **Document Abstract (Text):** Min: 30 | Max: 1.556 | Mean: 211,753 ± 90,246 | Median: 200,0 | P25: 153,0 | P75: 258,0 | P90: 312,0 tokens.
- **Combined Text (`title + " " + abstract`):** Min: 38 | Max: 1.575 | Mean: 225,325 ± 91,692 | Median: 213,0 | P25: 166,0 | P75: 273,0 | P90: 328,0 tokens.
- **Query Text (1.109 queries):** Min: 3 | Max: 41 | Mean: 12,904 ± 5,038 | Median: 12,0 | P25: 9,0 | P75: 16,0 | P90: 20,0 tokens.

### 4.2 SCIDOCS (25.657 documents, 1.000 queries)
- **Document Title:** Min: 2 | Max: 48 | Mean: 9,950 ± 3,868 | Median: 9,0 | P25: 7,0 | P75: 12,0 | P90: 15,0 tokens.
- **Document Abstract (Text):** Min: 0 (344 docs) | Max: 1.919 | Mean: 172,230 ± 118,062 | Median: 156,0 | P25: 118,0 | P75: 202,0 | P90: 256,0 tokens.
- **Combined Text:** Min: 2 | Max: 1.923 | Mean: 182,179 ± 118,402 | Median: 166,0 | P25: 127,0 | P75: 213,0 | P90: 267,0 tokens.
- **Query Text (1.000 queries):** Min: 2 | Max: 30 | Mean: 9,976 ± 3,549 | Median: 10,0 | P25: 7,0 | P75: 12,0 | P90: 14,0 tokens.

---

## 5. Kết quả Audit Toàn vẹn & Dị thường (Integrity Audit & Anomalies)

Kết quả kiểm tra tự động chạy bởi `src/scholargraph/ingest/beir_audit.py` và kiểm chứng bởi `tests/unit/test_data_integrity.py`:

### 5.1 Tính duy nhất và Toàn vẹn tham chiếu (Referential Integrity)
- **ID Uniqueness:** 100% ID của corpus và queries là duy nhất, không trùng lặp (SciFact: 5.183 docs, 1.109 queries; SCIDOCS: 25.657 docs, 1.000 queries).
- **ID Namespacing:** Ánh xạ lossless hai chiều `beir:<dataset>:<raw_id>` ↔ `raw_id` đạt 100% chính xác trên toàn bộ 100% tài liệu và câu truy vấn.
- **Orphan IDs:** Zero (0) orphan queries, Zero (0) orphan documents trong toàn bộ qrels.
- **Duplicate / Conflicting Qrels:** Zero (0) cặp `(query-id, doc-id)` trùng lặp hoặc xung đột điểm số.

### 5.2 Dị thường 1: 344 tài liệu SCIDOCS thiếu Abstract (Empty Text Anomaly)
- **Mô tả:** Trong snapshot chính thức của BEIR SCIDOCS, có đúng **344 tài liệu** chỉ có tiêu đề (`title`), còn phần tóm tắt (`text`) là chuỗi rỗng (`""`).
- **Tác động tới Qrels (Phân rã chính xác theo nhóm tài liệu và cặp đánh giá):**
  - Toàn bộ **344 tài liệu này đều xuất hiện trong tập qrels test** của SCIDOCS (tổng cộng 466 cặp query-document đánh giá: 187 cặp nhãn 1 và 279 cặp nhãn 0).
  - **Nhóm tài liệu có nhãn dương tính (`score = 1`):** Đúng **115 tài liệu** xuất hiện trong ít nhất một cặp dương tính (tổng cộng 187 cặp query-doc nhãn 1). Trong số 115 tài liệu này, có 15 tài liệu đồng thời xuất hiện trong 17 cặp mang nhãn 0 với các query khác.
  - **Nhóm tài liệu chỉ mang nhãn không liên quan (`score = 0`):** **229 tài liệu còn lại** hoàn toàn chỉ xuất hiện với nhãn 0 (tổng cộng 262 cặp query-doc nhãn 0).
  - **Tổng hợp nhãn 0:** Tổng số cặp query-doc mang nhãn 0 trên toàn bộ 344 tài liệu là đúng **279 cặp** ($262 + 17 = 279$).
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
  - Không fine-tune không loại trừ rò rỉ khi lựa chọn cấu hình trên internal dev. Các query trùng nội dung phải được xử lý bằng split policy trước tuning; SG-010 chỉ phát hiện và báo cáo, không tự sửa split hoặc lọc benchmark.
  - Trường `query_text_exact_overlap_count` đếm số văn bản riêng biệt sau `strip + casefold`; `query_text_exact_overlap_details` liệt kê mọi cặp query train/test khớp nhau. Với snapshot này có 2 văn bản và 2 cặp.

---

## 6. Tuân thủ Giao thức Nghiên cứu (Research Protocol Compliance)

SG-010 kiểm tra dữ liệu đầu vào; các yêu cầu downstream dưới đây vẫn phải được kiểm chứng tại module tương ứng:
1. **Không lọc dữ liệu ngầm:** Auditor đọc toàn bộ corpus, không loại tài liệu thiếu abstract. Retriever phải dùng full corpus và áp dụng self-removal theo Protocol v1; auditor chưa chứng minh index/retriever thực hiện đúng điều này.
2. **Không rò rỉ nhãn:** Auditor được đọc qrels để phát hiện lỗi. Ranker không được nhận qrels; ranh giới đó cần tests của interface/ranker và split audit, không suy ra từ data audit PASS.
3. **Tính tái lập:** Lần audit đọc file local; báo cáo giữ hash đầu vào trước/sau và kiểm tra chúng không đổi. Provenance chính thức nằm ở manifests đã đối chiếu hash, không suy từ số lượng corpus hay số tài liệu thiếu abstract.

### 6.1 Contract báo cáo khi có lỗi — auditor `sg010-2.0.0`

- `schema_version=2`: mỗi component có `status`. Nếu file/split thiếu, parse lỗi hoặc dependency chưa audit được: `status=FAIL`, có `error`, số đo và nhóm số đo không khả dụng là JSON `null`. Không dùng 0 thay “chưa đo”. Split bắt buộc bị thiếu vẫn có entry FAIL trong `splits_audit`.
- Một tập quan sát rỗng có `count=0`, nhưng mean/min/max/percentiles là `null`. Query trong qrels có toàn nhãn 0 là quan sát hợp lệ với số positive bằng 0; vẫn nằm trong mẫu số thống kê `positives_per_query_stats`.
- Raw IDs phải là string không rỗng/không whitespace; query text phải là string không rỗng. Title-only và text-only được báo đúng missingness, nhưng kiểu dữ liệu sai, JSON trùng key và score ngoài 0/1/2 bị chặn. Positive self-qrel gây FAIL vì mâu thuẫn với self-removal.
- CLI trả 1 và ghi báo cáo FAIL khi dữ liệu sai/thiếu. Nếu đường dẫn output không ghi được hoặc trỏ vào raw benchmark, CLI báo `AUDIT FAILED` trên stderr, trả 1; không thể ghi report vào đường dẫn bị cấm. Auditor không ghi đè raw để lưu lỗi.
- Text overlap được báo thành anomaly; query ID collision làm FAIL. Dùng chung relevant document giữa hai split không tự nó là query leakage.

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
