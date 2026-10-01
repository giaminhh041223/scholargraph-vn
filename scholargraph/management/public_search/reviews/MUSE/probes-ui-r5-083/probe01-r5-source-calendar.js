/**
 * R5-083 Probe01: Finding-1 SourceResult strict + Finding-2 calendar + safe-URL parity.
 * Target (immutable, read-only): public-gemini HEAD 93f0c2d.
 * Run: node probe01-r5-source-calendar.js  (exit 0 = all hold, 1 = silent bypass/divergence)
 */
const fs = require("fs");
const TARGET_JS = "D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/ui/static/public_search.js";
const TARGET_UX = "D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ux_examples.json";
const U = require(TARGET_JS);
const ux = JSON.parse(fs.readFileSync(TARGET_UX, "utf-8"));
let pass = 0, fail = 0;
function ok(c, m) { if (c) { pass++; console.log("  [PASS] " + m); } else { fail++; console.error("  [FAIL] " + m); } }
function mustThrow(fn, m) { let t = false; try { fn(); } catch (e) { t = true; } ok(t, m); }
function clone(o) { return JSON.parse(JSON.stringify(o)); }

// Base valid SourceResult: take first attempted source from example_03 (openalex success w/ records? use empty variant for minimal)
// Use example_02 all_empty first source (empty, no records) as base for type tests.
const baseEnv = clone(ux.examples.example_02_tt01_all_empty.envelope);
const baseSR = clone(baseEnv.snapshot.source_results[0]);
console.log("--- P01A Finding-1: 9 required keys present ---");
{
  // sanity: valid passes
  try { U.validateSourceResult(baseSR); ok(true, "valid SourceResult accepted"); }
  catch (e) { ok(false, "valid SourceResult accepted (" + e.message + ")"); }
  // delete each of the 3 previously-unchecked keys must throw
  for (const k of ["source_total", "elapsed_seconds", "truncated"]) {
    const b = clone(baseSR); delete b[k];
    mustThrow(() => U.validateSourceResult(b), "missing " + k + " rejected");
  }
  // delete each of remaining 6 also rejected (strict presence)
  for (const k of ["source", "status", "records", "error", "filter_coverage", "raw_references"]) {
    const b = clone(baseSR); delete b[k];
    mustThrow(() => U.validateSourceResult(b), "missing " + k + " rejected");
  }
}
console.log("--- P01B Finding-1: nullable type/range guards ---");
{
  const b = clone(baseSR);
  // source_total string
  let m = clone(b); m.source_total = "wrong";
  mustThrow(() => U.validateSourceResult(m), "source_total string rejected");
  // source_total float
  m = clone(b); m.source_total = 1.5;
  mustThrow(() => U.validateSourceResult(m), "source_total float rejected");
  // source_total bool (must not accept as int)
  m = clone(b); m.source_total = true;
  mustThrow(() => U.validateSourceResult(m), "source_total bool rejected");
  // source_total negative
  m = clone(b); m.source_total = -1;
  mustThrow(() => U.validateSourceResult(m), "source_total negative rejected");
  // truncated string / int
  m = clone(b); m.truncated = "wrong";
  mustThrow(() => U.validateSourceResult(m), "truncated string rejected");
  m = clone(b); m.truncated = 1;
  mustThrow(() => U.validateSourceResult(m), "truncated int rejected");
  // elapsed string / bool / negative
  m = clone(b); m.elapsed_seconds = "wrong";
  mustThrow(() => U.validateSourceResult(m), "elapsed string rejected");
  m = clone(b); m.elapsed_seconds = true;
  mustThrow(() => U.validateSourceResult(m), "elapsed bool rejected");
  m = clone(b); m.elapsed_seconds = -1.0;
  mustThrow(() => U.validateSourceResult(m), "elapsed negative rejected");
  // elapsed int 1 accepted (parity: Python Seconds accepts int)
  m = clone(b); m.elapsed_seconds = 1;
  try { U.validateSourceResult(m); ok(true, "elapsed int 1 accepted (parity)"); }
  catch (e) { ok(false, "elapsed int 1 accepted (" + e.message + ")"); }
  // source_total null is allowed for attempted? contract allows null; check accepted
  m = clone(b); m.source_total = null;
  try { U.validateSourceResult(m); ok(true, "source_total null accepted (nullable)"); }
  catch (e) { ok(false, "source_total null accepted (" + e.message + ")"); }
  // truncated null allowed
  m = clone(b); m.truncated = null;
  try { U.validateSourceResult(m); ok(true, "truncated null accepted (nullable)"); }
  catch (e) { ok(false, "truncated null accepted (" + e.message + ")"); }
}
console.log("--- P01C Finding-1: not_requested vs attempted semantics ---");
{
  const b = clone(baseSR);
  // valid not_requested shape
  const nr = clone(b);
  nr.status = "not_requested"; nr.filter_coverage = "none";
  nr.records = []; nr.raw_references = [];
  nr.source_total = null; nr.elapsed_seconds = null; nr.truncated = null; nr.error = null;
  try { U.validateSourceResult(nr); ok(true, "not_requested all-null accepted"); }
  catch (e) { ok(false, "not_requested all-null accepted (" + e.message + ")"); }
  // not_requested with observations must fail (each)
  for (const [lbl, mut] of [["source_total=1", { source_total: 1 }], ["elapsed=0.5", { elapsed_seconds: 0.5 }], ["truncated=false", { truncated: false }], ["filter=server", { filter_coverage: "server" }]]) {
    const m = clone(nr); Object.assign(m, mut);
    mustThrow(() => U.validateSourceResult(m), "not_requested with " + lbl + " rejected");
  }
  // attempted with elapsed null must fail
  const att = clone(b); att.elapsed_seconds = null;
  mustThrow(() => U.validateSourceResult(att), "attempted elapsed null rejected");
}
console.log("--- P01D Finding-2: calendar year/offset ---");
{
  const cases = [
    ["0000-01-01T00:00:00Z", false, "year 0000 rejected"],
    ["0001-01-01T00:00:00Z", true, "year 0001 accepted"],
    ["2026-09-30T10:00:00+07:00", true, "offset +07:00 accepted"],
    ["2026-09-30T10:00:00Z", true, "Z accepted"],
    ["2026-01-01T00:00:00+23:59", false, "offset +23:59 rejected"],
    ["2026-01-01T00:00:00-23:59", false, "offset -23:59 rejected"],
    ["2026-01-01T00:00:00+24:00", false, "offset +24:00 rejected"],
    ["2026-01-01T00:00:00+14:00", true, "offset +14:00 accepted (boundary)"],
    ["2026-01-01T00:00:00+14:01", false, "offset +14:01 rejected"],
    ["2026-01-01T00:00:00-12:00", true, "offset -12:00 accepted (boundary)"],
    ["2026-01-01T00:00:00-12:01", false, "offset -12:01 rejected"],
    ["2026-02-31T01:00:00Z", false, "Feb31 rejected"],
    ["2024-02-29T00:00:00Z", true, "leap Feb29 accepted"],
    ["2026-09-30T24:00:00Z", false, "hour24 rejected"],
    ["2026-09-30T10:00:00", false, "naive rejected"],
  ];
  for (const [v, exp, lbl] of cases) {
    ok(U.isIsoTimeWithTz(v) === exp, lbl + " (" + v + ")");
  }
  // envelope-level: fetched_at mutations rejected
  const good = clone(ux.examples.example_03_tt02_success_plus_empty_with_hit.envelope);
  for (const [v, lbl] of [["0000-01-01T00:00:00Z", "envelope year0000"], ["2026-01-01T00:00:00+23:59", "envelope offset+23:59"]]) {
    const e = clone(good); e.snapshot.fetched_at = v; e.snapshot.expires_at = "2027-01-01T00:00:00+07:00";
    mustThrow(() => U.validateEnvelope(e), lbl + " rejected");
  }
}
console.log("--- P01E safe-URL spot parity ---");
{
  ok(U.isSafeUrl("https://arxiv.org/abs/2401.00001") === true, "safe https accepted");
  ok(U.isSafeUrl("https://example.com:0/badport") === true, "port 0 accepted");
  ok(U.isSafeUrl("https://example.com:65535/paper") === true, "port 65535 accepted");
  ok(U.isSafeUrl("https://example.com:65536/paper") === false, "port 65536 rejected");
  ok(U.isSafeUrl("javascript:alert(1)") === false, "javascript: rejected");
  ok(U.isSafeUrl("https:example.com/paper") === false, "missing authority rejected");
}
console.log(`TOTAL: ${pass + fail} PASSED=${pass} FAILED=${fail}`);
if (fail > 0) { console.error("PROBE01-R5 FAILED"); process.exit(1); }
console.log("PROBE01-R5 ALL PASSED");
