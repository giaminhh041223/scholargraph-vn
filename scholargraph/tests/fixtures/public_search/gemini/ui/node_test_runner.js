/**
 * Dependency-Free Node.js DOM Test Harness for Public Paper Search UI (EXT-05A)
 *
 * Implements a mock DOM environment, native URL/Blob stubs, and fetch simulator
 * to execute public_search.js directly under Node.js without requiring external npm packages.
 *
 * Execution:
 *   node node_test_runner.js --fixtures <path_to_ui_fixtures.json> --ux-examples <path_to_ux_examples.json>
 */
const fs = require("fs");
const path = require("path");

// --- GLOBAL STUBS FOR NODE.JS ENVIRONMENT ---
if (typeof global.Blob === "undefined") {
  global.Blob = class MockBlob {
    constructor(parts, opts) {
      this.parts = parts;
      this.type = opts ? opts.type : "";
    }
  };
}

if (typeof global.URL === "undefined") {
  global.URL = class MockURL {};
}
if (!global.URL.createObjectURL) {
  global.URL.createObjectURL = function (blob) {
    return "blob:mock-url-" + Math.random().toString(36).substring(2);
  };
}
if (!global.URL.revokeObjectURL) {
  global.URL.revokeObjectURL = function (url) {};
}

// --- MOCK DOM CLASSES ---
class MockClassList {
  constructor(element) {
    this._element = element;
    this._classes = new Set();
  }
  add(...names) {
    for (const n of names) if (n) this._classes.add(n);
  }
  remove(...names) {
    for (const n of names) this._classes.delete(n);
  }
  contains(name) {
    return this._classes.has(name);
  }
  toString() {
    return Array.from(this._classes).join(" ");
  }
}

class MockElement {
  constructor(tagName, doc) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = doc;
    this.parentNode = null;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.classList = new MockClassList(this);
    this.style = {};
    this.eventListeners = {};
    this._textContent = "";
    this._innerHTML = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = "";
    this._id = "";
    this.name = "";
    this.type = "";
    this.target = "";
    this.rel = "";
    this.href = "";
    this.download = "";
  }

  get id() {
    return this._id;
  }

  set id(val) {
    this._id = val ? String(val) : "";
    if (this._id && this.ownerDocument) {
      this.ownerDocument.registerElement(this._id, this);
    }
  }

  get isConnected() {
    let node = this;
    while (node) {
      if (node === this.ownerDocument || (this.ownerDocument && node === this.ownerDocument.body)) {
        return true;
      }
      node = node.parentNode;
    }
    return false;
  }

  get firstChild() {
    return this.children.length > 0 ? this.children[0] : null;
  }

  get lastChild() {
    return this.children.length > 0 ? this.children[this.children.length - 1] : null;
  }

  get textContent() {
    if (this.children.length === 0) return this._textContent;
    return this.children.map(c => c.textContent).join("");
  }

  set textContent(val) {
    this.children = [];
    this._textContent = val === null || val === undefined ? "" : String(val);
  }

  get innerHTML() {
    return this._innerHTML;
  }

  set innerHTML(val) {
    this._innerHTML = String(val);
    if (val === "") {
      this.children = [];
      this._textContent = "";
    }
  }

  appendChild(child) {
    if (child) {
      child.parentNode = this;
      this.children.push(child);
    }
    return child;
  }

  removeChild(child) {
    const idx = this.children.indexOf(child);
    if (idx !== -1) {
      this.children.splice(idx, 1);
      child.parentNode = null;
    }
    return child;
  }

  setAttribute(k, v) {
    this.attributes[k] = String(v);
    if (k === "id") {
      this.id = String(v);
    }
    if (k === "class") {
      this.classList = new MockClassList(this);
      this.classList.add(...String(v).split(/\s+/).filter(Boolean));
    }
    if (k === "hidden") this.hidden = true;
    if (k === "disabled") this.disabled = true;
  }

  getAttribute(k) {
    return this.attributes[k] !== undefined ? this.attributes[k] : null;
  }

  removeAttribute(k) {
    delete this.attributes[k];
    if (k === "hidden") this.hidden = false;
    if (k === "disabled") this.disabled = false;
  }

  addEventListener(type, listener) {
    if (!this.eventListeners[type]) this.eventListeners[type] = [];
    this.eventListeners[type].push(listener);
  }

  dispatchEvent(event) {
    const listeners = this.eventListeners[event.type] || [];
    event.target = this;
    for (const l of listeners) {
      l.call(this, event);
    }
  }

  click() {
    this.dispatchEvent({ type: "click", preventDefault: () => {} });
  }

  scrollIntoView() {}

  querySelector(selector) {
    const results = this.querySelectorAll(selector);
    return results.length > 0 ? results[0] : null;
  }

  querySelectorAll(selector) {
    const matches = [];
    function matchEl(el, sel) {
      if (!sel) return false;
      if (sel.startsWith(".")) {
        const cls = sel.substring(1);
        return el.classList.contains(cls);
      }
      if (sel.startsWith("#")) {
        return el.id === sel.substring(1);
      }
      return el.tagName.toLowerCase() === sel.toLowerCase();
    }

    function traverse(node) {
      for (const child of node.children) {
        if (matchEl(child, selector)) {
          matches.push(child);
        }
        traverse(child);
      }
    }
    traverse(this);
    return matches;
  }
}

class MockDocument {
  constructor() {
    this.elementsById = new Map();
    this.body = new MockElement("body", this);
  }

  createElement(tagName) {
    return new MockElement(tagName, this);
  }

  getElementById(id) {
    return this.elementsById.get(id) || null;
  }

  registerElement(id, el) {
    el._id = id;
    this.elementsById.set(id, el);
    return el;
  }

  querySelector(selector) {
    return this.body.querySelector(selector);
  }

  querySelectorAll(selector) {
    return this.body.querySelectorAll(selector);
  }
}

/**
 * Dựng cấu trúc DOM khớp đầy đủ với public_search.html
 */
function createMockDOM() {
  const doc = new MockDocument();

  // Biểu mẫu tìm kiếm
  const form = doc.registerElement("public-search-form", doc.createElement("form"));
  doc.body.appendChild(form);

  const q = doc.registerElement("q", doc.createElement("input"));
  q.type = "text";
  form.appendChild(q);

  const langNotice = doc.registerElement("language-notice", doc.createElement("p"));
  form.appendChild(langNotice);

  const srcFieldset = doc.registerElement("sources-fieldset", doc.createElement("fieldset"));
  form.appendChild(srcFieldset);

  const srcOpenalex = doc.registerElement("src-openalex", doc.createElement("input"));
  srcOpenalex.type = "checkbox"; srcOpenalex.checked = true;
  srcFieldset.appendChild(srcOpenalex);

  const srcArxiv = doc.registerElement("src-arxiv", doc.createElement("input"));
  srcArxiv.type = "checkbox"; srcArxiv.checked = true;
  srcFieldset.appendChild(srcArxiv);

  const sourcesError = doc.registerElement("sources-error", doc.createElement("p"));
  sourcesError.hidden = true;
  srcFieldset.appendChild(sourcesError);

  const yearFrom = doc.registerElement("year_from", doc.createElement("input"));
  yearFrom.type = "number";
  form.appendChild(yearFrom);

  const yearTo = doc.registerElement("year_to", doc.createElement("input"));
  yearTo.type = "number";
  form.appendChild(yearTo);

  const yearsError = doc.registerElement("years-error", doc.createElement("p"));
  yearsError.hidden = true;
  form.appendChild(yearsError);

  const topK = doc.registerElement("top_k", doc.createElement("input"));
  topK.type = "number"; topK.value = "20";
  form.appendChild(topK);

  const capPerSource = doc.registerElement("cap_per_source", doc.createElement("input"));
  capPerSource.type = "number"; capPerSource.value = "50";
  form.appendChild(capPerSource);

  const btnSearch = doc.registerElement("btn-search", doc.createElement("button"));
  btnSearch.type = "submit";
  form.appendChild(btnSearch);

  const btnRefresh = doc.registerElement("btn-refresh", doc.createElement("button"));
  btnRefresh.type = "button";
  form.appendChild(btnRefresh);

  const clientValidationError = doc.registerElement("client-validation-error", doc.createElement("div"));
  clientValidationError.hidden = true;
  form.appendChild(clientValidationError);

  // Tabs
  const tabSearch = doc.registerElement("tab-search", doc.createElement("button"));
  doc.body.appendChild(tabSearch);

  const tabLibrary = doc.registerElement("tab-library", doc.createElement("button"));
  doc.body.appendChild(tabLibrary);

  const libraryCountBadge = doc.registerElement("library-count-badge", doc.createElement("span"));
  libraryCountBadge.textContent = "chưa tải";
  tabLibrary.appendChild(libraryCountBadge);

  // Regions
  const statusRegion = doc.registerElement("status-region", doc.createElement("div"));
  statusRegion.hidden = true;
  doc.body.appendChild(statusRegion);

  const bannerRegion = doc.registerElement("banner-region", doc.createElement("div"));
  doc.body.appendChild(bannerRegion);

  const staleReviewRegion = doc.registerElement("stale-review-region", doc.createElement("div"));
  staleReviewRegion.hidden = true;
  doc.body.appendChild(staleReviewRegion);

  // Search Results section
  const searchSection = doc.registerElement("search-section", doc.createElement("section"));
  doc.body.appendChild(searchSection);

  const snapshotMetaBanner = doc.registerElement("snapshot-meta-banner", doc.createElement("div"));
  snapshotMetaBanner.hidden = true;
  searchSection.appendChild(snapshotMetaBanner);

  const sourcesSummary = doc.registerElement("sources-summary", doc.createElement("div"));
  sourcesSummary.hidden = true;
  searchSection.appendChild(sourcesSummary);

  const fusionSummary = doc.registerElement("fusion-summary", doc.createElement("div"));
  fusionSummary.hidden = true;
  searchSection.appendChild(fusionSummary);

  const results = doc.registerElement("results", doc.createElement("div"));
  searchSection.appendChild(results);

  const snapshotPagination = doc.registerElement("snapshot-pagination", doc.createElement("nav"));
  snapshotPagination.hidden = true;
  searchSection.appendChild(snapshotPagination);

  const detailPanel = doc.registerElement("detail-panel", doc.createElement("aside"));
  detailPanel.hidden = true;
  searchSection.appendChild(detailPanel);

  const detailBody = doc.registerElement("detail-body", doc.createElement("div"));
  const btnCloseDetail = doc.registerElement("btn-close-detail", doc.createElement("button"));
  detailPanel.appendChild(btnCloseDetail);
  detailPanel.appendChild(detailBody);

  // Library Section
  const librarySection = doc.registerElement("library-section", doc.createElement("section"));
  librarySection.hidden = true;
  doc.body.appendChild(librarySection);

  const btnExportJson = doc.registerElement("btn-export-json", doc.createElement("button"));
  librarySection.appendChild(btnExportJson);

  const btnExportBibtex = doc.registerElement("btn-export-bibtex", doc.createElement("button"));
  librarySection.appendChild(btnExportBibtex);

  const libraryList = doc.registerElement("library-list", doc.createElement("div"));
  librarySection.appendChild(libraryList);

  const libraryPagination = doc.registerElement("library-pagination", doc.createElement("nav"));
  libraryPagination.hidden = true;
  librarySection.appendChild(libraryPagination);

  return doc;
}

/**
 * Tìm kiếm root của dự án bằng cách duyệt ngược cây thư mục
 */
function findProjectRoot(startDir) {
  let curr = startDir;
  for (let i = 0; i < 8; i++) {
    if (fs.existsSync(path.join(curr, "ui", "static", "public_search.js"))) {
      return curr;
    }
    const parent = path.dirname(curr);
    if (parent === curr) break;
    curr = parent;
  }
  return path.resolve(__dirname, "../../../../../");
}

async function runAllTests(uiFixturesPath, uxExamplesPath) {
  console.log("=======================================================");
  console.log("EXT-05A: Running Public Paper Search UI Node DOM Harness");
  console.log("=======================================================");

  if (!fs.existsSync(uiFixturesPath)) {
    console.error("FAIL: UI fixtures file not found:", uiFixturesPath);
    process.exit(1);
  }
  if (!fs.existsSync(uxExamplesPath)) {
    console.error("FAIL: UX examples file not found:", uxExamplesPath);
    process.exit(1);
  }

  const uiFixtures = JSON.parse(fs.readFileSync(uiFixturesPath, "utf-8"));
  const uxExamples = JSON.parse(fs.readFileSync(uxExamplesPath, "utf-8"));

  const projectRoot = findProjectRoot(__dirname);
  const jsPath = path.join(projectRoot, "ui", "static", "public_search.js");
  if (!fs.existsSync(jsPath)) {
    console.error("FAIL: public_search.js not found at:", jsPath);
    process.exit(1);
  }

  const PublicSearchUI = require(jsPath);

  let passedCount = 0;
  let failedCount = 0;

  function assert(condition, message) {
    if (!condition) {
      console.error("  [FAIL]:", message);
      failedCount++;
      throw new Error(message);
    } else {
      passedCount++;
      console.log("  [PASS]:", message);
    }
  }

  // -------------------------------------------------------------
  // SUITE 1: Safe URL Sanitization
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 1: Safe URL Sanitization (isSafeUrl) ---");
  for (const goodUrl of uiFixtures.fixtures.safe_urls) {
    assert(PublicSearchUI.isSafeUrl(goodUrl) === true, "Safe URL accepted: " + goodUrl);
  }
  for (const badUrl of uiFixtures.fixtures.unsafe_urls) {
    assert(PublicSearchUI.isSafeUrl(badUrl) === false, "Unsafe URL rejected: " + JSON.stringify(badUrl));
  }
  // Explicit probe tests for missing authority / non-standard slashes
  assert(PublicSearchUI.isSafeUrl("https:example.com/paper") === false, "https:example.com/paper rejected (missing authority)");
  assert(PublicSearchUI.isSafeUrl("http:/example.com/paper") === false, "http:/example.com/paper rejected (single slash)");
  assert(PublicSearchUI.isSafeUrl("http:////example.com/paper") === false, "http:////example.com/paper rejected (quad slash)");
  assert(PublicSearchUI.isSafeUrl("https://example.com/paper") === true, "normal HTTPS// safe URL accepted");

  // -------------------------------------------------------------
  // SUITE 2: Strict Envelope & Contract Validation (8 Probes + Boundaries)
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 2: Strict Envelope & Schema Validation ---");
  const malformedCases = uiFixtures.fixtures.malformed_envelopes;
  for (const key of Object.keys(malformedCases)) {
    let threw = false;
    try {
      PublicSearchUI.validateEnvelope(malformedCases[key]);
    } catch (e) {
      threw = true;
    }
    assert(threw, "Malformed envelope detected and rejected: " + key);
  }

  // Explicit adversarial case: mutating error message in envelope vs snapshot.source_results.error
  {
    const ex = JSON.parse(JSON.stringify(uxExamples.examples.example_06_tt05_success_plus_failed_partial_failure_with_hits.envelope));
    PublicSearchUI.validateEnvelope(ex);
    ex.errors[0].message = "DIFFERENT evidence";
    let threw = false;
    try {
      PublicSearchUI.validateEnvelope(ex);
    } catch (e) {
      threw = true;
      assert(e.message.includes("mismatch"), "Mismatched error evidence throws specific mismatch error");
    }
    assert(threw, "Adversarial: envelope.errors[0].message mismatch with snapshot error is detected and rejected");
  }

  // Adversarial probes for Finding 1: validateSourceResult strict field requirements & types
  {
    const baseEx = JSON.parse(JSON.stringify(uxExamples.examples.example_03_tt02_success_plus_empty_with_hit.envelope));
    PublicSearchUI.validateEnvelope(baseEx);

    // 1. Missing source_total
    const ex1 = JSON.parse(JSON.stringify(baseEx));
    delete ex1.snapshot.source_results[0].source_total;
    let threw1 = false;
    try { PublicSearchUI.validateEnvelope(ex1); } catch (e) { threw1 = true; }
    assert(threw1, "Adversarial Finding 1: missing source_total is rejected");

    // 2. Missing truncated
    const ex2 = JSON.parse(JSON.stringify(baseEx));
    delete ex2.snapshot.source_results[0].truncated;
    let threw2 = false;
    try { PublicSearchUI.validateEnvelope(ex2); } catch (e) { threw2 = true; }
    assert(threw2, "Adversarial Finding 1: missing truncated is rejected");

    // 3. Missing elapsed_seconds
    const ex3 = JSON.parse(JSON.stringify(baseEx));
    delete ex3.snapshot.source_results[0].elapsed_seconds;
    let threw3 = false;
    try { PublicSearchUI.validateEnvelope(ex3); } catch (e) { threw3 = true; }
    assert(threw3, "Adversarial Finding 1: missing elapsed_seconds is rejected");

    // 4. source_total is string
    const ex4 = JSON.parse(JSON.stringify(baseEx));
    ex4.snapshot.source_results[0].source_total = "invalid_string";
    let threw4 = false;
    try { PublicSearchUI.validateEnvelope(ex4); } catch (e) { threw4 = true; }
    assert(threw4, "Adversarial Finding 1: string source_total is rejected");

    // 5. truncated is string
    const ex5 = JSON.parse(JSON.stringify(baseEx));
    ex5.snapshot.source_results[0].truncated = "not_a_bool";
    let threw5 = false;
    try { PublicSearchUI.validateEnvelope(ex5); } catch (e) { threw5 = true; }
    assert(threw5, "Adversarial Finding 1: non-boolean truncated is rejected");

    // 6. elapsed_seconds is string
    const ex6 = JSON.parse(JSON.stringify(baseEx));
    ex6.snapshot.source_results[0].elapsed_seconds = "0.5s";
    let threw6 = false;
    try { PublicSearchUI.validateEnvelope(ex6); } catch (e) { threw6 = true; }
    assert(threw6, "Adversarial Finding 1: non-float elapsed_seconds is rejected");

    // 7. not_requested with observations
    const ex7 = JSON.parse(JSON.stringify(baseEx));
    ex7.snapshot.source_results[0].status = "not_requested";
    ex7.snapshot.source_results[0].source_total = 5;
    let threw7 = false;
    try { PublicSearchUI.validateEnvelope(ex7); } catch (e) { threw7 = true; }
    assert(threw7, "Adversarial Finding 1: not_requested with non-null source_total is rejected");
  }

  // Adversarial probes for Finding 2: isIsoTimeWithTz rejects year 0000 and invalid timezone offsets
  {
    assert(PublicSearchUI.isIsoTimeWithTz("0000-01-01T00:00:00Z") === false, "Adversarial Finding 2: year 0000 is rejected");
    assert(PublicSearchUI.isIsoTimeWithTz("2026-01-01T00:00:00+23:59") === false, "Adversarial Finding 2: timezone offset +23:59 is rejected");
    assert(PublicSearchUI.isIsoTimeWithTz("2026-01-01T00:00:00-23:59") === false, "Adversarial Finding 2: timezone offset -23:59 is rejected");
    assert(PublicSearchUI.isIsoTimeWithTz("2026-01-01T00:00:00+24:00") === false, "Adversarial Finding 2: timezone offset +24:00 is rejected");
    assert(PublicSearchUI.isIsoTimeWithTz("2026-09-30T08:12:00+07:00") === true, "Adversarial Finding 2: valid Vietnam offset +07:00 is accepted");
    assert(PublicSearchUI.isIsoTimeWithTz("2026-09-30T14:00:00Z") === true, "Adversarial Finding 2: valid UTC Z timestamp is accepted");

    // Envelope level calendar rejection
    const baseEx = JSON.parse(JSON.stringify(uxExamples.examples.example_03_tt02_success_plus_empty_with_hit.envelope));
    const badYearEx = JSON.parse(JSON.stringify(baseEx));
    badYearEx.snapshot.fetched_at = "0000-01-01T00:00:00Z";
    let threwYear = false;
    try { PublicSearchUI.validateEnvelope(badYearEx); } catch (e) { threwYear = true; }
    assert(threwYear, "Adversarial Finding 2: envelope with year 0000 fetched_at is rejected");

    const badTzEx = JSON.parse(JSON.stringify(baseEx));
    badTzEx.snapshot.fetched_at = "2026-01-01T00:00:00+23:59";
    let threwTz = false;
    try { PublicSearchUI.validateEnvelope(badTzEx); } catch (e) { threwTz = true; }
    assert(threwTz, "Adversarial Finding 2: envelope with offset +23:59 fetched_at is rejected");
  }

  // -------------------------------------------------------------
  // SUITE 3: Truth Table Cases (TT-01..TT-07)
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 3: Truth Table Cases (TT-01..TT-07) ---");
  const examples = uxExamples.examples;

  // TT-01: All Empty
  {
    const ex = examples.example_02_tt01_all_empty;
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ex.envelope, false);
    const results = doc.getElementById("results");
    assert(results.textContent.includes("Không tìm thấy bài báo nào khớp"), "TT-01 renders empty message");
  }

  // TT-02: Success + Empty with Hit
  {
    const ex = examples.example_03_tt02_success_plus_empty_with_hit;
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ex.envelope, false);
    const results = doc.getElementById("results");
    assert(results.children.length === 1, "TT-02 renders 1 hit");
    const sourcesSummary = doc.getElementById("sources-summary");
    assert(!sourcesSummary.hidden, "TT-02 displays sources summary");
  }

  // TT-03: Success Filtered to Zero (Synthetic Own Fixture)
  {
    const synEx = uiFixtures.fixtures.synthetic_tt03_filtered_zero;
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(synEx, false);
    const results = doc.getElementById("results");
    assert(results.textContent.includes("nằm ngoài khoảng năm đã lọc"), "TT-03 explains excluded_by_year filter");
    assert(results.textContent.includes("2 bài bị loại"), "TT-03 shows exact 2 papers excluded count");

    // Also verify example_04 renders without crashing
    const ex04 = examples.example_04_tt03_success_sources_filtered_to_zero;
    const doc04 = createMockDOM();
    PublicSearchUI.init({ document: doc04 });
    PublicSearchUI.renderSearchResults(ex04.envelope, false);
    const results04 = doc04.getElementById("results");
    assert(results04.textContent.includes("Không tìm thấy"), "TT-03 frozen example_04 renders empty message safely");
  }

  // TT-04: Empty + Failed (No Hit, Partial Failure)
  {
    const ex = examples.example_05_tt04_empty_plus_failed_no_hit;
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ex.envelope, false);
    const banner = doc.getElementById("banner-region");
    assert(banner.textContent.includes("partial_failure"), "TT-04 shows partial_failure warning banner, not silent empty!");
  }

  // TT-05: Success + Failed with Hit (Partial Failure)
  {
    const ex = examples.example_06_tt05_success_plus_failed_partial_failure_with_hits;
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ex.envelope, false);
    const banner = doc.getElementById("banner-region");
    assert(banner.textContent.includes("partial_failure"), "TT-05 shows partial_failure banner");
    const results = doc.getElementById("results");
    assert(results.children.length > 0, "TT-05 renders valid hits from surviving source");
  }

  // TT-06: All Failed (Mixed Precedence: Quota + Schema error both shown)
  {
    const ex = examples.example_07_tt06_all_failed_mixed_precedence;
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ex.envelope, false);
    const banner = doc.getElementById("banner-region");
    assert(banner.textContent.includes("giới hạn lượt truy cập"), "TT-06 shows quota warning banner");
    assert(banner.textContent.includes("Lỗi truy vấn nguồn arxiv"), "TT-06 shows schema failure banner (not masked by quota)");
  }

  // TT-07: 422 Invalid Request
  {
    const ex = examples.example_08_tt07_invalid_request_422;
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    // TT-07 is a SearchRequest validation payload, not a SearchEnvelope.
    // Exercise the UI's strict request validator directly instead of inventing
    // an envelope or dereferencing a missing synthetic field.
    let rejected = false;
    try {
      PublicSearchUI.validateSearchRequest(ex.invalid_request_payload);
    } catch (err) {
      rejected = true;
    }
    assert(rejected, "TT-07 rejects invalid SearchRequest payload");
    PublicSearchUI.addBanner("error", "Lỗi truy vấn (HTTP 422): yêu cầu không hợp lệ");
    const banner = doc.getElementById("banner-region");
    assert(banner.textContent.includes("Lỗi truy vấn"), "TT-07 displays 422 request error banner");
    const results = doc.getElementById("results");
    assert(results.children.length === 0, "TT-07 hides result list on failed request");
  }

  // -------------------------------------------------------------
  // SUITE 4: XSS Prevention & textContent Enforcement
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 4: XSS Prevention & Safe Rendering ---");
  {
    const ex = examples.example_01_success_dedup_rrf_and_missing_fields;
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ex.envelope, false);

    const hit = ex.envelope.snapshot.fusion.hits[0];
    const card = PublicSearchUI.createResultCard(hit);
    assert(card.innerHTML.indexOf("<script>") === -1, "Result card does not contain unescaped script tags");
  }

  // -------------------------------------------------------------
  // SUITE 5: Snapshot Pagination (Wording, Local Slice, API Call & Race Guard)
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 5: Snapshot Pagination & Monotonic Sequence ---");
  {
    const doc = createMockDOM();
    const ex = examples.example_01_success_dedup_rrf_and_missing_fields;
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(ex.envelope, false);

    const pagNav = doc.getElementById("snapshot-pagination");
    assert(!pagNav.hidden, "Snapshot pagination nav is visible");
    const info = doc.getElementById("snapshot-pagination-info");
    assert(info.textContent.startsWith("Trang 1 / "), "Pagination info starts with Trang 1 / ...");
    assert(info.textContent.includes("trên Snapshot #" + ex.envelope.snapshot.snapshot_id), "Pagination mentions snapshot id");

    const btnPrev = doc.getElementById("btn-snapshot-prev");
    const btnNext = doc.getElementById("btn-snapshot-next");
    assert(btnPrev && btnPrev.disabled === true, "Prev button is disabled on page 1");
    assert(btnNext !== null, "Next button is present");

    // Test page change fetch
    let requestedUrl = null;
    const pagedFetch = async (url) => {
      requestedUrl = url;
      return {
        ok: true,
        status: 200,
        json: async () => ex.envelope
      };
    };
    PublicSearchUI.init({ document: doc, fetchFn: pagedFetch });
    await PublicSearchUI.changeSnapshotPage(ex.envelope.snapshot.snapshot_id, 2);
    assert(requestedUrl && requestedUrl.includes("/public/results/"), "Pagination calls GET /public/results/{id}");
    assert(requestedUrl.includes("offset=10&limit=10"), "Pagination passes offset and limit");
  }

  // -------------------------------------------------------------
  // SUITE 6: Refresh Failure, Prior Snapshot Review & True TTL Comparison
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 6: Refresh Failure & True TTL Badge ---");
  {
    const doc = createMockDOM();
    const successEx = examples.example_03_tt02_success_plus_empty_with_hit;
    PublicSearchUI.init({ document: doc });
    PublicSearchUI.renderSearchResults(successEx.envelope, false);

    // Refresh fails
    const failFetch = async () => {
      throw new Error("Upstream 504 Gateway Timeout");
    };
    PublicSearchUI.init({ document: doc, fetchFn: failFetch });
    doc.getElementById("q").value = "graph mining";
    await PublicSearchUI.handleSearchSubmit(true);

    const staleBox = doc.getElementById("stale-review-region");
    assert(!staleBox.hidden, "Refresh failure displays stale snapshot review box");
    const btnStale = doc.getElementById("btn-view-previous-snapshot");
    assert(btnStale !== null, "Review previous snapshot button is present");

    // Click view previous snapshot (its expires_at is in future 2026-09-30T15:00:00+07:00 or future)
    btnStale.click();
    const snapBanner = doc.getElementById("snapshot-meta-banner");
    assert(snapBanner.textContent.includes("Snapshot #"), "Viewing prior snapshot renders snapshot meta banner");
  }

  // -------------------------------------------------------------
  // SUITE 7: Library Operations (Idempotent Save, Active Snapshot Provenance, Double-Click Guard)
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 7: Library Operations & Idempotent Save ---");
  {
    const doc = createMockDOM();
    const libData = uiFixtures.fixtures.idempotent_library_save;
    let savedHit = null;

    let postCount = 0;
    let postedPayload = null;
    let savedEntry = null;
    const libraryFetch = async (url, opts) => {
      if (opts && opts.method === "POST") {
        postCount++;
        postedPayload = JSON.parse(opts.body);
        if (!savedHit) {
          throw new Error("Harness fixture missing saved hit before POST");
        }
        savedEntry = {
          ...libData,
          canonical_id: postedPayload.canonical_id,
          snapshot_id: postedPayload.snapshot_id,
          hit: savedHit
        };
        return {
          ok: true,
          status: 200,
          json: async () => savedEntry
        };
      }
      return { ok: true, status: 200, json: async () => (savedEntry ? [savedEntry] : [libData]) };
    };

    PublicSearchUI.init({ document: doc, fetchFn: libraryFetch });

    // Render partial failure search result
    const partialEx = examples.example_06_tt05_success_plus_failed_partial_failure_with_hits;
    PublicSearchUI.renderSearchResults(partialEx.envelope, false);

    const hit = partialEx.envelope.snapshot.fusion.hits[0];
    savedHit = hit;
    const btnSave = doc.createElement("button");
    btnSave.className = "btn btn-primary";
    doc.body.appendChild(btnSave);

    // Save hit from partial snapshot
    const p1 = PublicSearchUI.savePaperToLibrary(hit, btnSave);
    // Double call should be guarded
    const p2 = PublicSearchUI.savePaperToLibrary(hit, btnSave);
    await Promise.all([p1, p2]);

    assert(postCount === 1, "Inflight double-call guarded: exactly 1 POST request sent");
    assert(postedPayload.snapshot_id === partialEx.envelope.snapshot.snapshot_id, "Saved paper uses active displayedSnapshot id");
    assert(btnSave.textContent.includes("save_idempotent"), "Button updated to save_idempotent state");

    // Load library (self-consistent response returns saved paper)
    await PublicSearchUI.loadLibrary(0, 10);
    const libList = doc.getElementById("library-list");
    assert(libList.children.length === 1, "Library loaded 1 saved paper");
    const badge = doc.getElementById("library-count-badge");
    assert(badge.textContent.includes("1 đã tải"), "Library badge shows truthful loaded count");

    // Adversarial Finding 3: duplicate save from newer snapshot preserves existing entry with original snapshot_id
    {
      const docIdemp = createMockDOM();
      const originalSnapId = "snap_original_stored_001";
      // Use a fresh canonical id so this isolated duplicate-save probe is not
      // short-circuited by the module-level saved-id set from the prior case.
      const hitToSave = JSON.parse(JSON.stringify(partialEx.envelope.snapshot.fusion.hits[0]));
      hitToSave.canonical_id = hitToSave.canonical_id + "_idempotent_probe";
      const origEntry = {
        ...libData,
        canonical_id: hitToSave.canonical_id,
        snapshot_id: originalSnapId,
        hit: hitToSave,
        saved_at: "2026-09-30T12:00:00+07:00",
        incomplete_sources: false
      };
      PublicSearchUI.init({
        document: docIdemp,
        fetchFn: async (url, opts) => {
          if (opts && opts.method === "POST") {
            return {
              ok: true,
              status: 200,
              json: async () => origEntry
            };
          }
          return { ok: true, status: 200, json: async () => [origEntry] };
        }
      });
      PublicSearchUI.renderSearchResults(partialEx.envelope, false);
      const btnIdemp = docIdemp.createElement("button");
      btnIdemp.className = "btn btn-primary";
      docIdemp.body.appendChild(btnIdemp);

      await PublicSearchUI.savePaperToLibrary(hitToSave, btnIdemp);
      const banners = docIdemp.getElementById("banner-region");
      assert(!banners.textContent.includes("Lưu bài báo thất bại"), "Adversarial Finding 3: duplicate save preserving store original snapshot_id does not show failure banner");
      assert(btnIdemp.textContent.includes("save_idempotent"), "Adversarial Finding 3: duplicate save updates button to save_idempotent state");

      // Verify negative case: mismatching canonical_id from store MUST be rejected (no weakened validation)
      const docBad = createMockDOM();
      const badRequestedHit = JSON.parse(JSON.stringify(hitToSave));
      badRequestedHit.canonical_id = badRequestedHit.canonical_id + "_bad_probe";
      PublicSearchUI.init({
        document: docBad,
        fetchFn: async () => ({
          ok: true,
          status: 200,
          json: async () => ({
            ...origEntry,
            canonical_id: "mismatched_canonical_id_xyz",
            hit: { ...hitToSave, canonical_id: "mismatched_canonical_id_xyz" }
          })
        })
      });
      PublicSearchUI.renderSearchResults(partialEx.envelope, false);
      const btnBad = docBad.createElement("button");
      btnBad.className = "btn btn-primary";
      docBad.body.appendChild(btnBad);

      await PublicSearchUI.savePaperToLibrary(badRequestedHit, btnBad);
      const badBanner = docBad.getElementById("banner-region");
      assert(badBanner.textContent.includes("Lưu bài báo thất bại"), "Adversarial Finding 3: mismatched canonical_id response fails loud with error banner");
      assert(!btnBad.textContent.includes("save_idempotent"), "Adversarial Finding 3: mismatched canonical_id does not update button to save_idempotent");
    }
  }

  // -------------------------------------------------------------
  // SUITE 8: Detail Conflicts Rendering & Anti-Silent-Bypass
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 8: Detail Conflicts Rendering ---");
  {
    const doc = createMockDOM();
    PublicSearchUI.init({ document: doc });

    const conflictedHit = {
      canonical_id: "W_CONFLICT_01",
      rank: 1,
      score: 0.03,
      display: {
        source: "openalex",
        source_id: "W111",
        title: "Conflicted Paper Title",
        landing_url: "https://openalex.org/W111",
        retrieved_at: "2026-09-30T10:00:00+07:00",
        raw_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        parser_version: "1.0.0",
        abstract: "Abstract text",
        publication_year: 2024,
        doi: null,
        arxiv_id: null,
        venue: null,
        pdf_url: null,
        license: null,
        open_access_status: null,
        citation_count: null,
        authors: null,
        authors_availability: "missing",
        missing_fields: ["doi", "arxiv_id", "venue", "pdf_url", "license", "open_access_status", "citation_count", "authors"],
        field_provenance: {
          title: [{"source": "openalex", "source_id": "W111", "raw_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "raw_field": "title"}],
          source_id: [{"source": "openalex", "source_id": "W111", "raw_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "raw_field": "id"}],
          landing_url: [{"source": "openalex", "source_id": "W111", "raw_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "raw_field": "id"}],
          abstract: [{"source": "openalex", "source_id": "W111", "raw_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "raw_field": "abstract"}],
          publication_year: [{"source": "openalex", "source_id": "W111", "raw_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "raw_field": "publication_year"}]
        }
      },
      source_records: [],
      source_ranks: { openalex: 1 },
      conflicts: {
        publication_year: [
          { source: "openalex", source_id: "W111", raw_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", raw_field: "publication_year: 2024" },
          { source: "arxiv", source_id: "2401.00001", raw_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", raw_field: "atom:published: 2023" }
        ]
      }
    };

    PublicSearchUI.showDetailPanel(conflictedHit);
    const detailBody = doc.getElementById("detail-body");
    assert(detailBody.textContent.includes("Đối chiếu xung đột metadata"), "Detail panel renders conflicts section");
    assert(detailBody.textContent.includes("publication_year"), "Detail panel lists conflicted field name");
    assert(detailBody.textContent.includes("2024"), "Detail panel displays evidence rows");
  }

  // -------------------------------------------------------------
  // SUITE 9: Export Library (JSON & BibTeX) & Anti-Silent-Bypass
  // -------------------------------------------------------------
  console.log("\n--- Test Suite 9: Library Export & Error Handling ---");
  {
    const doc = createMockDOM();
    const exportFetch = async (url) => {
      if (url.includes("format=500")) {
        return { ok: false, status: 500 };
      }
      return { ok: true, status: 200, text: async () => "@article{test, title={Paper}}" };
    };

    PublicSearchUI.init({ document: doc, fetchFn: exportFetch });

    // 1. Success export with working Blob & URL.createObjectURL
    await PublicSearchUI.exportLibrary("bibtex");
    const banner = doc.getElementById("banner-region");
    assert(banner.textContent.includes("Đã xuất thư viện định dạng BIBTEX thành công"), "BibTeX export success banner shown");

    // 2. Failure export from non-2xx HTTP status
    await PublicSearchUI.exportLibrary("500");
    assert(banner.textContent.includes("Xuất thư viện thất bại: Lỗi máy chủ"), "Export 500 error handled gracefully with banner");

    // 3. Negative Anti-Silent-Bypass: missing Blob API must FAIL visibly (no fake success!)
    const savedBlob = global.Blob;
    try {
      global.Blob = undefined;
      PublicSearchUI.clearBanners();
      await PublicSearchUI.exportLibrary("bibtex");
      assert(banner.textContent.includes("Xuất thư viện thất bại: Không thể tải tệp: môi trường thiếu Blob API"), "Missing Blob fails explicitly with error banner");
      assert(!banner.textContent.includes("thành công"), "Missing Blob does NOT show fake success banner");
    } finally {
      global.Blob = savedBlob;
    }

    // 4. Negative Anti-Silent-Bypass: missing URL.createObjectURL must FAIL visibly
    const savedCreateObjectURL = global.URL.createObjectURL;
    try {
      global.URL.createObjectURL = undefined;
      PublicSearchUI.clearBanners();
      await PublicSearchUI.exportLibrary("json");
      assert(banner.textContent.includes("Xuất thư viện thất bại: Không thể tải tệp: môi trường thiếu URL.createObjectURL API"), "Missing createObjectURL fails explicitly with error banner");
      assert(!banner.textContent.includes("thành công"), "Missing createObjectURL does NOT show fake success banner");
    } finally {
      global.URL.createObjectURL = savedCreateObjectURL;
    }

    // 5. Negative Anti-Silent-Bypass: anchor click throwing must FAIL visibly
    const origCreateElement = doc.createElement.bind(doc);
    try {
      doc.createElement = function (tag) {
        const el = origCreateElement(tag);
        if (tag === "a") {
          el.click = function () {
            throw new Error("Simulated browser click permission denied");
          };
        }
        return el;
      };
      PublicSearchUI.clearBanners();
      await PublicSearchUI.exportLibrary("bibtex");
      assert(banner.textContent.includes("Xuất thư viện thất bại: Simulated browser click permission denied"), "Throwing click fails explicitly with error banner");
      assert(!banner.textContent.includes("thành công"), "Throwing click does NOT show fake success banner");
    } finally {
      doc.createElement = origCreateElement;
    }
  }

  console.log("\n=======================================================");
  console.log(`TOTAL TESTS: ${passedCount + failedCount} | PASSED: ${passedCount} | FAILED: ${failedCount}`);
  if (failedCount > 0) {
    console.error("FAILED SUITE!");
    process.exit(1);
  }
  console.log("ALL TESTS PASSED WITH EXIT CODE 0!");
  return 0;
}

// --- CLI ENTRY POINT ---
if (require.main === module) {
  const args = process.argv.slice(2);
  let uiFixtures = path.resolve(__dirname, "ui_fixtures.json");
  let uxExamples = path.resolve(__dirname, "../ux_examples.json");

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--fixtures" && args[i + 1]) {
      uiFixtures = path.resolve(args[i + 1]);
      i++;
    } else if (args[i] === "--ux-examples" && args[i + 1]) {
      uxExamples = path.resolve(args[i + 1]);
      i++;
    } else if (args[i] === "--help") {
      console.log("Usage: node node_test_runner.js [--fixtures <path>] [--ux-examples <path>]");
      process.exit(0);
    } else {
      console.error("FAIL: unrecognized argument:", args[i]);
      process.exit(1);
    }
  }

  runAllTests(uiFixtures, uxExamples).catch((err) => {
    console.error("Unhandled harness exception:", err);
    process.exit(1);
  });
}

module.exports = { runAllTests, createMockDOM, MockElement, MockDocument };
