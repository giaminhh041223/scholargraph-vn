# PHASEB-POLICY-107 — Review chính sách nguồn phaseB (file-only)

Verdict: CHANGES_REQUIRED — policy đủ cho pilot bounded, implementation NOT_RUN chưa review.
Execution: NOT_RUN. File-only, không bash/terminal, không mạng/subagent, không sửa implementation/board. Implementation parent đang viết dở, không review code mutable.

## Evidence đã kiểm (parent)
- `configs/public_site_joss.json`: origin `https://joss.theoj.org`, seed `/papers/published.html`, UA `ScholarGraphPublicCrawler/1.0`, `min_interval 3.0s`, `max_pages 5/max_papers 3/depth 1`, `max_body 1048576`, `parser joss-citation-1.0.0`.
- `data/public_search/phase_b/policy-107/manifest.json`: 5 resource status 200, có sha/raw/retrieved_at.
- `.../joss-robots.txt`: 1 dòng comment, không Disallow — cho phép nhưng vẫn phải đọc live mỗi run.
- `.../joss-list.txt:218-222,636-638`: 20 card/trang, tổng 3733, link canonical `/papers/10.21105/joss.<digits>`, phân trang `?page=2`.
- `.../joss-paper.txt:113-124,257-260`: đủ `citation_title/author/date/journal/doi/pdf_url`, DOI `10.21105/joss.09260` khớp landing, license CC BY 4.0.
- `.../joss-about.txt:196-306,660`: scope/submission, CC BY 4.0 public content, ISSN 2475-9066.
- `.../crossref-policy.txt:1,285`: REST public/polite/Metadata Plus, khuyến nghị mailto, rate-limit theo header.
- `docs/PUBLIC_PAPER_SEARCH_TASKS.md EXT-09/10`: DEFERRED, exact-DOI, allowlist/robots/rate/resume, cấm quét toàn web.
- `management/public_search/dispatch/GEMINI-EXT10-107.txt`: bound chặt URL/DNS/redirect/body/robots/checkpoint/CLI1.

## Ràng buộc thực tế
- JOSS: robots comment-only không miễn trừ; seed exact, depth1, quota nhỏ, sequential concurrency1, interval 3s (chặt hơn 1req/s). PDF embed trỏ `www.theoj.org` — chỉ ghi metadata, cấm fetch foreign.
- Crossref: sidecar exact-DOI, giữ gốc, public anonymous được nhưng quota thấp; giữ <=1req/s/concurrency1, nên dùng polite mailto. Không cần human labels.
- About: tôn trọng CC BY 4.0, provenance rõ, không claim toàn web.

## Gaps / việc cần làm
1. GEMINI phải giao `site_crawler.py/crawl_public.py/test/doc/packet` đúng allow paths, schema strict không `.get` mặc định, landing DOI phải khớp citation DOI, singleton mâu thuẫn FAIL.
2. Bắt buộc negative tmp-path: missing/malformed/title-only/mismatch/leakage keys/URL cấm/redirect/DNS riêng/robots denied/oversize/quota/duplicate/resume dở/complete integrity + subprocess CLI exit1; bodycap/DNS/resume/URL/robots phải có test riêng.
3. Coordinator chạy pytest + pilot live sau; không bịa PASS.
