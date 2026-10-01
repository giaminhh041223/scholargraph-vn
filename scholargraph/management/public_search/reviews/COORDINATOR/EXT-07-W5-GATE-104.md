# Gate W5 — PASS trong phạm vi đã kiểm

- Code target `66264a7`; UI audit target `6a5d4e1`, JS byte-identical tới target cuối; storage/verifier giữ nguyên từ `7726c83`. Ba audit và third-worker consistency PASS theo evidence trong board.
- Coordinator regression: 630 PASS / 0 failed, CLI0, 321.284s. 33 core freeze files giữ nguyên. Verifier W5-FINAL-104: PASS/CLI0, 7 adversarial PASS, 155 required resources. Manifest cũ được giữ nguyên; chỉ ba hash code/test thay đổi theo delta được phép, thêm bảy resources.
- MUSE native R2: 63 PASS+1 FAIL tại temp sâu Windows (raw path274chars), 57 PASS author scope. Giữ kết quả native FAIL rõ; full coordinator suite tại temp ngắn hơn có test đó PASS. Không quy native chạy630cases. Các lần lặp không cộng thànhunique.
- Verifier setup lần đầu FAIL do helper trỏ ui/public.html không tồn tại; lần sau FAIL vì command là array trong report trong khi verifier đòi string. Sửa helper/path/report serialization, giữ command_argv và reports setup/format FAIL; không sửa product hoặc đổi số đo.
- Live provenance vẫn code `ca0344d`: recovery10=5refresh+5cache hai nguồn PASS; history26=20success+6partialFAIL; readiness101 đứng riêng. Không gọi live pilot chạy trên code66264a7. P95 cache0.5674156s n5 vượt proposal500ms, refresh2.2064683s đạt15s. Không tuyên bố availability dài hạn/relevance.
- F03 OpenAlex nullable arxiv_id: alias dedup DOI-less chưa được enrich; hoãn phaseB, cần document, không implement tính năng mới. RateState process-local; dùng một tiến trình, nhiều CLI process không có shared rate coordination.
- Câu tuyệt đối như “100%/không có lỗi hồi quy/đồng thuận tuyệt đối” trong author reports chỉ được chấp nhận trong scope test/evidence đã nêu, không là bảo đảm mọi input/deployment.
- Preview đã restart target hiện tại, localhost8011; real browser knowledge graph cached hai nguồn3records/source,3hits PASS. Historical server log thêm query Ontology504 ngoài cohort; không nhập vào26canonicalruns hay suy availability từpilot. Browser tải file và human demo còn PENDING.
- EXT05A/B và07S/G/M DONE phần agent; EXT08 mở sau dependenciesDONE. Final human/merge gate PENDING; không merge master; EXT09/10DEFERRED.
