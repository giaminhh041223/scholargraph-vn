"""Citation graph neighborhood service — task SG-037.

Two explicit display modes over the real frozen OpenAlex core snapshot
(manifest: data/manifests/graph_core.json, task SG-016):

- ``evaluated`` (default, demo gắn với truy hồi): ONLY the masked adjacency
  ``data/processed/graph/adjacency_masked.tsv`` (26,186 internal directed
  edges, G_mask) plus ``split_queries.json`` for dev/test query marking.
  Trusted evaluator/auditor artifacts (the held-out edge list and the mask
  edge list) are NEVER read by this module — enforced by test_graph_ui.py
  via source inspection + a live leakage probe on a real dev query node.
- ``snapshot`` (structure reference only, clearly labeled "full snapshot"):
  the pre-mask adjacency ``data/processed/graph/adjacency_premask.tsv``
  (26,516 internal directed edges). May contain edges that are held out for
  evaluation; therefore it must never be the default mode.

Anti-silent-bypass (ADR-013/014): every required resource (manifest, both
adjacency files, split queries, works metadata index) is hash- or
count-verified at load time; any mismatch/missing file raises GraphServiceError
(mapped to HTTP 500/400/404 by the API layer). ``dict.get`` is used ONLY for
(a) optional metadata fields (title/year are legitimately nullable and are
rendered as "không có" downstream, never fabricated) and (b) adjacency
membership lookups where "no out-edges" is a measured property of the node,
not a missing resource.

Edge direction follows docs/GRAPH_PROTOCOL.md §1.3: a TSV row ``u<TAB>v``
means ``v ∈ referenced_works(u)`` — i.e. u cites v. The API exposes this as
``cites`` (edge leaving the viewed node) vs ``cited-by`` (edge entering it).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

MANIFEST_RELPATH = Path("data") / "manifests" / "graph_core.json"
ADJACENCY_MASKED_RELPATH = Path("data") / "processed" / "graph" / "adjacency_masked.tsv"
ADJACENCY_PREMASK_RELPATH = Path("data") / "processed" / "graph" / "adjacency_premask.tsv"
SPLIT_QUERIES_RELPATH = Path("data") / "processed" / "graph" / "split_queries.json"
WORKS_RELPATH = Path("data") / "processed" / "openalex" / "works.jsonl"

MODE_EDGE_FILES: dict[str, Path] = {
    "evaluated": ADJACENCY_MASKED_RELPATH,
    "snapshot": ADJACENCY_PREMASK_RELPATH,
}
MODE_LABELS: dict[str, str] = {
    "evaluated": "G_mask (evaluated) — chỉ cạnh observed sau masking; KHÔNG chứa cạnh held-out; dùng cho demo gắn với truy hồi",
    "snapshot": "full snapshot (pre-mask) — toàn bộ cạnh thật của snapshot; chỉ để tham khảo cấu trúc, có thể chứa cạnh held-out",
}
CANONICAL_ID_RE = re.compile(r"^openalex:W\d+$")

DEFAULT_CAP = 30
MAX_CAP = 100
MIN_HOP = 1
MAX_HOP = 3
MAX_RETURNED_EDGES = 2000

GRAPH_LEGEND: dict[str, Any] = {
    "arrow_rule": "Mũi tên vẽ theo chiều trích dẫn: u → v nghĩa là u TRÍCH DẪN v (v nằm trong referenced_works của u).",
    "cites": "cites: cạnh đi RA KHỎI node đang xem — node đang xem trích dẫn bài kia (bài kia là tham khảo của nó).",
    "cited_by": "cited-by: cạnh đi VÀO node đang xem — bài kia trích dẫn node đang xem.",
    "node_colors": {
        "center": "node đang xem (xanh dương)",
        "cites": "bài mà node đang xem trích dẫn (hổ phách)",
        "cited_by": "bài trích dẫn node đang xem (xanh lục)",
        "both": "vừa được node xem trích dẫn, vừa trích dẫn node xem (teal)",
        "multi_hop": "bạn gián tiếp qua hop ≥ 2 (xám)",
        "query_ring": "viền nét đứt tím: node thuộc bộ query dev/test (chỉ chế độ evaluated)",
    },
    "modes": MODE_LABELS,
    "missing_metadata": "Metadata thiếu (tiêu đề/năm) hiển thị “không có”, không bịa.",
}


class GraphServiceError(Exception):
    """Fatal graph service error mapped to an HTTP error response."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_openalex_id(raw: str, where: str) -> str:
    cid = raw.strip()
    if cid.startswith("http://") or cid.startswith("https://"):
        cid = "openalex:" + cid.rsplit("/", 1)[-1]
    if not CANONICAL_ID_RE.match(cid):
        raise GraphServiceError(f"Non-canonical OpenAlex ID {raw!r} in {where}")
    return cid


def read_manifest_snapshot(project_root: Path | str) -> dict[str, Any]:
    """Light manifest read for the /graph page context (no adjacency parsing).

    Raises GraphServiceError when the manifest is missing, unparseable or not
    COMPLETED — never silently renders a page without snapshot provenance.
    """
    root = Path(project_root)
    manifest_path = root / MANIFEST_RELPATH
    if not manifest_path.is_file():
        raise GraphServiceError(f"Missing required manifest: {MANIFEST_RELPATH}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GraphServiceError(f"Unparseable graph manifest JSON: {exc}") from exc
    if manifest.get("status") != "COMPLETED":
        raise GraphServiceError(
            f"Graph manifest status is {manifest.get('status')!r}, expected 'COMPLETED'")
    try:
        hashes = manifest["hashes"]
        snap = manifest["provenance"]["snapshot_manifest"]
        counts = manifest["counts"]
        masked = hashes["adjacency_masked"]
        premask = hashes["adjacency_premask"]
        return {
            "snapshot_id": snap["snapshot_id"],
            "retrieved_completed_at": snap["retrieved_completed_at"],
            "nodes": counts["nodes"],
            "hash_masked": masked["sha256"],
            "hash_premask": premask["sha256"],
            "edges_masked": masked["edge_count"],
            "edges_premask": premask["edge_count"],
        }
    except (KeyError, TypeError) as exc:
        raise GraphServiceError(
            f"Graph manifest missing required field: {exc}") from exc


class _ModeGraph:
    """Directed adjacency for one display mode (read-only after build)."""

    def __init__(self, edges: list[tuple[str, str]]) -> None:
        out_adj: dict[str, list[str]] = {}
        in_adj: dict[str, list[str]] = {}
        for u, v in edges:
            out_adj.setdefault(u, []).append(v)
            in_adj.setdefault(v, []).append(u)
        self.out_adj = {u: sorted(vs) for u, vs in out_adj.items()}
        self.in_adj = {v: sorted(us) for v, us in in_adj.items()}
        self.out_degree = {u: len(vs) for u, vs in self.out_adj.items()}
        self.in_degree = {v: len(us) for v, us in self.in_adj.items()}
        self.edge_count = len(edges)
        self.edges = edges  # sorted at the call site


class GraphService:
    """Loaded once at first /graph request; read-only afterwards."""

    def __init__(self, project_root: Path | str) -> None:
        root = Path(project_root)
        self._root = root

        manifest_path = root / MANIFEST_RELPATH
        if not manifest_path.is_file():
            raise GraphServiceError(f"Missing required manifest: {MANIFEST_RELPATH}")
        try:
            self._manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GraphServiceError(f"Unparseable graph manifest JSON: {exc}") from exc
        if self._manifest.get("status") != "COMPLETED":
            raise GraphServiceError(
                f"Graph manifest status is {self._manifest.get('status')!r}, "
                "expected 'COMPLETED'")
        try:
            counts = self._manifest["counts"]
            hashes = self._manifest["hashes"]
            holdout = self._manifest["holdout"]  # top-level key in graph_core.json
            self._manifest_counts = {
                "nodes": counts["nodes"],
                "internal_directed_edges_premask": counts["internal_directed_edges_premask"],
                "internal_directed_edges_postmask": counts["internal_directed_edges_postmask"],
                "heldout_edges_total": holdout["heldout_edges_total"],
                "mask_edges_total": holdout["mask_edges_total"],
            }
            self._masked_hash = hashes["adjacency_masked"]["sha256"]
            self._premask_hash = hashes["adjacency_premask"]["sha256"]
            self._split_hash = hashes["split_queries"]["sha256"]
            self._masked_edge_count = hashes["adjacency_masked"]["edge_count"]
            self._premask_edge_count = hashes["adjacency_premask"]["edge_count"]
            snap = self._manifest["provenance"]["snapshot_manifest"]
            self._snapshot_id = snap["snapshot_id"]
            self._retrieved_at = snap["retrieved_completed_at"]
            works_prov = self._manifest["provenance"]["works_jsonl"]
            self._works_relpath = Path(works_prov["path"])
            self._works_sha256 = works_prov["sha256"]
            self._selected_queries_expected = holdout["selected_queries"]
        except (KeyError, TypeError) as exc:
            raise GraphServiceError(
                f"Graph manifest missing required field: {exc}") from exc

        # Hash-verify every required artifact against the manifest.
        for relpath, expected in (
            (ADJACENCY_MASKED_RELPATH, self._masked_hash),
            (ADJACENCY_PREMASK_RELPATH, self._premask_hash),
            (SPLIT_QUERIES_RELPATH, self._split_hash),
        ):
            path = root / relpath
            if not path.is_file():
                raise GraphServiceError(f"Missing required graph artifact: {relpath}")
            actual = _sha256_file(path)
            if actual != expected:
                raise GraphServiceError(
                    f"Hash mismatch for {relpath}: manifest {expected}, actual {actual}")

        self._graphs: dict[str, _ModeGraph] = {}
        for mode, relpath in MODE_EDGE_FILES.items():
            edges = self._load_adjacency(root / relpath)
            expected_count = (self._masked_edge_count if mode == "evaluated"
                              else self._premask_edge_count)
            if len(edges) != expected_count:
                raise GraphServiceError(
                    f"{relpath} has {len(edges)} edges, manifest expects {expected_count}")
            self._graphs[mode] = _ModeGraph(edges)

        self._dev_queries, self._test_queries = self._load_split_queries(root)
        self._nodes = self._load_nodes(root)
        self._check_referential_integrity()

    # ------------------------------------------------------------------ load

    def _check_referential_integrity(self) -> None:
        """Every adjacency endpoint must exist in the works snapshot (fail loud)."""
        for mode, graph in self._graphs.items():
            endpoints = (set(graph.out_adj) | set(graph.in_adj)) - set(self._nodes)
            if endpoints:
                raise GraphServiceError(
                    f"mode {mode}: adjacency references {len(endpoints)} node(s) missing "
                    f"from the works snapshot, e.g. {sorted(endpoints)[:3]}")

    def _load_adjacency(self, path: Path) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.endswith("\n"):
                    raise GraphServiceError(f"{path.name}:{lineno}: truncated line")
                line = line.rstrip("\n")
                if not line:
                    raise GraphServiceError(f"{path.name}:{lineno}: blank line")
                parts = line.split("\t")
                if len(parts) != 2:
                    raise GraphServiceError(
                        f"{path.name}:{lineno}: expected 2 tab-separated columns, "
                        f"got {len(parts)}")
                u = _canonical_openalex_id(parts[0], f"{path.name}:{lineno}")
                v = _canonical_openalex_id(parts[1], f"{path.name}:{lineno}")
                if u == v:
                    raise GraphServiceError(f"{path.name}:{lineno}: self-loop {u}")
                if (u, v) in seen:
                    raise GraphServiceError(f"{path.name}:{lineno}: duplicate edge {(u, v)}")
                seen.add((u, v))
                edges.append((u, v))
        edges.sort()
        return edges

    def _load_split_queries(self, root: Path) -> tuple[frozenset[str], frozenset[str]]:
        path = root / SPLIT_QUERIES_RELPATH
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GraphServiceError(f"Unparseable split queries JSON: {exc}") from exc
        try:
            dev = data["cohorts"]["dev"]["selected"]
            test = data["cohorts"]["test"]["selected"]
        except (KeyError, TypeError) as exc:
            raise GraphServiceError(
                f"Split queries missing required field: {exc}") from exc
        if not isinstance(dev, list) or not isinstance(test, list):
            raise GraphServiceError("Split query 'selected' fields must be lists")
        dev_ids = frozenset(_canonical_openalex_id(x, "split_queries.dev") for x in dev)
        test_ids = frozenset(_canonical_openalex_id(x, "split_queries.test") for x in test)
        if dev_ids & test_ids:
            raise GraphServiceError(
                f"dev/test query overlap is a fatal split error: {sorted(dev_ids & test_ids)}")
        expected = self._selected_queries_expected
        if len(dev_ids) != expected["dev"] or len(test_ids) != expected["test"]:
            raise GraphServiceError(
                f"Split query counts {len(dev_ids)}/{len(test_ids)} dev/test "
                f"disagree with manifest {expected['dev']}/{expected['test']}")
        return dev_ids, test_ids

    def _load_nodes(self, root: Path) -> dict[str, dict[str, Any]]:
        path = root / self._works_relpath
        if not path.is_file():
            raise GraphServiceError(f"Missing required works snapshot: {self._works_relpath}")
        actual = _sha256_file(path)
        if actual != self._works_sha256:
            raise GraphServiceError(
                f"works.jsonl hash mismatch: manifest {self._works_sha256}, actual {actual}")
        nodes: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    raise GraphServiceError(f"works.jsonl:{lineno}: blank line")
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GraphServiceError(f"works.jsonl:{lineno}: bad JSON: {exc}") from exc
                try:
                    cid = _canonical_openalex_id(row["id"], f"works.jsonl:{lineno}")
                except KeyError as exc:
                    raise GraphServiceError(
                        f"works.jsonl:{lineno}: missing required field {exc}") from exc
                if cid in nodes:
                    raise GraphServiceError(f"works.jsonl:{lineno}: duplicate ID {cid}")
                title = row.get("title")  # optional metadata; None → "không có"
                year = row.get("publication_year")  # optional metadata; None → "không có"
                if title is not None and not isinstance(title, str):
                    raise GraphServiceError(f"works.jsonl:{lineno}: title must be string or null")
                if year is not None and not isinstance(year, int):
                    raise GraphServiceError(
                        f"works.jsonl:{lineno}: publication_year must be integer or null")
                nodes[cid] = {"title": title, "year": year}
        expected_nodes = self._manifest_counts["nodes"]
        if len(nodes) != expected_nodes:
            raise GraphServiceError(
                f"works.jsonl has {len(nodes)} works, manifest expects {expected_nodes}")
        return nodes

    # ------------------------------------------------------------ neighborhood

    def _split_role(self, doc_id: str, mode: str) -> str | None:
        if mode != "evaluated":
            return None
        if doc_id in self._dev_queries:
            return "dev_query"
        if doc_id in self._test_queries:
            return "test_query"
        return None

    def _node_payload(self, doc_id: str, depth: int, graph: _ModeGraph,
                      mode: str) -> dict[str, Any]:
        meta = self._nodes[doc_id]
        return {
            "doc_id": doc_id,
            "title": meta["title"],
            "year": meta["year"],
            "depth": depth,
            "in_degree": graph.in_degree.get(doc_id, 0),
            "out_degree": graph.out_degree.get(doc_id, 0),
            "degree": graph.in_degree.get(doc_id, 0) + graph.out_degree.get(doc_id, 0),
            "split_role": self._split_role(doc_id, mode),
        }

    def neighborhood(self, doc_id: str, mode: str = "evaluated", hop: int = 1,
                     cap: int = DEFAULT_CAP) -> dict[str, Any]:
        if mode not in MODE_EDGE_FILES:
            raise GraphServiceError(
                f"Unknown mode: {mode!r} (expected 'evaluated' or 'snapshot')")
        if isinstance(hop, bool) or not isinstance(hop, int) or not MIN_HOP <= hop <= MAX_HOP:
            raise GraphServiceError(
                f"hop must be an integer in [{MIN_HOP},{MAX_HOP}], got {hop!r}")
        if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= MAX_CAP:
            raise GraphServiceError(
                f"cap must be an integer in [1,{MAX_CAP}], got {cap!r}")
        if doc_id not in self._nodes:
            raise GraphServiceError(f"Unknown document: {doc_id}")

        graph = self._graphs[mode]
        depth: dict[str, int] = {doc_id: 0}
        frontier = [doc_id]
        for d in range(hop):
            nxt: list[str] = []
            for u in frontier:
                # Membership lookups: a node with no incident edges on one side
                # is a measured graph property, not a missing resource.
                for v in graph.out_adj.get(u, ()):
                    if v not in depth:
                        depth[v] = d + 1
                        nxt.append(v)
                for v in graph.in_adj.get(u, ()):
                    if v not in depth:
                        depth[v] = d + 1
                        nxt.append(v)
            frontier = nxt
            if not frontier:
                break

        neighbors_all = sorted(n for n in depth if n != doc_id)
        total_neighbors = len(neighbors_all)
        truncated = False
        message: str | None = None
        if total_neighbors > cap:
            selected = sorted(neighbors_all,
                              key=lambda n: (-(graph.in_degree.get(n, 0)
                                               + graph.out_degree.get(n, 0)), n))[:cap]
            truncated = True
            message = (f"Neighborhood có {total_neighbors} node láng giềng, vượt cap={cap}: "
                       f"chỉ trả về {cap} node bậc cao nhất (ưu tiên theo bậc, hòa thì theo ID). "
                       f"Tăng cap (tối đa {MAX_CAP}) hoặc giảm hop để xem nhiều node hơn.")
        elif total_neighbors == 0:
            selected = []
            message = (f"Node này không có cạnh nội bộ nào trong chế độ {mode} "
                       "(node isolated trong tập cạnh của chế độ đó).")
        else:
            selected = neighbors_all

        shown = set(selected)
        shown.add(doc_id)
        edges: list[tuple[str, str]] = []
        for u in sorted(shown):
            for v in graph.out_adj.get(u, ()):
                if v in shown:
                    edges.append((u, v))
        edges.sort()
        edges_truncated = False
        if len(edges) > MAX_RETURNED_EDGES:
            edges = edges[:MAX_RETURNED_EDGES]
            edges_truncated = True
            message = ((message + " " if message else "")
                       + f"Số cạnh hiển thị bị cắt ở {MAX_RETURNED_EDGES} cạnh.")

        nodes_payload = [self._node_payload(doc_id, 0, graph, mode)]
        nodes_payload += [self._node_payload(n, depth[n], graph, mode) for n in selected]
        edges_payload = [{
            "src": u,
            "dst": v,
            "relation_to_center": ("cites" if u == doc_id
                                   else ("cited_by" if v == doc_id else None)),
        } for u, v in edges]

        relpath = MODE_EDGE_FILES[mode]
        return {
            "doc_id": doc_id,
            "title": self._nodes[doc_id]["title"],
            "year": self._nodes[doc_id]["year"],
            "mode": mode,
            "mode_label": MODE_LABELS[mode],
            "hop": hop,
            "cap": cap,
            "truncated": truncated,
            "edges_truncated": edges_truncated,
            "message": message,
            "counts": {
                "neighbor_nodes_total": total_neighbors,
                "neighbor_nodes_returned": len(selected),
                "edges_returned": len(edges_payload),
                "cites_edges_returned": sum(1 for e in edges_payload
                                            if e["relation_to_center"] == "cites"),
                "cited_by_edges_returned": sum(1 for e in edges_payload
                                               if e["relation_to_center"] == "cited_by"),
                "center_in_degree": graph.in_degree.get(doc_id, 0),
                "center_out_degree": graph.out_degree.get(doc_id, 0),
            },
            "nodes": nodes_payload,
            "edges": edges_payload,
            "split": {
                "dev_query_count": len(self._dev_queries),
                "test_query_count": len(self._test_queries),
                "center_split_role": self._split_role(doc_id, mode),
                "shown_in_mode": mode == "evaluated",
            },
            "legend": GRAPH_LEGEND,
            "snapshot": {
                "snapshot_id": self._snapshot_id,
                "retrieved_completed_at": self._retrieved_at,
                "edge_file": str(relpath).replace("\\", "/"),
                "edge_sha256": (self._masked_hash if mode == "evaluated"
                                else self._premask_hash),
                "edge_count_total": (self._masked_edge_count if mode == "evaluated"
                                     else self._premask_edge_count),
            },
            "inputs": self._mode_inputs(mode),
            "manifest_counts": self._manifest_counts,
        }

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def _mode_inputs(self, mode: str) -> list[str]:
        """Files this mode actually reads (provenance shown 1:1 on the UI)."""
        inputs = [str(MANIFEST_RELPATH).replace("\\", "/"),
                  str(MODE_EDGE_FILES[mode]).replace("\\", "/"),
                  str(self._works_relpath).replace("\\", "/")]
        if mode == "evaluated":
            inputs.append(str(SPLIT_QUERIES_RELPATH).replace("\\", "/"))
        return inputs
