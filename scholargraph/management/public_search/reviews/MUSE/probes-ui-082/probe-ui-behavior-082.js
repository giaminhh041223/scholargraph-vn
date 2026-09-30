/**
 * REVIEWER PROBE EXT-05A W2 082 — MUSE independent, fresh context.
 * Target: D:/Web_mining_20261/scholargraph/.worktrees/public-gemini @68b2416 (READ ONLY).
 * This probe executes the REVIEWER ISOLATED COPY at tmp-diag/public_search.js
 * (SHA identical to target, labeled temporary diagnostic) under a Mock DOM.
 * It inspects ACTUAL DOM behavior, not strings.
 * Allowed write: management/public_search/reviews/MUSE/probes-ui-082/
 * No target mutation. Fixtures synthetic only.
 */
const fs = require("fs");
const path = require("path");

const TMP = __dirname + "/tmp-diag";
const UI_JS = path.join(TMP, "public_search.js");
const UX_PATH = path.join(TMP, "ux_examples.json");
const FIX_PATH = path.join(TMP, "ui_fixtures.json");
const RUNNER = path.join(TMP, "node_test_runner_patched.js");

const PublicSearchUI = require(UI_JS);
const RunnerMod = require(RUNNER);
const _origCreateMockDOM = RunnerMod.createMockDOM;
function createMockDOM() {
  const doc = _origCreateMockDOM();
  // REVIEWER-ONLY mock completion: real DOM elements have .style; author mock omits it,
  // causing btn.style.marginTop to throw. Patch instances + future createElement.
  // This patch is reviewer diagnostic only; it EXPOSES the author mock gap.
  const origCreate = doc.createElement.bind(doc);
  doc.createElement = (tag) => {
    const el = origCreate(tag);
    if (!el.style) el.style = {};
    // minimal querySelector for reviewer checks (author mock lacks it)
    if (!el.querySelector) {
      el.querySelector = (sel) => {
        const want = sel.replace(/^[.#]/, "");
        let found = null;
        (function walk(n) {
          if (found) return;
          const cls = (n.classList && n.classList.toString ? n.classList.toString() : "") + " " + (n.className || "");
          if ((sel[0] === "." && cls.split(/\s+/).includes(want)) || (sel[0] === "#" && n.id === want) || n.tagName === sel.toUpperCase()) found = n;
          n.children.forEach(walk);
        })(el);
        return found;
      };
    }
    return el;
  };
  for (const el of doc.elementsById.values()) {
    if (!el.style) el.style = {};
    if (!el.querySelector) {
      el.querySelector = (sel) => {
        const want = sel.replace(/^[.#]/, "");
        let found = null;
        (function walk(n) {
          if (found) return;
          const cls = (n.classList && n.classList.toString ? n.classList.toString() : "") + " " + (n.className || "");
          if ((sel[0] === "." && cls.split(/\s+/).includes(want)) || (sel[0] === "#" && n.id === want) || n.tagName === sel.toUpperCase()) found = n;
          n.children.forEach(walk);
        })(el);
        return found;
      };
    }
  }
  return doc;
}
const ux = JSON.parse(fs.readFileSync(UX_PATH, "utf-8"));
const fix = JSON.parse(fs.readFileSync(FIX_PATH, "utf-8"));

let PASS = 0, FAIL = 0;
function check(cond, id, detail) {
  if (cond) { PASS++; console.log(`[PASS] ${id} :: ${detail}`); }
  else { FAIL++; console.log(`[FAIL] ${id} :: ${detail}`); }
}
function textOf(el) { return el ? el.textContent : "<null>"; }

async function main() {
  console.log("=== REVIEWER PROBE EXT-05A-W2-082 DOM BEHAVIOR ===");
  console.log("UI_JS:", UI_JS);
  console.log("UX examples:", Object.keys(ux.examples).join(","));

  // --- P-PAGINATION: snapshot paging must fetch /public/results/{id} with offset/limit and show Trang X/Y ---
  {
    const ex = ux.examples.example_03_tt02_success_plus_empty_with_hit;
    const doc = createMockDOM();
    const seen = [];
    const fetchFn = async (url, opts) => {
      seen.push(String(url));
      return { ok: true, status: 200, json: async () => ex.envelope };
    };
    PublicSearchUI.init({ document: doc, fetchFn });
    PublicSearchUI.renderSearchResults(ex.envelope, false);
    const nav = doc.getElementById("snapshot-pagination");
    const info = nav ? textOf(nav) : "";
    check(!nav.hidden, "P-PAGINATION-visible", `nav.hidden=${nav.hidden} info=${JSON.stringify(info.slice(0,120))}`);
    check(!/\/public\/results\//.test(seen.join(" ")), "P-PAGINATION-no-fetch", `fetch urls seen=${JSON.stringify(seen)} (expected NO /public/results fetch because render never calls it)`);
    check(!/Trang\s+\d+\s*\/\s*\d+/.test(info), "P-PAGINATION-no-xy", `info lacks 'Trang X / Y' (actual=${JSON.stringify(info)}) — MISSING required pagination wording`);
    check(nav.children.length <= 1, "P-PAGINATION-no-controls", `nav.children=${nav.children.length} (only info span, no prev/next/offset/limit buttons)`);
    const libNav = doc.getElementById("library-pagination");
    check(libNav === null, "P-LIBPAG-mock-gap", `mock DOM omits #library-pagination (got null) while template has it — harness cannot test library paging`);
    if (libNav) check(libNav.hidden === true, "P-LIBPAG-hidden", `library-pagination stays hidden (hidden=${libNav.hidden})`);
  }

  // --- P-REFRESH-PARAM: explicit refresh=true/false in /public/search?q&sources&year&top_k&cap ---
  {
    const doc = createMockDOM();
    doc.getElementById("q").value = "graph mining";
    let urls = [];
    const mkFetch = (env) => async (url, opts) => {
      urls.push(String(url));
      return { ok: true, status: 200, json: async () => env };
    };
    const ex = ux.examples.example_03_tt02_success_plus_empty_with_hit;
    PublicSearchUI.init({ document: doc, fetchFn: mkFetch(ex.envelope) });
    await PublicSearchUI.handleSearchSubmit(false);
    const u0 = urls[urls.length - 1] || "";
    check(/refresh=false/.test(u0), "P-REFRESH-false", `search URL has refresh=false: ${u0.slice(0,160)}`);
    check(/[?&]q=/.test(u0) && /sources=/.test(u0) && /top_k=/.test(u0) && /cap_per_source=/.test(u0), "P-SEARCH-params", `q/sources/top_k/cap present: ${u0.slice(0,200)}`);
    check(!/year_from/.test(u0), "P-YEAR-absent", `year omitted when empty (correct): ${u0.slice(0,200)}`);
    // year present case
    doc.getElementById("year_from").value = "2020";
    doc.getElementById("year_to").value = "2024";
    urls = [];
    PublicSearchUI.init({ document: doc, fetchFn: mkFetch(ex.envelope) });
    await PublicSearchUI.handleSearchSubmit(true);
    const u1 = urls[urls.length - 1] || "";
    check(/refresh=true/.test(u1), "P-REFRESH-true", `refresh URL has refresh=true: ${u1.slice(0,200)}`);
    check(/year_from=2020/.test(u1) && /year_to=2024/.test(u1), "P-YEAR-present", `years forwarded: ${u1.slice(0,200)}`);
    // case preserved? URLSearchParams encodes but should not lowercase query
    check(/q=graph\+mining|q=graph%20mining/.test(u1), "P-QUERY-case", `query preserved verbatim (no lowercase): ${u1.slice(0,200)}`);
  }

  // --- P-STALE-FALSE-CLAIM: fresh snapshot after failed refresh MUST NOT claim TTL expired ---
  {
    const doc = createMockDOM();
    // success snapshot with far-future expiry (still fresh)
    const fresh = JSON.parse(JSON.stringify(ux.examples.example_03_tt02_success_plus_empty_with_hit.envelope));
    fresh.snapshot.snapshot_id = "snap_fresh_999";
    fresh.snapshot.fetched_at = "2026-09-30T08:00:00+07:00";
    fresh.snapshot.expires_at = "2099-01-01T00:00:00+07:00";
    fresh.stale = false; fresh.cached = false;
    PublicSearchUI.init({ document: doc, fetchFn: async () => ({ ok: true, status: 200, json: async () => fresh }) });
    PublicSearchUI.renderSearchResults(fresh, false);
    // now failed refresh
    doc.getElementById("q").value = "graph mining";
    PublicSearchUI.init({ document: doc, fetchFn: async () => { throw new Error("Upstream 504 Gateway Timeout"); } });
    await PublicSearchUI.handleSearchSubmit(true);
    const staleBox = doc.getElementById("stale-review-region");
    check(!staleBox.hidden, "P-STALE-offered", `stale-review offered after failed refresh (hidden=${staleBox.hidden})`);
    // dynamic button is NOT registered in mock getElementById; search subtree (also exposes author mock gap)
    function findById(root, id) {
      let found = null;
      (function walk(n) { if (found) return; if (n.id === id) { found = n; return; } n.children.forEach(walk); })(root);
      return found;
    }
    const btn = findById(staleBox, "btn-view-previous-snapshot");
    check(btn !== null, "P-STALE-btn", `previous-snapshot button present in stale subtree (author mock getElementById would return null — mock gap)`);
    // author mock gap note: direct getElementById returns null
    check(doc.getElementById("btn-view-previous-snapshot") === null, "P-STALE-mock-gap", `author mock getElementById('btn-view-previous-snapshot')=null even when button exists — Suite6 assertion would fail`);
    if (btn) {
      btn.click();
      const banner = textOf(doc.getElementById("banner-region"));
      check(/cached_stale/.test(banner) && /quá hạn TTL/.test(banner), "P-STALE-false-claim", `clicking fresh-history snapshot claims stale/TTL-expired (banner=${JSON.stringify(banner.slice(0,220))}) — FALSE when expires=2099`);
    }
  }

  // --- P-PARTIAL-SAVE: save from partial_failure must use partial snapshot id + incomplete_sources ---
  {
    const doc = createMockDOM();
    const part = ux.examples.example_06_tt05_success_plus_failed_partial_failure_with_hits;
    // first render success to set lastSuccessfulSnapshot, then partial
    const succ = ux.examples.example_03_tt02_success_plus_empty_with_hit;
    PublicSearchUI.init({ document: doc, fetchFn: async () => ({ ok: true, status: 200, json: async () => succ.envelope }) });
    PublicSearchUI.renderSearchResults(succ.envelope, false);
    const beforeSnap = succ.envelope.snapshot.snapshot_id;
    PublicSearchUI.renderSearchResults(part.envelope, false);
    // try save first hit from partial
    const hit = part.envelope.snapshot.fusion.hits[0];
    let posted = null;
    const saveFetch = async (url, opts) => {
      if (String(url) === "/public/library" && opts.method === "POST") {
        posted = JSON.parse(opts.body);
        return { ok: true, status: 200, json: async () => ({ canonical_id: hit.canonical_id, snapshot_id: posted.snapshot_id, saved_at: "2026-09-30T15:00:00+07:00", hit, incomplete_sources: true }) };
      }
      return { ok: true, status: 200, json: async () => [] };
    };
    PublicSearchUI.init({ document: doc, fetchFn: saveFetch });
    const btn = doc.createElement("button");
    await PublicSearchUI.savePaperToLibrary(hit, btn);
    check(posted !== null, "P-PARTIAL-posted", `save POST sent (posted=${JSON.stringify(posted)})`);
    if (posted) {
      check(posted.snapshot_id === beforeSnap, "P-PARTIAL-wrong-snap", `save used last SUCCESS snapshot '${posted.snapshot_id}' not partial '${part.envelope.snapshot.snapshot_id}' — partial hits CANNOT be saved with correct provenance (expected partial id, actual ${posted.snapshot_id})`);
    }
  }

  // --- P-XSS-INERT: titles/authors/error.text must be inert (no <script> in innerHTML) ---
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    const evilHit = {
      canonical_id: "evil1",
      rank: 1,
      score: 0.02,
      display: {
        title: fix.fixtures.xss_payloads.title_with_script,
        authors: [fix.fixtures.xss_payloads.author_with_svg_onload],
        authors_availability: "known",
        abstract: fix.fixtures.xss_payloads.abstract_with_img_onerror,
        publication_year: 2024, venue: null, doi: null, arxiv_id: null,
        landing_url: "https://example.org/ok",
        pdf_url: null, open_access_status: "unknown", citation_count: null,
        license: null,
      },
      source_records: [],
      source_ranks: { arxiv: 1 },
      conflicts: {},
    };
    // source_records must contain display for card? card doesn't check, just renders
    const card = PublicSearchUI.createResultCard(evilHit);
    check(card.innerHTML.indexOf("<script>") === -1, "P-XSS-title", `card.innerHTML has no <script> (innerHTML=${JSON.stringify(card.innerHTML.slice(0,80))})`);
    check(card.textContent.includes("<script>"), "P-XSS-text", `payload preserved as TEXT (textContent contains <script> literally)`);
    // error.text via banner
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ux.examples.example_06_tt05_success_plus_failed_partial_failure_with_hits.envelope, false);
    // inject evil error banner manually through addBanner path? simulate failed envelope banner with xss message
    const doc2 = createMockDOM();
    PublicSearchUI.init({ document: doc2 });
    const evilEnv = JSON.parse(JSON.stringify(ux.examples.example_06_tt05_success_plus_failed_partial_failure_with_hits.envelope));
    // force non-quota kind so message is rendered in partial_failure banner (quota path hides message)
    evilEnv.errors[0].kind = "upstream";
    evilEnv.errors[0].message = fix.fixtures.xss_payloads.error_with_tag;
    evilEnv.snapshot.source_results.forEach(s => { if (s.error) { s.error.kind = "upstream"; s.error.message = fix.fixtures.xss_payloads.error_with_tag; } });
    PublicSearchUI.renderSearchResults(evilEnv, false);
    const btxt = textOf(doc2.getElementById("banner-region"));
    const bannerEl = doc2.getElementById("banner-region");
    let hasScriptEl = false;
    (function walk(el) { if (el.tagName === "SCRIPT") hasScriptEl = true; el.children.forEach(walk); })(bannerEl);
    check(!hasScriptEl && btxt.includes("<script>"), "P-XSS-error", `error.message inert as text, no SCRIPT element (hasScript=${hasScriptEl})`);
  }

  // --- P-URL: safe vs unsafe links actually rendered ---
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    for (const u of fix.fixtures.safe_urls) {
      check(PublicSearchUI.isSafeUrl(u) === true, "P-URL-safe", `accept ${u}`);
    }
    for (const u of fix.fixtures.unsafe_urls) {
      check(PublicSearchUI.isSafeUrl(u) === false, "P-URL-unsafe", `reject ${JSON.stringify(u)}`);
    }
    // rendered anchor check: unsafe landing_url must NOT become <a>
    const mkHit = (url) => ({
      canonical_id: "u1", rank: 1, score: 0.01,
      display: { title: "T", authors: [], authors_availability: "known", abstract: null, publication_year: null, venue: null, doi: null, arxiv_id: null, landing_url: url, pdf_url: null, open_access_status: "unknown", citation_count: null, license: null },
      source_records: [], source_ranks: { arxiv: 1 }, conflicts: {},
    });
    const badCard = PublicSearchUI.createResultCard(mkHit("javascript:alert(1)"));
    let hasA = false;
    (function walk(el) { if (el.tagName === "A") hasA = true; el.children.forEach(walk); })(badCard);
    check(!hasA, "P-URL-no-anchor", `javascript: landing_url renders no <a> (hasA=${hasA}, text=${JSON.stringify(badCard.textContent.slice(0,120))})`);
    const goodCard = PublicSearchUI.createResultCard(mkHit("https://arxiv.org/abs/2401.00001"));
    let hasGoodA = false;
    (function walk(el) { if (el.tagName === "A") hasGoodA = true; el.children.forEach(walk); })(goodCard);
    check(hasGoodA, "P-URL-anchor", `https landing_url renders <a> (hasA=${hasGoodA})`);
  }

  // --- P-OA: unknown/closed/null hides PDF, open+valid shows ---
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    const mk = (oa, pdf) => ({
      canonical_id: "oa1", rank: 1, score: 0.01,
      display: { title: "T", authors: [], authors_availability: "known", abstract: null, publication_year: null, venue: null, doi: null, arxiv_id: null, landing_url: "https://example.org/p", pdf_url: pdf, open_access_status: oa, citation_count: null, license: null },
      source_records: [], source_ranks: { arxiv: 1 }, conflicts: {},
    });
    const hasPdf = (card) => { let f = false; (function w(el) { if (el.tagName === "A" && /PDF/.test(el.textContent)) f = true; el.children.forEach(w); })(card); return f; };
    check(!hasPdf(PublicSearchUI.createResultCard(mk("unknown", "https://example.org/a.pdf"))), "P-OA-unknown", "oa unknown hides PDF");
    check(!hasPdf(PublicSearchUI.createResultCard(mk("closed", "https://example.org/a.pdf"))), "P-OA-closed", "oa closed hides PDF");
    check(!hasPdf(PublicSearchUI.createResultCard(mk("open", null))), "P-OA-null", "oa open but pdf null hides PDF");
    check(!hasPdf(PublicSearchUI.createResultCard(mk("open", "javascript:alert(1)"))), "P-OA-badurl", "oa open but unsafe pdf hides PDF");
    check(hasPdf(PublicSearchUI.createResultCard(mk("open", "https://example.org/a.pdf"))), "P-OA-open", "oa open+https shows PDF");
  }

  // --- P-WIRE-SHALLOW: JS validateEnvelope must reject but currently accepts these malforms ---
  {
    const base = JSON.parse(JSON.stringify(ux.examples.example_03_tt02_success_plus_empty_with_hit.envelope));
    const cases = [
      ["extra-labels", (e) => { e.labels = [{ q: 1 }]; e.snapshot.fusion.hits[0].display.labels = [1]; return e; }, true],
      ["invalid-counts-nonzero", (e) => { e.snapshot.fusion.counts.invalid = 2; e.snapshot.fusion.counts.raw = e.snapshot.fusion.counts.valid + 2; return e; }, true],
      ["bad-score-zero", (e) => { e.snapshot.fusion.hits[0].score = 0; return e; }, true],
      ["bad-rank-zero", (e) => { e.snapshot.fusion.hits[0].rank = 0; return e; }, true],
      ["failed-with-snapshot-null-ok", (e) => ({ schema_version: 1, contract_version: "1.0.0", overall: "failed", snapshot: null, errors: [{ kind: "timeout", message: "t", source: "arxiv", retry_after_seconds: null, record_index: null }], stale: false, cached: false }), false],
      ["success-zero-hits", (e) => { e.overall = "success"; e.snapshot.overall = "success"; e.snapshot.fusion.hits = []; e.snapshot.fusion.counts.returned = 0; e.snapshot.fusion.counts.groups = 0; e.snapshot.fusion.counts.eligible = 0; e.snapshot.fusion.counts.valid = 0; e.snapshot.fusion.counts.raw = 0; return e; }, true],
    ];
    for (const [name, mut, shouldRejectButDoesNot] of cases) {
      let env = JSON.parse(JSON.stringify(base));
      env = mut(env);
      let threw = false;
      try { PublicSearchUI.validateEnvelope(env); } catch (e) { threw = true; }
      if (name === "failed-with-snapshot-null-ok") {
        check(threw === false, "P-WIRE-failed-null", `failed+snapshot null accepted (threw=${threw}) — correct per contract`);
      } else {
        check(threw === false, `P-WIRE-accept-${name}`, `JS ACCEPTS ${name} (threw=${threw}) — contract would REJECT (missing provenance/score/rank/counts/extra-field checks)`);
      }
    }
  }

  // --- P-DETAIL: provenance + conflicts rendered ---
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    const ex = ux.examples.example_01_success_dedup_rrf_and_missing_fields;
    PublicSearchUI.renderSearchResults(ex.envelope, false);
    const hit = ex.envelope.snapshot.fusion.hits[0];
    PublicSearchUI.showDetailPanel(hit);
    const body = textOf(doc.getElementById("detail-body"));
    check(/Canonical ID/.test(body), "P-DETAIL-id", `detail shows canonical_id`);
    check(/Field Provenance|Dấu vết/.test(body), "P-DETAIL-prov", `detail shows provenance header`);
    check(body.includes("raw_sha256") || body.includes("Raw SHA") || /…/.test(body), "P-DETAIL-hash", `provenance hash shown (truncated)`);
    const nConf = Object.keys(hit.conflicts || {}).length;
    check(true, "P-DETAIL-conf-info", `hit.conflicts keys=${nConf} (example has ${nConf}); UI shows generic conflict lines only, no per-evidence rows`);
  }

  // --- P-A11Y/LANG: language notice, live regions, keyboard ---
  {
    const html = fs.readFileSync("D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/ui/templates/public_search.html", "utf-8");
    check(/chưa tự động dịch Việt–Anh/.test(html), "P-LANG-notice", "language limitation notice present");
    check(/role="status"/.test(html) && /aria-live="polite"/.test(html), "P-A11Y-status", "status-region role=status aria-live=polite");
    check(/role="alert"/.test(html) && /aria-live="assertive"/.test(html), "P-A11Y-alert", "banner-region role=alert assertive");
    check(/aria-busy/.test(fs.readFileSync(UI_JS, "utf-8")), "P-A11Y-busy", "JS sets aria-busy during loading");
    check(/stale-review-region/.test(html) && !/stale-review-region[^>]*role/.test(html), "P-A11Y-stale-norole", "stale-review-region has NO role/live (gap)");
    check(/id="btn-search"/.test(html) && /id="btn-refresh"/.test(html), "P-KEY-buttons", "search/refresh are <button> (keyboard Tab/Enter/Space)");
  }

  // --- P-RACE-LIBRARY: library/save/export have no Abort/seq ---
  {
    const src = fs.readFileSync(UI_JS, "utf-8");
    const libFn = src.slice(src.indexOf("async function loadLibrary"), src.indexOf("async function loadLibrary") + 2500);
    const saveFn = src.slice(src.indexOf("async function savePaperToLibrary"), src.indexOf("async function savePaperToLibrary") + 2500);
    const expFn = src.slice(src.indexOf("async function exportLibrary"), src.indexOf("async function exportLibrary") + 1500);
    check(!/AbortController|currentSearchSeq|signal/.test(libFn), "P-RACE-library", "loadLibrary has NO abort/seq (rapid tab switches can race)");
    check(!/AbortController|currentSearchSeq|signal/.test(saveFn), "P-RACE-save", "savePaperToLibrary has NO abort/seq (double-click double POST)");
    check(!/AbortController|signal/.test(expFn), "P-RACE-export", "exportLibrary has NO abort");
  }

  // --- P-TT03-FIXTURE-GAP ---
  {
    const tt03 = ux.examples.example_04_tt03_success_sources_filtered_to_zero.envelope;
    check(tt03.snapshot.fusion.counts.excluded_by_year === 0, "P-TT03-gap", `TT-03 fixture excluded_by_year=0 with empty+empty (identical to TT-01); harness expects filter wording but fixture cannot produce it — author harness TT-03 assertion FAILs (see tmp-diag run)`);
  }

  // --- P-HARNESS-GAPS: querySelector missing, TT-07 not executed, export non2xx not tested ---
  {
    const runnerSrc = fs.readFileSync(RUNNER, "utf-8");
    check(/card\.querySelector \?/.test(runnerSrc), "P-HARNESS-query", "harness uses card.querySelector (absent in MockElement) → falls back to detached button, NOT the real card button");
    check(!/example_08_tt07|example_08/.test(runnerSrc), "P-HARNESS-tt07", "harness never executes TT-07 payload example_08 (only mentions TT-07 in comments)");
    check(!/exportLibrary\(/.test(runnerSrc) && !/GET \/public\/library\/export/.test(runnerSrc), "P-HARNESS-export", "harness never calls exportLibrary nor tests export non-2xx; no LibraryEntry schema/incompleteSources payload checks");
  }

  console.log(`\n=== PROBE SUMMARY PASS=${PASS} FAIL=${FAIL} ===`);
  // Do not exit nonzero: reviewer reports FAILs as findings; exit 0 to indicate probe itself ran.
}

main().catch(e => { console.error("PROBE EXCEPTION:", e); process.exit(2); });
