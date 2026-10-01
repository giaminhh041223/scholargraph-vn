# Phiên 096 — EXT-06 pilot và gia cố verifier

- User xác nhận 5 query đã đề xuất; yêu cầu tiếp tục đến hết phạm vi extension.
- Kế thừa MUSE runner failure W4; coordinator và SOL helper viết tests/evidence, ghi rõ actual authors.
- Hai production bug được sửa và có regression: OpenAlex abstract chứa từ `labels` (`cca7021`); CLI redirect Windows phải UTF-8 (`f957242`). Các harness lỗi trước fix vẫn được giữ.
- Regression thực tế session 82695: **523 passed**, 2 dependency warnings, exit 0, 153.00s. Có offline API/UI/graph/export trên dữ liệu frozen thật.
- Live 5 query hai nguồn + 1 retry: 6 partial failures, 4 timeout arXiv + 2 quota; OpenAlex thành công. Explicit OpenAlex 5 refresh + 5 cache exit 0; API lưu lặp 10 lần thành 5 entries, xuất JSON/BibTeX 200.
- `verify_release.check_freeze()` kiểm 33 pinned files khớp freeze SHA `34159fb133594633530c08390b259ea6efd7e024a384cb2c25092bf6e4797557`.
- Fresh SOL pre-review tìm silent bypass {} / null freeze, split IDs khuyết thiếu, acceptance không evidence và output overwrite protected freeze. Coordinator sửa; worker chỉ bổ sung negative tests. Pre-review probes giữ ở `.tmp/review-ext06-096/`.
- Verifier hiện kiểm mandatory sections/hash, nonempty/unique/count/overlap split, hashed test reports, rederive pilot từ strict envelopes và UTF-8/cp1252 bytes, CLI/status/count/P95/median/n; output không được trùng input hoặc ngoài project. Argparse lỗi exit 1.
- Evidence gate và operational gate được tách rõ qua [decision](../reviews/COORDINATOR/EXT-06-EVIDENCE-DECISION-096.md). Actual validator run 097: evidence PASS, operational FAIL, CLI **1**. Chưa tuyên bố MVP hai nguồn hoàn tất.
- Tiếp theo: pin test/schema sau helper kết thúc; fresh SOL re-review exact commit và artifacts. Sau acceptance evidence mới mở ba audit W5 rồi tài liệu W6. Human demo và arXiv giữ gate release PENDING.
