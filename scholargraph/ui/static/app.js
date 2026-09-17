/* ScholarGraph VN demo UI — vanilla JS, offline, no CDN. */
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || ("HTTP " + r.status));
  }
  return r.json();
}

function card(row) {
  const div = document.createElement("article");
  div.className = "card";
  const title = row.title || "(không có tiêu đề)";
  div.innerHTML = "";
  const h = document.createElement("h3");
  const a = document.createElement("a");
  a.href = "#";
  a.textContent = title;
  a.dataset.docId = row.doc_id;
  a.addEventListener("click", (e) => { e.preventDefault(); showDetail(row.doc_id); });
  h.appendChild(a);
  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = row.doc_id + " · score " + Number(row.score).toFixed(4) + " · " + row.method;
  div.appendChild(h);
  div.appendChild(meta);
  if (row.snippet) {
    const sn = document.createElement("p");
    sn.className = "snippet";
    sn.textContent = row.snippet;
    div.appendChild(sn);
  }
  return div;
}

async function showDetail(docId) {
  const status = document.getElementById("status");
  try {
    const paper = await api("/paper/" + encodeURIComponent(docId));
    const body = document.getElementById("detail-body");
    body.innerHTML = "";
    const h = document.createElement("h3");
    h.textContent = paper.title || "(không có tiêu đề)";
    const abs = document.createElement("p");
    abs.textContent = paper.abstract || "(không có tóm tắt)";
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = "Năm: " + (paper.year === null || paper.year === undefined ? "không có" : paper.year)
      + " · DOI: " + (paper.doi || "không có");
    body.append(h, abs, meta);
    const rel = await api("/recommend/" + encodeURIComponent(docId) + "?top_k=5");
    const relDiv = document.getElementById("related");
    relDiv.innerHTML = "";
    rel.results.forEach((row) => relDiv.appendChild(card(row)));
    document.getElementById("detail").hidden = false;
  } catch (e) {
    status.textContent = "Lỗi: " + e.message;
  }
}

document.getElementById("search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("status");
  const results = document.getElementById("results");
  results.innerHTML = "";
  status.textContent = "Đang tìm kiếm…";
  const q = document.getElementById("q").value;
  const method = document.getElementById("method").value;
  const top_k = document.getElementById("top_k").value;
  try {
    const data = await api("/search?q=" + encodeURIComponent(q) + "&method=" + method + "&top_k=" + top_k);
    status.textContent = "Tìm thấy " + data.results.length + " kết quả (" + data.method + ").";
    if (data.results.length === 0) {
      status.textContent += " Không có kết quả phù hợp.";
    }
    data.results.forEach((row) => results.appendChild(card(row)));
  } catch (err) {
    status.textContent = "Lỗi: " + err.message;
  }
});
