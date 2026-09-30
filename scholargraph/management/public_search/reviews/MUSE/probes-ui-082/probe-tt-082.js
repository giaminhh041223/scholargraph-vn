/** REVIEWER TT PROBE — TT-01..06 + quota + stale truthfulness */
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
  const oc = doc.createElement.bind(doc);
  doc.createElement = (t) => { const e = oc(t); if (!e.style) e.style = {}; return e; };
  for (const e of doc.elementsById.values()) if (!e.style) e.style = {};
  return doc;
}
const ux = JSON.parse(fs.readFileSync(UX_PATH, "utf-8"));
let P = 0, F = 0;
function check(c, id, d) { if (c) { P++; console.log(`[PASS] ${id} :: ${d}`); } else { F++; console.log(`[FAIL] ${id} :: ${d}`); } }
function txt(el) { return el ? el.textContent : "<null>"; }
async function main() {
  console.log("=== TT PROBE ===");
  const cases = [
    ["TT-01", "example_02_tt01_all_empty", "empty", "Không tìm thấy"],
    ["TT-02", "example_03_tt02_success_plus_empty_with_hit", "success", null],
    ["TT-04", "example_05_tt04_empty_plus_failed_no_hit", "partial_failure", "partial_failure"],
    ["TT-05", "example_06_tt05_success_plus_failed_partial_failure_with_hits", "partial_failure", "partial_failure"],
    ["TT-06", "example_07_tt06_all_failed_mixed_precedence", "failed", "Lỗi truy vấn nguồn"],
  ];
  for (const [tt, key, overall, expect] of cases) {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    const env = ux.examples[key].envelope;
    if (env.overall !== overall) check(false, `${tt}-overall`, `fixture overall ${env.overall} != ${overall}`);
    else check(true, `${tt}-overall`, `overall=${overall}`);
    // validate via JS (should pass for these valid fixtures)
    let v = true;
    try { PublicSearchUI.validateEnvelope(env); } catch (e) { v = false; console.log(`  validate err ${tt}: ${e.message}`); }
    check(v, `${tt}-validate`, `JS validate ${v ? "accept" : "reject"}`);
    PublicSearchUI.renderSearchResults(env, false);
    const banner = txt(doc.getElementById("banner-region"));
    const results = doc.getElementById("results");
    if (tt === "TT-01") check(/Không tìm thấy/.test(txt(results)), `${tt}-render`, `empty message shown`);
    if (tt === "TT-02") check(results.children.length === 1, `${tt}-render`, `1 hit (got ${results.children.length})`);
    if (tt === "TT-04") {
      check(/partial_failure/.test(banner), `${tt}-banner`, `partial banner shown`);
      check(/Không tìm thấy|nằm ngoài|Danh sách/.test(txt(results)) || results.children.length === 0 || /Không tìm/.test(txt(results)), `${tt}-hits`, `no hits but banner (results=${JSON.stringify(txt(results).slice(0,100))})`);
    }
    if (tt === "TT-05") {
      check(/partial_failure/.test(banner) || /Quota/.test(banner), `${tt}-banner`, `partial/quota banner`);
      check(results.children.length > 0, `${tt}-hits`, `hits preserved (${results.children.length})`);
    }
    if (tt === "TT-06") {
      // example_07 has quota+schema; JS shows quota warning but SUPPRESSES schema error (if !quotaHit guard) — bug
      const hasQuota = /Quota|giới hạn/.test(banner);
      const hasFailed = /Lỗi truy vấn nguồn/.test(banner);
      check(hasQuota, `${tt}-banner-quota`, `quota warning shown (mixed)`);
      check(!hasFailed, `${tt}-banner-suppress`, `schema error SUPPRESSED when quota present (banner=${JSON.stringify(banner.slice(0,220))}) — BUG: mixed errors hidden`);
    }
  }
  // quota retry_after shown?
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ux.examples.example_06_tt05_success_plus_failed_partial_failure_with_hits.envelope, false);
    const b = txt(doc.getElementById("banner-region"));
    check(/retry_after_seconds|Thời gian chờ/.test(b), "TT-QUOTA-retry", `quota banner shows retry_after: ${JSON.stringify(b.slice(0,180))}`);
  }
  // non-2xx body read? simulate fetch 502 with JSON body containing partial envelope
  {
    const doc = createMockDOM();
    doc.getElementById("q").value = "x";
    const part = ux.examples.example_06_tt05_success_plus_failed_partial_failure_with_hits.envelope;
    PublicSearchUI.init({ document: doc, fetchFn: async () => ({ ok: false, status: 502, json: async () => part }) });
    await PublicSearchUI.handleSearchSubmit(false);
    const b = txt(doc.getElementById("banner-region"));
    const r = doc.getElementById("results");
    check(/partial_failure|Quota|giới hạn/.test(b), "TT-NON2XX-banner", `502 body parsed, partial/quota banner shown (actual=${JSON.stringify(b.slice(0,150))})`);
    check(r.children.length > 0, "TT-NON2XX-hits", `502 body hits rendered (${r.children.length}) — correct non-2xx body read`);
  }
  console.log(`\n=== TT SUMMARY PASS=${P} FAIL=${F} ===`);
}
main().catch(e => { console.error("TT EXCEPTION:", e); process.exit(2); });
