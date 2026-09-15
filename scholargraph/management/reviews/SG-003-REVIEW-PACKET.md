# SG-003 — Gói đầu vào cho review riêng

Ngày: 2026-09-15. Worker: SESSION-20260915-006, lane R + coordinator.
Trạng thái: READY_FOR_REVIEW. Đây là packet của worker, không phải review report/PASS.

## 1. Snapshot và phạm vi

Worker đã dừng sửa hai artifact sau. SHA-256 tính trên byte của file local; nếu checkout đổi CRLF/LF, đối chiếu nội dung với Git commit bàn giao và ghi rõ normalization trước review.

| Artifact | SHA-256 |
|---|---|
| [RELATED_WORK.md](../../docs/RELATED_WORK.md) | `97470E8EF2C313423E97F7F0BE0214745458B2972F1C165E909A8296EAC2481A` |
| [references.bib](../../docs/references.bib) | `BE4592972DEA6C3563F7998FAB2152812B2D9CB38411D49862FDF4FADDCCE408` |

Đầu vào khác: [task card](../../docs/TASKS.md), [scope](../../docs/SCOPE.md), [protocol](../../docs/RESEARCH_PROTOCOL.md), [decisions](../DECISIONS.md), [routing](../model_routing.json), [log worker](../logs/SESSION-20260915-006.md).

Output reviewer được giao: `management/reviews/SG-003-REVIEW-20260915.md`. Chưa có file này hoặc reviewer/session riêng tại thời điểm tạo packet. Reviewer chỉ ghi report của mình; coordinator tích hợp findings và đổi board sau đó.

## 2. Việc worker đã làm

- 12 nguồn với citation keys duy nhất; BM25, RRF, PPR, SPECTER/SciNCL/SPECTER2, BEIR/SciFact, CiteRank/rescaled PageRank, multilingual E5 và TextTAGC 2026.
- Phân biệt đóng góp tích hợp/thực nghiệm với novelty thuật toán; đề xuất cho bốn RQ chưa thay protocol.
- Ví dụ RRF/PPR và citation proxy; kế hoạch đọc sâu RRF, SciRepEval, time-balanced centrality cho cả hai người.
- Chỉ dựa abstract/metadata nhà xuất bản cho TextTAGC. Không claim full-text review hoặc so sánh score của ScholarGraph với bài.

## 3. Các điểm reviewer phải kiểm tra

1. Metadata BibTeX đúng tác giả/năm/venue; CiteRank 2007 khác preprint 2006; TextTAGC là 2026 dù DOI chứa 2025.
2. RW02: công thức RRF, quy ước rank và ví dụ số; k=60 không bị coi là optimum phổ quát.
3. RW03: alpha trong công thức dự án là follow probability; không gán query-seeded implementation cho đúng thuật toán topic vectors của nguồn.
4. RW04–06: citation pretraining khác inference graph; proximity khác ad-hoc search; pretrained overlap vẫn mở tại SG-011/017.
5. RW09–10: age prior khác score rescaling; nguồn rescaling dùng publication-order window; không gán phát hiện significance thành relevance cho query.
6. RW12: các claim chỉ ở mức abstract đã đọc; hạn chế full-text thể hiện đúng. Bằng chứng tiền lệ có đủ để ngăn claim novelty quá rộng không?
7. Đề xuất RQ không đổi scope/baselines hoặc mở SG-004 trước dependency; masked graph và ba tuyến A/B/C vẫn nhất quán.
8. Không có claim hai thành viên đã đọc. Task card yêu cầu hoạt động này dù routing không cần một human approval riêng.

## 4. Self-check đã thực hiện và giới hạn

- Kiểm tra PowerShell: 12 entries có key duy nhất, author/title/year/url, ánh xạ đủ 12 dòng ma trận và số ngoặc cân bằng; phép tính RRF khớp 0,03068/0,03200.
- Đây là kiểm tra cấu trúc, chưa compile bằng BibTeX: runtime không có bibtex/pandoc/pybtex/bibtexparser. Chưa cần cài thêm để viết tổng quan Markdown.
- Project checker kiểm tra đường dẫn/registry; không xác minh nội dung khoa học. Kết quả cuối ghi trong log.
- Chưa chạy lại benchmark/GPU hoặc test ứng dụng vì không thay mã ứng dụng/dữ liệu thí nghiệm.
- Fresh-context review chưa thực hiện. Hoạt động đọc của hai thành viên chưa xác nhận.

## 5. Lệnh giao review ở một phiên riêng

```text
Review task SG-003 của ScholarGraph tại D:/Web_mining_20261/scholargraph.
Đọc AGENTS.md và management/reviews/SG-003-REVIEW-PACKET.md.
Vai trò reviewer lane V; xác minh snapshot của docs/RELATED_WORK.md và docs/references.bib.
Đối chiếu primary sources, acceptance và protocol; đặc biệt novelty, citation proxy,
RRF/PPR và các khác biệt giữa freshness, age normalization, relevance, significance.
Chỉ ghi management/reviews/SG-003-REVIEW-20260915.md với verdict và findings có nguồn.
Không sửa hai artifact hoặc shared board. Ghi riêng việc hai thành viên đọc paper còn pending.
```

## 6. Sau review

Coordinator xử lý findings; nếu artifact đổi thì cập nhật snapshot và re-review phần ảnh hưởng. Nhận ghi chú đọc từ hai thành viên theo bảng §7 của RELATED_WORK. Chỉ sau khi phần việc task card và gate review hoàn tất mới chuyển SG-003 DONE, mở SG-004. Một PASS AI review không xác nhận thay việc con người đã đọc.
