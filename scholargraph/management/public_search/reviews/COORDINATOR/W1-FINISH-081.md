# Gate W1 — PASS

EXT-02 OpenAlex, EXT-03 arXiv và EXT-04A SQLite/cache/library/export đã review độc lập, sửa findings và nhập nhánh chính. [Manifest W1](../../W1-FREEZE-081.json) khóa bytes cuối, input W0 vẫn khớp 14/14 pin.

## Kiểm chứng cuối

Parent suite thực chạy: **362 passed, 0 failed, exit0, 36.52s**. Gồm 111 contract/transport, 106 OpenAlex, 70 arXiv, 44 storage/export và 31 controller. Lệnh: Python .venv `-m pytest` bảy file `tests/unit/test_public_{contracts,transport,openalex,arxiv,store,export,worker_control}.py -q -p no:cacheprovider`, PYTHONPATH parent src. Evidence local `data/public_search/control/w1-081/parent-w1-final-r4.log`.

- OpenAlex: [MUSE review PASS](../MUSE/EXT-02-W1-081.md).
- arXiv: [SOL R5 PASS](../SOL/EXT-03-W1-R5-081.md), 14 independent cases, secret redaction/diagnosis/ports/root/encoding/provenance đã kiểm. Parent chỉ cleanup khoảng trắng năm dòng trống sau nhập, final suite chạy đúng bytes đó.
- Storage: [Gemini R2](../GEMINI/EXT-04A-W1-R2-081.md) và [SOL R4](../SOL/EXT-04A-W1-R4-081.md). Final gate có controlled metadata/close probe qua subprocess; R4 chờ metadata hoàn tất trước đóng connection. Close/evidence fault CLI1 đã kiểm riêng.
- Controller: [quyền ghi](MUSE-PERMISSIONS-081.md), path relative scope và denied-action FAIL được kiểm bằng temp/subprocess CLI1.

## Lịch sử lỗi giữ nguyên

First combined R3 suite crash Windows access violation `-1073741819`, log `parent-w1-final.log`; không có final count hợp lệ. R4 dùng chung RLock cho toàn public operations và nested calls; reviewer đối chiếu 25 shared connection references nằm trong lock. Không bỏ concurrency test hoặc xóa kết quả crash.

Muse initial author timeout và hai lượt required writes denied được lưu. Controller cũ ghi process/turn PASS không chứng minh artifact thành công, đã ghi reconciliation và sửa. Gemini R4 author INTERNAL500 và R3 review eligibility host connection failures không bị đổi thành thành công. Final storage review được giao SOL context mới; không nhận đó là Gemini R3 PASS. SOL actual runtime metadata chưa xác minh; Muse free/xhigh xác minh từ read-only assistant metadata.

## Phạm vi sau W1

W1 hoàn tất lớp adapter và lưu trữ; fusion, service/routes/production CLI và UI vẫn TODO. Chưa có demo tìm kiếm toàn luồng, chưa đo live sustained quota/runtime. UTF-32 XML unsupported rõ; CLI adapter/storage hiện là kiểm boundary. RateState process-local. Crossref/HTML crawler DEFERRED. Không thay human gates core hay dùng nhãn test/core data.

Next executable: chuẩn bị dispatch W2 EXT-04B và EXT-05A trong lượt tiếp theo, đọc card/ownership và xác minh kênh Gemini trước chạy. Worker hiện idle; chưa dispatch W2 trong vòng W1 này.
