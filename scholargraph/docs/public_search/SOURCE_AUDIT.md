# Source audit — OpenAlex + arXiv (EXT-01B, MUSE)

- Task: EXT-01B; session `ses_f0fc34300ffehYtM193B3KNg56`; actual model unknown.
- Date: 2026-09-30; branch `codex/public-search-muse`, base `46328b2`, head `9f70669`.
- Live request budget used: **3** (OpenAlex x2 incl. one Retry-After-honoring retry, arXiv x1). No 429 provoked on purpose; no account created.
- Raw (immutable): `data/public_search/muse/source_pilot/` (local-only, git-ignored) + `MANIFEST.json` hashes. Headers redacted (cookie/auth/token classes). Raw files were not modified in this revision.
- Hashes (bytes, full SHA-256, match MANIFEST + meta + bytes):
  - `openalex_search.body` 253 bytes `e2853e1081387fb57084d3fbaa427c9e4dc1562c2af5ff09044420a58189aca6` (429).
  - `openalex_retry.body` 101458 bytes `8050e77aba06e90709c0ef2006647049ef8306e55f48e2e034bc538764468a0d` (200).
  - `arxiv_search.body` 4457 bytes `e38e577822f80ed9e8555322c5865e34ecc60b604a2af1bd767effa08535254c` (200).

## 1. Verified (live evidence)

### OpenAlex — usable with conditions

- Official docs live: `https://help.openalex.org/api/` (docs-only: anonymous and keyed access described per official docs; keyed behavior not probed; no account created).
- Anonymous search **observed throttled under load**: 1 request -> **429** `Retry-After: 33` (from `openalex_search.meta.json` headers `retry-after: 33`), body 253 bytes (sha256 `e2853e10...` full above): rate-limit message asking to retry or use a free key for uninterrupted access.
- Retry -> **200**, 101458 bytes (sha256 `8050e77a...` full above), 3 works. Observed first-page only: `meta.page` 1, `meta.per_page` 3, `meta.count` 976071 for the probe query, `meta.cost_usd` 0.001 (all from response body, observed). Work records observed carry id/doi/title/authorships/`abstract_inverted_index` (3/3 have `abstract_inverted_index`; 3/3 have doi).
- Retry provenance (sparse meta): `openalex_retry.meta.json` has only `status`/`elapsed_s`/`bytes`/`sha256`/`retry_after: null`/`remaining: "990"`; it has no `url`, no `headers`, no `date`. Therefore wait interval between 429 and retry, `remaining: "990"`, and any retry headers/timestamps are author-reported/unverified, not observed headers. This audit does not reconstruct the retry request URL (url missing, not rebuilt) and does not fabricate retry headers/timestamps.
- Observed first-page/filter coverage vs docs-only: observed is first page only (`page` 1, `per_page` 3, filter `fulltext.search:graph neural networks` from body `meta.x_query.url`); sustained quota, other pages, other filters, and runtime for the section-8 pilot are docs-only and sustained quota/runtime not measured.
- Prior art in-repo was read read-only for context only; this audit makes no claim about adapter auth encoding and imposes no auth gate.

### arXiv — usable

- Manual live (`info.arxiv.org/help/api/user-manual.html`): GET/POST, `search_query`/`id_list`, `start`/`max_results` paging (slices <=2000), sortBy/sortOrder, Atom 1.0 responses, errors-as-feed entries, **3-second delay between calls**.
- Terms live (`info.arxiv.org/help/api/tou.html`) — **previously unreachable in planning, reachable now**: legacy APIs <=1 request/3 s, single connection, counted across all machines under control; storing/transforming/sharing descriptive metadata allowed; discovery tools allowed; circumvention -> block.
- Live probe (single request, 4 s gap from previous call, author-reported/unverified gap timing): **200**, 4457 bytes (sha256 `e38e5778...` full above), valid Atom, 2 entries, `totalResults` 186833, entry fields observed (id/title/published/updated/summary/author/category/abstract+pdf links/arxiv extensions incl. primary_category/journal_ref).
- DOI (full payload): 0/2 records have `arxiv:doi` (both missing; both have `journal_ref` instead). Not verified; do not build DOI coverage on this probe. Counts: 2 entries, 0/2 with DOI.

## 2. Unverified (do not build on yet)

- Sustained anonymous quota and runtime for the section-8 pilot (10 queries x cache miss/hit runs): not measured; sustained quota/runtime not measured. The single `remaining: "990"` value is author-reported/unverified (no header provenance in sparse retry meta) and is not a sustained quota measurement.
- Retry wait interval, retry headers, and retry timestamps: author-reported/unverified (sparse meta has no url/headers/date).
- Observed first-page/filter coverage only (`page` 1, `per_page` 3); beyond first page is docs-only.
- EXT-01A contract / EXT-01C UX do not exist yet — nothing reviewed.
- Crossref / website crawling: phase B, untouched.
- OpenAlex keyed behavior: docs-only per official docs; not probed, no account created.

## 3. Proposed (needs coordinator/user decision)

- P1: pilot scope decision (coordinator): anonymous-only within observed first-page limits vs reduced scope; this audit imposes no account or quota gate.
- P2: 10 pilot queries need user/two-member confirmation (plan section-8).

## 4. Verdict

- arXiv: **READY** for adapter work within Terms (3 s delay, single connection).
- OpenAlex: **CONDITIONAL** — works for observed first-page, but anonymous search was throttled once (429 observed); sustained quota/runtime not measured. Not a code BLOCKED; a policy/scope decision.
- No mocked evidence used anywhere in this audit. Counts: 3 requests, 2x200 + 1x429, 0 failures to report beyond the (handled, documented) 429.