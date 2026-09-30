"""Build the standalone VN labeling kit (.zip + offline HTML tool) and merge A/B labels (SG-033).

Subcommands:
  1. build-kit:
     Reads data/annotations/vn_pool.json and data/processed/openalex/works.jsonl
     (read-only; NEVER reads vn_pool_provenance.json so blinding is mathematically
     guaranteed) and builds:
       - artifacts/vn_labeling_kit_SG033/label_tool.html (standalone offline web app)
       - artifacts/vn_labeling_kit_SG033/templates/vn_labels_A_dev.jsonl
       - artifacts/vn_labeling_kit_SG033/templates/vn_labels_B_dev.jsonl
       - artifacts/vn_labeling_kit_SG033/templates/vn_labels_A_test.jsonl
       - artifacts/vn_labeling_kit_SG033/templates/vn_labels_B_test.jsonl
       - artifacts/vn_labeling_kit_SG033/HUONG_DAN_GAN_NHAN.md
       - artifacts/vn_labeling_kit_SG033.zip (ready to send to teammate)

  2. merge:
     Combines independent JSONL files from Annotator A and Annotator B (plus
     optional adjudicated JSONL file) into a target vn_labels.jsonl after
     strict validation (no null labels, no provenance leak, valid grades).

  3. export-disagreements:
     Extracts pairs where independent Annotator A and Annotator B disagree into
     a JSONL template with round="adjudicated" for post-kappa adjudication.

Anti-Silent-Bypass: exits 1 on any missing input, provenance leak, null label,
or pair mismatch.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FORBIDDEN_KEYS = ("method", "system", "score", "rank", "provenance", "source")
VALID_LABELS = (0, 1, 2, "unjudged")


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def _load_works_map(works_path: Path) -> dict[str, dict[str, Any]]:
    if not works_path.is_file():
        raise FileNotFoundError(f"Missing works file: {works_path}")
    from scholargraph.ingest.openalex import canonical_openalex_work_id

    works: dict[str, dict[str, Any]] = {}
    with open(works_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            raw_id = str(row.get("id") or row.get("doc_id") or row.get("work_id") or "").strip()
            if not raw_id:
                raise ValueError(f"Line {lineno} in {works_path} lacks work ID")
            wid = canonical_openalex_work_id(raw_id) if ("openalex.org/" in raw_id or raw_id.startswith("W") or raw_id.startswith("openalex:")) else raw_id
            inv = row.get("abstract_inverted_index")
            if isinstance(inv, dict):
                words = sorted(((p, w) for w, ps in inv.items() for p in ps), key=lambda t: t[0])
                abstract = " ".join(w for _, w in words)
            else:
                abstract = str(row.get("abstract") or "").strip()
            works[wid] = {
                "title": str(row.get("title") or "").strip(),
                "abstract": abstract,
                "year": row.get("publication_year", row.get("year")),
            }
    return works


def _build_enriched_pool(pool_path: Path, works_path: Path) -> dict[str, Any]:
    if not pool_path.is_file():
        raise FileNotFoundError(f"Missing pool file: {pool_path}")
    pool_doc = json.loads(pool_path.read_text(encoding="utf-8"))
    if not pool_doc.get("blinded"):
        raise ValueError("vn_pool.json is not marked blinded=true")

    works = _load_works_map(works_path)
    enriched_pools: list[dict[str, Any]] = []
    for p in pool_doc.get("pools", []):
        qid = str(p["query_id"])
        cands_out: list[dict[str, Any]] = []
        for c in p.get("candidates", []):
            for bad in FORBIDDEN_KEYS:
                if bad in c:
                    raise ValueError(f"Pool candidate ({qid}, {c.get('doc_id')}) leaks {bad!r}")
            did = str(c["doc_id"])
            if did not in works:
                raise ValueError(f"Pooled doc {did} missing from {works_path}")
            w = works[did]
            cands_out.append(
                {
                    "position": int(c["position"]),
                    "doc_id": did,
                    "title": w["title"] or str(c.get("title") or ""),
                    "abstract": w["abstract"],
                    "year": w["year"] if w["year"] is not None else c.get("year"),
                }
            )
        enriched_pools.append(
            {
                "query_id": qid,
                "split": str(p["split"]),
                "intent_family": str(p.get("intent_family") or ""),
                "text_vi": str(p["text_vi"]),
                "text_en": str(p.get("text_en") or ""),
                "pool_size": len(cands_out),
                "candidates": cands_out,
            }
        )
    return {
        "schema_version": 1,
        "task_id": "SG-033",
        "blinded": True,
        "counts": pool_doc.get("counts", {}),
        "pools": enriched_pools,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ScholarGraph VN — Công cụ Gán nhãn Độc lập (SG-033)</title>
<style>
  :root {
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #0f172a;
    --muted: #475569;
    --border: #e2e8f0;
    --primary: #2563eb;
    --g0: #ef4444;
    --g1: #f59e0b;
    --g2: #10b981;
    --gu: #64748b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.55;
  }
  header {
    background: #0f172a;
    color: #fff;
    padding: 14px 24px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  header h1 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }
  .toolbar label {
    font-size: 13px;
    color: #cbd5e1;
  }
  .toolbar select, .toolbar button {
    padding: 6px 11px;
    border-radius: 6px;
    border: 1px solid #334155;
    font-size: 13px;
    background: #1e293b;
    color: #fff;
    cursor: pointer;
  }
  .toolbar button.export-btn {
    background: #2563eb;
    border-color: #3b82f6;
    font-weight: 600;
  }
  .toolbar button.export-btn:hover { background: #1d4ed8; }
  .container {
    max-width: 1120px;
    margin: 18px auto;
    padding: 0 16px 48px;
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 18px;
  }
  @media (max-width: 860px) {
    .container { grid-template-columns: 1fr; }
  }
  .sidebar, .main-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  }
  .progress-box {
    margin-bottom: 14px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }
  .progress-bar-bg {
    width: 100%;
    height: 8px;
    background: #e2e8f0;
    border-radius: 99px;
    overflow: hidden;
    margin: 6px 0;
  }
  .progress-bar-fill {
    height: 100%;
    background: var(--g2);
    width: 0%;
    transition: width 0.2s;
  }
  .pair-list {
    max-height: 520px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .pair-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 8px;
    border-radius: 6px;
    font-size: 12.5px;
    cursor: pointer;
    border: 1px solid transparent;
  }
  .pair-item:hover { background: #f1f5f9; }
  .pair-item.active {
    border-color: var(--primary);
    background: #eff6ff;
    font-weight: 600;
  }
  .badge {
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    color: #fff;
  }
  .badge-null { background: #cbd5e1; color: #334155; }
  .badge-0 { background: var(--g0); }
  .badge-1 { background: var(--g1); }
  .badge-2 { background: var(--g2); }
  .badge-unjudged { background: var(--gu); }
  .query-banner {
    background: #f8fafc;
    border-left: 4px solid var(--primary);
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 16px;
  }
  .query-meta {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 4px;
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }
  .query-vi {
    font-size: 17px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 4px;
  }
  .query-en {
    font-size: 13.5px;
    color: #334155;
    font-style: italic;
  }
  .doc-box {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
  }
  .doc-meta {
    font-size: 12.5px;
    color: var(--muted);
    margin-bottom: 6px;
    font-family: Consolas, monospace;
  }
  .doc-title {
    font-size: 16.5px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 10px;
  }
  .doc-abstract {
    font-size: 14.5px;
    color: #1e293b;
    white-space: pre-wrap;
    background: #fcfcfd;
    padding: 12px;
    border-radius: 6px;
    border: 1px solid #f1f5f9;
    max-height: 300px;
    overflow-y: auto;
  }
  .grade-buttons {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 14px;
  }
  @media (max-width: 640px) {
    .grade-buttons { grid-template-columns: 1fr 1fr; }
  }
  .grade-btn {
    padding: 12px 10px;
    border-radius: 8px;
    border: 2px solid var(--border);
    background: #fff;
    cursor: pointer;
    text-align: left;
    transition: all 0.12s;
  }
  .grade-btn:hover { border-color: #94a3b8; }
  .grade-btn .title { font-weight: 700; font-size: 14px; display: block; }
  .grade-btn .desc { font-size: 11.5px; color: var(--muted); display: block; margin-top: 2px; }
  .grade-btn.selected-0 { border-color: var(--g0); background: #fef2f2; }
  .grade-btn.selected-1 { border-color: var(--g1); background: #fffbeb; }
  .grade-btn.selected-2 { border-color: var(--g2); background: #ecfdf5; }
  .grade-btn.selected-unjudged { border-color: var(--gu); background: #f1f5f9; }
  .nav-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
  }
  .nav-row input[type="text"] {
    flex: 1;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
  }
  .nav-btn {
    padding: 8px 14px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: #f8fafc;
    cursor: pointer;
    font-weight: 600;
  }
  .nav-btn:hover { background: #e2e8f0; }
  details.rubric {
    margin-top: 16px;
    font-size: 13px;
    color: #334155;
    border-top: 1px solid var(--border);
    padding-top: 12px;
  }
</style>
</head>
<body>
<header>
  <h1>ScholarGraph VN — Công cụ Gán nhãn Độc lập (SG-033)</h1>
  <div class="toolbar">
    <label>Người chấm:
      <select id="annotatorSelect">
        <option value="A">Thành viên A (Annotator A)</option>
        <option value="B">Thành viên B (Annotator B)</option>
      </select>
    </label>
    <label>Vòng chấm:
      <select id="roundSelect">
        <option value="independent">Độc lập (independent)</option>
        <option value="adjudicated">Phân xử (adjudicated)</option>
      </select>
    </label>
    <label>Tập (Split):
      <select id="splitFilter">
        <option value="dev">1. Dev (219 cặp — chấm trước)</option>
        <option value="test">2. Test (443 cặp — sau freeze SG-034)</option>
        <option value="all">Tất cả (662 cặp)</option>
      </select>
    </label>
    <label>Hiển thị:
      <select id="statusFilter">
        <option value="all">Tất cả cặp</option>
        <option value="unlabeled">Chỉ cặp chưa chấm</option>
      </select>
    </label>
    <button type="button" id="importBtn">Nhập JSONL đã lưu...</button>
    <input type="file" id="importFile" accept=".jsonl,.json" style="display:none">
    <button type="button" class="export-btn" id="exportSplitBtn">Tải xuống JSONL (Tập đang chọn)</button>
  </div>
</header>

<div class="container">
  <aside class="sidebar">
    <div class="progress-box">
      <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:600;">
        <span id="progressLabel">Tiến độ: 0 / 219</span>
        <span id="progressPct">0%</span>
      </div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" id="progressFill"></div></div>
      <div style="font-size:11.5px;color:#64748b;" id="overallStats">Dev: 0/219 | Test: 0/443</div>
    </div>
    <div class="pair-list" id="pairList"></div>
  </aside>

  <main class="main-card">
    <div class="query-banner">
      <div class="query-meta">
        <span id="qMetaId">Query: —</span>
        <span id="qMetaSplit">Split: —</span>
        <span id="qMetaIntent">Chủ đề: —</span>
        <span id="qMetaPos">Ứng viên: —</span>
      </div>
      <div class="query-vi" id="qTextVi">—</div>
      <div class="query-en" id="qTextEn">—</div>
    </div>

    <div class="doc-box">
      <div class="doc-meta" id="docMeta">Doc ID: — | Năm: —</div>
      <div class="doc-title" id="docTitle">—</div>
      <div class="doc-abstract" id="docAbstract">—</div>
    </div>

    <div class="grade-buttons">
      <button type="button" class="grade-btn" data-grade="0" onclick="setGrade(0)">
        <span class="title">[Phím 0] 0 — Không liên quan</span>
        <span class="desc">Không trả lời phần nào của câu hỏi hoặc chỉ trùng từ khóa bề mặt.</span>
      </button>
      <button type="button" class="grade-btn" data-grade="1" onclick="setGrade(1)">
        <span class="title">[Phím 1] 1 — Liên quan một phần</span>
        <span class="desc">Cùng chủ đề/cơ chế nhưng chỉ trả lời một khía cạnh hoặc khác đối tượng/quy mô.</span>
      </button>
      <button type="button" class="grade-btn" data-grade="2" onclick="setGrade(2)">
        <span class="title">[Phím 2] 2 — Liên quan trực tiếp</span>
        <span class="desc">Trả lời trực tiếp toàn bộ câu hỏi với thiết kế/dữ liệu phù hợp.</span>
      </button>
      <button type="button" class="grade-btn" data-grade="unjudged" onclick="setGrade('unjudged')">
        <span class="title">[Phím U] Unjudged</span>
        <span class="desc">Thiếu thông tin (chỉ có tiêu đề, không đủ kết luận) — bắt buộc ghi lý do ở ô Note.</span>
      </button>
    </div>

    <div class="nav-row">
      <button type="button" class="nav-btn" onclick="moveIndex(-1)">← Trước (Phím ←)</button>
      <input type="text" id="noteInput" placeholder="Ghi chú tùy chọn (bắt buộc nếu chọn Unjudged)..." oninput="saveNote(this.value)">
      <button type="button" class="nav-btn" onclick="moveIndex(1)">Tiếp theo (Phím →) →</button>
    </div>

    <details class="rubric" open>
      <summary style="font-weight:600;cursor:pointer;">Hướng dẫn nhanh & Quy tắc gán nhãn (ANNOTATION_GUIDE SG-031/SG-033)</summary>
      <ul style="margin:8px 0 0 18px;padding:0;">
        <li><strong>Làm mù hoàn toàn (Blinded):</strong> Thứ tự bài báo đã được xáo trộn ngẫu nhiên (`seed=20260915`) và ẩn hoàn toàn tên thuật toán/điểm số.</li>
        <li><strong>Chấm độc lập:</strong> Thành viên A và Thành viên B chấm riêng (không xem nhãn của nhau). Chấm xong <strong>219 cặp Dev</strong> trước → bấm <em>"Tải xuống JSONL"</em> gửi lại để tính hệ số đồng thuận Kappa và khóa cấu hình <code>SG-034</code> → sau đó mới chấm <strong>443 cặp Test</strong>.</li>
        <li><strong>Phím tắt:</strong> Bấm phím <code>0</code>, <code>1</code>, <code>2</code>, hoặc <code>U</code> để gán nhãn và tự động chuyển sang cặp tiếp theo; phím mũi tên <code>←</code> / <code>→</code> để lùi/tiến. Tiến độ được tự động lưu vào trình duyệt (<code>localStorage</code>).</li>
      </ul>
    </details>
  </main>
</div>

<script id="poolDataScript" type="application/json">__POOL_JSON_PLACEHOLDER__</script>
<script>
const POOL_DOC = JSON.parse(document.getElementById('poolDataScript').textContent);
const ALL_PAIRS = [];
for (const p of POOL_DOC.pools) {
  for (const c of p.candidates) {
    ALL_PAIRS.push({
      key: p.query_id + '__' + c.doc_id,
      query_id: p.query_id,
      split: p.split,
      intent_family: p.intent_family,
      text_vi: p.text_vi,
      text_en: p.text_en,
      pool_size: p.pool_size,
      position: c.position,
      doc_id: c.doc_id,
      title: c.title,
      abstract: c.abstract || '',
      year: c.year
    });
  }
}

const STORAGE_KEY = 'scholargraph_sg033_labels_v1';
let state = {
  annotator: 'A',
  round: 'independent',
  splitFilter: 'dev',
  statusFilter: 'all',
  currentIndex: 0,
  records: {}
};

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      state = Object.assign(state, parsed);
    }
  } catch (e) { console.error(e); }
  document.getElementById('annotatorSelect').value = state.annotator;
  document.getElementById('roundSelect').value = state.round;
  document.getElementById('splitFilter').value = state.splitFilter;
  document.getElementById('statusFilter').value = state.statusFilter;
}

function persistState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) { console.error(e); }
}

function recordKey(pair) {
  return state.annotator + '::' + state.round + '::' + pair.key;
}

function getRecord(pair) {
  return state.records[recordKey(pair)] || { label: null, note: null };
}

function getFilteredPairs() {
  return ALL_PAIRS.filter(p => {
    if (state.splitFilter !== 'all' && p.split !== state.splitFilter) return false;
    if (state.statusFilter === 'unlabeled' && getRecord(p).label !== null) return false;
    return true;
  });
}

function renderSidebar() {
  const filtered = getFilteredPairs();
  if (state.currentIndex >= filtered.length) state.currentIndex = Math.max(0, filtered.length - 1);

  const splitPairs = ALL_PAIRS.filter(p => state.splitFilter === 'all' ? true : p.split === state.splitFilter);
  const doneSplit = splitPairs.filter(p => getRecord(p).label !== null).length;
  const pct = splitPairs.length ? Math.round((doneSplit * 100) / splitPairs.length) : 0;
  document.getElementById('progressLabel').textContent = `Tiến độ (${state.splitFilter.toUpperCase()}): ${doneSplit} / ${splitPairs.length}`;
  document.getElementById('progressPct').textContent = `${pct}%`;
  document.getElementById('progressFill').style.width = `${pct}%`;

  const devDone = ALL_PAIRS.filter(p => p.split === 'dev' && getRecord(p).label !== null).length;
  const testDone = ALL_PAIRS.filter(p => p.split === 'test' && getRecord(p).label !== null).length;
  document.getElementById('overallStats').textContent = `Người chấm ${state.annotator} (${state.round}) — Dev: ${devDone}/219 | Test: ${testDone}/443`;

  const listEl = document.getElementById('pairList');
  listEl.innerHTML = '';
  filtered.forEach((p, idx) => {
    const rec = getRecord(p);
    const item = document.createElement('div');
    item.className = 'pair-item' + (idx === state.currentIndex ? ' active' : '');
    const lblText = rec.label === null ? '—' : String(rec.label);
    const badgeClass = rec.label === null ? 'badge-null' : ('badge-' + String(rec.label));
    item.innerHTML = `<span>${p.query_id} #${p.position} <small style="color:#64748b">(${p.doc_id.replace('openalex:', '')})</small></span><span class="badge ${badgeClass}">${lblText}</span>`;
    item.onclick = () => { state.currentIndex = idx; renderAll(); };
    listEl.appendChild(item);
  });
}

function renderMain() {
  const filtered = getFilteredPairs();
  if (!filtered.length) {
    document.getElementById('qTextVi').textContent = 'Không còn cặp nào trong bộ lọc hiện tại.';
    document.getElementById('qTextEn').textContent = '';
    document.getElementById('docTitle').textContent = 'Hãy chuyển bộ lọc Hiển thị sang "Tất cả cặp" hoặc bấm "Tải xuống JSONL".';
    document.getElementById('docAbstract').textContent = '';
    return;
  }
  const p = filtered[state.currentIndex];
  const rec = getRecord(p);

  document.getElementById('qMetaId').textContent = `Query: ${p.query_id}`;
  document.getElementById('qMetaSplit').textContent = `Split: ${p.split.toUpperCase()}`;
  document.getElementById('qMetaIntent').textContent = `Chủ đề: ${p.intent_family}`;
  document.getElementById('qMetaPos').textContent = `Ứng viên: ${p.position} / ${p.pool_size} (Đang xem ${state.currentIndex + 1}/${filtered.length})`;
  document.getElementById('qTextVi').textContent = p.text_vi;
  document.getElementById('qTextEn').textContent = `Bản dịch tham khảo (Opus-MT): ${p.text_en}`;

  document.getElementById('docMeta').textContent = `Doc ID: ${p.doc_id} | Năm xuất bản: ${p.year ?? 'N/A'}`;
  document.getElementById('docTitle').textContent = p.title || '(Không có tiêu đề)';
  document.getElementById('docAbstract').textContent = p.abstract ? p.abstract : '(Bài báo này không có abstract trong dữ liệu gốc — chỉ có tiêu đề. Nếu tiêu đề không đủ thông tin để kết luận, hãy chọn Unjudged kèm ghi chú.)';

  document.getElementById('noteInput').value = rec.note || '';

  document.querySelectorAll('.grade-btn').forEach(btn => {
    const g = btn.getAttribute('data-grade');
    btn.className = 'grade-btn';
    if (rec.label !== null && String(rec.label) === g) {
      btn.classList.add('selected-' + g);
    }
  });
}

function renderAll() {
  renderSidebar();
  renderMain();
  persistState();
}

function setGrade(grade) {
  const filtered = getFilteredPairs();
  if (!filtered.length) return;
  const p = filtered[state.currentIndex];
  const cur = getRecord(p);
  state.records[recordKey(p)] = {
    label: grade,
    note: cur.note || null
  };
  if (state.statusFilter === 'unlabeled') {
    renderAll();
  } else {
    if (state.currentIndex < filtered.length - 1) {
      state.currentIndex += 1;
    }
    renderAll();
  }
}

function saveNote(val) {
  const filtered = getFilteredPairs();
  if (!filtered.length) return;
  const p = filtered[state.currentIndex];
  const cur = getRecord(p);
  state.records[recordKey(p)] = {
    label: cur.label,
    note: val.trim() ? val.trim() : null
  };
  persistState();
}

function moveIndex(delta) {
  const filtered = getFilteredPairs();
  if (!filtered.length) return;
  state.currentIndex = Math.max(0, Math.min(filtered.length - 1, state.currentIndex + delta));
  renderAll();
}

document.getElementById('annotatorSelect').onchange = (e) => {
  state.annotator = e.target.value;
  state.currentIndex = 0;
  renderAll();
};
document.getElementById('roundSelect').onchange = (e) => {
  state.round = e.target.value;
  state.currentIndex = 0;
  renderAll();
};
document.getElementById('splitFilter').onchange = (e) => {
  state.splitFilter = e.target.value;
  state.currentIndex = 0;
  renderAll();
};
document.getElementById('statusFilter').onchange = (e) => {
  state.statusFilter = e.target.value;
  state.currentIndex = 0;
  renderAll();
};

document.getElementById('exportSplitBtn').onclick = () => {
  const targetPairs = ALL_PAIRS.filter(p => state.splitFilter === 'all' ? true : p.split === state.splitFilter);
  const missing = targetPairs.filter(p => getRecord(p).label === null);
  if (missing.length > 0) {
    const ok = confirm(`Cảnh báo: Còn ${missing.length} / ${targetPairs.length} cặp trong tập ${state.splitFilter.toUpperCase()} chưa được gán nhãn (label = null). Bạn vẫn muốn tải xuống bản nháp JSONL chứ?`);
    if (!ok) return;
  }
  const lines = targetPairs.map(p => {
    const rec = getRecord(p);
    return JSON.stringify({
      query_id: p.query_id,
      doc_id: p.doc_id,
      label: rec.label,
      annotator: state.annotator,
      round: state.round,
      note: rec.note || null
    });
  });
  const blob = new Blob([lines.join('\\n') + '\\n'], { type: 'application/x-jsonlines;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `vn_labels_${state.annotator}_${state.splitFilter}.jsonl`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
};

document.getElementById('importBtn').onclick = () => {
  document.getElementById('importFile').click();
};
document.getElementById('importFile').onchange = (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const text = ev.target.result;
      const lines = text.split(/\\r?\\n/).filter(l => l.trim());
      let imported = 0;
      for (const line of lines) {
        const row = JSON.parse(line);
        if (row.query_id && row.doc_id) {
          const ann = row.annotator || state.annotator;
          const rnd = row.round || state.round;
          const k = ann + '::' + rnd + '::' + row.query_id + '__' + row.doc_id;
          state.records[k] = {
            label: row.label !== undefined ? row.label : null,
            note: row.note || null
          };
          imported += 1;
        }
      }
      alert(`Đã nhập thành công ${imported} dòng nhãn!`);
      renderAll();
    } catch (err) {
      alert('Lỗi đọc file JSONL: ' + err.message);
    }
  };
  reader.readAsText(file, 'utf-8');
};

window.addEventListener('keydown', (e) => {
  if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
  if (e.key === '0') { e.preventDefault(); setGrade(0); }
  else if (e.key === '1') { e.preventDefault(); setGrade(1); }
  else if (e.key === '2') { e.preventDefault(); setGrade(2); }
  else if (e.key === 'u' || e.key === 'U') { e.preventDefault(); setGrade('unjudged'); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); moveIndex(-1); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); moveIndex(1); }
});

loadState();
renderAll();
</script>
</body>
</html>
"""


GUIDE_MD = r"""# Hướng dẫn Gán nhãn Độc lập Truy vấn Tiếng Việt — `SG-033`

Bộ công cụ này đã đóng gói sẵn toàn bộ **30 câu hỏi tiếng Việt** (`10 dev = 219 cặp`, `20 test = 443 cặp`) kèm **tiêu đề + tóm tắt (abstract) đầy đủ** của từng bài báo ứng viên trong một file giao diện duy nhất chạy offline trên trình duyệt.

---

## 1. Cách mở công cụ và gán nhãn (Không cần cài đặt Python)

1. Giải nén file `vn_labeling_kit_SG033.zip` ra một thư mục trên máy tính.
2. Nhấp đúp mở file **`label_tool.html`** bằng trình duyệt bất kỳ (Chrome, Edge, Firefox, Brave...).
3. Trên thanh công cụ màu đen ở góc trên:
   - **Người chấm:**
     - Nếu bạn là Thành viên A: chọn **`Thành viên A (Annotator A)`**.
     - Nếu bạn là Thành viên B: chọn **`Thành viên B (Annotator B)`**.
   - **Vòng chấm:** Giữ mặc định là **`Độc lập (independent)`**.
   - **Tập (Split):**
     - **BƯỚC 1 (Làm ngay):** Chọn **`1. Dev (219 cặp — chấm trước)`**.
     - **BƯỚC 2 (Sau khi nhóm đã chạy khóa cấu hình `SG-034`):** Chọn **`2. Test (443 cặp — sau freeze SG-034)`**.

---

## 2. Thang điểm gán nhãn (`0`, `1`, `2`, `unjudged`)

- **Phím `0` (`0 — Không liên quan`):** Bài báo không chứa thông tin trả lời câu hỏi, hoặc chỉ vô tình trùng vài từ khóa bề mặt nhưng khác chủ đề.
- **Phím `1` (`1 — Liên quan một phần`):** Bài báo cùng chủ đề/cơ chế khoa học nhưng chỉ trả lời một phần câu hỏi, hoặc khác đối tượng/thiết kế nghiên cứu (ví dụ câu hỏi hỏi thử nghiệm lâm sàng trên người cao tuổi nhưng bài báo nghiên cứu trên tế bào/động vật hoặc chỉ đo chỉ số trung gian).
- **Phím `2` (`2 — Liên quan trực tiếp`):** Bài báo trả lời trực tiếp và đúng trọng tâm toàn bộ câu hỏi.
- **Phím `U` (`unjudged — Không đủ thông tin`):** Chỉ dùng khi bài báo khuyết abstract và riêng tiêu đề không đủ để kết luận (ghi ngắn gọn lý do vào ô Note).

> **Mẹo thao tác nhanh:** Bạn có thể bấm trực tiếp phím **`0`**, **`1`**, **`2`**, **`U`** trên bàn phím để chấm và tự động nhảy sang bài tiếp theo; dùng phím mũi tên **`←` / `→`** để quay lại hoặc tiến lên. Mọi thao tác được lưu tự động vào trình duyệt (`localStorage`).

---

## 3. Xuất file kết quả gửi lại cho nhóm

1. Khi chấm đủ `219 / 219` cặp của tập **Dev**, bấm nút màu xanh **`Tải xuống JSONL (Tập đang chọn)`** ở góc trên bên phải:
   - Thành viên A sẽ nhận được file `vn_labels_A_dev.jsonl`.
   - Thành viên B sẽ nhận được file `vn_labels_B_dev.jsonl`.
2. Gửi file `.jsonl` đó về máy chính để chạy kiểm tra độ đồng thuận (Cohen's Kappa) và khóa cấu hình Dev (`SG-034`):
   ```powershell
   .\.venv\Scripts\python.exe scripts\manage_vn_labels.py merge --file-a vn_labels_A_dev.jsonl --file-b vn_labels_B_dev.jsonl --output data/annotations/vn_labels_dev.jsonl
   .\.venv\Scripts\python.exe scripts\score_vn_agreement.py --labels data/annotations/vn_labels_dev.jsonl
   ```
3. Sau khi phân xử các cặp lệch nhãn (nếu có) và chạy `--phase freeze-dev`, hai thành viên tiếp tục chấm **443 cặp Test** và xuất `vn_labels_A_test.jsonl` / `vn_labels_B_test.jsonl`.
"""


def build_kit(pool_path: Path, works_path: Path, out_dir: Path, zip_path: Path) -> dict[str, Any]:
    enriched = _build_enriched_pool(pool_path, works_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    tpl_dir = out_dir / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)

    pool_json_str = json.dumps(enriched, ensure_ascii=False)
    html_content = HTML_TEMPLATE.replace("__POOL_JSON_PLACEHOLDER__", pool_json_str)
    html_path = out_dir / "label_tool.html"
    html_path.write_text(html_content, encoding="utf-8")

    guide_path = out_dir / "HUONG_DAN_GAN_NHAN.md"
    guide_path.write_text(GUIDE_MD, encoding="utf-8")

    for ann in ("A", "B"):
        for split_name in ("dev", "test"):
            rows = []
            for p in enriched["pools"]:
                if p["split"] != split_name:
                    continue
                for c in p["candidates"]:
                    rows.append(
                        json.dumps(
                            {
                                "query_id": p["query_id"],
                                "doc_id": c["doc_id"],
                                "label": None,
                                "annotator": ann,
                                "round": "independent",
                                "note": None,
                            },
                            ensure_ascii=False,
                        )
                    )
            (tpl_dir / f"vn_labels_{ann}_{split_name}.jsonl").write_text(
                "\n".join(rows) + "\n", encoding="utf-8"
            )

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(out_dir.rglob("*")):
            if file_path.is_file():
                arcname = f"vn_labeling_kit_SG033/{file_path.relative_to(out_dir).as_posix()}"
                zf.write(file_path, arcname=arcname)

    dev_pairs = sum(len(p["candidates"]) for p in enriched["pools"] if p["split"] == "dev")
    test_pairs = sum(len(p["candidates"]) for p in enriched["pools"] if p["split"] == "test")
    return {
        "status": "OK",
        "kit_dir": str(out_dir),
        "zip_path": str(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "dev_pairs": dev_pairs,
        "test_pairs": test_pairs,
        "total_pairs": dev_pairs + test_pairs,
    }


def _read_and_validate_jsonl(path: Path, expected_annotator: str | None, expected_round: str) -> dict[tuple[str, str], dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing label file: {path}")
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"Blank line {lineno} in {path}")
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Line {lineno} in {path} is not a JSON object")
        for leaked in FORBIDDEN_KEYS:
            if leaked in row:
                raise ValueError(f"Line {lineno} in {path} leaks system provenance ({leaked!r})")
        for req in ("query_id", "doc_id", "label", "annotator", "round"):
            if req not in row:
                raise ValueError(f"Line {lineno} in {path} lacks required field {req!r}")
        if row["label"] is None:
            raise ValueError(f"Line {lineno} in {path} has null label ({row['query_id']}, {row['doc_id']})")
        if row["label"] != "unjudged" and (type(row["label"]) is not int or row["label"] not in (0, 1, 2)):
            raise ValueError(f"Line {lineno} in {path} has invalid label {row['label']!r}")
        if expected_annotator is not None and row["annotator"] != expected_annotator:
            raise ValueError(
                f"Line {lineno} in {path}: expected annotator={expected_annotator!r}, got {row['annotator']!r}"
            )
        if row["round"] != expected_round:
            raise ValueError(f"Line {lineno} in {path}: expected round={expected_round!r}, got {row['round']!r}")
        key = (str(row["query_id"]), str(row["doc_id"]))
        if key in records:
            raise ValueError(f"Duplicate pair {key} at line {lineno} in {path}")
        records[key] = {
            "query_id": key[0],
            "doc_id": key[1],
            "label": row["label"],
            "annotator": str(row["annotator"]),
            "round": str(row["round"]),
            "note": row.get("note"),
        }
    if not records:
        raise ValueError(f"Empty label file: {path}")
    return records


def merge_labels(
    file_a: Path,
    file_b: Path,
    output_path: Path,
    adjudicated_file: Path | None = None,
) -> dict[str, Any]:
    recs_a = _read_and_validate_jsonl(file_a, "A", "independent")
    recs_b = _read_and_validate_jsonl(file_b, "B", "independent")
    if set(recs_a.keys()) != set(recs_b.keys()):
        only_a = sorted(set(recs_a.keys()) - set(recs_b.keys()))[:3]
        only_b = sorted(set(recs_b.keys()) - set(recs_a.keys()))[:3]
        raise ValueError(f"Pair mismatch between A and B: only_in_A={only_a}, only_in_B={only_b}")

    adj_recs: dict[tuple[str, str], dict[str, Any]] = {}
    if adjudicated_file is not None:
        adj_recs = _read_and_validate_jsonl(adjudicated_file, None, "adjudicated")

    out_lines: list[str] = []
    disagreements = 0
    unresolved = 0
    for key in sorted(recs_a.keys()):
        ra = recs_a[key]
        rb = recs_b[key]
        out_lines.append(json.dumps(ra, ensure_ascii=False))
        out_lines.append(json.dumps(rb, ensure_ascii=False))
        if ra["label"] != rb["label"]:
            disagreements += 1
            if key not in adj_recs:
                unresolved += 1
        if key in adj_recs:
            out_lines.append(json.dumps(adj_recs[key], ensure_ascii=False))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return {
        "status": "OK",
        "output": str(output_path),
        "pairs": len(recs_a),
        "disagreements": disagreements,
        "adjudicated_rows": len(adj_recs),
        "unresolved_disagreements": unresolved,
    }


def export_disagreements(file_a: Path, file_b: Path, output_path: Path) -> dict[str, Any]:
    recs_a = _read_and_validate_jsonl(file_a, "A", "independent")
    recs_b = _read_and_validate_jsonl(file_b, "B", "independent")
    if set(recs_a.keys()) != set(recs_b.keys()):
        raise ValueError("Pair sets in A and B do not match")

    rows: list[str] = []
    for key in sorted(recs_a.keys()):
        la = recs_a[key]["label"]
        lb = recs_b[key]["label"]
        if la != lb:
            rows.append(
                json.dumps(
                    {
                        "query_id": key[0],
                        "doc_id": key[1],
                        "label": None,
                        "annotator": "A",
                        "round": "adjudicated",
                        "note": f"Disagreement: A={la} vs B={lb}",
                    },
                    ensure_ascii=False,
                )
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(("\n".join(rows) + "\n") if rows else "", encoding="utf-8")
    return {
        "status": "OK",
        "disagreements_count": len(rows),
        "output": str(output_path),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Manage SG-033 VN labeling kit and A/B label files")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_kit = sub.add_parser("build-kit", help="Build offline HTML labeling tool and zip archive")
    p_kit.add_argument("--pool", default="data/annotations/vn_pool.json")
    p_kit.add_argument("--works", default="data/processed/openalex/works.jsonl")
    p_kit.add_argument("--out-dir", default="artifacts/vn_labeling_kit_SG033")
    p_kit.add_argument("--zip-out", default="artifacts/vn_labeling_kit_SG033.zip")

    p_merge = sub.add_parser("merge", help="Validate and merge Annotator A and Annotator B JSONL files")
    p_merge.add_argument("--file-a", required=True)
    p_merge.add_argument("--file-b", required=True)
    p_merge.add_argument("--adjudicated", default=None)
    p_merge.add_argument("--output", required=True)

    p_dis = sub.add_parser("export-disagreements", help="Export disagreeing pairs for adjudication")
    p_dis.add_argument("--file-a", required=True)
    p_dis.add_argument("--file-b", required=True)
    p_dis.add_argument("--output", required=True)

    args = ap.parse_args(argv)
    try:
        if args.cmd == "build-kit":
            pool_p = Path(args.pool) if Path(args.pool).is_absolute() else ROOT / args.pool
            works_p = Path(args.works) if Path(args.works).is_absolute() else ROOT / args.works
            out_d = Path(args.out_dir) if Path(args.out_dir).is_absolute() else ROOT / args.out_dir
            zip_p = Path(args.zip_out) if Path(args.zip_out).is_absolute() else ROOT / args.zip_out
            res = build_kit(pool_p, works_p, out_d, zip_p)
            print(json.dumps(res, indent=2))
            return 0
        if args.cmd == "merge":
            fa = Path(args.file_a) if Path(args.file_a).is_absolute() else ROOT / args.file_a
            fb = Path(args.file_b) if Path(args.file_b).is_absolute() else ROOT / args.file_b
            fadj = (
                (Path(args.adjudicated) if Path(args.adjudicated).is_absolute() else ROOT / args.adjudicated)
                if args.adjudicated
                else None
            )
            fout = Path(args.output) if Path(args.output).is_absolute() else ROOT / args.output
            res = merge_labels(fa, fb, fout, fadj)
            print(json.dumps(res, indent=2))
            return 0
        if args.cmd == "export-disagreements":
            fa = Path(args.file_a) if Path(args.file_a).is_absolute() else ROOT / args.file_a
            fb = Path(args.file_b) if Path(args.file_b).is_absolute() else ROOT / args.file_b
            fout = Path(args.output) if Path(args.output).is_absolute() else ROOT / args.output
            res = export_disagreements(fa, fb, fout)
            print(json.dumps(res, indent=2))
            return 0
        return fail(f"Unknown command: {args.cmd}")
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
