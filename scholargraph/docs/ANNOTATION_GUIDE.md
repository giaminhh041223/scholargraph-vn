# ANNOTATION_GUIDE — Hướng dẫn gán nhãn liên quan cho query Việt (SG-031)

**Trạng thái:** bản kèm manifest nháp `data/annotations/vn_query_manifest.json` (`status=draft_pending_human_approval`). Guide và manifest chỉ có hiệu lực sau khi người phụ trách duyệt/sửa và ghi nhận phê duyệt vào manifest (`provenance.human_approval`) + log phiên.

## 1. Phạm vi

- 30 query tiếng Việt (10 dev / 20 test) cho **pilot nội bộ nhỏ** theo Protocol v1: đánh giá truy hồi cross-lingual (query tiếng Việt → corpus tiếng Anh SciFact/SCIDOCS + OpenAlex core).
- 5 query dev đầu (có `annotation_pilot=true`) dùng để **tập huấn gán nhãn** trước khi vào test.
- Pool nhãn sinh ở SG-033 từ các phương pháp `translated_bm25`, `multilingual_dense`, `vn_hybrid_rrf` (depth 10, seed 20260915, provenance bị che khi chấm).

## 2. Rubric liên quan 0/1/2

| Nhãn | Ý nghĩa | Tiêu chí |
|---|---|---|
| **0 — irrelevant** | Không liên quan | Tài liệu không chứa thông tin trả lời bất kỳ phần nào của nhu cầu tin; hoặc chỉ trùng từ khóa bề mặt. |
| **1 — partially_relevant** | Liên quan một phần | Trả lời được một khía cạnh của nhu cầu tin, hoặc cùng chủ đề nhưng khác khía cạnh/quy mô nghiên cứu (vd: query hỏi RCT trên người lớn, tài liệu là nghiên cứu trên động vật cùng cơ chế). |
| **2 — directly_relevant** | Liên quan trực tiếp | Trả lời trực tiếp toàn bộ nhu cầu tin với thiết kế/kết quả phù hợp (nghiên cứu gốc, tổng quan có định lượng, hoặc dữ liệu trực tiếp về câu hỏi). |

**Ví dụ** (query: *"Bổ sung vitamin D có giúp ngăn ngừa gãy xương ở người cao tuổi không?"*):
- **2:** RCT/ meta-analysis về bổ sung vitamin D (± canxi) và tỷ lệ gãy xương ở người ≥60 tuổi.
- **1:** Nghiên cứu quan sát về mật độ xương (BMD) ở người cao tuổi dùng vitamin D (kết quả trung gian, không trực tiếp là gãy xương).
- **0:** Nghiên cứu vitamin D về miễn dịch/ung thư; hoặc gãy xương do chấn thương thể thao ở thanh niên.

**Ví dụ** (query: *"Chỉ số h có hạn chế gì khi đánh giá nhà nghiên cứu?"*):
- **2:** Bài phân pháp/bình luận phân tích hạn chế của h-index (thiên vị sự nghiệp, lĩnh vực, self-citation...).
- **1:** Bài đề xuất chỉ số thay thế có so sánh với h-index nhưng không phân tích hạn chế làm chính.
- **0:** Bài dùng h-index như một biến đo lường không bàn về hạn chế.

## 3. Quy tắc chung

1. **Ngôn ngữ:** corpus tiếng Anh, query tiếng Việt — đánh giá trên **nội dung khoa học**, không trừ điểm vì khác ngôn ngữ. Bản dịch máy của tài liệu có thể dùng để hỗ trợ hiểu, ghi rõ nếu dùng.
2. **Thiếu thông tin:** nếu tài liệu không đủ nội dung để kết luận (chỉ có tiêu đề, abstract rỗng) → nhãn `unjudged` (không 0, không 1/2) kèm lý do.
3. **Metadata thiếu** (năm/DOI/venue trống) **không** ảnh hưởng nhãn liên quan.
4. **Không dùng qrels/quyết định của hệ thống làm căn cứ** — chỉ đọc tài liệu và nhu cầu tin.
5. Mỗi cặp (query, doc) do **2 người gán nhãn độc lập** trước khi thảo luận; `linearly_weighted_cohen_kappa` tính trước adjudication (protocol: weights `1-|a-b|/2`).
6. Tranh chấp sau thảo luận: điều giải (adjudication) do 2 người cùng chốt; nếu bất đồng không giải quyết được → `unjudged` + ghi chú, không ép nhãn.

## 4. Quy trình 5 bước

1. **Tập huấn:** 2 người cùng chấm 5 query pilot (10–15 cặp đầu), đối chiếu cách hiểu rubric, chốt ví dụ ranh giới.
2. **Gán nhãn độc lập** trên pool đã xáo trộn (seed 20260915, provenance hệ thống bị che).
3. **Tính agreement** (kappa + raw agreement + confusion matrix) trước bất kỳ buổi thảo luận nào.
4. **Adjudication** các cặp lệch nhãn ≥1 mức; giữ nguyên nhãn gốc trong file (`original_labels_preserved=true`).
5. **Khoá nhãn:** ghi `vn_labels.jsonl` (format do SG-033 phát hành), hash file, không sửa sau freeze.

## 5. Format nhãn (SG-033 sẽ phát hành công cụ)

```jsonl
{"query_id": "vn:test:001", "doc_id": "...", "label": 2, "annotator": "A|B", "round": "independent|adjudicated", "note": null}
```

- `label`: 0/1/2 hoặc `"unjudged"`.
- Không ghi thông tin hệ thống sinh candidate vào dòng nhãn (blinding).

## 6. Điều đã chốt từ protocol (trích)

- `annotators_per_pair`: 2; `judgment_upper_bound`: 1800; pool depth 10; deduplicate.
- `reduction_policy`: uniform trước khi chấm test, có ADR nếu cắt.
- Kappa báo cáo: pair_count, raw_agreement, confusion_matrix; kappa không xác định nếu phân phối thoái hoá — ghi `undefined`.

## 7. Việc còn lại trước khi guide có hiệu lực

1. Người phụ trách duyệt/sửa manifest 30 query (đặc biệt: đổi query không tự nhiên, tách/gộp intent family).
2. Ghi phê duyệt vào `provenance.human_approval` + log phiên.
3. Sau duyệt: SG-032 pin translation + multilingual encoder; SG-033 sinh pool và công cụ chấm — **dừng chờ 2 người gán nhãn thật**.
