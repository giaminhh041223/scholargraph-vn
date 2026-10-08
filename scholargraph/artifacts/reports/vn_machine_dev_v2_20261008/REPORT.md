# Thử chấm bằng hai agent — dev v2

Kết quả máy thử nghiệm; không phải nhãn người hoặc kết quả SG-034.

Mỗi agent chấm 227 cặp. Phân bố: A {'0': 80, '1': 106, '2': 19, 'unjudged': 22}; B {'0': 74, '1': 113, '2': 18, 'unjudged': 22}.
Cả hai có nhãn số: 205; giống nhau 196; agreement 0.9560975609756097; kappa trọng số tuyến tính 0.9307198377830347.
Cặp có ít nhất một unjudged: 22; cả hai unjudged: 22. Tổng bất đồng mọi loại nhãn: 9.

## So với người

Chưa đo: nhãn người đã lưu thuộc v1, còn thử nghiệm này dùng v2. Không ghép hai bộ query hoặc báo độ đúng khi chưa có nhãn người cùng cặp.

## Giới hạn

Hai context chấm độc lập dùng cùng model yêu cầu gpt-6.1-sol/high; có thể cùng mắc lỗi. Độ đồng thuận không chứng minh độ đúng. Chỉ đọc title/abstract, không chấm test, không phân xử.

## Xem kết quả

[File máy A](vn2_labels_machine_A_dev.jsonl), [file máy B](vn2_labels_machine_B_dev.jsonl), [toàn bộ cặp CSV](all_pairs.csv), [cặp bất đồng CSV](disagreements.csv), [số đếm JSON](agreement.json).

## Theo query

| Query | Số cặp | Bất đồng |
|---|---:|---:|
| vn2:dev:001 | 26 | 2 |
| vn2:dev:002 | 24 | 0 |
| vn2:dev:003 | 25 | 0 |
| vn2:dev:004 | 24 | 0 |
| vn2:dev:005 | 21 | 2 |
| vn2:dev:006 | 18 | 3 |
| vn2:dev:007 | 25 | 0 |
| vn2:dev:008 | 22 | 2 |
| vn2:dev:009 | 22 | 0 |
| vn2:dev:010 | 20 | 0 |

## Chín cặp khác nhau

Có 6 cặp A=0/B=1, 1 cặp A=1/B=2 và 2 cặp A=2/B=1; không có bất đồng 0↔2. Dưới đây là quyết định nguyên bản, chưa phân xử. CSV kèm lý do đầy đủ của cả hai máy.

| Query | Bài | A | B |
|---|---|---:|---:|
| vn2:dev:001 | WebGLM: Towards an Efficient and Reliable Web-Enhanced Question-Answering System | 0 | 1 |
| vn2:dev:001 | Domain Adaptation for Conversational Query Production with the RAG Model Feedback | 0 | 1 |
| vn2:dev:005 | Synthesizing high utility suggestions for rare web search queries | 0 | 1 |
| vn2:dev:005 | Quality Over Clicks: Iterative Reinforcement Learning for Early-Stage E-Commerce Query Suggestion | 0 | 1 |
| vn2:dev:006 | A Novel Triangle Count-Based Influence Maximization Method on Social Networks | 0 | 1 |
| vn2:dev:006 | A community-based entropic method to identify influential nodes across multiple social networks | 0 | 1 |
| vn2:dev:006 | Label Propagation Algorithm Based on Random Wandering for Community Detection | 2 | 1 |
| vn2:dev:008 | A Survey on Aspect Extraction Approaches for Sentiment Analysis | 2 | 1 |
| vn2:dev:008 | Movie Recommendation Algorithm Based on Sentiment Analysis and LDA | 1 | 2 |

Hai machine raters đã dừng. Coordinator kiểm coverage/schema/hash/đếm và tái tính kappa bằng ma trận; chưa xác nhận đúng/sai semantic từ người. 7 resources được ghim trong manifest (nhãn official v1/v2, nhãn người v1 thô, pool/manifest v2 và frozen_main) giữ nguyên SHA-256.
