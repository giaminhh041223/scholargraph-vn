/**
 * ScholarGraph VN — Public Paper Search Frontend (EXT-05A, Wave W2)
 *
 * Conforming strictly to:
 * - Anti-Silent-Bypass Protocol (no fake zeros, no empty strings hiding errors)
 * - Strict schema validators for all frozen models from contracts.py
 * - Safe URL Sanitization (native URL: http/https only, no credentials/control/backslash, valid port)
 * - No untrusted innerHTML (textContent and document.createElement throughout)
 * - AbortController + Monotonic Sequence race condition protection for search, page, and library
 * - Snapshot Paging (Trang X / Y trên Snapshot #id (chốt lúc fetched_at)) with local slice & GET /public/results/{id}
 * - Active displayedSnapshot provenance tracking for partial & historical hits
 * - Stale review with real TTL check against expires_at (no hardcoded stale=true)
 * - Truth Table Cases (TT-01..TT-07) and 9 Mandatory UI States
 * - Non-2xx HTTP Body Parsing & Partial Hits Rendering
 * - Idempotent Library Save & Offline JSON/BibTeX Export
 */

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.PublicSearchUI = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // --- HẰNG SỐ & CONFIG MẶC ĐỊNH ---
  const CONTRACT_VERSION = "1.0.0";
  const SCHEMA_VERSION = 1;
  const YEAR_MIN = 1800;
  const YEAR_MAX = 2100;
  const SNAPSHOT_PAGE_SIZE = 10;
  const LIBRARY_PAGE_SIZE = 10;

  // --- TRẠNG THÁI RUNTIME (BỌC TRONG CLOSURE) ---
  let envDocument = typeof document !== "undefined" ? document : null;
  let envFetch = typeof fetch !== "undefined" ? fetch.bind(typeof window !== "undefined" ? window : globalThis) : null;

  let currentSearchSeq = 0;
  let activeSearchAbortController = null;

  let currentLibrarySeq = 0;
  let activeLibraryAbortController = null;

  let displayedSnapshot = null;
  let lastSuccessfulSnapshot = null;
  let currentSnapshotPage = 1;

  let savedLibraryCanonicalIds = new Map(); // canonical_id -> saved_at
  const pendingSaveCanonicalIds = new Set();
  let isExporting = false;

  // =========================================================================
  // BỘ HÀM KIỂM TRA CƠ BẢN (STRICT VALIDATION HELPERS)
  // =========================================================================

  function hasExtraKeys(obj, allowedKeys) {
    const allowed = new Set(allowedKeys);
    for (const k of Object.keys(obj)) {
      if (!allowed.has(k)) {
        return k;
      }
    }
    return null;
  }

  function isStrictInteger(val) {
    return typeof val === "number" && Number.isInteger(val) && Number.isFinite(val);
  }

  function isStrictFloat(val) {
    return typeof val === "number" && !Number.isNaN(val) && Number.isFinite(val);
  }

  function isNonEmptyString(val) {
    return typeof val === "string" && val.trim().length > 0;
  }

  function isSha256(val) {
    return typeof val === "string" && /^[0-9a-f]{64}$/.test(val);
  }

  function isIsoTimeWithTz(val) {
    if (typeof val !== "string") return false;
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/.exec(val);
    if (!match) return false;

    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const hour = Number(match[4]);
    const min = Number(match[5]);
    const sec = Number(match[6]);
    const tz = match[7];

    // Python datetime contract: 1 <= year <= 9999 (rejects year 0000)
    if (year < 1 || year > 9999) return false;
    if (month < 1 || month > 12) return false;
    if (hour < 0 || hour > 23) return false;
    if (min < 0 || min > 59) return false;
    if (sec < 0 || sec > 59) return false;

    // Python contract / Speedate: ISO 8601 timezone offsets strictly within [-12:00, +14:00]
    // Rejects offsets outside valid range such as +23:59, -23:59, +24:00
    if (tz !== "Z") {
      const sign = tz.charAt(0);
      const tzH = Number(tz.slice(1, 3));
      const tzM = Number(tz.slice(4, 6));
      if (tzM < 0 || tzM > 59) return false;
      const totalTzMin = tzH * 60 + tzM;
      if (sign === "+" && totalTzMin > 14 * 60) return false;
      if (sign === "-" && totalTzMin > 12 * 60) return false;
    }

    const isLeap = (year % 4 === 0 && year % 100 !== 0) || (year % 400 === 0);
    const daysInMonths = [0, 31, isLeap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (day < 1 || day > daysInMonths[month]) return false;

    const t = new Date(val).getTime();
    return !Number.isNaN(t);
  }

  /**
   * Kiểm tra tính an toàn của URL (Safe URL Sanitization)
   * Đúng theo quy tắc tại contracts.py safe_url()
   */
  function isSafeUrl(url) {
    if (typeof url !== "string" || !url.trim()) return false;
    for (let i = 0; i < url.length; i++) {
      if (url.charCodeAt(i) <= 32 || url.charAt(i) === "\\") return false;
    }
    // Yêu cầu tiền tố http:// hoặc https:// tường minh không phân biệt hoa thường,
    // theo sau bởi authority hợp lệ không rỗng (loại bỏ https:example, http:/example, http:////example)
    const authMatch = /^https?:\/\/([^\/?#]+)/i.exec(url);
    if (!authMatch || !authMatch[1]) return false;
    if (authMatch[1].includes("@")) return false;

    try {
      const parsed = new URL(url);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
      if (parsed.username || parsed.password) return false;
      if (!parsed.hostname) return false;
      if (parsed.port !== "") {
        const p = Number(parsed.port);
        if (!Number.isInteger(p) || p < 0 || p > 65535) return false;
      }
      return true;
    } catch (e) {
      return false;
    }
  }

  // =========================================================================
  // BỘ XÁC THỰC CÁC ĐỐI TƯỢNG CONTRACT CHỐNG LỖI NGẦM (ANTI-SILENT-BYPASS)
  // =========================================================================

  function validateSearchRequest(req) {
    if (!req || typeof req !== "object") {
      throw new Error("SearchRequest phải là một đối tượng JSON");
    }
    const extra = hasExtraKeys(req, ["query", "sources", "top_k", "cap_per_source", "year_from", "year_to", "refresh"]);
    if (extra) {
      throw new Error("SearchRequest chứa trường không được phép (extra forbidden): " + extra);
    }
    if (!isNonEmptyString(req.query) || req.query.trim().length > 500) {
      throw new Error("SearchRequest.query phải là chuỗi có độ dài 1..500 ký tự");
    }
    if (!Array.isArray(req.sources) || req.sources.length === 0) {
      throw new Error("SearchRequest.sources phải là mảng không rỗng");
    }
    const validSources = ["openalex", "arxiv"];
    const seenSources = new Set();
    for (const s of req.sources) {
      if (!validSources.includes(s) || seenSources.has(s)) {
        throw new Error("SearchRequest.sources chứa nguồn không hợp lệ hoặc bị trùng lặp: " + s);
      }
      seenSources.add(s);
    }
    if (!isStrictInteger(req.top_k) || req.top_k < 1 || req.top_k > 50) {
      throw new Error("SearchRequest.top_k phải là số nguyên trong khoảng 1..50");
    }
    if (!isStrictInteger(req.cap_per_source) || req.cap_per_source < 1 || req.cap_per_source > 50) {
      throw new Error("SearchRequest.cap_per_source phải là số nguyên trong khoảng 1..50");
    }
    if (req.year_from !== null && (!isStrictInteger(req.year_from) || req.year_from < YEAR_MIN || req.year_from > YEAR_MAX)) {
      throw new Error("SearchRequest.year_from phải là null hoặc số nguyên 1800..2100");
    }
    if (req.year_to !== null && (!isStrictInteger(req.year_to) || req.year_to < YEAR_MIN || req.year_to > YEAR_MAX)) {
      throw new Error("SearchRequest.year_to phải là null hoặc số nguyên 1800..2100");
    }
    if (req.year_from !== null && req.year_to !== null && req.year_from > req.year_to) {
      throw new Error("SearchRequest: year bounds reversed (year_from > year_to)");
    }
    if (req.refresh !== undefined && typeof req.refresh !== "boolean") {
      throw new Error("SearchRequest.refresh phải là boolean nếu có");
    }
    return true;
  }

  function validateSearchError(err) {
    if (!err || typeof err !== "object") {
      throw new Error("SearchError phải là một đối tượng JSON");
    }
    const extra = hasExtraKeys(err, ["kind", "message", "source", "retry_after_seconds", "record_index"]);
    if (extra) {
      throw new Error("SearchError chứa trường không được phép (extra forbidden): " + extra);
    }
    const validKinds = ["request", "config", "policy", "auth", "quota", "timeout", "upstream", "schema", "storage"];
    if (!validKinds.includes(err.kind)) {
      throw new Error("SearchError.kind không hợp lệ: " + err.kind);
    }
    if (!isNonEmptyString(err.message)) {
      throw new Error("SearchError.message phải là chuỗi không rỗng");
    }
    if (err.source !== null && err.source !== "openalex" && err.source !== "arxiv") {
      throw new Error("SearchError.source không hợp lệ: " + err.source);
    }
    if (err.retry_after_seconds !== null && (!isStrictFloat(err.retry_after_seconds) || err.retry_after_seconds < 0)) {
      throw new Error("SearchError.retry_after_seconds phải là null hoặc số thực không âm");
    }
    if (err.record_index !== null && (!isStrictInteger(err.record_index) || err.record_index < 0)) {
      throw new Error("SearchError.record_index phải là null hoặc số nguyên không âm");
    }
    return true;
  }

  function validateRawReference(ref) {
    if (!ref || typeof ref !== "object") {
      throw new Error("RawReference phải là đối tượng JSON");
    }
    const extra = hasExtraKeys(ref, ["raw_id", "sha256", "byte_count"]);
    if (extra) {
      throw new Error("RawReference chứa trường không được phép: " + extra);
    }
    if (!isNonEmptyString(ref.raw_id)) {
      throw new Error("RawReference.raw_id phải là chuỗi không rỗng");
    }
    if (!isSha256(ref.sha256)) {
      throw new Error("RawReference.sha256 phải là mã băm 64 ký tự hex hợp lệ");
    }
    if (!isStrictInteger(ref.byte_count) || ref.byte_count < 0) {
      throw new Error("RawReference.byte_count phải là số nguyên không âm");
    }
    return true;
  }

  function validateFieldEvidence(ev) {
    if (!ev || typeof ev !== "object") {
      throw new Error("FieldEvidence phải là đối tượng JSON");
    }
    const extra = hasExtraKeys(ev, ["source", "source_id", "raw_sha256", "raw_field"]);
    if (extra) {
      throw new Error("FieldEvidence chứa trường không được phép: " + extra);
    }
    if (ev.source !== "openalex" && ev.source !== "arxiv") {
      throw new Error("FieldEvidence.source không hợp lệ: " + ev.source);
    }
    if (!isNonEmptyString(ev.source_id)) {
      throw new Error("FieldEvidence.source_id phải là chuỗi không rỗng");
    }
    if (!isSha256(ev.raw_sha256)) {
      throw new Error("FieldEvidence.raw_sha256 phải là mã băm 64 ký tự hex hợp lệ");
    }
    if (!isNonEmptyString(ev.raw_field)) {
      throw new Error("FieldEvidence.raw_field phải là chuỗi không rỗng");
    }
    return true;
  }

  function validatePaperRecord(rec) {
    if (!rec || typeof rec !== "object") {
      throw new Error("PaperRecord phải là đối tượng JSON");
    }
    const allowed = [
      "source", "source_id", "title", "landing_url", "retrieved_at", "raw_sha256", "parser_version",
      "abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url", "license",
      "open_access_status", "citation_count", "authors", "authors_availability", "missing_fields", "field_provenance"
    ];
    const extra = hasExtraKeys(rec, allowed);
    if (extra) {
      throw new Error("PaperRecord chứa trường không được phép: " + extra);
    }

    // Kiểm tra tất cả các trường bắt buộc phải present
    for (const key of allowed) {
      if (!(key in rec)) {
        throw new Error("PaperRecord thiếu trường bắt buộc (kể cả nullable): " + key);
      }
    }

    if (rec.source !== "openalex" && rec.source !== "arxiv") {
      throw new Error("PaperRecord.source không hợp lệ: " + rec.source);
    }
    if (!isNonEmptyString(rec.source_id)) {
      throw new Error("PaperRecord.source_id phải là chuỗi không rỗng");
    }
    if (!isNonEmptyString(rec.title)) {
      throw new Error("PaperRecord.title phải là chuỗi không rỗng");
    }
    if (!isSafeUrl(rec.landing_url)) {
      throw new Error("PaperRecord.landing_url không an toàn hoặc không hợp lệ: " + rec.landing_url);
    }
    if (!isIsoTimeWithTz(rec.retrieved_at)) {
      throw new Error("PaperRecord.retrieved_at phải là ISO timestamp kèm timezone");
    }
    if (!isSha256(rec.raw_sha256)) {
      throw new Error("PaperRecord.raw_sha256 phải là 64 ký tự hex");
    }
    if (!isNonEmptyString(rec.parser_version)) {
      throw new Error("PaperRecord.parser_version phải là chuỗi không rỗng");
    }

    // Các trường nullable
    if (rec.abstract !== null && !isNonEmptyString(rec.abstract)) {
      throw new Error("PaperRecord.abstract phải là null hoặc chuỗi không rỗng");
    }
    if (rec.publication_year !== null && (!isStrictInteger(rec.publication_year) || rec.publication_year < YEAR_MIN || rec.publication_year > YEAR_MAX)) {
      throw new Error("PaperRecord.publication_year phải là null hoặc số nguyên 1800..2100");
    }
    if (rec.doi !== null && (!isNonEmptyString(rec.doi) || !/^10\.\d{4,9}\/[^\s]+$/i.test(rec.doi))) {
      throw new Error("PaperRecord.doi phải là null hoặc định dạng chuẩn 10.xxxx/...");
    }
    if (rec.arxiv_id !== null && !isNonEmptyString(rec.arxiv_id)) {
      throw new Error("PaperRecord.arxiv_id phải là null hoặc chuỗi không rỗng");
    }
    if (rec.venue !== null && !isNonEmptyString(rec.venue)) {
      throw new Error("PaperRecord.venue phải là null hoặc chuỗi không rỗng");
    }
    if (rec.pdf_url !== null && !isSafeUrl(rec.pdf_url)) {
      throw new Error("PaperRecord.pdf_url phải là null hoặc URL an toàn");
    }
    if (rec.license !== null && !isNonEmptyString(rec.license)) {
      throw new Error("PaperRecord.license phải là null hoặc chuỗi không rỗng");
    }
    if (rec.open_access_status !== null && !["open", "closed", "unknown"].includes(rec.open_access_status)) {
      throw new Error("PaperRecord.open_access_status không hợp lệ: " + rec.open_access_status);
    }
    if (rec.citation_count !== null && (!isStrictInteger(rec.citation_count) || rec.citation_count < 0)) {
      throw new Error("PaperRecord.citation_count phải là null hoặc số nguyên không âm");
    }
    if (rec.authors !== null) {
      if (!Array.isArray(rec.authors)) {
        throw new Error("PaperRecord.authors phải là null hoặc mảng các chuỗi");
      }
      for (const a of rec.authors) {
        if (!isNonEmptyString(a)) {
          throw new Error("PaperRecord.authors chứa phần tử không phải chuỗi không rỗng");
        }
      }
    }

    if (!["known", "missing"].includes(rec.authors_availability)) {
      throw new Error("PaperRecord.authors_availability phải là 'known' hoặc 'missing'");
    }
    if ((rec.authors === null) !== (rec.authors_availability === "missing")) {
      throw new Error("PaperRecord: authors availability mismatch");
    }

    // Invariant: missing_fields
    const nullableFields = ["abstract", "publication_year", "doi", "arxiv_id", "venue", "pdf_url", "license", "open_access_status", "citation_count", "authors"];
    const expectedMissing = new Set(nullableFields.filter(f => rec[f] === null));
    if (!Array.isArray(rec.missing_fields)) {
      throw new Error("PaperRecord.missing_fields phải là mảng");
    }
    const actualMissing = new Set(rec.missing_fields);
    if (actualMissing.size !== expectedMissing.size || rec.missing_fields.length !== expectedMissing.size) {
      throw new Error("PaperRecord.missing_fields không khớp chính xác các trường null");
    }
    for (const m of expectedMissing) {
      if (!actualMissing.has(m)) {
        throw new Error("PaperRecord.missing_fields thiếu trường null: " + m);
      }
    }

    // Invariant: field_provenance
    if (!rec.field_provenance || typeof rec.field_provenance !== "object" || Array.isArray(rec.field_provenance)) {
      throw new Error("PaperRecord.field_provenance phải là đối tượng bản đồ");
    }
    const presentFields = new Set(["title", "source_id", "landing_url"]);
    for (const f of nullableFields) {
      if (rec[f] !== null) presentFields.add(f);
    }
    const provKeys = new Set(Object.keys(rec.field_provenance));
    if (provKeys.size !== presentFields.size) {
      throw new Error("PaperRecord.field_provenance phải có mặt cho đúng tất cả các trường hiện diện");
    }
    for (const pf of presentFields) {
      if (!provKeys.has(pf)) {
        throw new Error("PaperRecord.field_provenance thiếu dấu vết nguồn cho trường: " + pf);
      }
      const evList = rec.field_provenance[pf];
      if (!Array.isArray(evList) || evList.length === 0) {
        throw new Error("PaperRecord.field_provenance[" + pf + "] phải là mảng không rỗng");
      }
      for (const ev of evList) {
        validateFieldEvidence(ev);
        if (ev.source !== rec.source || ev.source_id !== rec.source_id || ev.raw_sha256 !== rec.raw_sha256) {
          throw new Error("PaperRecord.field_provenance[" + pf + "] không khớp source/source_id/raw_sha256 của bản ghi");
        }
      }
    }

    return true;
  }

  function validateSourceResult(res) {
    if (!res || typeof res !== "object" || Array.isArray(res)) {
      throw new Error("SourceResult phải là đối tượng JSON");
    }
    const requiredKeys = ["source", "status", "records", "error", "source_total", "elapsed_seconds", "filter_coverage", "truncated", "raw_references"];
    const extra = hasExtraKeys(res, requiredKeys);
    if (extra) {
      throw new Error("SourceResult chứa trường không được phép: " + extra);
    }
    for (const key of requiredKeys) {
      if (!Object.prototype.hasOwnProperty.call(res, key)) {
        throw new Error("SourceResult thiếu trường bắt buộc: " + key);
      }
    }
    if (res.source !== "openalex" && res.source !== "arxiv") {
      throw new Error("SourceResult.source không hợp lệ: " + res.source);
    }
    const validStatuses = ["success", "empty", "failed", "not_requested"];
    if (!validStatuses.includes(res.status)) {
      throw new Error("SourceResult.status không hợp lệ: " + res.status);
    }
    if (!Array.isArray(res.records)) {
      throw new Error("SourceResult.records phải là mảng");
    }
    if (!["server", "bounded_pool", "none"].includes(res.filter_coverage)) {
      throw new Error("SourceResult.filter_coverage không hợp lệ: " + res.filter_coverage);
    }
    if (!Array.isArray(res.raw_references)) {
      throw new Error("SourceResult.raw_references phải là mảng");
    }

    // Exact type and range validation (nullable fields per frozen contract)
    if (res.source_total !== null && (!isStrictInteger(res.source_total) || res.source_total < 0)) {
      throw new Error("SourceResult.source_total phải là số nguyên không âm hoặc null");
    }
    if (res.elapsed_seconds !== null && (!isStrictFloat(res.elapsed_seconds) || res.elapsed_seconds < 0)) {
      throw new Error("SourceResult.elapsed_seconds phải là số thực không âm hoặc null");
    }
    if (res.truncated !== null && typeof res.truncated !== "boolean") {
      throw new Error("SourceResult.truncated phải là boolean hoặc null");
    }

    // Coherence checks
    if ((res.status === "failed") !== (res.error !== null)) {
      throw new Error("SourceResult: failed requires error; other statuses forbid error");
    }
    if (res.error !== null) {
      validateSearchError(res.error);
      if (res.error.source !== res.source) {
        throw new Error("SourceResult.error.source không khớp source");
      }
    }
    if (res.status === "success" && res.records.length === 0) {
      throw new Error("SourceResult: success requires records");
    }
    if (res.status !== "success" && res.records.length > 0) {
      throw new Error("SourceResult: only successful source exposes validated records");
    }

    if (res.status === "not_requested") {
      if (res.filter_coverage !== "none") {
        throw new Error("SourceResult: not_requested requires filter_coverage=none");
      }
      if (res.raw_references.length > 0 || res.elapsed_seconds !== null || res.source_total !== null || res.truncated !== null) {
        throw new Error("SourceResult: not_requested must not claim observations");
      }
    } else {
      if (res.elapsed_seconds === null) {
        throw new Error("SourceResult: attempted source requires elapsed time");
      }
    }

    for (const ref of res.raw_references) {
      validateRawReference(ref);
    }
    const rawHashes = new Set(res.raw_references.map(r => r.sha256));
    for (const rec of res.records) {
      validatePaperRecord(rec);
      if (rec.source !== res.source || !rawHashes.has(rec.raw_sha256)) {
        throw new Error("SourceResult.records chứa bản ghi không khớp source hoặc raw_sha256");
      }
    }

    return true;
  }

  function validateRankedHit(hit) {
    if (!hit || typeof hit !== "object") {
      throw new Error("RankedHit phải là đối tượng JSON");
    }
    const allowed = ["canonical_id", "rank", "score", "display", "source_records", "source_ranks", "conflicts"];
    const extra = hasExtraKeys(hit, allowed);
    if (extra) {
      throw new Error("RankedHit chứa trường không được phép: " + extra);
    }
    if (!isNonEmptyString(hit.canonical_id)) {
      throw new Error("RankedHit.canonical_id phải là chuỗi không rỗng");
    }
    if (!isStrictInteger(hit.rank) || hit.rank < 1) {
      throw new Error("RankedHit.rank phải là số nguyên >= 1");
    }
    if (!isStrictFloat(hit.score) || hit.score <= 0) {
      throw new Error("RankedHit.score phải là số thực hữu hạn > 0");
    }

    validatePaperRecord(hit.display);
    if (!Array.isArray(hit.source_records) || hit.source_records.length === 0) {
      throw new Error("RankedHit.source_records phải là mảng không rỗng");
    }
    let displayFound = false;
    for (const sr of hit.source_records) {
      validatePaperRecord(sr);
      if (sr.source === hit.display.source && sr.source_id === hit.display.source_id && sr.raw_sha256 === hit.display.raw_sha256) {
        displayFound = true;
      }
    }
    if (!displayFound) {
      throw new Error("RankedHit.display phải là một bản ghi trong source_records");
    }

    if (!hit.source_ranks || typeof hit.source_ranks !== "object" || Array.isArray(hit.source_ranks)) {
      throw new Error("RankedHit.source_ranks phải là đối tượng");
    }
    const expectedSources = new Set(hit.source_records.map(r => r.source));
    const rankSources = new Set(Object.keys(hit.source_ranks));
    if (expectedSources.size !== rankSources.size) {
      throw new Error("RankedHit.source_ranks phải có khóa khớp đúng các nguồn trong source_records");
    }
    for (const s of expectedSources) {
      if (!rankSources.has(s)) {
        throw new Error("RankedHit.source_ranks thiếu nguồn: " + s);
      }
      const r = hit.source_ranks[s];
      if (!isStrictInteger(r) || r < 1) {
        throw new Error("RankedHit.source_ranks[" + s + "] phải là số nguyên >= 1");
      }
    }

    if (!hit.conflicts || typeof hit.conflicts !== "object" || Array.isArray(hit.conflicts)) {
      throw new Error("RankedHit.conflicts phải là đối tượng");
    }
    for (const f of Object.keys(hit.conflicts)) {
      const evList = hit.conflicts[f];
      if (!Array.isArray(evList)) {
        throw new Error("RankedHit.conflicts[" + f + "] phải là mảng");
      }
      for (const ev of evList) {
        validateFieldEvidence(ev);
      }
    }

    return true;
  }

  function validateFusionCounts(counts) {
    if (!counts || typeof counts !== "object") {
      throw new Error("FusionCounts phải là đối tượng JSON");
    }
    const allowed = ["raw", "valid", "invalid", "excluded_by_year", "eligible", "groups", "duplicate_excess", "returned"];
    const extra = hasExtraKeys(counts, allowed);
    if (extra) {
      throw new Error("FusionCounts chứa trường không được phép: " + extra);
    }
    for (const k of allowed) {
      if (!isStrictInteger(counts[k]) || counts[k] < 0) {
        throw new Error("FusionCounts." + k + " phải là số nguyên hữu hạn không âm (nhận được: " + counts[k] + ")");
      }
    }
    if (counts.raw !== counts.valid + counts.invalid) {
      throw new Error("Vi phạm đẳng thức bộ đếm: raw !== valid + invalid (" + counts.raw + " !== " + counts.valid + " + " + counts.invalid + ")");
    }
    if (counts.valid !== counts.eligible + counts.excluded_by_year) {
      throw new Error("Vi phạm đẳng thức bộ đếm: valid !== eligible + excluded_by_year (" + counts.valid + " !== " + counts.eligible + " + " + counts.excluded_by_year + ")");
    }
    if (counts.eligible !== counts.groups + counts.duplicate_excess) {
      throw new Error("Vi phạm đẳng thức bộ đếm: eligible !== groups + duplicate_excess (" + counts.eligible + " !== " + counts.groups + " + " + counts.duplicate_excess + ")");
    }
    if (counts.returned > counts.groups) {
      throw new Error("Vi phạm đẳng thức bộ đếm: returned > groups (" + counts.returned + " > " + counts.groups + ")");
    }
    return true;
  }

  function validateFusionResult(fusion) {
    if (!fusion || typeof fusion !== "object") {
      throw new Error("FusionResult phải là đối tượng JSON");
    }
    const extra = hasExtraKeys(fusion, ["hits", "counts"]);
    if (extra) {
      throw new Error("FusionResult chứa trường không được phép: " + extra);
    }
    if (!Array.isArray(fusion.hits)) {
      throw new Error("FusionResult.hits phải là mảng");
    }
    validateFusionCounts(fusion.counts);

    if (fusion.hits.length !== fusion.counts.returned) {
      throw new Error("FusionResult: returned count mismatch (hits.length=" + fusion.hits.length + " !== returned=" + fusion.counts.returned + ")");
    }

    const seenCanonical = new Set();
    for (let i = 0; i < fusion.hits.length; i++) {
      const h = fusion.hits[i];
      validateRankedHit(h);
      if (h.rank !== i + 1) {
        throw new Error("FusionResult: rank không tuần tự liên tục bắt đầu từ 1 (hit " + i + " có rank=" + h.rank + ")");
      }
      if (seenCanonical.has(h.canonical_id)) {
        throw new Error("FusionResult: duplicate canonical_id trong hits: " + h.canonical_id);
      }
      seenCanonical.add(h.canonical_id);
    }
    return true;
  }

  function computeOverallStatus(results, request, hitCount) {
    if (!isStrictInteger(hitCount) || hitCount < 0) {
      throw new Error("hitCount không hợp lệ");
    }
    const mapping = {};
    for (const r of results) {
      if (mapping[r.source]) {
        throw new Error("Duplicate source result: " + r.source);
      }
      mapping[r.source] = r;
    }
    for (const s of request.sources) {
      if (!mapping[s] || mapping[s].status === "not_requested") {
        throw new Error("Missing selected source result: " + s);
      }
    }
    for (const r of results) {
      if (!request.sources.includes(r.source) && r.status !== "not_requested") {
        throw new Error("Unselected source was attempted: " + r.source);
      }
    }
    let failedCount = 0;
    for (const s of request.sources) {
      if (mapping[s].status === "failed") failedCount++;
    }
    if (hitCount > 0) {
      const anySuccess = request.sources.some(s => mapping[s].status === "success");
      if (!anySuccess) {
        throw new Error("hits without successful source");
      }
    }
    if (failedCount === request.sources.length) return "failed";
    if (failedCount > 0) return "partial_failure";
    return hitCount > 0 ? "success" : "empty";
  }

  function validateSearchSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== "object") {
      throw new Error("SearchSnapshot phải là đối tượng JSON");
    }
    const allowed = [
      "schema_version", "contract_version", "snapshot_id", "request", "config_sha256",
      "adapter_sha256", "source_results", "fusion", "overall", "fetched_at", "expires_at"
    ];
    const extra = hasExtraKeys(snapshot, allowed);
    if (extra) {
      throw new Error("SearchSnapshot chứa trường không được phép: " + extra);
    }

    if (snapshot.schema_version !== SCHEMA_VERSION) {
      throw new Error("SearchSnapshot.schema_version sai: " + snapshot.schema_version);
    }
    if (snapshot.contract_version !== CONTRACT_VERSION) {
      throw new Error("SearchSnapshot.contract_version sai: " + snapshot.contract_version);
    }
    if (!isNonEmptyString(snapshot.snapshot_id)) {
      throw new Error("SearchSnapshot.snapshot_id phải là chuỗi không rỗng");
    }
    validateSearchRequest(snapshot.request);
    if (!isSha256(snapshot.config_sha256)) {
      throw new Error("SearchSnapshot.config_sha256 phải là mã băm SHA-256");
    }

    if (!snapshot.adapter_sha256 || typeof snapshot.adapter_sha256 !== "object" || Array.isArray(snapshot.adapter_sha256)) {
      throw new Error("SearchSnapshot.adapter_sha256 phải là đối tượng");
    }
    const reqSources = new Set(snapshot.request.sources);
    const adapterSources = new Set(Object.keys(snapshot.adapter_sha256));
    if (reqSources.size !== adapterSources.size) {
      throw new Error("SearchSnapshot.adapter_sha256 keys must match request.sources exactly");
    }
    for (const s of reqSources) {
      if (!adapterSources.has(s) || !isSha256(snapshot.adapter_sha256[s])) {
        throw new Error("SearchSnapshot.adapter_sha256 thiếu hoặc sai mã băm cho: " + s);
      }
    }

    if (!Array.isArray(snapshot.source_results)) {
      throw new Error("SearchSnapshot.source_results phải là mảng");
    }
    for (const sr of snapshot.source_results) {
      validateSourceResult(sr);
    }
    validateFusionResult(snapshot.fusion);

    const validOverall = ["success", "empty", "partial_failure", "failed"];
    if (!validOverall.includes(snapshot.overall)) {
      throw new Error("SearchSnapshot.overall không hợp lệ: " + snapshot.overall);
    }

    if (!isIsoTimeWithTz(snapshot.fetched_at) || !isIsoTimeWithTz(snapshot.expires_at)) {
      throw new Error("SearchSnapshot timestamps phải có timezone");
    }
    if (new Date(snapshot.expires_at).getTime() <= new Date(snapshot.fetched_at).getTime()) {
      throw new Error("SearchSnapshot: expires_at must follow fetched_at");
    }

    // Invariant: overall computation
    const expectedOverall = computeOverallStatus(snapshot.source_results, snapshot.request, snapshot.fusion.hits.length);
    if (snapshot.overall !== expectedOverall) {
      throw new Error("SearchSnapshot.overall mismatch: nhận được '" + snapshot.overall + "', tính toán được '" + expectedOverall + "'");
    }

    // Invariant: invalid must be 0 in snapshot
    if (snapshot.fusion.counts.invalid !== 0) {
      throw new Error("SearchSnapshot cannot contain invalid source records (invalid must be 0, received " + snapshot.fusion.counts.invalid + ")");
    }

    // Invariant: all source records must equal valid count
    const allRecords = [];
    for (const s of snapshot.source_results) {
      for (const r of s.records) allRecords.push(r);
    }
    if (snapshot.fusion.counts.valid !== allRecords.length) {
      throw new Error("SearchSnapshot: counts.valid (" + snapshot.fusion.counts.valid + ") !== tổng số records từ các nguồn (" + allRecords.length + ")");
    }

    // Invariant: hits traced to source records
    const allRecordsSet = new Set(allRecords.map(r => r.source + ":" + r.source_id + ":" + r.raw_sha256));
    for (const h of snapshot.fusion.hits) {
      for (const sr of h.source_records) {
        if (!allRecordsSet.has(sr.source + ":" + sr.source_id + ":" + sr.raw_sha256)) {
          throw new Error("Hit source record không thể truy nguyên về source_results hợp lệ: " + sr.source + ":" + sr.source_id);
        }
      }
    }

    return true;
  }

  function validateEnvelope(envelope) {
    if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
      throw new Error("SearchEnvelope phải là một đối tượng JSON");
    }
    const allowed = ["schema_version", "contract_version", "overall", "snapshot", "errors", "stale", "cached"];
    const extra = hasExtraKeys(envelope, allowed);
    if (extra) {
      throw new Error("SearchEnvelope chứa trường không được phép (extra forbidden): " + extra);
    }
    if (envelope.schema_version !== SCHEMA_VERSION) {
      throw new Error("Sai schema_version trong SearchEnvelope: mong đợi " + SCHEMA_VERSION + ", nhận được " + envelope.schema_version);
    }
    if (envelope.contract_version !== CONTRACT_VERSION) {
      throw new Error("Sai contract_version trong SearchEnvelope: mong đợi " + CONTRACT_VERSION + ", nhận được " + envelope.contract_version);
    }
    const validOverall = ["success", "empty", "partial_failure", "failed"];
    if (!validOverall.includes(envelope.overall)) {
      throw new Error("Trạng thái overall không hợp lệ: " + envelope.overall);
    }
    if (typeof envelope.stale !== "boolean" || typeof envelope.cached !== "boolean") {
      throw new Error("Trường stale và cached bắt buộc phải là boolean");
    }
    if (!Array.isArray(envelope.errors)) {
      throw new Error("Trường errors bắt buộc phải là một mảng");
    }
    for (const e of envelope.errors) {
      validateSearchError(e);
    }

    // Anti-Silent-Bypass: Trường snapshot là bắt buộc (required-nullable)
    if (!Object.prototype.hasOwnProperty.call(envelope, "snapshot")) {
      throw new Error("SearchEnvelope thiếu trường bắt buộc: snapshot");
    }
    if (envelope.snapshot !== null && (typeof envelope.snapshot !== "object" || Array.isArray(envelope.snapshot))) {
      throw new Error("SearchEnvelope.snapshot phải là null hoặc đối tượng JSON (không được là primitive hoặc mảng)");
    }

    const good = envelope.overall === "success" || envelope.overall === "empty";
    if (good) {
      if (envelope.snapshot === null) {
        throw new Error("Trạng thái overall=" + envelope.overall + " bắt buộc phải có đối tượng snapshot (không được null)");
      }
      if (envelope.errors.length > 0) {
        throw new Error("Trạng thái overall=" + envelope.overall + " yêu cầu mảng errors phải rỗng");
      }
    } else {
      if (envelope.errors.length === 0) {
        throw new Error("Trạng thái lỗi overall=" + envelope.overall + " bắt buộc phải chứa ít nhất một SearchError trong errors");
      }
    }

    if (envelope.overall === "partial_failure" && envelope.snapshot === null) {
      throw new Error("Trạng thái partial_failure bắt buộc phải chứa snapshot bằng chứng (không được null)");
    }

    if (envelope.cached && !good) {
      throw new Error("failure is not a cache success (cached=true không được đi kèm overall thất bại)");
    }

    if (envelope.snapshot !== null) {
      validateSearchSnapshot(envelope.snapshot);
      if (envelope.snapshot.overall !== envelope.overall) {
        throw new Error("SearchEnvelope overall (" + envelope.overall + ") không khớp snapshot overall (" + envelope.snapshot.overall + ")");
      }

      // Kiểm tra khớp errors giữa envelope và source_results (deepEqual từng error theo cùng thứ tự)
      const expectedErrors = envelope.snapshot.source_results
        .filter(s => s.error !== null)
        .map(s => s.error);
      const sourceErrors = envelope.errors.filter(e => e.source !== null);
      if (sourceErrors.length !== expectedErrors.length) {
        throw new Error("SearchEnvelope errors không khớp số lượng source failures trong snapshot");
      }
      for (let i = 0; i < sourceErrors.length; i++) {
        const se = sourceErrors[i];
        const ee = expectedErrors[i];
        if (
          se.kind !== ee.kind ||
          se.message !== ee.message ||
          se.source !== ee.source ||
          se.retry_after_seconds !== ee.retry_after_seconds ||
          se.record_index !== ee.record_index
        ) {
          throw new Error("SearchEnvelope errors[" + i + "] không khớp chính xác với snapshot.source_results error: kind/message/source/retry_after_seconds/record_index mismatch");
        }
      }
    }

    return true;
  }

  function validateLibraryEntry(entry) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error("LibraryEntry phải là đối tượng JSON");
    }
    const allowed = ["canonical_id", "snapshot_id", "saved_at", "hit", "incomplete_sources"];
    const extra = hasExtraKeys(entry, allowed);
    if (extra) {
      throw new Error("LibraryEntry chứa trường không được phép: " + extra);
    }
    for (const key of allowed) {
      if (!Object.prototype.hasOwnProperty.call(entry, key)) {
        throw new Error("LibraryEntry thiếu trường bắt buộc: " + key);
      }
    }
    if (!isNonEmptyString(entry.canonical_id)) {
      throw new Error("LibraryEntry.canonical_id phải là chuỗi không rỗng");
    }
    if (!isNonEmptyString(entry.snapshot_id)) {
      throw new Error("LibraryEntry.snapshot_id phải là chuỗi không rỗng");
    }
    if (!isIsoTimeWithTz(entry.saved_at)) {
      throw new Error("LibraryEntry.saved_at phải là ISO timestamp kèm timezone");
    }
    if (typeof entry.incomplete_sources !== "boolean") {
      throw new Error("LibraryEntry.incomplete_sources phải là boolean");
    }
    validateRankedHit(entry.hit);
    if (entry.canonical_id !== entry.hit.canonical_id) {
      throw new Error("LibraryEntry: library identity mismatch (canonical_id !== hit.canonical_id)");
    }
    return true;
  }

  function validateLibrarySaveEnvelope(env) {
    if (!env || typeof env !== "object" || Array.isArray(env)) {
      throw new Error("LibrarySaveEnvelope phải là một đối tượng JSON");
    }
    const allowed = ["contract_version", "entry", "errors"];
    const extra = hasExtraKeys(env, allowed);
    if (extra) {
      throw new Error("LibrarySaveEnvelope chứa trường không được phép: " + extra);
    }
    for (const key of allowed) {
      if (!Object.prototype.hasOwnProperty.call(env, key)) {
        throw new Error("LibrarySaveEnvelope thiếu trường bắt buộc: " + key);
      }
    }
    if (env.contract_version !== CONTRACT_VERSION) {
      throw new Error("Sai contract_version trong LibrarySaveEnvelope: mong đợi " + CONTRACT_VERSION + ", nhận được " + env.contract_version);
    }
    if (!Array.isArray(env.errors)) {
      throw new Error("LibrarySaveEnvelope.errors phải là mảng");
    }
    if (env.errors.length > 0) {
      for (const err of env.errors) {
        validateSearchError(err);
      }
      throw new Error("LibrarySaveEnvelope: errors phải rỗng trong phản hồi lưu thành công");
    }
    if (!env.entry || typeof env.entry !== "object" || Array.isArray(env.entry)) {
      throw new Error("LibrarySaveEnvelope.entry phải là đối tượng LibraryEntry");
    }
    validateLibraryEntry(env.entry);
    return true;
  }

  function validateLibraryListEnvelope(env) {
    if (!env || typeof env !== "object" || Array.isArray(env)) {
      throw new Error("LibraryListEnvelope phải là đối tượng JSON (không chấp nhận bare array)");
    }
    const allowed = ["contract_version", "entries", "errors"];
    const extra = hasExtraKeys(env, allowed);
    if (extra) {
      throw new Error("LibraryListEnvelope chứa trường không được phép: " + extra);
    }
    for (const key of allowed) {
      if (!Object.prototype.hasOwnProperty.call(env, key)) {
        throw new Error("LibraryListEnvelope thiếu trường bắt buộc: " + key);
      }
    }
    if (env.contract_version !== CONTRACT_VERSION) {
      throw new Error("Sai contract_version trong LibraryListEnvelope: mong đợi " + CONTRACT_VERSION + ", nhận được " + env.contract_version);
    }
    if (!Array.isArray(env.errors)) {
      throw new Error("LibraryListEnvelope.errors phải là mảng");
    }
    if (env.errors.length > 0) {
      for (const err of env.errors) {
        validateSearchError(err);
      }
      throw new Error("LibraryListEnvelope: errors phải rỗng trong phản hồi danh sách thành công");
    }
    if (!Array.isArray(env.entries)) {
      throw new Error("LibraryListEnvelope.entries phải là một mảng");
    }
    for (const entry of env.entries) {
      validateLibraryEntry(entry);
    }
    return true;
  }

  // =========================================================================
  // KHỞI TẠO VÀ SỰ KIỆN GIAO DIỆN
  // =========================================================================

  function init(options) {
    options = options || {};
    if (options.document) envDocument = options.document;
    if (options.fetchFn) envFetch = options.fetchFn;

    if (!envDocument) return;

    // Gắn sự kiện biểu mẫu tìm kiếm
    const form = envDocument.getElementById("public-search-form");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        handleSearchSubmit(false);
      });
    }

    const btnRefresh = envDocument.getElementById("btn-refresh");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", function (e) {
        e.preventDefault();
        handleSearchSubmit(true);
      });
    }

    // Gắn sự kiện chuyển tab
    const tabSearch = envDocument.getElementById("tab-search");
    const tabLibrary = envDocument.getElementById("tab-library");
    if (tabSearch && tabLibrary) {
      tabSearch.addEventListener("click", function () {
        switchTab("search");
      });
      tabLibrary.addEventListener("click", function () {
        switchTab("library");
      });
    }

    // Gắn sự kiện xuất thư viện
    const btnExportJson = envDocument.getElementById("btn-export-json");
    if (btnExportJson) {
      btnExportJson.addEventListener("click", function () {
        exportLibrary("json");
      });
    }
    const btnExportBibtex = envDocument.getElementById("btn-export-bibtex");
    if (btnExportBibtex) {
      btnExportBibtex.addEventListener("click", function () {
        exportLibrary("bibtex");
      });
    }

    // Gắn sự kiện đóng panel chi tiết
    const btnCloseDetail = envDocument.getElementById("btn-close-detail");
    if (btnCloseDetail) {
      btnCloseDetail.addEventListener("click", function () {
        const detailPanel = envDocument.getElementById("detail-panel");
        if (detailPanel) detailPanel.hidden = true;
      });
    }

    // Kiểm tra trực quan ô chọn nguồn
    const srcOpenAlex = envDocument.getElementById("src-openalex");
    const srcArxiv = envDocument.getElementById("src-arxiv");
    const sourcesError = envDocument.getElementById("sources-error");
    function checkSourcesInline() {
      if (srcOpenAlex && srcArxiv && sourcesError) {
        const hasSource = srcOpenAlex.checked || srcArxiv.checked;
        sourcesError.hidden = hasSource;
      }
    }
    if (srcOpenAlex) srcOpenAlex.addEventListener("change", checkSourcesInline);
    if (srcArxiv) srcArxiv.addEventListener("change", checkSourcesInline);

    // Kiểm tra trực quan khoảng năm
    const yearFrom = envDocument.getElementById("year_from");
    const yearTo = envDocument.getElementById("year_to");
    const yearsError = envDocument.getElementById("years-error");
    function checkYearsInline() {
      if (yearFrom && yearTo && yearsError) {
        const yf = parseInt(yearFrom.value, 10);
        const yt = parseInt(yearTo.value, 10);
        if (!isNaN(yf) && !isNaN(yt) && yf > yt) {
          yearsError.hidden = false;
        } else {
          yearsError.hidden = true;
        }
      }
    }
    if (yearFrom) yearFrom.addEventListener("input", checkYearsInline);
    if (yearTo) yearTo.addEventListener("input", checkYearsInline);
  }

  function switchTab(target) {
    if (!envDocument) return;
    const tabSearch = envDocument.getElementById("tab-search");
    const tabLibrary = envDocument.getElementById("tab-library");
    const searchSection = envDocument.getElementById("search-section");
    const librarySection = envDocument.getElementById("library-section");

    if (target === "search") {
      if (tabSearch) {
        tabSearch.classList.add("active");
        tabSearch.setAttribute("aria-selected", "true");
      }
      if (tabLibrary) {
        tabLibrary.classList.remove("active");
        tabLibrary.setAttribute("aria-selected", "false");
      }
      if (searchSection) searchSection.hidden = false;
      if (librarySection) librarySection.hidden = true;
    } else {
      if (tabSearch) {
        tabSearch.classList.remove("active");
        tabSearch.setAttribute("aria-selected", "false");
      }
      if (tabLibrary) {
        tabLibrary.classList.add("active");
        tabLibrary.setAttribute("aria-selected", "true");
      }
      if (searchSection) searchSection.hidden = true;
      if (librarySection) librarySection.hidden = false;
      loadLibrary(0, LIBRARY_PAGE_SIZE);
    }
  }

  function collectFormInputs() {
    if (!envDocument) return null;
    const qInput = envDocument.getElementById("q");
    const srcOpenAlex = envDocument.getElementById("src-openalex");
    const srcArxiv = envDocument.getElementById("src-arxiv");
    const yearFromInput = envDocument.getElementById("year_from");
    const yearToInput = envDocument.getElementById("year_to");
    const topKInput = envDocument.getElementById("top_k");
    const capInput = envDocument.getElementById("cap_per_source");

    const query = qInput ? qInput.value.trim() : "";
    const sources = [];
    if (srcOpenAlex && srcOpenAlex.checked) sources.push("openalex");
    if (srcArxiv && srcArxiv.checked) sources.push("arxiv");

    let yearFrom = null;
    if (yearFromInput && yearFromInput.value.trim() !== "") {
      yearFrom = parseInt(yearFromInput.value.trim(), 10);
    }
    let yearTo = null;
    if (yearToInput && yearToInput.value.trim() !== "") {
      yearTo = parseInt(yearToInput.value.trim(), 10);
    }

    let topK = 20;
    if (topKInput && topKInput.value.trim() !== "") {
      topK = parseInt(topKInput.value.trim(), 10);
    }
    let cap = 50;
    if (capInput && capInput.value.trim() !== "") {
      cap = parseInt(capInput.value.trim(), 10);
    }

    return {
      query: query,
      sources: sources,
      year_from: yearFrom,
      year_to: yearTo,
      top_k: topK,
      cap_per_source: cap
    };
  }

  function validateFormInputs(inputs) {
    const errors = [];
    if (!inputs.query || inputs.query.length === 0) {
      errors.push("Từ khóa tìm kiếm không được để trống (bắt buộc 1..500 ký tự).");
    } else if (inputs.query.length > 500) {
      errors.push("Từ khóa tìm kiếm vượt quá độ dài tối đa 500 ký tự.");
    }

    if (!inputs.sources || inputs.sources.length === 0) {
      errors.push("Vui lòng chọn ít nhất một nguồn tìm kiếm (OpenAlex hoặc arXiv).");
    }

    if (inputs.year_from !== null) {
      if (isNaN(inputs.year_from) || inputs.year_from < YEAR_MIN || inputs.year_from > YEAR_MAX) {
        errors.push("Năm bắt đầu phải là số nguyên trong khoảng " + YEAR_MIN + ".." + YEAR_MAX + ".");
      }
    }
    if (inputs.year_to !== null) {
      if (isNaN(inputs.year_to) || inputs.year_to < YEAR_MIN || inputs.year_to > YEAR_MAX) {
        errors.push("Năm kết thúc phải là số nguyên trong khoảng " + YEAR_MIN + ".." + YEAR_MAX + ".");
      }
    }
    if (inputs.year_from !== null && inputs.year_to !== null && inputs.year_from > inputs.year_to) {
      errors.push("Khoảng năm không hợp lệ: Năm bắt đầu phải nhỏ hơn hoặc bằng năm kết thúc.");
    }

    if (isNaN(inputs.top_k) || inputs.top_k < 1 || inputs.top_k > 50) {
      errors.push("Số lượng hiển thị (top_k) phải nằm trong khoảng 1..50.");
    }
    if (isNaN(inputs.cap_per_source) || inputs.cap_per_source < 1 || inputs.cap_per_source > 50) {
      errors.push("Ngân sách mỗi nguồn (cap) phải nằm trong khoảng 1..50.");
    }

    return errors;
  }

  // =========================================================================
  // XỬ LÝ TÌM KIẾM VÀ PHẢN HỒI (SEARCH SUBMIT & RESPONSE)
  // =========================================================================

  async function handleSearchSubmit(isRefresh) {
    if (!envDocument) return;
    const clientErrDiv = envDocument.getElementById("client-validation-error");
    if (clientErrDiv) {
      clientErrDiv.hidden = true;
      clientErrDiv.textContent = "";
    }
    clearBanners();

    const inputs = collectFormInputs();
    if (!inputs) return;

    const validationErrors = validateFormInputs(inputs);
    if (validationErrors.length > 0) {
      if (clientErrDiv) {
        clientErrDiv.hidden = false;
        clientErrDiv.textContent = validationErrors.join(" ");
      }
      return;
    }

    // Chống Race Condition: hủy request cũ đang chạy
    if (activeSearchAbortController) {
      activeSearchAbortController.abort();
    }
    activeSearchAbortController = typeof AbortController !== "undefined" ? new AbortController() : null;
    const seq = ++currentSearchSeq;

    setLoadingState(true);

    const params = new URLSearchParams();
    params.set("q", inputs.query);
    params.set("sources", inputs.sources.join(","));
    if (inputs.year_from !== null) {
      params.set("year_from", String(inputs.year_from));
    }
    if (inputs.year_to !== null) {
      params.set("year_to", String(inputs.year_to));
    }
    params.set("top_k", String(inputs.top_k));
    params.set("cap_per_source", String(inputs.cap_per_source));
    params.set("refresh", isRefresh ? "true" : "false");

    const endpoint = "/public/search?" + params.toString();

    try {
      const fetchOpts = {
        method: "GET",
        headers: { "Accept": "application/json" }
      };
      if (activeSearchAbortController) {
        fetchOpts.signal = activeSearchAbortController.signal;
      }

      const res = await envFetch(endpoint, fetchOpts);
      let data = null;
      try {
        data = await res.json();
      } catch (jsonErr) {
        throw new Error("Lỗi giải mã JSON phản hồi từ máy chủ: " + jsonErr.message);
      }

      // Sequence guard: response cũ bị bỏ qua
      if (seq !== currentSearchSeq) return;

      validateEnvelope(data);

      setLoadingState(false);
      renderSearchResults(data, isRefresh);

    } catch (err) {
      if (seq !== currentSearchSeq) return;
      if (err.name === "AbortError") return;

      setLoadingState(false);
      handleSearchError(err, isRefresh);
    }
  }

  function setLoadingState(isLoading) {
    if (!envDocument) return;
    const statusRegion = envDocument.getElementById("status-region");
    const btnSearch = envDocument.getElementById("btn-search");
    const btnRefresh = envDocument.getElementById("btn-refresh");

    if (isLoading) {
      if (statusRegion) {
        statusRegion.hidden = false;
        statusRegion.textContent = "Đang truy vấn nguồn công khai (openalex, arxiv)… Vui lòng chờ (tối đa theo ngân sách deadline 30s).";
        statusRegion.setAttribute("aria-busy", "true");
      }
      if (btnSearch) btnSearch.disabled = true;
      if (btnRefresh) btnRefresh.disabled = true;
    } else {
      if (statusRegion) {
        statusRegion.hidden = true;
        statusRegion.textContent = "";
        statusRegion.removeAttribute("aria-busy");
      }
      if (btnSearch) btnSearch.disabled = false;
      if (btnRefresh) btnRefresh.disabled = false;
    }
  }

  function clearBanners() {
    if (!envDocument) return;
    const bannerRegion = envDocument.getElementById("banner-region");
    if (bannerRegion) {
      while (bannerRegion.firstChild) {
        bannerRegion.removeChild(bannerRegion.firstChild);
      }
    }
    const staleReviewRegion = envDocument.getElementById("stale-review-region");
    if (staleReviewRegion) {
      staleReviewRegion.hidden = true;
      while (staleReviewRegion.firstChild) {
        staleReviewRegion.removeChild(staleReviewRegion.firstChild);
      }
    }
  }

  function addBanner(type, text) {
    if (!envDocument) return null;
    const bannerRegion = envDocument.getElementById("banner-region");
    if (!bannerRegion) return null;

    const div = envDocument.createElement("div");
    div.className = "banner banner-" + type;
    div.setAttribute("role", type === "error" ? "alert" : "status");
    div.textContent = text;
    bannerRegion.appendChild(div);
    return div;
  }

  function handleSearchError(err, isRefresh) {
    const errorMsg = err && err.message ? err.message : String(err);
    addBanner("error", "Lỗi tìm kiếm: " + errorMsg);

    if (isRefresh && lastSuccessfulSnapshot) {
      renderStaleReviewButton(lastSuccessfulSnapshot);
    }
  }

  /**
   * Hiển thị nút cho phép người dùng xem lại snapshot cũ sau khi refresh thất bại
   * Kiểm tra TTL thực tế so với expires_at, không hardcode stale: true
   */
  function renderStaleReviewButton(snapshot) {
    if (!envDocument) return;
    const staleReviewRegion = envDocument.getElementById("stale-review-region");
    if (!staleReviewRegion) return;

    while (staleReviewRegion.firstChild) {
      staleReviewRegion.removeChild(staleReviewRegion.firstChild);
    }

    const box = envDocument.createElement("div");
    box.className = "banner banner-warning";
    const p = envDocument.createElement("p");
    p.textContent = "Thao tác làm mới từ nguồn thất bại hoặc không hoàn chỉnh. Bạn có thể mở lại bản ghi Snapshot đã lưu trước đó:";
    box.appendChild(p);

    const btn = envDocument.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-secondary btn-small";
    btn.id = "btn-view-previous-snapshot";
    btn.style.marginTop = "0.5rem";
    btn.textContent = "Xem lại snapshot #" + snapshot.snapshot_id + " (thu thập lúc " + snapshot.fetched_at + ")";
    btn.addEventListener("click", function () {
      const now = new Date();
      const expiresAt = new Date(snapshot.expires_at);
      const isExpired = now.getTime() >= expiresAt.getTime();

      const historicalEnvelope = {
        schema_version: SCHEMA_VERSION,
        contract_version: CONTRACT_VERSION,
        overall: snapshot.overall,
        snapshot: snapshot,
        errors: [],
        stale: isExpired,
        cached: true
      };
      clearBanners();
      renderSearchResults(historicalEnvelope, false);
    });
    box.appendChild(btn);

    staleReviewRegion.appendChild(box);
    staleReviewRegion.hidden = false;
  }

  /**
   * Render kết quả tìm kiếm từ SearchEnvelope
   */
  function renderSearchResults(envelope, isRefresh) {
    if (!envDocument) return;
    clearBanners();

    // 1. Quota warnings (HTTP 503)
    for (const err of envelope.errors) {
      if (err.kind === "quota") {
        const retrySec = (err.retry_after_seconds !== null && err.retry_after_seconds !== undefined)
          ? (err.retry_after_seconds + " giây")
          : "nguồn không cung cấp thời gian chờ";
        addBanner("warning", "Nguồn " + (err.source || "hệ thống") + " đã chạm giới hạn lượt truy cập (Quota / Rate Limit). Thời gian chờ khuyến nghị: " + retrySec + ".");
      }
    }

    // 2. Partial Failure: Không nuốt lỗi! Cảnh báo kết quả không đầy đủ cho mọi lỗi (kể cả quota)
    if (envelope.overall === "partial_failure") {
      for (const err of envelope.errors) {
        addBanner("warning", "Cảnh báo kết quả không đầy đủ (partial_failure): Nguồn " + (err.source || "không rõ") + " gặp lỗi (" + err.kind + ": " + err.message + "). Danh sách dưới đây chỉ phản ánh dữ liệu từ nguồn còn lại.");
      }
      if (isRefresh && lastSuccessfulSnapshot) {
        renderStaleReviewButton(lastSuccessfulSnapshot);
      }
    }

    // 3. Failed: Hiện TẤT CẢ các lỗi, không để quotaHit nuốt schema error!
    if (envelope.overall === "failed") {
      for (const err of envelope.errors) {
        if (err.kind !== "quota") {
          addBanner("error", "Lỗi truy vấn nguồn " + (err.source || "công khai") + " (" + err.kind + "): " + err.message);
        }
      }
      hideSearchSections();
      if (isRefresh && lastSuccessfulSnapshot) {
        renderStaleReviewButton(lastSuccessfulSnapshot);
      }
      return;
    }

    const snapshot = envelope.snapshot;
    if (!snapshot) return;

    // Cập nhật displayedSnapshot (dùng cho việc lưu bài với đúng provenance)
    displayedSnapshot = snapshot;
    currentSnapshotPage = 1;

    // Chỉ lưu lastSuccessfulSnapshot khi hoàn tất success hoặc empty
    if (envelope.overall === "success" || envelope.overall === "empty") {
      lastSuccessfulSnapshot = snapshot;
    }

    // 4. Render Snapshot Banner & Cache Badge
    renderSnapshotBanner(envelope);

    // 5. Render Thẻ trạng thái từng nguồn
    renderSourcesSummary(snapshot.source_results);

    // 6. Render Bộ đếm Fusion & Giải thích RRF
    renderFusionSummary(snapshot.fusion.counts);

    // 7. Render Danh sách bài báo (Hits) phân trang slice 10 bài
    renderHitsList(snapshot.fusion.hits, envelope.overall, snapshot.fusion.counts.excluded_by_year, currentSnapshotPage);

    // 8. Render Điều khiển phân trang trên snapshot
    renderSnapshotPagination(snapshot);
  }

  function hideSearchSections() {
    if (!envDocument) return;
    const snapBanner = envDocument.getElementById("snapshot-meta-banner");
    const sourcesSummary = envDocument.getElementById("sources-summary");
    const fusionSummary = envDocument.getElementById("fusion-summary");
    const results = envDocument.getElementById("results");
    const pagination = envDocument.getElementById("snapshot-pagination");
    const detailPanel = envDocument.getElementById("detail-panel");

    if (snapBanner) snapBanner.hidden = true;
    if (sourcesSummary) sourcesSummary.hidden = true;
    if (fusionSummary) fusionSummary.hidden = true;
    if (results) {
      while (results.firstChild) results.removeChild(results.firstChild);
    }
    if (pagination) pagination.hidden = true;
    if (detailPanel) detailPanel.hidden = true;
  }

  function renderSnapshotBanner(envelope) {
    if (!envDocument) return;
    const banner = envDocument.getElementById("snapshot-meta-banner");
    if (!banner) return;

    while (banner.firstChild) banner.removeChild(banner.firstChild);

    const snapshot = envelope.snapshot;
    const infoSpan = envDocument.createElement("span");
    infoSpan.textContent = "Snapshot #" + snapshot.snapshot_id + " · Thu thập: " + snapshot.fetched_at + " · Hết hạn: " + snapshot.expires_at;
    banner.appendChild(infoSpan);

    const badgesSpan = envDocument.createElement("span");
    badgesSpan.className = "snapshot-badges";

    if (envelope.cached) {
      const badge = envDocument.createElement("span");
      if (envelope.stale) {
        badge.className = "badge badge-stale";
        badge.textContent = "cached_stale";
        addBanner("warning", "Bạn đang xem bản lưu Snapshot cũ đã quá hạn TTL (cached_stale — thu thập lúc " + snapshot.fetched_at + "). Đây là dữ liệu lịch sử do bạn chọn mở, không phải kết quả làm mới trực tiếp.");
      } else {
        badge.className = "badge badge-fresh";
        badge.textContent = "cached_fresh";
        addBanner("info", "Bạn đang xem bản lưu Snapshot lịch sử còn hạn TTL (thu thập lúc " + snapshot.fetched_at + ").");
      }
      badgesSpan.appendChild(badge);
    }

    banner.appendChild(badgesSpan);
    banner.hidden = false;
  }

  function renderSourcesSummary(sourceResults) {
    if (!envDocument) return;
    const container = envDocument.getElementById("sources-summary");
    if (!container) return;

    while (container.firstChild) container.removeChild(container.firstChild);

    for (const res of sourceResults) {
      const card = envDocument.createElement("div");
      card.className = "source-card";
      card.dataset.source = res.source;

      const header = envDocument.createElement("div");
      header.className = "source-card-header";

      const title = envDocument.createElement("span");
      title.className = "source-card-title";
      title.textContent = res.source === "openalex" ? "OpenAlex" : (res.source === "arxiv" ? "arXiv" : res.source);
      header.appendChild(title);

      const statusBadge = envDocument.createElement("span");
      statusBadge.className = "badge";
      if (res.status === "success") {
        statusBadge.classList.add("badge-fresh");
      } else if (res.status === "failed") {
        statusBadge.classList.add("banner-error");
      } else if (res.status === "empty") {
        statusBadge.classList.add("badge-missing");
      }
      statusBadge.textContent = res.status;
      header.appendChild(statusBadge);
      card.appendChild(header);

      const stats = envDocument.createElement("div");
      stats.className = "source-card-stats";
      const countText = res.records ? res.records.length : 0;
      const elapsedText = (res.elapsed_seconds !== null && res.elapsed_seconds !== undefined) ? res.elapsed_seconds.toFixed(2) + "s" : "N/A";
      stats.textContent = "Số bài: " + countText + " · Thời gian: " + elapsedText + " · Lọc: " + res.filter_coverage;
      card.appendChild(stats);

      if (res.status === "failed" && res.error) {
        const errDiv = envDocument.createElement("div");
        errDiv.className = "source-card-error";
        errDiv.textContent = "Lỗi (" + res.error.kind + "): " + res.error.message;
        card.appendChild(errDiv);
      }

      container.appendChild(card);
    }

    container.hidden = false;
  }

  function renderFusionSummary(counts) {
    if (!envDocument) return;
    const container = envDocument.getElementById("fusion-summary");
    if (!container) return;

    while (container.firstChild) container.removeChild(container.firstChild);

    const heading = envDocument.createElement("h4");
    heading.textContent = "Thống kê Hợp nhất (Fusion Counts):";
    container.appendChild(heading);

    const grid = envDocument.createElement("div");
    grid.className = "fusion-counts-grid";

    const keys = [
      { k: "raw", lbl: "Tổng thô (raw)" },
      { k: "valid", lbl: "Hợp lệ (valid)" },
      { k: "invalid", lbl: "Không hợp lệ" },
      { k: "excluded_by_year", lbl: "Loại theo năm" },
      { k: "eligible", lbl: "Đủ điều kiện" },
      { k: "groups", lbl: "Nhóm duy nhất" },
      { k: "duplicate_excess", lbl: "Trùng thừa" },
      { k: "returned", lbl: "Trả về (returned)" }
    ];

    for (const item of keys) {
      const box = envDocument.createElement("div");
      box.className = "fusion-count-item";

      const val = envDocument.createElement("div");
      val.className = "fusion-count-val";
      val.textContent = String(counts[item.k]);
      box.appendChild(val);

      const lbl = envDocument.createElement("div");
      lbl.className = "fusion-count-lbl";
      lbl.textContent = item.lbl;
      box.appendChild(lbl);

      grid.appendChild(box);
    }
    container.appendChild(grid);

    const rrfP = envDocument.createElement("p");
    rrfP.className = "rrf-explanation";
    rrfP.textContent = "Thứ tự kết quả được xếp hạng bằng Reciprocal Rank Fusion (RRF = \u2211 1/(60 + rank), rank \u2265 1) dựa trên thứ tự trả về của từng nguồn. Mỗi nguồn đóng góp tối đa một thứ hạng cho mỗi bài; trường hợp bằng điểm phân định xác định theo canonical_id.";
    container.appendChild(rrfP);

    container.hidden = false;
  }

  /**
   * Render Danh sách bài báo (Hits) phân trang cục bộ
   */
  function renderHitsList(hits, overall, excludedByYear, page) {
    if (!envDocument) return;
    const resultsContainer = envDocument.getElementById("results");
    if (!resultsContainer) return;

    while (resultsContainer.firstChild) resultsContainer.removeChild(resultsContainer.firstChild);

    // Anti-Silent-Bypass: nếu overall là success mà hits rỗng -> lỗi contract
    if (overall === "success" && hits.length === 0) {
      addBanner("error", "Lỗi dữ liệu: overall=success nhưng danh sách bài báo rỗng (mâu thuẫn hợp đồng).");
      return;
    }

    if (overall === "empty" || hits.length === 0) {
      const emptyDiv = envDocument.createElement("div");
      emptyDiv.className = "banner banner-info";
      emptyDiv.id = "empty-results-message";
      if (excludedByYear && excludedByYear > 0) {
        emptyDiv.textContent = "Các nguồn có bài hợp lệ nhưng tất cả đều nằm ngoài khoảng năm đã lọc (" + excludedByYear + " bài bị loại). Gợi ý: nới rộng khoảng năm tìm kiếm.";
      } else {
        emptyDiv.textContent = "Không tìm thấy bài báo nào khớp với từ khóa trên các nguồn đã chọn.";
      }
      resultsContainer.appendChild(emptyDiv);
      return;
    }

    page = page || 1;
    const start = (page - 1) * SNAPSHOT_PAGE_SIZE;
    const pageHits = hits.slice(start, start + SNAPSHOT_PAGE_SIZE);

    for (const hit of pageHits) {
      const card = createResultCard(hit);
      resultsContainer.appendChild(card);
    }
  }

  /**
   * Render điều khiển phân trang trên snapshot đã chốt
   * Wording chuẩn: "Trang X / Y trên Snapshot #id (chốt lúc fetched_at)"
   */
  function renderSnapshotPagination(snapshot) {
    if (!envDocument) return;
    const nav = envDocument.getElementById("snapshot-pagination");
    if (!nav) return;

    while (nav.firstChild) nav.removeChild(nav.firstChild);

    const totalHits = snapshot.fusion.hits.length;
    const totalPages = Math.max(1, Math.ceil(totalHits / SNAPSHOT_PAGE_SIZE));

    if (totalHits === 0) {
      nav.hidden = true;
      return;
    }

    // Nút Trang trước
    const btnPrev = envDocument.createElement("button");
    btnPrev.type = "button";
    btnPrev.id = "btn-snapshot-prev";
    btnPrev.className = "btn btn-secondary btn-small";
    btnPrev.textContent = "\u2190 Trang trước";
    btnPrev.disabled = currentSnapshotPage <= 1;
    btnPrev.addEventListener("click", function () {
      if (currentSnapshotPage > 1) {
        changeSnapshotPage(snapshot.snapshot_id, currentSnapshotPage - 1);
      }
    });
    nav.appendChild(btnPrev);

    // Thông tin phân trang
    const info = envDocument.createElement("span");
    info.className = "pagination-info";
    info.id = "snapshot-pagination-info";
    info.textContent = "Trang " + currentSnapshotPage + " / " + totalPages + " trên Snapshot #" + snapshot.snapshot_id + " (chốt lúc " + snapshot.fetched_at + ")";
    nav.appendChild(info);

    // Nút Trang sau
    const btnNext = envDocument.createElement("button");
    btnNext.type = "button";
    btnNext.id = "btn-snapshot-next";
    btnNext.className = "btn btn-secondary btn-small";
    btnNext.textContent = "Trang sau \u2192";
    btnNext.disabled = currentSnapshotPage >= totalPages;
    btnNext.addEventListener("click", function () {
      if (currentSnapshotPage < totalPages) {
        changeSnapshotPage(snapshot.snapshot_id, currentSnapshotPage + 1);
      }
    });
    nav.appendChild(btnNext);

    nav.hidden = false;
  }

  /**
   * Chuyển trang snapshot qua GET /public/results/{snapshot_id}?offset&limit
   * Bảo vệ race condition với sequence của lượt tìm kiếm
   */
  async function changeSnapshotPage(snapshotId, targetPage) {
    if (!envDocument || !displayedSnapshot || displayedSnapshot.snapshot_id !== snapshotId) return;

    const seq = currentSearchSeq;
    const offset = (targetPage - 1) * SNAPSHOT_PAGE_SIZE;
    const limit = SNAPSHOT_PAGE_SIZE;
    const endpoint = "/public/results/" + encodeURIComponent(snapshotId) + "?offset=" + offset + "&limit=" + limit;

    try {
      const fetchOpts = {
        method: "GET",
        headers: { "Accept": "application/json" }
      };
      if (activeSearchAbortController) {
        fetchOpts.signal = activeSearchAbortController.signal;
      }

      const res = await envFetch(endpoint, fetchOpts);
      if (!res.ok) {
        throw new Error("Lỗi khi tải trang snapshot (HTTP " + res.status + ")");
      }
      const data = await res.json();

      // Nếu có query mới đã kích hoạt, bỏ qua kết quả trang cũ
      if (seq !== currentSearchSeq) return;

      validateEnvelope(data);
      displayedSnapshot = data.snapshot;
      currentSnapshotPage = targetPage;

      renderHitsList(displayedSnapshot.fusion.hits, data.overall, displayedSnapshot.fusion.counts.excluded_by_year, currentSnapshotPage);
      renderSnapshotPagination(displayedSnapshot);
    } catch (err) {
      if (seq !== currentSearchSeq) return;
      if (err.name === "AbortError") return;
      addBanner("error", "Chuyển trang thất bại: " + err.message);
    }
  }

  /**
   * Tạo Card bài báo DOM bằng createElement và textContent (Chống XSS)
   */
  function createResultCard(hit) {
    const card = envDocument.createElement("article");
    card.className = "result-card";
    card.dataset.canonicalId = hit.canonical_id;

    const display = hit.display;

    // 1. Dòng trên: Thứ hạng RRF + Tiêu đề
    const topRow = envDocument.createElement("div");
    topRow.className = "card-top";

    const rankSpan = envDocument.createElement("span");
    rankSpan.className = "card-rank";
    rankSpan.textContent = "#" + hit.rank + " (RRF " + hit.score.toFixed(4) + ")";
    topRow.appendChild(rankSpan);

    const titleH3 = envDocument.createElement("h3");
    titleH3.className = "card-title";
    titleH3.textContent = display.title;
    topRow.appendChild(titleH3);

    card.appendChild(topRow);

    // 2. Tác giả
    const authorsP = envDocument.createElement("p");
    authorsP.className = "card-authors";
    if (display.authors_availability === "missing") {
      const missingBadge = envDocument.createElement("span");
      missingBadge.className = "badge badge-missing";
      missingBadge.textContent = "Chưa rõ tác giả (metadata thiếu từ nguồn)";
      authorsP.appendChild(missingBadge);
    } else if (Array.isArray(display.authors) && display.authors.length > 0) {
      authorsP.textContent = "Tác giả: " + display.authors.join(", ");
    } else {
      authorsP.textContent = "Tác giả: Nguồn xác nhận danh sách tác giả rỗng";
    }
    card.appendChild(authorsP);

    // 3. Metadata: Huy hiệu nguồn, Năm, Nơi công bố, DOI, arXiv, Lượt trích dẫn
    const metaP = envDocument.createElement("div");
    metaP.className = "card-meta";

    const sourcesList = Object.keys(hit.source_ranks).sort();
    const srcBadge = envDocument.createElement("span");
    srcBadge.className = "badge badge-source";
    if (sourcesList.length > 1) {
      srcBadge.textContent = "[" + sourcesList.map(s => s === "openalex" ? "OpenAlex" : (s === "arxiv" ? "arXiv" : s)).join(" + ") + "]";
    } else if (sourcesList[0] === "openalex") {
      srcBadge.textContent = "[OpenAlex]";
    } else if (sourcesList[0] === "arxiv") {
      srcBadge.textContent = "[arXiv]";
    } else {
      srcBadge.textContent = "[" + sourcesList[0] + "]";
    }
    metaP.appendChild(srcBadge);

    const yearSpan = envDocument.createElement("span");
    if (display.publication_year !== null && display.publication_year !== undefined) {
      yearSpan.textContent = "Năm: " + display.publication_year;
    } else {
      yearSpan.className = "badge-missing";
      yearSpan.textContent = "Năm xuất bản: không có dữ liệu";
    }
    metaP.appendChild(yearSpan);

    const venueSpan = envDocument.createElement("span");
    if (display.venue) {
      venueSpan.textContent = "Nơi công bố: " + display.venue;
    } else {
      venueSpan.className = "badge-missing";
      venueSpan.textContent = "Nơi công bố / Chuyên mục: không có dữ liệu";
    }
    metaP.appendChild(venueSpan);

    if (display.doi) {
      const doiSpan = envDocument.createElement("span");
      doiSpan.textContent = "DOI: " + display.doi;
      metaP.appendChild(doiSpan);
    }
    if (display.arxiv_id) {
      const arxivSpan = envDocument.createElement("span");
      arxivSpan.textContent = "arXiv: " + display.arxiv_id;
      metaP.appendChild(arxivSpan);
    }

    const citeSpan = envDocument.createElement("span");
    if (display.citation_count !== null && display.citation_count !== undefined) {
      citeSpan.textContent = "Lượt trích dẫn (OpenAlex): " + display.citation_count + " (chỉ tham khảo, không phải điểm chất lượng)";
    } else {
      citeSpan.textContent = "Lượt trích dẫn: không có dữ liệu từ arXiv";
    }
    metaP.appendChild(citeSpan);

    card.appendChild(metaP);

    // 4. Bản tóm tắt (Abstract)
    const abstractP = envDocument.createElement("p");
    abstractP.className = "card-abstract";
    if (display.abstract) {
      abstractP.textContent = display.abstract;
    } else {
      abstractP.className = "card-abstract badge-missing";
      abstractP.textContent = "Tóm tắt: nguồn không cung cấp bản tóm tắt (Title-only record hợp lệ)";
    }
    card.appendChild(abstractP);

    // 5. Nút thao tác & Liên kết an toàn
    const actionsDiv = envDocument.createElement("div");
    actionsDiv.className = "card-actions";

    if (isSafeUrl(display.landing_url)) {
      const aLanding = envDocument.createElement("a");
      aLanding.href = display.landing_url;
      aLanding.target = "_blank";
      aLanding.rel = "noopener noreferrer";
      aLanding.className = "btn btn-outline btn-small";
      aLanding.textContent = "Mở trang bài báo tại nguồn";
      actionsDiv.appendChild(aLanding);
    } else {
      const warnSpan = envDocument.createElement("span");
      warnSpan.className = "badge banner-error";
      warnSpan.textContent = "Liên kết nguồn không an toàn/bị từ chối";
      actionsDiv.appendChild(warnSpan);
    }

    if (display.open_access_status === "open" && display.pdf_url && isSafeUrl(display.pdf_url)) {
      const aPdf = envDocument.createElement("a");
      aPdf.href = display.pdf_url;
      aPdf.target = "_blank";
      aPdf.rel = "noopener noreferrer";
      aPdf.className = "btn btn-outline btn-small";
      aPdf.textContent = "Mở PDF công khai";
      actionsDiv.appendChild(aPdf);
    } else {
      const oaBadge = envDocument.createElement("span");
      oaBadge.className = "badge badge-oa-unknown";
      oaBadge.textContent = "Toàn văn / PDF: Chưa xác nhận quyền truy cập mở (oa_unknown) — chỉ có liên kết trang thông tin bài báo";
      actionsDiv.appendChild(oaBadge);
    }

    const btnDetail = envDocument.createElement("button");
    btnDetail.type = "button";
    btnDetail.className = "btn btn-secondary btn-small";
    btnDetail.textContent = "Xem chi tiết & Provenance";
    btnDetail.addEventListener("click", function () {
      showDetailPanel(hit);
    });
    actionsDiv.appendChild(btnDetail);

    // Nút Lưu vào thư viện (Idempotent & bảo vệ double-click)
    const btnSave = envDocument.createElement("button");
    btnSave.type = "button";
    btnSave.className = "btn btn-primary btn-small";
    btnSave.textContent = "Lưu vào thư viện";

    if (savedLibraryCanonicalIds.has(hit.canonical_id)) {
      btnSave.disabled = true;
      btnSave.className = "btn btn-secondary btn-small badge-idempotent";
      btnSave.textContent = "Đã có trong thư viện (save_idempotent) lúc " + savedLibraryCanonicalIds.get(hit.canonical_id);
    }

    btnSave.addEventListener("click", function () {
      savePaperToLibrary(hit, btnSave);
    });
    actionsDiv.appendChild(btnSave);

    card.appendChild(actionsDiv);
    return card;
  }

  /**
   * Hiển thị bảng Chi tiết & Dấu vết nguồn (Provenance Panel)
   * Render đối chiếu đầy đủ từng FieldEvidence khi có xung đột
   */
  function showDetailPanel(hit) {
    if (!envDocument) return;
    const panel = envDocument.getElementById("detail-panel");
    const body = envDocument.getElementById("detail-body");
    if (!panel || !body) return;

    while (body.firstChild) body.removeChild(body.firstChild);

    if (!hit || !hit.display || !hit.display.field_provenance) {
      addBanner("error", "Không thể hiển thị chi tiết: Bản ghi thiếu trường field_provenance bắt buộc.");
      return;
    }

    // 1. Thông tin định danh
    const idInfo = envDocument.createElement("p");
    idInfo.textContent = "Canonical ID: " + hit.canonical_id;
    body.appendChild(idInfo);

    // 2. Bảng Field Provenance
    const provH4 = envDocument.createElement("h4");
    provH4.textContent = "Dấu vết nguồn từng trường (Field Provenance):";
    body.appendChild(provH4);

    const table = envDocument.createElement("table");
    table.className = "provenance-table";

    const thead = envDocument.createElement("thead");
    const trHead = envDocument.createElement("tr");
    ["Trường", "Nguồn", "ID nguồn", "Raw SHA-256", "Trường gốc"].forEach(function (hText) {
      const th = envDocument.createElement("th");
      th.textContent = hText;
      trHead.appendChild(th);
    });
    thead.appendChild(trHead);
    table.appendChild(thead);

    const tbody = envDocument.createElement("tbody");
    for (const fieldName of Object.keys(hit.display.field_provenance)) {
      const evidences = hit.display.field_provenance[fieldName] || [];
      for (const ev of evidences) {
        const tr = envDocument.createElement("tr");

        const tdField = envDocument.createElement("td");
        tdField.textContent = fieldName;
        tr.appendChild(tdField);

        const tdSource = envDocument.createElement("td");
        tdSource.textContent = ev.source;
        tr.appendChild(tdSource);

        const tdId = envDocument.createElement("td");
        tdId.textContent = ev.source_id;
        tr.appendChild(tdId);

        const tdHash = envDocument.createElement("td");
        tdHash.className = "provenance-hash";
        tdHash.textContent = ev.raw_sha256 ? ev.raw_sha256.substring(0, 16) + "\u2026" : "N/A";
        tr.appendChild(tdHash);

        const tdRawField = envDocument.createElement("td");
        tdRawField.textContent = ev.raw_field;
        tr.appendChild(tdRawField);

        tbody.appendChild(tr);
      }
    }
    table.appendChild(tbody);
    body.appendChild(table);

    // 3. Xung đột metadata giữa các nguồn: Render từng FieldEvidence để đối chiếu
    if (hit.conflicts && Object.keys(hit.conflicts).length > 0) {
      const confH4 = envDocument.createElement("h4");
      confH4.style.marginTop = "1rem";
      confH4.style.color = "var(--warning-text)";
      confH4.textContent = "Đối chiếu xung đột metadata giữa các nguồn:";
      body.appendChild(confH4);

      for (const fName of Object.keys(hit.conflicts)) {
        const pConf = envDocument.createElement("p");
        pConf.textContent = "- Trường '" + fName + "' có sự khác biệt giữa các nguồn:";
        body.appendChild(pConf);

        const confTable = envDocument.createElement("table");
        confTable.className = "provenance-table conflict-table";
        const cThead = envDocument.createElement("thead");
        const cTrHead = envDocument.createElement("tr");
        ["Nguồn", "ID nguồn", "Raw SHA-256", "Trường gốc"].forEach(function (hText) {
          const th = envDocument.createElement("th");
          th.textContent = hText;
          cTrHead.appendChild(th);
        });
        cThead.appendChild(cTrHead);
        confTable.appendChild(cThead);

        const cTbody = envDocument.createElement("tbody");
        const evList = hit.conflicts[fName] || [];
        for (const ev of evList) {
          const tr = envDocument.createElement("tr");
          const tdSrc = envDocument.createElement("td");
          tdSrc.textContent = ev.source;
          tr.appendChild(tdSrc);
          const tdId = envDocument.createElement("td");
          tdId.textContent = ev.source_id;
          tr.appendChild(tdId);
          const tdH = envDocument.createElement("td");
          tdH.className = "provenance-hash";
          tdH.textContent = ev.raw_sha256 ? ev.raw_sha256.substring(0, 16) + "\u2026" : "N/A";
          tr.appendChild(tdH);
          const tdRaw = envDocument.createElement("td");
          tdRaw.textContent = ev.raw_field;
          tr.appendChild(tdRaw);
          cTbody.appendChild(tr);
        }
        confTable.appendChild(cTbody);
        body.appendChild(confTable);
      }
    }

    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth" });
  }

  // =========================================================================
  // QUẢN LÝ THƯ VIỆN CÁ NHÂN (LIBRARY OPERATIONS)
  // =========================================================================

  /**
   * Lưu bài báo vào thư viện cá nhân (POST /public/library)
   * Sử dụng snapshot_id của displayedSnapshot (hỗ trợ lưu partial/stale),
   * chống double-click và guard late responses
   */
  async function savePaperToLibrary(hit, btnElement) {
    const targetSnapshot = displayedSnapshot;
    if (!targetSnapshot || !targetSnapshot.snapshot_id) {
      addBanner("error", "Không thể lưu bài: Thiếu snapshot_id hợp lệ của kết quả đang hiển thị");
      return;
    }

    const canonicalId = hit.canonical_id;

    if (pendingSaveCanonicalIds.has(canonicalId)) {
      return;
    }
    if (savedLibraryCanonicalIds.has(canonicalId)) {
      return;
    }

    pendingSaveCanonicalIds.add(canonicalId);
    const targetSnapshotId = targetSnapshot.snapshot_id;

    const payload = {
      snapshot_id: targetSnapshotId,
      canonical_id: canonicalId
    };

    try {
      if (btnElement) {
        btnElement.disabled = true;
        btnElement.textContent = "Đang lưu…";
      }

      const res = await envFetch("/public/library", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) await throwLibraryHttpError(res);

      const envelope = await res.json();
      validateLibrarySaveEnvelope(envelope);
      const entry = envelope.entry;

      // Identity validation: canonical_id must match requested paper and hit identity
      if (entry.canonical_id !== canonicalId) {
        throw new Error("Phản hồi LibraryEntry không khớp canonical_id đã gửi (" + entry.canonical_id + " !== " + canonicalId + ")");
      }
      if (!entry.hit || entry.hit.canonical_id !== canonicalId) {
        throw new Error("Phản hồi LibraryEntry chứa hit không khớp canonical_id đã gửi");
      }
      // Note: Store idempotency retains the existing entry's original snapshot_id/provenance
      // when duplicate save comes from a newer snapshot. Do not reject differing snapshot_id;
      // treat verified canonical identity as success and retain truthful response snapshot/provenance.

      savedLibraryCanonicalIds.set(canonicalId, entry.saved_at);
      pendingSaveCanonicalIds.delete(canonicalId);

      // Guard late response: chỉ cập nhật nút nếu nút còn gắn trong DOM
      if (btnElement && (typeof btnElement.isConnected === "undefined" || btnElement.isConnected)) {
        btnElement.disabled = true;
        btnElement.className = "btn btn-secondary btn-small badge-idempotent";
        btnElement.textContent = "Đã có trong thư viện (save_idempotent) lúc " + entry.saved_at;
      }

      if (entry.incomplete_sources) {
        addBanner("warning", "Bài báo #" + canonicalId + " được lưu từ snapshot không đầy đủ (incomplete_sources=true).");
      }
    } catch (err) {
      pendingSaveCanonicalIds.delete(canonicalId);
      if (btnElement && (typeof btnElement.isConnected === "undefined" || btnElement.isConnected)) {
        btnElement.disabled = false;
        btnElement.textContent = "Lưu vào thư viện";
      }
      addBanner("error", "Lưu bài báo thất bại: " + err.message);
    }
  }

  /**
   * Tải danh sách thư viện (GET /public/library) có phân trang
   * và sequence guard chống race condition
   */
  async function throwLibraryHttpError(res) {
    let envelope;
    try {
      envelope = await res.json();
      validateEnvelope(envelope);
      if (envelope.overall !== "failed" || envelope.errors.length === 0) {
        throw new Error("Phản hồi lỗi phải có overall=failed và errors không rỗng");
      }
    } catch (err) {
      throw new Error("HTTP " + res.status + ": phản hồi lỗi không hợp lệ: " + err.message);
    }
    throw new Error("HTTP " + res.status + ": " + envelope.errors.map(function (e) {
      return "[" + e.kind + "] " + e.message;
    }).join("; "));
  }

  async function loadLibrary(offset, limit) {
    if (!envDocument) return;
    offset = typeof offset === "number" ? offset : 0;
    limit = typeof limit === "number" ? limit : LIBRARY_PAGE_SIZE;

    const listContainer = envDocument.getElementById("library-list");
    const paginationNav = envDocument.getElementById("library-pagination");
    if (!listContainer) return;

    if (activeLibraryAbortController) {
      activeLibraryAbortController.abort();
    }
    activeLibraryAbortController = typeof AbortController !== "undefined" ? new AbortController() : null;
    const seq = ++currentLibrarySeq;

    while (listContainer.firstChild) listContainer.removeChild(listContainer.firstChild);
    if (paginationNav) paginationNav.hidden = true;

    try {
      const fetchOpts = {
        method: "GET",
        headers: { "Accept": "application/json" }
      };
      if (activeLibraryAbortController) {
        fetchOpts.signal = activeLibraryAbortController.signal;
      }

      const res = await envFetch("/public/library?offset=" + offset + "&limit=" + limit, fetchOpts);
      if (!res.ok) await throwLibraryHttpError(res);

      const envelope = await res.json();
      if (seq !== currentLibrarySeq) return;

      validateLibraryListEnvelope(envelope);
      const entries = envelope.entries;

      updateLibraryCountBadge(entries.length);

      if (entries.length === 0 && offset === 0) {
        const emptyP = envDocument.createElement("p");
        emptyP.className = "banner banner-info";
        emptyP.textContent = "Thư viện hiện đang trống. Hãy tìm kiếm và bấm 'Lưu vào thư viện' để lưu bài báo.";
        listContainer.appendChild(emptyP);
        return;
      }

      for (const entry of entries) {
        savedLibraryCanonicalIds.set(entry.canonical_id, entry.saved_at);
        const card = createLibraryEntryCard(entry);
        listContainer.appendChild(card);
      }

      // Phân trang thư viện
      if (paginationNav) {
        while (paginationNav.firstChild) paginationNav.removeChild(paginationNav.firstChild);

        const btnPrev = envDocument.createElement("button");
        btnPrev.type = "button";
        btnPrev.className = "btn btn-secondary btn-small";
        btnPrev.textContent = "\u2190 Trang trước";
        btnPrev.disabled = offset <= 0;
        btnPrev.addEventListener("click", function () {
          loadLibrary(Math.max(0, offset - limit), limit);
        });
        paginationNav.appendChild(btnPrev);

        const infoSpan = envDocument.createElement("span");
        infoSpan.className = "pagination-info";
        infoSpan.textContent = "Đã tải " + entries.length + " bản ghi (vị trí " + (offset + 1) + "–" + (offset + entries.length) + ")";
        paginationNav.appendChild(infoSpan);

        const btnNext = envDocument.createElement("button");
        btnNext.type = "button";
        btnNext.className = "btn btn-secondary btn-small";
        btnNext.textContent = "Trang sau \u2192";
        btnNext.disabled = entries.length < limit;
        btnNext.addEventListener("click", function () {
          loadLibrary(offset + limit, limit);
        });
        paginationNav.appendChild(btnNext);

        paginationNav.hidden = false;
      }
    } catch (err) {
      if (seq !== currentLibrarySeq) return;
      if (err.name === "AbortError") return;
      const errP = envDocument.createElement("p");
      errP.className = "banner banner-error";
      errP.textContent = "Lỗi khi đọc thư viện: " + err.message;
      listContainer.appendChild(errP);
    }
  }

  function createLibraryEntryCard(entry) {
    if (!entry.hit || !entry.hit.display || !entry.hit.display.title) {
      throw new Error("Bản ghi thư viện thiếu trường title bắt buộc");
    }

    const card = envDocument.createElement("article");
    card.className = "result-card";
    card.dataset.canonicalId = entry.canonical_id;

    const topRow = envDocument.createElement("div");
    topRow.className = "card-top";

    const savedBadge = envDocument.createElement("span");
    savedBadge.className = "badge badge-fresh";
    savedBadge.textContent = "Đã lưu: " + entry.saved_at;
    topRow.appendChild(savedBadge);

    if (entry.incomplete_sources) {
      const incBadge = envDocument.createElement("span");
      incBadge.className = "badge badge-incomplete";
      incBadge.textContent = "incomplete_sources";
      topRow.appendChild(incBadge);
    }

    const titleH3 = envDocument.createElement("h3");
    titleH3.className = "card-title";
    titleH3.textContent = entry.hit.display.title;
    topRow.appendChild(titleH3);

    card.appendChild(topRow);

    const display = entry.hit.display;

    const metaP = envDocument.createElement("div");
    metaP.className = "card-meta";
    metaP.textContent = "Canonical ID: " + entry.canonical_id + " · Snapshot: " + entry.snapshot_id +
      " · Năm: " + (display.publication_year !== null && display.publication_year !== undefined ? display.publication_year : "không có");
    card.appendChild(metaP);

    if (display.abstract) {
      const absP = envDocument.createElement("p");
      absP.className = "card-abstract";
      absP.textContent = display.abstract;
      card.appendChild(absP);
    }

    const actions = envDocument.createElement("div");
    actions.className = "card-actions";
    if (isSafeUrl(display.landing_url)) {
      const a = envDocument.createElement("a");
      a.href = display.landing_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "btn btn-outline btn-small";
      a.textContent = "Mở trang bài báo";
      actions.appendChild(a);
    }
    card.appendChild(actions);

    return card;
  }

  function updateLibraryCountBadge(loadedCount) {
    if (!envDocument) return;
    const badge = envDocument.getElementById("library-count-badge");
    if (badge && typeof loadedCount === "number") {
      badge.textContent = loadedCount + " đã tải";
    }
  }

  async function exportLibrary(format) {
    if (isExporting) return;
    isExporting = true;
    const btnExportJson = envDocument ? envDocument.getElementById("btn-export-json") : null;
    const btnExportBibtex = envDocument ? envDocument.getElementById("btn-export-bibtex") : null;
    if (btnExportJson) btnExportJson.disabled = true;
    if (btnExportBibtex) btnExportBibtex.disabled = true;

    try {
      const res = await envFetch("/public/library/export?format=" + format, {
        method: "GET",
        headers: { "Accept": format === "json" ? "application/json" : "text/plain" }
      });

      if (!res.ok) {
        throw new Error("Lỗi máy chủ khi xuất dữ liệu (HTTP " + res.status + ")");
      }

      const blobText = await res.text();
      downloadTextFile("library_export." + (format === "json" ? "json" : "bib"), blobText);
      addBanner("success", "Đã xuất thư viện định dạng " + format.toUpperCase() + " thành công.");
    } catch (err) {
      addBanner("error", "Xuất thư viện thất bại: " + err.message);
    } finally {
      isExporting = false;
      if (btnExportJson) btnExportJson.disabled = false;
      if (btnExportBibtex) btnExportBibtex.disabled = false;
    }
  }

  function downloadTextFile(filename, text) {
    if (!envDocument) {
      throw new Error("Không thể tải tệp: thiếu tài nguyên document");
    }
    if (typeof Blob === "undefined") {
      throw new Error("Không thể tải tệp: môi trường thiếu Blob API");
    }
    if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
      throw new Error("Không thể tải tệp: môi trường thiếu URL.createObjectURL API");
    }
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    let a = null;
    try {
      a = envDocument.createElement("a");
      a.href = url;
      a.download = filename;
      if (!envDocument.body) {
        throw new Error("Không thể tải tệp: document.body không tồn tại");
      }
      envDocument.body.appendChild(a);
      if (typeof a.click === "function") {
        a.click();
      } else {
        throw new Error("Không thể tải tệp: thẻ liên kết không hỗ trợ phương thức click()");
      }
    } finally {
      if (a && a.parentNode) {
        a.parentNode.removeChild(a);
      }
      if (typeof URL.revokeObjectURL === "function") {
        URL.revokeObjectURL(url);
      }
    }
  }

  // Tự động khởi tạo nếu chạy trên trình duyệt
  if (typeof window !== "undefined" && typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () {
        init({ document: document, fetchFn: window.fetch.bind(window) });
      });
    } else {
      init({ document: document, fetchFn: window.fetch.bind(window) });
    }
  }

  return {
    CONTRACT_VERSION: CONTRACT_VERSION,
    SCHEMA_VERSION: SCHEMA_VERSION,
    YEAR_MIN: YEAR_MIN,
    YEAR_MAX: YEAR_MAX,
    SNAPSHOT_PAGE_SIZE: SNAPSHOT_PAGE_SIZE,
    init: init,
    isSafeUrl: isSafeUrl,
    isIsoTimeWithTz: isIsoTimeWithTz,
    validateSearchRequest: validateSearchRequest,
    validateSearchError: validateSearchError,
    validateRawReference: validateRawReference,
    validateFieldEvidence: validateFieldEvidence,
    validatePaperRecord: validatePaperRecord,
    validateSourceResult: validateSourceResult,
    validateRankedHit: validateRankedHit,
    validateFusionCounts: validateFusionCounts,
    validateFusionResult: validateFusionResult,
    validateSearchSnapshot: validateSearchSnapshot,
    validateEnvelope: validateEnvelope,
    validateLibraryEntry: validateLibraryEntry,
    validateLibrarySaveEnvelope: validateLibrarySaveEnvelope,
    validateLibraryListEnvelope: validateLibraryListEnvelope,
    collectFormInputs: collectFormInputs,
    validateFormInputs: validateFormInputs,
    handleSearchSubmit: handleSearchSubmit,
    renderSearchResults: renderSearchResults,
    renderSnapshotPagination: renderSnapshotPagination,
    changeSnapshotPage: changeSnapshotPage,
    createResultCard: createResultCard,
    showDetailPanel: showDetailPanel,
    savePaperToLibrary: savePaperToLibrary,
    loadLibrary: loadLibrary,
    exportLibrary: exportLibrary,
    downloadTextFile: downloadTextFile,
    switchTab: switchTab,
    addBanner: addBanner,
    clearBanners: clearBanners,
    setLoadingState: setLoadingState
  };
});
