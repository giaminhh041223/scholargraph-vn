/**
 * R5-083 Probe02: Finding-3 idempotent snapshot preservation + regression
 * (race, XSS, pagination, stale/refresh, detail, export, TT spot).
 * Target immutable 93f0c2d, read-only require. Minimal MockDocument independent of author harness.
 */
const fs = require("fs");
const TARGET_JS = "D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/ui/static/public_search.js";
const TARGET_UX = "D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ux_examples.json";
const U = require(TARGET_JS);
const ux = JSON.parse(fs.readFileSync(TARGET_UX, "utf-8"));
let pass = 0, fail = 0;
function ok(c, m) { if (c) { pass++; console.log("  [PASS] " + m); } else { fail++; console.error("  [FAIL] " + m); } }

class El {
  constructor(tag, doc) { this.tagName = tag.toUpperCase(); this.ownerDocument = doc; this.children = []; this.attributes = {}; this.dataset = {}; this.classList = { _s: new Set(), add(...a) { a.forEach(x => this._s.add(x)); }, remove(...a) { a.forEach(x => this._s.delete(x)); }, contains(x) { return this._s.has(x); } }; this.style = {}; this.eventListeners = {}; this._text = ""; this._html = ""; this.hidden = false; this.disabled = false; this.checked = false; this.value = ""; this._id = ""; this.href = ""; this.download = ""; this.parentNode = null; }
  get id() { return this._id; } set id(v) { this._id = String(v); if (this._id && this.ownerDocument) this.ownerDocument.map.set(this._id, this); }
  get firstChild() { return this.children[0] || null; }
  get textContent() { if (this.children.length === 0) return this._text; return this.children.map(c => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get innerHTML() { return this._html; } set innerHTML(v) { this._html = String(v); if (v === "") { this.children = []; this._text = ""; } }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) { this.children.splice(i, 1); c.parentNode = null; } return c; }
  setAttribute(k, v) { this.attributes[k] = String(v); if (k === "id") this.id = String(v); }
  getAttribute(k) { return this.attributes[k] ?? null; }
  removeAttribute(k) { delete this.attributes[k]; }
  addEventListener(t, f) { (this.eventListeners[t] = this.eventListeners[t] || []).push(f); }
  dispatchEvent(e) { (this.eventListeners[e.type] || []).forEach(f => f.call(this, e)); }
  click() { this.dispatchEvent({ type: "click", preventDefault() {} }); }
  scrollIntoView() {}
  get isConnected() { let n = this; while (n) { if (n === this.ownerDocument || n === this.ownerDocument.body) return true; n = n.parentNode; } return false; }
}
class Doc {
  constructor() { this.map = new Map(); this.body = new El("body", this); }
  createElement(t) { return new El(t, this); }
  getElementById(id) { return this.map.get(id) || null; }
}
function makeDoc() {
  const d = new Doc();
  const ids = ["public-search-form", "q", "language-notice", "sources-fieldset", "src-openalex", "src-arxiv", "sources-error", "year_from", "year_to", "years-error", "top_k", "cap_per_source", "btn-search", "btn-refresh", "client-validation-error", "tab-search", "tab-library", "library-count-badge", "status-region", "banner-region", "stale-review-region", "search-section", "snapshot-meta-banner", "sources-summary", "fusion-summary", "results", "snapshot-pagination", "detail-panel", "detail-body", "btn-close-detail", "library-section", "btn-export-json", "btn-export-bibtex", "library-list", "library-pagination"];
  for (const id of ids) { const el = d.createElement("div"); el.id = id; d.body.appendChild(el); }
  d.getElementById("src-openalex").checked = true; d.getElementById("src-arxiv").checked = true;
  d.getElementById("q").value = "graph mining"; d.getElementById("top_k").value = "20"; d.getElementById("cap_per_source").value = "50";
  return d;
}
function clone(o) { return JSON.parse(JSON.stringify(o)); }

async function main() {
  console.log("--- P02A Finding-3: duplicate save preserves ORIGINAL snapshot_id ---");
  {
    const doc = makeDoc();
    // displayed snapshot is NEWER (snap_newer_999), store already has paper from ORIGINAL (snap_syn_w2_001)
    const partial = clone(ux.examples.example_06_tt05_success_plus_failed_partial_failure_with_hits.envelope);
    const newerSnapId = "snap_newer_999";
    partial.snapshot.snapshot_id = newerSnapId;
    const hit = partial.snapshot.fusion.hits[0];
    const originalSnapId = "snap_syn_w2_001";
    let posts = [];
    const saveFetch = async (url, opts) => {
      if (opts && opts.method === "POST") {
        posts.push(JSON.parse(opts.body));
        // store returns ORIGINAL entry (idempotent, provenance preserved)
        return { ok: true, status: 200, json: async () => ({ canonical_id: hit.canonical_id, snapshot_id: originalSnapId, saved_at: "2026-09-30T12:00:00+07:00", hit: hit, incomplete_sources: true }) };
      }
      return { ok: true, status: 200, json: async () => [] };
    };
    U.init({ document: doc, fetchFn: saveFetch });
    U.renderSearchResults(partial, false);
    const btn = doc.createElement("button"); doc.body.appendChild(btn);
    await U.savePaperToLibrary(hit, btn);
    ok(posts.length === 1, "1 POST sent with displayed (newer) snapshot_id");
    ok(posts[0].snapshot_id === newerSnapId, "POST uses displayedSnapshot id " + newerSnapId);
    const banner = doc.getElementById("banner-region").textContent;
    ok(!banner.includes("thất bại"), "differing ORIGINAL snapshot_id does NOT show failure banner (accepted as idempotent)");
    ok(btn.textContent.includes("save_idempotent"), "button shows save_idempotent for preserved-original response");
    // mismatched canonical must fail loud (use fresh canonical to bypass saved-guard from previous save)
    const doc2 = makeDoc();
    const freshHit = clone(hit);
    freshHit.canonical_id = "fresh_mismatch_probe_r5_001";
    // keep display/source_records consistent for render path (save only uses canonical_id, not full validation of hit)
    const badFetch = async () => ({ ok: true, status: 200, json: async () => ({ canonical_id: "WRONG_ID", snapshot_id: originalSnapId, saved_at: "2026-09-30T12:00:00+07:00", hit: hit, incomplete_sources: false }) });
    U.init({ document: doc2, fetchFn: badFetch });
    U.renderSearchResults(partial, false);
    const btn2 = doc2.createElement("button"); doc2.body.appendChild(btn2);
    await U.savePaperToLibrary(freshHit, btn2);
    ok(doc2.getElementById("banner-region").textContent.includes("thất bại"), "mismatched canonical_id fails loud");
    ok(!btn2.textContent.includes("save_idempotent"), "mismatched canonical does not set idempotent");
  }
  console.log("--- P02B Finding-3 direct validator: snapshot_id free, canonical strict ---");
  {
    const fix = JSON.parse(fs.readFileSync("D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ui/ui_fixtures.json", "utf-8"));
    const entry = clone(fix.fixtures.idempotent_library_save);
    // differing snapshot_id must still validate (only canonical checked)
    const e2 = clone(entry); e2.snapshot_id = "snap_newer_999";
    try { U.validateLibraryEntry(e2); ok(true, "validateLibraryEntry accepts differing snapshot_id"); }
    catch (err) { ok(false, "validateLibraryEntry accepts differing snapshot_id (" + err.message + ")"); }
    const e3 = clone(entry); e3.canonical_id = "mismatched";
    let threw = false; try { U.validateLibraryEntry(e3); } catch (e) { threw = true; }
    ok(threw, "validateLibraryEntry rejects canonical mismatch");
  }
  console.log("--- P02C regression: race / XSS / pagination / stale / export / detail ---");
  {
    // race: slow old ignored
    const doc = makeDoc();
    const env1 = clone(ux.examples.example_03_tt02_success_plus_empty_with_hit.envelope);
    const env2 = clone(ux.examples.example_02_tt01_all_empty.envelope);
    let call = 0;
    const raceFetch = async () => {
      call++;
      if (call === 1) { await new Promise(r => setTimeout(r, 60)); return { ok: true, status: 200, json: async () => env1 }; }
      await new Promise(r => setTimeout(r, 10)); return { ok: true, status: 200, json: async () => env2 };
    };
    U.init({ document: doc, fetchFn: raceFetch });
    const p1 = U.handleSearchSubmit(false);
    await new Promise(r => setTimeout(r, 5));
    const p2 = U.handleSearchSubmit(false);
    await Promise.all([p1, p2]);
    ok(doc.getElementById("results").textContent.includes("Không tìm thấy"), "search race: slow old ignored");
    // XSS
    const docX = makeDoc(); U.init({ document: docX });
    const evil = clone(ux.examples.example_01_success_dedup_rrf_and_missing_fields.envelope.snapshot.fusion.hits[0]);
    evil.display.title = "<script>alert(1)</script>";
    const card = U.createResultCard(evil);
    ok(card.innerHTML.indexOf("<script>") === -1, "XSS: no script in innerHTML");
    ok(card.textContent.includes("<script>alert(1)</script>"), "XSS: evil inert text");
    // pagination wording + fetch URL
    const docP = makeDoc(); U.init({ document: docP });
    const env = clone(ux.examples.example_01_success_dedup_rrf_and_missing_fields.envelope);
    U.renderSearchResults(env, false);
    const pag = docP.getElementById("snapshot-pagination");
    ok(!pag.hidden, "pagination visible");
    const info = pag.children.find(c => c.textContent && c.textContent.startsWith("Trang"));
    ok(info && info.textContent.includes("trên Snapshot #") && info.textContent.includes(env.snapshot.snapshot_id), "pagination wording with snapshot_id");
    // stale
    const stale = clone(env); stale.cached = true; stale.stale = true;
    U.renderSearchResults(stale, false);
    ok(docP.getElementById("banner-region").textContent.includes("cached_stale"), "stale banner");
    // detail conflicts via textContent
    U.showDetailPanel(evil);
    ok(docP.getElementById("detail-panel").textContent.includes("xung đột") || docP.getElementById("detail-body").textContent.length > 0, "detail panel renders");
    // export: success vs 500 vs missing Blob (no silent success)
    const docE = makeDoc();
    if (typeof global.Blob === "undefined") global.Blob = class { constructor(p) { this.parts = p; } };
    if (!global.URL.createObjectURL) global.URL.createObjectURL = () => "blob:mock";
    if (!global.URL.revokeObjectURL) global.URL.revokeObjectURL = () => {};
    U.init({ document: docE, fetchFn: async () => ({ ok: true, status: 200, text: async () => "x" }) });
    await U.exportLibrary("json");
    ok(docE.getElementById("banner-region").textContent.includes("thành công"), "export 200 success");
    U.init({ document: docE, fetchFn: async () => ({ ok: false, status: 500 }) });
    U.clearBanners();
    await U.exportLibrary("json");
    const b = docE.getElementById("banner-region");
    ok(b.textContent.includes("thất bại") && !b.textContent.includes("thành công"), "export 500 no fake success");
    const saved = global.Blob; global.Blob = undefined;
    try { U.clearBanners(); await U.exportLibrary("json"); ok(docE.getElementById("banner-region").textContent.includes("thất bại"), "missing Blob fails loud"); }
    finally { global.Blob = saved; }
  }
  console.log(`TOTAL: ${pass + fail} PASSED=${pass} FAILED=${fail}`);
  if (fail > 0) { console.error("PROBE02-R5 FAILED"); process.exit(1); }
  console.log("PROBE02-R5 ALL PASSED");
}
main().catch(e => { console.error("Unhandled:", e); process.exit(1); });
