# MAIN_FREEZE — Freeze chính trước final runs (SG-027)

**Freeze lúc:** 2026-09-19T22:22:02+07:00 — **trước khi bất kỳ run nào chạm test split.**
**Manifest máy đọc:** `configs/frozen_main.json` (32 hash + selection + git HEAD). File này là narrative; hash là nguồn sự thật.

## 1. Những gì bị khóa

| Nhóm | Nội dung |
|---|---|
| **Data** | SciFact corpus/queries/qrels (train+test), SCIDOCS corpus/queries/qrels test, OpenAlex processed (works.jsonl) + text-subset (works_text.jsonl) |
| **Splits** | SciFact dev (809/919) + test (300/339), SCIDOCS test (1000/29.928), graph split (adjacency_masked 26.186 cạnh, holdout, features) |
| **Graph** | graph_core.json manifest + G_mask + holdout + features — sản phẩm SG-016 đã review PASS |
| **Models** | dense core bge-base-en-v1.5 @ a5beb1e3 (SG-017), multilingual e5-base @ d1287505 (SG-032 pin), MiniLM fallback |
| **Configs** | protocol_v1, split_policy, tuning_space, vn_methods (translation opus-mt @ c8d2853e + cache), hybrid, ppr, age_adjustment, candidate_policy |
| **Dense indexes** | 5 index embeddings.npy (scifact/scidocs/openalex × bge; scifact/openalex × e5) |
| **Evaluator** | sg008-1.0.0 (đã nghiệm thu SG-008, đối chiếu trec_eval, max err 1.67e-16) |
| **Code** | git HEAD ghi trong freeze manifest |

## 2. Primary comparison (chốt, không đổi sau freeze)

- **Track A — SciFact dev→test:** bm25_positive_idf · tfidf_protocol · dense_bge-base · hybrid_rrf_k60
- **Track A — SCIDOCS test:** bm25_positive_idf · dense_bge-base · hybrid_rrf_k60
- **Track B — graph dev→test:** global_pagerank_control · ppr_age (gamma=0.3, lambda=0.0 — selection SG-026 đã human-approve)
- **Track C — VN (pool sau SG-033 nhãn):** translated_bm25 · multilingual_dense_e5 · vn_hybrid_rrf; original_vi_bm25 chỉ diagnostic
- **Metrics:** nDCG@10, Recall@100, MRR@10, MAP@100, P@5 (evaluator sg008-1.0.0)

## 3. Ablations (SG-029, chạy sau final runs)

1. Age adjustment: lambda=0 (best) vs lambda∈{0.01,0.03,0.1} — kiểm tra finding âm của dev
2. RRF k ∈ {30, 60, 100}
3. Graph feature variants (degree masked vs unmasked computed pre-mask — chỉ để đối chiếu leakage, không dùng làm kết quả chính)
4. Per-intent error analysis VN (30 query theo intent family)

## 4. Quy tắc sau freeze

1. Mọi thay đổi data/split/graph/model/config → **bump schema_version của freeze + ADR mới** ghi lý do; không sửa `frozen_main.json` tại chỗ.
2. **Tuning trên test bị cấm vĩnh viễn** — phân biệt sửa bug (được, có ADR + version) và tune theo test (cấm).
3. Final runs (SG-028) chạy trên đúng freeze này; run manifest phải dẫn lại `frozen_main.json` sha256.
4. Mọi kết quả published phải truy ngược được: freeze manifest → run ID → data hash.

## 5. Leakage statement

- G_mask loại H_dev ∪ H_test ∪ reverse (ADR-016); evaluated mode không chứa cạnh held-out (SG-037 review PASS).
- Track A không dùng graph; track B không dùng qrels; VN queries không sinh từ test docs (SG-031).
- Evaluator không nhận test labels làm input ranking (SG-008 + adversarial tests).
