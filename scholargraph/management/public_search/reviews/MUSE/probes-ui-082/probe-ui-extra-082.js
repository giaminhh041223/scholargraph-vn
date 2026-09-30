/** REVIEWER EXTRA PROBE EXT-05A W2 082 — form/cached/export/race/detail-crash/library-fallback */
const fs = require("fs");
const path = require("path");
const TMP = __dirname + "/tmp-diag";
const UI_JS = path.join(TMP, "public_search.js");
const UX_PATH = path.join(TMP, "ux_examples.json");
const PublicSearchUI = require(UI_JS);
const RunnerMod = require(path.join(TMP, "node_test_runner_patched.js"));
const _orig = RunnerMod.createMockDOM;
function createMockDOM() {
  const doc = _orig();
  const origCreate = doc.createElement.bind(doc);
  doc.createElement = (tag) => { const el = origCreate(tag); if (!el.style) el.style = {}; return el; };
  for (const el of doc.elementsById.values()) if (!el.style) el.style = {};
  return doc;
}
const ux = JSON.parse(fs.readFileSync(UX_PATH, "utf-8"));
let P = 0, F = 0;
function check(c, id, d) { if (c) { P++; console.log(`[PASS] ${id} :: ${d}`); } else { F++; console.log(`[FAIL] ${id} :: ${d}`); } }
function txt(el) { return el ? el.textContent : "<null>"; }

async function main() {
  console.log("=== EXTRA PROBE ===");
  // E-FORM: invalid inputs rejected client-side
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    let e = PublicSearchUI.validateFormInputs({ query: "", sources: ["openalex"], year_from: null, year_to: null, top_k: 20, cap_per_source: 50 });
    check(e.length > 0, "E-FORM-empty", `empty query rejected: ${JSON.stringify(e).slice(0,120)}`);
    e = PublicSearchUI.validateFormInputs({ query: "x".repeat(501), sources: ["openalex"], year_from: null, year_to: null, top_k: 20, cap_per_source: 50 });
    check(e.length > 0, "E-FORM-long", `>500 rejected`);
    e = PublicSearchUI.validateFormInputs({ query: "x", sources: [], year_from: null, year_to: null, top_k: 20, cap_per_source: 50 });
    check(e.length > 0, "E-FORM-nosource", `no source rejected`);
    e = PublicSearchUI.validateFormInputs({ query: "x", sources: ["openalex"], year_from: 2025, year_to: 2020, top_k: 20, cap_per_source: 50 });
    check(e.length > 0 && /Năm bắt đầu/.test(e.join(" ")), "E-FORM-year-rev", `year reversed rejected with wording`);
    e = PublicSearchUI.validateFormInputs({ query: "x", sources: ["openalex"], year_from: 1700, year_to: null, top_k: 20, cap_per_source: 50 });
    check(e.length > 0, "E-FORM-year-range", `year 1700 out of 1800..2100 rejected`);
    e = PublicSearchUI.validateFormInputs({ query: "x", sources: ["openalex"], year_from: null, year_to: null, top_k: 75, cap_per_source: 50 });
    check(e.length > 0, "E-FORM-topk", `top_k 75 rejected`);
    e = PublicSearchUI.validateFormInputs({ query: "x", sources: ["openalex"], year_from: null, year_to: null, top_k: 0, cap_per_source: 50 });
    check(e.length > 0, "E-FORM-topk0", `top_k 0 rejected`);
    e = PublicSearchUI.validateFormInputs({ query: "  graph mining  ", sources: ["openalex"], year_from: null, year_to: null, top_k: 20, cap_per_source: 50 });
    check(e.length === 0, "E-FORM-trim-ok", `trimmed valid passes`);
  }
  // E-CACHED: badges truthful
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    const fresh = JSON.parse(JSON.stringify(ux.examples.example_09_cache_fresh_stale_and_refresh_failure.subcases.A_cached_fresh.envelope));
    PublicSearchUI.renderSearchResults(fresh, false);
    const banner = txt(doc.getElementById("snapshot-meta-banner"));
    check(/cached_fresh/.test(txt(doc.getElementById("snapshot-meta-banner"))), "E-CACHED-fresh", `fresh badge shown: ${banner.slice(0,120)}`);
    // non-cached success should show NO badge
    const doc2 = createMockDOM();
    PublicSearchUI.init({ document: doc2 });
    const nocache = JSON.parse(JSON.stringify(ux.examples.example_03_tt02_success_plus_empty_with_hit.envelope));
    PublicSearchUI.renderSearchResults(nocache, false);
    const b2 = txt(doc2.getElementById("snapshot-meta-banner"));
    check(!/cached_fresh|cached_stale/.test(b2), "E-CACHED-nocache", `non-cached shows no badge (actual=${JSON.stringify(b2.slice(0,100))})`);
  }
  // E-EXPORT-ERR: non-2xx export must show error, not success
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc, fetchFn: async () => ({ ok: false, status: 500, text: async () => "boom" }) });
    await PublicSearchUI.exportLibrary("json");
    const b = txt(doc.getElementById("banner-region"));
    check(/Xuất thư viện thất bại/.test(b) && /500/.test(b), "E-EXPORT-err", `export 500 shows error banner: ${JSON.stringify(b.slice(0,150))}`);
    // success path
    const doc2 = createMockDOM();
    PublicSearchUI.init({ document: doc2, fetchFn: async () => ({ ok: true, status: 200, text: async () => "{}" }) });
    // stub download to avoid Blob/URL in mock
    const src = fs.readFileSync(UI_JS, "utf-8");
    check(/downloadTextFile/.test(src), "E-EXPORT-dl", `export success calls downloadTextFile (Blob+URL.createObjectURL — mock lacks Blob, browser-only)`);
  }
  // E-RACE-SEARCH: delayed search race protected (re-run harness Suite5 logic with patched mock)
  {
    const doc = createMockDOM();
    doc.getElementById("q").value = "test query";
    let n = 0;
    const exEmpty = ux.examples.example_02_tt01_all_empty;
    const exHit = ux.examples.example_03_tt02_success_plus_empty_with_hit;
    const fakeFetch = (url, opts) => {
      n++;
      const cur = n;
      return new Promise((res) => {
        const delay = cur === 1 ? 40 : 10;
        setTimeout(() => {
          const ex = cur === 1 ? exEmpty : exHit;
          res({ ok: true, status: 200, json: async () => ex.envelope });
        }, delay);
      });
    };
    PublicSearchUI.init({ document: doc, fetchFn: fakeFetch });
    const p1 = PublicSearchUI.handleSearchSubmit(false);
    const p2 = PublicSearchUI.handleSearchSubmit(false);
    await Promise.all([p1, p2]);
    await new Promise(r => setTimeout(r, 80));
    const res = doc.getElementById("results");
    check(res.children.length === 1, "E-RACE-search", `stale slow request ignored, fast newer preserved (children=${res.children.length})`);
  }
  // E-RACE-LIBRARY-double-save still double POSTs
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    const succ = ux.examples.example_03_tt02_success_plus_empty_with_hit;
    PublicSearchUI.renderSearchResults(succ.envelope, false);
    let posts = 0;
    const hit = succ.envelope.snapshot.fusion.hits[0];
    const lf = async (url, opts) => {
      if (String(url) === "/public/library" && opts.method === "POST") {
        posts++;
        return { ok: true, status: 200, json: async () => ({ canonical_id: hit.canonical_id, snapshot_id: succ.envelope.snapshot.snapshot_id, saved_at: "2026-09-30T15:00:00+07:00", hit, incomplete_sources: false }) };
      }
      return { ok: true, status: 200, json: async () => [] };
    };
    PublicSearchUI.init({ document: doc, fetchFn: lf });
    const btn = doc.createElement("button");
    await PublicSearchUI.savePaperToLibrary(hit, btn);
    await PublicSearchUI.savePaperToLibrary(hit, btn);
    check(posts === 2, "E-RACE-double-post", `double save sends ${posts} POSTs (no client idempotent guard; server must dedup)`);
    check(/save_idempotent/.test(btn.textContent), "E-SAVE-badge", `button shows save_idempotent: ${JSON.stringify(btn.textContent.slice(0,100))}`);
  }
  // E-DETAIL-CRASH: hit without field_provenance throws?
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    const badHit = { canonical_id: "bad", rank: 1, score: 0.01, display: { title: "T", field_provenance: null }, source_records: [], source_ranks: {}, conflicts: {} };
    let threw = false;
    try { PublicSearchUI.showDetailPanel(badHit); } catch (e) { threw = true; }
    check(threw, "E-DETAIL-crash", `showDetailPanel with field_provenance=null throws (threw=${threw}) — no graceful FAIL banner`);
  }
  // E-LIB-FALLBACK: missing title shows placeholder instead of FAIL
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    // createLibraryEntryCard is not exported; check source for placeholder
    const src = fs.readFileSync(UI_JS, "utf-8");
    check(/\(Không có tiêu đề\)/.test(src), "E-LIB-placeholder", `library card uses "(Không có tiêu đề)" fallback — hides required-title schema violation instead of explicit FAIL`);
  }
  // E-EMPTY-OVERALL: success with 0 hits rendered as empty (masks overall mismatch)
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    const env = JSON.parse(JSON.stringify(ux.examples.example_03_tt02_success_plus_empty_with_hit.envelope));
    env.overall = "success"; env.snapshot.overall = "success";
    env.snapshot.fusion.hits = []; env.snapshot.fusion.counts.returned = 0;
    env.snapshot.fusion.counts.groups = 0; env.snapshot.fusion.counts.eligible = 0;
    env.snapshot.fusion.counts.valid = 0; env.snapshot.fusion.counts.raw = 0;
    // validateEnvelope will ACCEPT (it doesn't check hits vs overall)
    let threw = false;
    try { PublicSearchUI.validateEnvelope(env); } catch (e) { threw = true; }
    check(!threw, "E-EMPTY-accept", `JS accepts success+0hits (threw=${threw}) — contract snapshot overall would be empty, mismatch hidden`);
    PublicSearchUI.renderSearchResults(env, false);
    const t = txt(doc.getElementById("results"));
    check(/Không tìm thấy/.test(t), "E-EMPTY-render", `rendered as empty message, masking overall=success mismatch`);
  }
  // E-NO-OFFLINE: no offline endpoints
  {
    const src = fs.readFileSync(UI_JS, "utf-8");
    check(!/\/paper\/|\/recommend\//.test(src), "E-NO-OFFLINE", `no /paper/ or /recommend/ calls`);
    check(!/ux_examples\.json/.test(src) || /ux_examples/.test(src) === false, "E-NO-FIXTURE", `production JS has no ux_examples fixture import (only harness uses it)`);
  }
  console.log(`\n=== EXTRA SUMMARY PASS=${P} FAIL=${F} ===`);
}
main().catch(e => { console.error("EXTRA EXCEPTION:", e); process.exit(2); });
