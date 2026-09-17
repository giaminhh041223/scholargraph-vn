"""SG-037 citation graph UI/API tests — real frozen data, no mocks.

Covers the SG-037 acceptance surface:
- /graph/{doc_id} returns exactly the edges recorded in adjacency_masked.tsv
  (evaluated) / adjacency_premask.tsv (snapshot), cross-checked row-by-row
  against the TSV files inside these tests ("so tay với file TSV").
- Explicit edge direction (cites vs cited-by), neighborhood cap with
  top-by-degree fallback, hop expansion.
- Evaluated mode NEVER reads the trusted held-out artifacts: static source
  inspection + a live sys.addaudithook probe over the full load+query path.
- 404 for unknown nodes, missing metadata rendered null (never fabricated),
  template/static offline rendering, adversarial tampered/missing artifacts
  (fail loud) including a subprocess exit-code probe (ADR-013/014).
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "src"

CENTER = "openalex:W1004023663"      # out 5 / in 0 on G_mask; real title+year
HUB = "openalex:W1678356000"         # cited-by hub: in-degree 5341 on G_mask
DEV_QUERY = "openalex:W4399631598"   # dev query source: 28 observed of 36 refs
ISOLATED = "openalex:W1003264260"    # zero internal edges post-mask
NO_TITLE = "openalex:W126924136"     # work without title in the snapshot
UNKNOWN = "openalex:W999999999999"

MASKED_TSV = PROJECT_ROOT / "data" / "processed" / "graph" / "adjacency_masked.tsv"
PREMASK_TSV = PROJECT_ROOT / "data" / "processed" / "graph" / "adjacency_premask.tsv"
MANIFEST = PROJECT_ROOT / "data" / "manifests" / "graph_core.json"


def load_edges(path: Path) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                u, v = line.rstrip("\n").split("\t")
                edges.add((u, v))
    return edges


def degrees(edges: set[tuple[str, str]]) -> dict[str, int]:
    deg: dict[str, int] = defaultdict(int)
    for u, v in edges:
        deg[u] += 1
        deg[v] += 1
    return dict(deg)


def bfs(edges: set[tuple[str, str]], start: str, hop: int) -> set[str]:
    """Neighborhood over both directions, same semantics as the service."""
    out: dict[str, set[str]] = defaultdict(set)
    inn: dict[str, set[str]] = defaultdict(set)
    for u, v in edges:
        out[u].add(v)
        inn[v].add(u)
    seen = {start}
    frontier = [start]
    for _ in range(hop):
        nxt: list[str] = []
        for u in frontier:
            for v in out[u] | inn[u]:
                if v not in seen:
                    seen.add(v)
                    nxt.append(v)
        frontier = nxt
        if not frontier:
            break
    return seen


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import scholargraph.api.app as app_module

    importlib.reload(app_module)
    with TestClient(app_module.app) as tc:  # lazy services, real frozen data
        yield tc


# ---------------------------------------------------------------- template/UI

def test_graph_page_renders(client):
    r = client.get("/graph")
    assert r.status_code == 200
    body = r.text
    assert "/graph-static/graph.js" in body and "/graph-static/graph.css" in body
    # snapshot provenance from the real manifest
    assert "openalex-core-03b28664fca6" in body
    assert "2026-09-16T20:44:01" in body
    assert "26186" in body and "26516" in body and "18251" in body
    # both modes offered, evaluated default
    assert 'value="evaluated" selected' in body and 'value="snapshot"' in body
    # direction explanation present on the page (cited-by/cites, per task card)
    assert "cites" in body and "cited-by" in body
    assert "referenced_works" in body
    assert "held-out" in body


def test_graph_static_assets_offline(client):
    r = client.get("/graph-static/graph.js")
    assert r.status_code == 200 and "fetch(" in r.text
    graph_dir = PROJECT_ROOT / "ui" / "graph"
    for path in graph_dir.iterdir():
        if path.suffix in {".js", ".css"}:
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "http://" in line or "https://" in line:
                    # the only allowed http:// literal is the W3C SVG namespace
                    # identifier (not a network resource, required by DOM API)
                    assert "www.w3.org/2000/svg" in line, path.name


def test_legend_payload_explains_directions(client):
    r = client.get(f"/graph/{CENTER}")
    assert r.status_code == 200
    legend = r.json()["legend"]
    assert "TRÍCH DẪN" in legend["arrow_rule"] and "referenced_works" in legend["arrow_rule"]
    assert "cites" in legend and "cited_by" in legend
    assert "G_mask" in legend["modes"]["evaluated"]
    assert "full snapshot" in legend["modes"]["snapshot"]
    assert "không có" in legend["missing_metadata"]


# ------------------------------------------------------------- evaluated mode

def test_evaluated_neighborhood_matches_masked_tsv(client):
    masked = load_edges(MASKED_TSV)
    r = client.get(f"/graph/{CENTER}")  # defaults: evaluated, hop=1, cap=30
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "evaluated"
    shown = {n["doc_id"] for n in body["nodes"]}
    assert body["doc_id"] == CENTER and CENTER in shown
    neighbors = shown - {CENTER}
    expected_neighbors = ({u for u, v in masked if v == CENTER}
                          | {v for u, v in masked if u == CENTER})
    assert neighbors == expected_neighbors
    assert body["counts"]["neighbor_nodes_total"] == len(expected_neighbors)
    returned_edges = {(e["src"], e["dst"]) for e in body["edges"]}
    expected_edges = {(u, v) for (u, v) in masked if u in shown and v in shown}
    assert returned_edges == expected_edges
    assert body["counts"]["edges_returned"] == len(expected_edges)
    assert body["truncated"] is False


def test_direction_labels_and_center_metadata(client):
    r = client.get(f"/graph/{CENTER}")
    body = r.json()
    for e in body["edges"]:
        if e["src"] == CENTER:
            assert e["relation_to_center"] == "cites"
        elif e["dst"] == CENTER:
            assert e["relation_to_center"] == "cited_by"
        else:
            assert e["relation_to_center"] is None
    assert body["counts"]["cites_edges_returned"] == 5      # 5 references cited
    assert body["counts"]["cited_by_edges_returned"] == 0   # nobody cites it here
    assert body["counts"]["center_out_degree"] == 5
    assert body["counts"]["center_in_degree"] == 0
    center = body["nodes"][0]
    assert center["doc_id"] == CENTER and center["depth"] == 0
    assert center["degree"] == 5
    assert center["title"] == ("An Empirical Study on Web Search Behavior through the "
                               "Investigation of a User-Clustered Query Session")
    assert center["year"] == 2011


def test_hop2_truncation_matches_test_side_bfs(client):
    masked = load_edges(MASKED_TSV)
    r = client.get(f"/graph/{CENTER}", params={"hop": 2, "cap": 100})
    assert r.status_code == 200
    body = r.json()
    visited = bfs(masked, CENTER, 2)
    assert body["counts"]["neighbor_nodes_total"] == len(visited) - 1
    assert body["truncated"] is True
    assert "vượt cap" in body["message"]
    assert body["counts"]["neighbor_nodes_returned"] == 100
    deg = degrees(masked)
    expected_top = sorted(visited - {CENTER}, key=lambda n: (-deg[n], n))[:100]
    returned = [n["doc_id"] for n in body["nodes"] if n["doc_id"] != CENTER]
    assert returned == expected_top
    shown = {CENTER, *returned}
    expected_edges = {(u, v) for (u, v) in masked if u in shown and v in shown}
    assert {(e["src"], e["dst"]) for e in body["edges"]} == expected_edges
    # every returned node carries its real BFS depth
    depth = {CENTER: 0}
    frontier = [CENTER]
    for d in (1, 2):
        nxt = []
        for u in frontier:
            for e in masked:
                if e[0] == u and e[1] not in depth:
                    depth[e[1]] = d; nxt.append(e[1])
                if e[1] == u and e[0] not in depth:
                    depth[e[0]] = d; nxt.append(e[0])
        frontier = nxt
    for n in body["nodes"]:
        assert n["depth"] == depth[n["doc_id"]]


def test_cap_truncates_top_by_degree(client):
    masked = load_edges(MASKED_TSV)
    r = client.get(f"/graph/{HUB}", params={"cap": 10})
    assert r.status_code == 200
    body = r.json()
    neighbors = {u for u, v in masked if v == HUB} | {v for u, v in masked if u == HUB}
    assert body["counts"]["neighbor_nodes_total"] == len(neighbors) == 5341
    assert body["truncated"] is True and "cap=10" in body["message"]
    deg = degrees(masked)
    expected_top = sorted(neighbors, key=lambda n: (-deg[n], n))[:10]
    returned = [n["doc_id"] for n in body["nodes"] if n["doc_id"] != HUB]
    assert returned == expected_top
    shown = {HUB, *returned}
    expected_edges = {(u, v) for (u, v) in masked if u in shown and v in shown}
    assert {(e["src"], e["dst"]) for e in body["edges"]} == expected_edges
    assert body["counts"]["cited_by_edges_returned"] == sum(
        1 for (u, v) in expected_edges if v == HUB)


def test_parameter_validation_returns_400(client):
    for params in ({"mode": "full"}, {"hop": 0}, {"hop": 4}, {"cap": 0}, {"cap": 101}):
        r = client.get(f"/graph/{CENTER}", params=params)
        assert r.status_code == 400, params
        assert "detail" in r.json()


def test_unknown_node_returns_404(client):
    r = client.get(f"/graph/{UNKNOWN}")
    assert r.status_code == 404
    assert r.json()["detail"].startswith("Unknown document")


def test_isolated_node_zero_edges(client):
    r = client.get(f"/graph/{ISOLATED}")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["neighbor_nodes_total"] == 0
    assert body["edges"] == []
    assert "không có cạnh nội bộ" in body["message"]
    assert body["nodes"][0]["title"] == "Preface"   # real metadata from works.jsonl
    assert body["nodes"][0]["year"] == 2008


def test_missing_metadata_is_null_not_fabricated(client):
    r = client.get(f"/graph/{NO_TITLE}")
    assert r.status_code == 200
    center = r.json()["nodes"][0]
    assert center["doc_id"] == NO_TITLE
    assert center["title"] is None       # rendered "không có" downstream
    assert center["year"] == 2005


# ----------------------------------------------- evaluated vs snapshot modes

def test_evaluated_vs_snapshot_on_dev_query_source(client):
    masked = load_edges(MASKED_TSV)
    premask = load_edges(PREMASK_TSV)
    ev = client.get(f"/graph/{DEV_QUERY}", params={"cap": 100}).json()
    sn = client.get(f"/graph/{DEV_QUERY}",
                    params={"mode": "snapshot", "cap": 100}).json()
    assert ev["counts"]["center_out_degree"] == 28 == sum(
        1 for (u, _v) in masked if u == DEV_QUERY)
    assert sn["counts"]["center_out_degree"] == 36 == sum(
        1 for (u, _v) in premask if u == DEV_QUERY)
    ev_out = {e["dst"] for e in ev["edges"] if e["relation_to_center"] == "cites"}
    sn_out = {e["dst"] for e in sn["edges"] if e["relation_to_center"] == "cites"}
    assert ev_out == {v for (u, v) in masked if u == DEV_QUERY}
    assert sn_out == {v for (u, v) in premask if u == DEV_QUERY}
    assert ev_out < sn_out                       # 8 held-out refs only in snapshot
    assert "full snapshot" in sn["mode_label"]
    assert "KHÔNG chứa cạnh held-out" in ev["mode_label"]
    assert ev["split"]["center_split_role"] == "dev_query"
    assert sn["split"]["center_split_role"] is None and sn["split"]["shown_in_mode"] is False


def test_hashes_and_inputs_in_response(client):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ev = client.get(f"/graph/{CENTER}").json()
    assert ev["snapshot"]["edge_sha256"] == \
        manifest["hashes"]["adjacency_masked"]["sha256"]
    assert ev["snapshot"]["edge_sha256"] == manifest["graph_hash"]
    assert ev["snapshot"]["edge_count_total"] == 26186
    assert ev["snapshot"]["retrieved_completed_at"] == "2026-09-16T20:44:01.099407+00:00"
    assert ev["manifest_counts"]["nodes"] == 18251
    assert ev["manifest_counts"]["heldout_edges_total"] == 330
    assert ev["manifest_counts"]["mask_edges_total"] == 660
    assert ev["inputs"] == [
        "data/manifests/graph_core.json",
        "data/processed/graph/adjacency_masked.tsv",
        "data/processed/openalex/works.jsonl",
        "data/processed/graph/split_queries.json",
    ]
    sn = client.get(f"/graph/{CENTER}", params={"mode": "snapshot"}).json()
    assert sn["snapshot"]["edge_sha256"] == \
        manifest["hashes"]["adjacency_premask"]["sha256"]
    assert sn["snapshot"]["edge_count_total"] == 26516
    assert "split_queries.json" not in sn["inputs"]


# ------------------------------------------------------------- leakage probe

def test_evaluated_mode_never_reads_holdout_artifacts(client):
    """Static source inspection + live audit-hook probe (ADR-013 leakage check)."""
    src = (SRC / "scholargraph" / "api" / "graph_service.py").read_text(encoding="utf-8")
    # The trusted artifact FILES must never be referenced by the module. (The
    # manifest *count fields* "heldout_edges_total"/"mask_edges_total" are pure
    # numbers from graph_core.json, not the trusted edge lists.)
    assert "holdout_edges.tsv" not in src
    assert "mask_edges.tsv" not in src
    tsv_literals = set(re.findall(r'"([^"]*\.tsv)"', src))
    assert tsv_literals <= {"adjacency_masked.tsv", "adjacency_premask.tsv"}, tsv_literals
    assert "adjacency_masked" in src  # positive control: the probe below must see it

    from scholargraph.api.graph_service import GraphService

    opened: list[str] = []
    state = {"capture": False}

    def hook(event, args):
        if state["capture"] and event == "open":
            opened.append(str(args[0]).lower())

    sys.addaudithook(hook)  # stays installed; gated by the capture flag
    try:
        state["capture"] = True
        svc = GraphService(PROJECT_ROOT)          # full cold load path
        svc.neighborhood(DEV_QUERY)               # evaluated (default)
        svc.neighborhood(DEV_QUERY, mode="snapshot")
        r = client.get(f"/graph/{DEV_QUERY}")     # evaluated via the API layer
        assert r.status_code == 200
    finally:
        state["capture"] = False
    joined = "|".join(opened)
    assert "holdout" not in joined, f"held-out artifact opened: {opened}"
    assert "mask_edges" not in joined, f"mask artifact opened: {opened}"
    assert "adjacency_masked.tsv" in joined
    assert "split_queries.json" in joined


# ------------------------------------------------- adversarial (ADR-013/014)

def _make_tmp_root(tmp_root: Path) -> Path:
    root = tmp_root / "proj"
    (root / "data" / "manifests").mkdir(parents=True)
    (root / "data" / "processed" / "graph").mkdir(parents=True)
    (root / "data" / "processed" / "openalex").mkdir(parents=True)
    shutil.copy(MASKED_TSV, root / "data" / "processed" / "graph" / "adjacency_masked.tsv")
    shutil.copy(PREMASK_TSV, root / "data" / "processed" / "graph" / "adjacency_premask.tsv")
    shutil.copy(PROJECT_ROOT / "data" / "processed" / "graph" / "split_queries.json",
                root / "data" / "processed" / "graph" / "split_queries.json")
    shutil.copy(MANIFEST, root / "data" / "manifests" / "graph_core.json")
    return root


def _patched_manifest(root: Path, mutate) -> Path:
    path = root / "data" / "manifests" / "graph_core.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_adversarial_missing_and_tampered_artifacts_fail_loud(tmp_path):
    from scholargraph.api.graph_service import GraphService, GraphServiceError

    root = _make_tmp_root(tmp_path)

    # 1. missing required adjacency file
    (root / "data" / "processed" / "graph" / "adjacency_masked.tsv").unlink()
    with pytest.raises(GraphServiceError, match="Missing required graph artifact"):
        GraphService(root)

    # 2. tampered adjacency content -> manifest hash mismatch
    root2 = _make_tmp_root(tmp_path / "t2")
    with (root2 / "data" / "processed" / "graph" / "adjacency_masked.tsv")\
            .open("a", encoding="utf-8") as fh:
        fh.write("openalex:W999999990001\topenalex:W999999990002\n")
    with pytest.raises(GraphServiceError, match="Hash mismatch.*adjacency_masked"):
        GraphService(root2)

    # 3. manifest edge_count disagreeing with the (hash-valid) file
    root3 = _make_tmp_root(tmp_path / "t3")
    _patched_manifest(
        root3, lambda m: m["hashes"]["adjacency_masked"].__setitem__("edge_count", 26187))
    with pytest.raises(GraphServiceError, match="manifest expects"):
        GraphService(root3)

    # 4. manifest not COMPLETED
    root4 = _make_tmp_root(tmp_path / "t4")
    _patched_manifest(root4, lambda m: m.__setitem__("status", "PARTIAL"))
    with pytest.raises(GraphServiceError, match="COMPLETED"):
        GraphService(root4)

    # 5. unparseable manifest JSON
    root5 = _make_tmp_root(tmp_path / "t5")
    (root5 / "data" / "manifests" / "graph_core.json")\
        .write_text("{not json", encoding="utf-8")
    with pytest.raises(GraphServiceError, match="Unparseable"):
        GraphService(root5)


def test_adversarial_malformed_adjacency_rows(tmp_path):
    from scholargraph.api.graph_service import GraphService, GraphServiceError

    # _load_adjacency is a pure function of the file path; the service instance
    # is not touched, so a bare object keeps this test cheap (no 150 MB parse).
    svc = object.__new__(GraphService)

    def write_and_load(content: str) -> None:
        path = tmp_path / "adj.tsv"
        path.write_text(content, encoding="utf-8")
        GraphService._load_adjacency(svc, path)

    with pytest.raises(GraphServiceError, match="2 tab-separated"):
        write_and_load("openalex:W1\topenalex:W2\topenalex:W3\n")
    with pytest.raises(GraphServiceError, match="duplicate edge"):
        write_and_load("openalex:W1\topenalex:W2\nopenalex:W1\topenalex:W2\n")
    with pytest.raises(GraphServiceError, match="self-loop"):
        write_and_load("openalex:W1\topenalex:W1\n")
    with pytest.raises(GraphServiceError, match="blank line"):
        write_and_load("openalex:W1\topenalex:W2\n\n")
    with pytest.raises(GraphServiceError, match="truncated line"):
        write_and_load("openalex:W1\topenalex:W2")
    with pytest.raises(GraphServiceError, match="Non-canonical"):
        write_and_load("W1\topenalex:W2\n")
    # happy-path sanity for the same loader
    path = tmp_path / "ok.tsv"
    path.write_text("openalex:W1\topenalex:W2\nopenalex:W2\topenalex:W3\n", encoding="utf-8")
    assert GraphService._load_adjacency(svc, path) == [
        ("openalex:W1", "openalex:W2"), ("openalex:W2", "openalex:W3")]


def test_adversarial_subprocess_missing_artifact_exit_code(tmp_path):
    """CLI/subprocess contract: fatal resource error -> exit code 1 (ADR-013)."""
    root = _make_tmp_root(tmp_path / "sub")
    (root / "data" / "processed" / "graph" / "adjacency_masked.tsv").unlink()
    code = (
        "import sys; sys.path.insert(0, r'{src}'); "
        "from scholargraph.api.graph_service import GraphService; "
        "GraphService(r'{root}')"
    ).format(src=str(SRC), root=str(root))
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 1
    assert "Missing required graph artifact" in proc.stderr


# ------------------------------------------------------------- regression

def test_route_table_stays_additive():
    """SG-037 must not break the DONE SG-035/SG-036 routes; only add new ones."""
    import scholargraph.api.app as app_module

    paths = {getattr(route, "path", None) for route in app_module.app.routes}
    assert {"/health", "/", "/search", "/paper/{doc_id}",
            "/recommend/{doc_id}"} <= paths
    assert "/graph" in paths and "/graph/{doc_id}" in paths
    assert "/graph-static" in paths and "/static" in paths


def test_search_route_validation_intact(client):
    """Live regression without loading the search model: missing q -> 422."""
    r = client.get("/search")
    assert r.status_code == 422
