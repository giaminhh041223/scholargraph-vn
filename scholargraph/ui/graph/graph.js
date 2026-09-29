/* ScholarGraph VN — Citation graph UI (task SG-037).
   Vanilla JS + SVG, offline, no CDN. Data comes only from the /graph API,
   which reads the real frozen snapshot (manifest-verified). */
const SVG_NS = "http://www.w3.org/2000/svg"; // W3C namespace identifier, not a network resource

const NODE_COLORS = {
  center: "#1d4ed8",
  cites: "#d97706",
  cited_by: "#059669",
  both: "#0d9488",
  multi_hop: "#94a3b8",
};
const EDGE_COLORS = { cites: "#d97706", cited_by: "#059669", other: "#94a3b8" };
const LABEL_LIMIT = 40;

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const detail = body && body.detail !== undefined && body.detail !== null
      ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail))
      : null;
    throw Object.assign(new Error(detail || ("HTTP " + r.status)), { status: r.status });
  }
  return r.json();
}

function el(name, attrs, text) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
  return node;
}

function truncate(text, n) {
  if (text === null || text === undefined) return null;
  return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

function nodeRole(node, centerId, centerOut, centerIn) {
  if (node.doc_id === centerId) return "center";
  const out = centerOut.has(node.doc_id);
  const inn = centerIn.has(node.doc_id);
  if (out && inn) return "both";
  if (out) return "cites";
  if (inn) return "cited_by";
  return "multi_hop";
}

function setStatus(text, kind) {
  const status = document.getElementById("status");
  status.textContent = text;
  status.className = kind || "";
}

function renderGraph(data) {
  const svg = document.getElementById("graph-svg");
  svg.innerHTML = "";
  const centerId = data.doc_id;
  const centerOut = new Set();
  const centerIn = new Set();
  for (const e of data.edges) {
    if (e.src === centerId) centerOut.add(e.dst);
    if (e.dst === centerId) centerIn.add(e.src);
  }

  const defs = el("defs");
  for (const key of Object.keys(EDGE_COLORS)) {
    const marker = el("marker", {
      id: "arrow-" + key, viewBox: "0 0 10 10", refX: "9", refY: "5",
      markerWidth: "6.5", markerHeight: "6.5", orient: "auto-start-reverse",
    });
    marker.appendChild(el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: EDGE_COLORS[key] }));
    defs.appendChild(marker);
  }
  svg.appendChild(defs);

  const CX = 450, CY = 450;
  const RADII = { 1: 180, 2: 340, 3: 450 };
  const byDepth = new Map();
  for (const node of data.nodes) {
    const d = node.depth;
    if (!byDepth.has(d)) byDepth.set(d, []);
    byDepth.get(d).push(node);
  }
  const positions = new Map();
  positions.set(centerId, { x: CX, y: CY });
  for (const depthStr of Object.keys(RADII)) {
    const depth = Number(depthStr);
    const ring = byDepth.get(depth) || [];
    ring.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / Math.max(ring.length, 1) - Math.PI / 2;
      positions.set(node.doc_id, {
        x: CX + RADII[depth] * Math.cos(angle),
        y: CY + RADII[depth] * Math.sin(angle),
      });
    });
  }
  svg.setAttribute("viewBox", "0 0 900 900");

  const edgeLayer = el("g");
  for (const e of data.edges) {
    const a = positions.get(e.src);
    const b = positions.get(e.dst);
    if (!a || !b) continue;
    const cls = e.relation_to_center || "other";
    const line = el("line", {
      x1: a.x.toFixed(1), y1: a.y.toFixed(1),
      x2: b.x.toFixed(1), y2: b.y.toFixed(1),
      class: "edge " + cls + (e.relation_to_center ? " bold" : ""),
      "marker-end": "url(#arrow-" + cls + ")",
    });
    const t = el("title", null,
      e.src + " cites " + e.dst +
      (e.relation_to_center ? " (" + (e.relation_to_center === "cites"
        ? "node đang xem trích dẫn bài này" : "bài này trích dẫn node đang xem") + ")" : ""));
    line.appendChild(t);
    edgeLayer.appendChild(line);
  }
  svg.appendChild(edgeLayer);

  const nodeLayer = el("g");
  const labelLayer = el("g");
  const showLabels = data.nodes.length <= LABEL_LIMIT;
  for (const node of data.nodes) {
    const pos = positions.get(node.doc_id);
    if (!pos) continue;
    const role = nodeRole(node, centerId, centerOut, centerIn);
    const radius = 5 + Math.min(16, 1.4 * Math.sqrt(node.degree));
    const circle = el("circle", {
      cx: pos.x.toFixed(1), cy: pos.y.toFixed(1), r: radius.toFixed(1),
      fill: NODE_COLORS[role], class: "node-circle" + (role === "center" ? " center" : ""),
    });
    const label = node.title || node.doc_id;
    const tip = el("title", null,
      node.doc_id + "\n" + (node.title || "(không có tiêu đề)") +
      "\nNăm: " + (node.year === null ? "không có" : node.year) +
      "\nBậc: " + node.degree + " (out " + node.out_degree + " / in " + node.in_degree + ")" +
      (node.split_role ? "\n" + node.split_role : ""));
    circle.appendChild(tip);
    circle.addEventListener("click", () => showDetail(node));
    nodeLayer.appendChild(circle);
    if (node.split_role) {
      nodeLayer.appendChild(el("circle", {
        cx: pos.x.toFixed(1), cy: pos.y.toFixed(1), r: (radius + 4).toFixed(1),
        class: "node-ring",
      }));
    }
    if (showLabels) {
      const text = el("text", {
        x: (pos.x + radius + 4).toFixed(1), y: (pos.y + 4).toFixed(1),
        class: "node-label",
      }, truncate(label, 30) || node.doc_id);
      labelLayer.appendChild(text);
    }
  }
  svg.appendChild(nodeLayer);
  svg.appendChild(labelLayer);
}

function renderNodeList(data) {
  const panel = document.getElementById("node-list");
  panel.innerHTML = "";
  const h = document.createElement("h2");
  h.textContent = "Danh sách node (" + data.nodes.length + ")";
  panel.appendChild(h);
  const table = document.createElement("table");
  const head = document.createElement("tr");
  ["Node", "Bậc (out/in)", "Hop", "Query"].forEach((t) => {
    const th = document.createElement("th");
    th.textContent = t;
    head.appendChild(th);
  });
  table.appendChild(head);
  for (const node of data.nodes) {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td");
    const a = document.createElement("a");
    a.textContent = truncate(node.title || node.doc_id, 34) || node.doc_id;
    a.className = "clickable";
    a.addEventListener("click", () => showDetail(node));
    td1.appendChild(a);
    const td2 = document.createElement("td");
    td2.textContent = node.degree + " (" + node.out_degree + "/" + node.in_degree + ")";
    const td3 = document.createElement("td");
    td3.textContent = String(node.depth);
    const td4 = document.createElement("td");
    if (node.split_role) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = node.split_role;
      td4.appendChild(badge);
    } else {
      td4.textContent = "—";
    }
    tr.append(td1, td2, td3, td4);
    table.appendChild(tr);
  }
  panel.appendChild(table);
}

function renderProvenance(data) {
  const panel = document.getElementById("provenance");
  panel.innerHTML = "";
  const h = document.createElement("h2");
  h.textContent = "Nguồn dữ liệu lần vẽ này";
  panel.appendChild(h);
  const p = document.createElement("p");
  p.textContent = "Chế độ: " + data.mode + " — " + data.mode_label;
  panel.appendChild(p);
  const counts = document.createElement("p");
  counts.textContent = "Số liệu: " + data.counts.neighbor_nodes_total + " node láng giềng, trả về "
    + data.counts.neighbor_nodes_returned + " · " + data.counts.edges_returned + " cạnh trong ảnh hiển thị"
    + " (cites " + data.counts.cites_edges_returned + ", cited-by " + data.counts.cited_by_edges_returned + ")"
    + " · hop=" + data.hop + ", cap=" + data.cap;
  panel.appendChild(counts);
  const ul = document.createElement("ul");
  for (const input of data.inputs) {
    const li = document.createElement("li");
    const code = document.createElement("code");
    code.textContent = input;
    li.appendChild(code);
    ul.appendChild(li);
  }
  panel.appendChild(ul);
  const hash = document.createElement("p");
  hash.textContent = "Hash cạnh (đã xác minh theo manifest): ";
  const code = document.createElement("code");
  code.textContent = data.snapshot.edge_sha256.slice(0, 16) + "…";
  hash.appendChild(code);
  panel.appendChild(hash);
}

async function showDetail(node) {
  const detail = document.getElementById("detail");
  detail.innerHTML = "";
  const docId = node.doc_id;
  const h = document.createElement("h3");
  h.textContent = node.title || "(không có tiêu đề)";
  const idLine = document.createElement("p");
  idLine.className = "meta";
  idLine.textContent = docId;
  detail.append(h, idLine);
  try {
    const paper = await api("/paper/" + encodeURIComponent(docId));
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = "Năm: " + (paper.year === null || paper.year === undefined ? "không có" : paper.year)
      + " · DOI: " + (paper.doi || "không có");
    const abs = document.createElement("p");
    abs.className = "abstract";
    abs.textContent = paper.abstract || "(không có tóm tắt)";
    detail.append(meta, abs);
  } catch (e) {
    const err = document.createElement("p");
    err.className = "meta";
    err.textContent = "Không tải được chi tiết: " + e.message;
    detail.appendChild(err);
  }
  if (node.split_role) {
    const badge = document.createElement("p");
    badge.className = "meta";
    badge.textContent = "Node thuộc bộ query " + node.split_role + " (split_queries.json, chế độ evaluated).";
    detail.appendChild(badge);
  }
  const link = document.createElement("p");
  const a = document.createElement("a");
  a.href = "/paper/" + encodeURIComponent(docId);
  a.textContent = "Xem JSON chi tiết (/paper)";
  link.appendChild(a);
  detail.appendChild(link);
  const btn = document.createElement("button");
  btn.textContent = "Vẽ neighborhood quanh bài này";
  btn.addEventListener("click", () => {
    document.getElementById("doc_id").value = docId;
    drawGraph();
  });
  detail.appendChild(btn);
  const rel = document.createElement("h4");
  rel.textContent = "Tài liệu liên quan (recommend, dữ liệu thật)";
  detail.appendChild(rel);
  try {
    const r = await api("/recommend/" + encodeURIComponent(docId) + "?top_k=5");
    const ul = document.createElement("ul");
    for (const row of r.results) {
      const li = document.createElement("li");
      const ra = document.createElement("a");
      ra.className = "clickable";
      ra.textContent = row.title || "(không có tiêu đề)";
      ra.addEventListener("click", () => showDetail({ doc_id: row.doc_id, title: row.title }));
      li.appendChild(ra);
      ul.appendChild(li);
    }
    detail.appendChild(ul);
  } catch (e) {
    const err = document.createElement("p");
    err.className = "meta";
    err.textContent = "Không tải được gợi ý: " + e.message;
    detail.appendChild(err);
  }
}

async function drawGraph() {
  const docId = document.getElementById("doc_id").value.trim();
  const mode = document.getElementById("mode").value;
  const hop = document.getElementById("hop").value;
  const cap = document.getElementById("cap").value;
  document.getElementById("graph-svg").innerHTML = "";
  document.getElementById("detail").innerHTML = "";
  if (!docId) {
    setStatus("Nhập doc_id (vd: openalex:W1678356000).", "error");
    return;
  }
  setStatus("Đang tải neighborhood…");
  try {
    const data = await api("/graph/" + encodeURIComponent(docId)
      + "?mode=" + encodeURIComponent(mode) + "&hop=" + encodeURIComponent(hop)
      + "&cap=" + encodeURIComponent(cap));
    renderGraph(data);
    renderNodeList(data);
    renderProvenance(data);
    let note = "Đã vẽ " + data.counts.neighbor_nodes_returned + " node láng giềng / "
      + data.counts.edges_returned + " cạnh (mode " + data.mode + ", hop " + data.hop + ", cap " + data.cap + ").";
    if (data.message) note += " " + data.message;
    setStatus(note, data.message ? "warning" : "");
  } catch (e) {
    setStatus((e.status === 404 ? "Không tìm thấy node (404): " : "Lỗi: ") + e.message, "error");
  }
}

document.getElementById("graph-form").addEventListener("submit", (e) => {
  e.preventDefault();
  drawGraph();
});

const initial = new URLSearchParams(location.search).get("doc_id");
if (initial) {
  document.getElementById("doc_id").value = initial;
  drawGraph();
}
