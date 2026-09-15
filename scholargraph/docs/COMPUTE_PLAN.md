# Compute plan và GPU pilot — ScholarGraph VN

Phiên bản: `sg002-v1`

Ngày audit local: 2026-09-15

Task: SG-002
Trạng thái: local audit và CPU pilot đã hoàn tất; GPU cloud chưa đo.

## 1. Kết luận vận hành

- Máy local đủ cho ingestion, BM25/TF-IDF, graph 10–20K node, evaluator, API/UI và kiểm thử nhỏ nếu quản lý RAM.
- GPU NVIDIA MX550 chỉ có 2 GB VRAM. Hệ điều hành nhìn thấy GPU, nhưng Python hiện có `torch 2.12.0+cpu`; vì vậy không có bằng chứng CUDA local và không dùng máy này làm nguồn số liệu GPU chính.
- Ổ D còn nhiều dung lượng hơn ổ C; đặt environment/cache/model/data/artifact của ScholarGraph trên D. Tránh tải model lớn vào C vì dung lượng trống thấp.
- Dùng Kaggle/Colab cho batch embedding. Chỉ cân nhắc thuê GPU sau một run 1.000 văn bản thật trên free GPU và sau khi ước lượng cho model được chọn ở SG-017.
- Notebook [compute_smoke.ipynb](../notebooks/compute_smoke.ipynb) đo cùng một pipeline trên CPU hoặc CUDA và ghi [compute_pilot.json](../artifacts/reports/compute_pilot.json). Đây là compute benchmark, không phải retrieval-quality benchmark.

## 2. Số đo local đã xác minh

Các số dưới đây được quan sát trực tiếp trong phiên, có thể thay đổi theo tải máy:

| Thành phần | Giá trị quan sát | Cách hiểu |
|---|---|---|
| Hệ điều hành | Windows 11, build 26200, x64 | Local development host |
| CPU | Intel Core i7-1355U, 12 logical cores | Đủ cho pipeline CPU và graph core; phải profile thật |
| RAM | 15,69 GB tổng; khoảng 2,26 GB khả dụng lúc 11:50 | RAM free thấp do tải hiện tại; đóng ứng dụng nặng trước data/index run |
| Ổ C | khoảng 11,76 GB trống lúc đo | Không dùng làm cache model/data chính |
| Ổ D | khoảng 159,61 GB trống lúc đo | Workspace và artifacts chính |
| GPU local | NVIDIA GeForce MX550, driver 596.08 | GPU tồn tại |
| VRAM local | 2.048 MiB tổng; 1.906 MiB trống lúc đo | Chỉ phù hợp smoke nhỏ nếu có CUDA build; hiện chưa có |
| Python hệ thống | 3.13.0 | Có numpy/torch/transformers/sentence-transformers/Jupyter |
| PyTorch hệ thống | 2.12.0+cpu; `torch.cuda.is_available() == False` | Không đo GPU local bằng môi trường này |
| Python bundled | 3.12.14 | Có numpy; chưa có torch/transformers/Jupyter |
| Git HEAD trước SG-002 | `0a662acd58c6d96aed4953d48588016bb044ba80` | Commit SG-005; không phải kết quả SG-002 |

`Get-CimInstance` bị access denied trong sandbox, nên RAM/OS được lấy qua .NET; CPU lấy từ registry; GPU/VRAM lấy từ `nvidia-smi`. Python 3.13 cần quyền chạy ngoài sandbox và đã được xác minh trực tiếp. Không suy số liệu còn thiếu từ tên phần cứng.

Môi trường Python hiện có NumPy 2.4.6, trong khi SciPy phát cảnh báo tương thích yêu cầu NumPy nhỏ hơn 2.3. Đây chưa làm sai pilot embedding đã kiểm tra, nhưng phải được cô lập bằng environment khóa phiên bản ở SG-005/SG-017 trước thí nghiệm khoa học chính thức.

## 3. Kết quả CPU pilot đã chạy

Run `sg002-20260915T050847Z` đã encode đủ 1.000 văn bản fixture tổng hợp bằng CPU. Model lần đầu được tải và revision thực tế đã được lưu trong report.

| Chỉ số | Kết quả đã đo |
|---|---:|
| Model/revision | `sentence-transformers/all-MiniLM-L6-v2` / `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` |
| Device / batch / max length | CPU / 8 / 256 |
| Model load | 35,32 giây, gồm lần tải/cache đầu |
| Encode 1.000 văn bản | 21,99 giây |
| Throughput | 45,48 documents/second |
| RSS tăng trong process | 120.946.688 byte, khoảng 115,3 MiB |
| Embedding | `[1000, 384]`, float32, normalized |
| File embedding | 1.536.128 byte; checksum khớp report |
| Dự toán 10K / 20K / 50K, gồm 25% overhead | 4,58 / 9,16 / 22,90 phút |

Đây là baseline compute bằng MiniLM trên fixture tổng hợp, không phải bằng chứng chất lượng retrieval và không được dùng để cam kết tốc độ model cuối. GPU peak memory để `null` và cloud status để `not_run`, đúng với môi trường CPU-only.

## 4. Thiết kế pilot 1.000 văn bản

### Mục tiêu

Đo model load time, encode time, documents/second, batch size, embedding shape/file size, process RAM và CUDA peak memory nếu thật sự chạy trên CUDA. Sau đó ước lượng thời gian 10K/20K/50K bằng cùng pipeline.

### Cấu hình mặc định

| Trường | Giá trị | Lý do/giới hạn |
|---|---|---|
| Số văn bản | 1.000 | Task acceptance; đủ đo overhead và throughput sơ bộ |
| Model smoke | `sentence-transformers/all-MiniLM-L6-v2` | Nhẹ để kiểm tra hạ tầng; **không phải model khoa học cuối** |
| Revision request | `main`; lưu resolved commit nếu model config cung cấp | SG-017 phải pin model/revision cuối |
| Max sequence length | 256 | Phù hợp title+abstract rút gọn cho pilot; phải báo truncation về sau |
| Batch CUDA/CPU mặc định | 32 / 8 | Có thể giảm 16→8→4 khi OOM; mọi lần chạy ghi batch thật |
| Warmup | 16 văn bản | Tách khởi tạo CUDA/model khỏi throughput chính |
| Output | normalized float32 embeddings + JSON report | Kiểm tra shape, finite values, norms và SHA-256 |

Nếu chưa truyền corpus, notebook dùng fixture tổng hợp xác định trước, đánh dấu `synthetic=true`. Fixture chỉ dùng đo compute; không xuất hiện trong bảng retrieval. Khi SG-009/013 có corpus thật, đặt biến `SCHOLARGRAPH_PILOT_JSONL` tới JSONL có `title`/`abstract` và chạy lại đúng 1.000 document.

### Công thức ước lượng

Với tốc độ pilot `r` documents/second:

- thời gian thô cho `N` document: `N / r` giây;
- dự toán vận hành: `(N / r) × 1,25` để có 25% overhead cho tokenization/I/O/checkpoint;
- storage vector float32: `N × embedding_dimension × 4` byte, chưa gồm index/text/model.

Chỉ dùng phép ngoại suy cho cùng model, max length, batch/device và distribution độ dài tương đương. Không lấy tốc độ MiniLM để cam kết tốc độ SPECTER2 hoặc model SG-017.

## 5. Cách chạy

### Local CPU — kiểm tra notebook

Từ thư mục `scholargraph` với Python có Jupyter và sentence-transformers:

```powershell
$env:SCHOLARGRAPH_PROJECT_ROOT = (Get-Location).Path
$env:SCHOLARGRAPH_BATCH_SIZE = "8"
python -m jupyter nbconvert --to notebook --execute notebooks/compute_smoke.ipynb `
  --output compute_smoke.local.executed.ipynb --ExecutePreprocessor.timeout=1800
```

Local run có `device=cpu` chỉ cho baseline/thẩm định notebook; trường GPU vẫn phải là null/not_run.

Nếu môi trường có Jupyter nhưng thiếu `nbconvert`, dùng runner plain-Python của project (cùng code cells, report giống nhau):

```powershell
$env:SCHOLARGRAPH_PROJECT_ROOT = (Get-Location).Path
$env:SCHOLARGRAPH_BATCH_SIZE = "8"
python scripts/run_compute_smoke.py
```

### Google Colab

1. Upload project/notebook hoặc clone repo được cấp quyền; không đưa token/secret vào notebook.
2. Chọn `Runtime → Change runtime type → GPU`, restart rồi chạy từ đầu.
3. Xác nhận cell cấu hình in `device: cuda`; nếu là CPU thì dừng, không dùng số đo làm GPU result.
4. Chạy toàn bộ notebook. Tải về `compute_pilot.json` và embedding/checksum; cập nhật report trên project bằng coordinator.
5. Tắt GPU runtime khi xong. Colab nói rõ GPU/quota/type/runtime thay đổi và không được bảo đảm; free notebook có thể bị ngắt, nên mọi run dài phải shard/checkpoint. [Colab FAQ](https://research.google.com/colaboratory/faq.html)

### Kaggle

1. Import notebook; trong Settings chọn `Accelerator → GPU` và chờ runtime restart.
2. Bật Internet chỉ khi cần tải model và điều kiện notebook cho phép; sau đó cache/pin revision.
3. Xác nhận `device=cuda`, GPU name và VRAM trong report, rồi Run All.
4. Lưu output version và tải report/embeddings về. Tài liệu Kaggle cho biết GPU miễn phí có thể phải chờ khi bận; không ghi P100/T4 nếu report thực tế không xác nhận. [Kaggle Notebooks](https://www.kaggle.com/docs/notebooks)

## 6. Shard, resume và storage cho core

- Đơn vị shard mặc định: 1.000 document trong giai đoạn pilot; có thể tăng 2.000–5.000 sau khi biết VRAM/RAM và thời gian mỗi shard.
- Tên: `embeddings/{dataset_id}/{model_revision}/shard-00000.npy` kèm `shard-00000.json`.
- Manifest mỗi shard: doc ID đầu/cuối, count, input hash, model/tokenizer revision, max length, pooling, dtype, dimension, device/GPU, batch, started/finished, output SHA-256 và status.
- Ghi file tạm `*.partial`; chỉ rename thành output hoàn tất sau shape/finite/hash validation. Resume bỏ qua shard chỉ khi manifest `completed` và checksum khớp.
- Không ghi đè shard completed; thay model/config/data hash tạo namespace/run ID mới.
- Lưu notebook runtime trên disk tạm để encode nhanh, nhưng đồng bộ report/manifest/shard hoàn tất sang nơi bền vững trước khi phiên cloud kết thúc.
- Dự kiến embeddings float32 20K × 384 của MiniLM khoảng 30,7 MB; 20K × 768 khoảng 61,4 MB. Index, model và corpus là phần riêng, nên giữ tối thiểu 10 GB trống trên D cho core; đây là budget vận hành, không phải dung lượng đã sử dụng.

## 7. Cổng quyết định thuê GPU

Không thuê ở SG-002 nếu free GPU chạy được pilot và dự toán 20K nằm trong một phiên an toàn. Chỉ lập đề xuất thuê khi có ít nhất một trong các bằng chứng:

- không lấy được free GPU sau các lần thử được ghi thời điểm/provider;
- OOM sau khi giảm batch hợp lý và max length đúng protocol;
- dự toán cùng model SG-017 vượt cửa sổ runtime với shard/resume;
- cần lặp nhiều cấu hình đã được SG-026 phê duyệt mà free quota không đủ.

Đề xuất thuê phải ghi GPU, VRAM, đơn giá hiện hành, số giờ, storage/egress và mức trần chi phí; người dùng duyệt trước. Không dùng benchmark web thay cho pilot của chính pipeline.

## 8. Trạng thái nghiệm thu SG-002

| Hạng mục | Trạng thái hiện tại |
|---|---|
| Runtime/RAM/disk local | VERIFIED |
| GPU local/VRAM qua nvidia-smi | VERIFIED, nhưng PyTorch CPU-only |
| Notebook 1.000 mẫu + validation | VERIFIED bằng runner plain-Python, exit code 0 |
| CPU docs/second và RAM | VERIFIED — 45,48 docs/s; RSS tăng khoảng 115,3 MiB |
| Colab/Kaggle GPU name, docs/second, peak VRAM | UNVERIFIED — cần một run thật |
| Account quota | UNVERIFIED — chỉ tài khoản người dùng/runtime thực tế xác nhận được |
| Shard/resume/storage plan | DOCUMENTED |

SG-002 không được DONE chỉ từ cấu hình local. Nếu CPU run hoàn tất nhưng chưa có cloud GPU, task chuyển BLOCKED hoặc REVIEW có blocker rõ tùy kết quả; không điền số GPU từ quảng cáo/provider docs.
