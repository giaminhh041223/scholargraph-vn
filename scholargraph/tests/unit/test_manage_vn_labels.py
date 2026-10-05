"""Unit and adversarial/destructive tests for scripts/manage_vn_labels.py (SG-033 helper)."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "manage_vn_labels.py"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _make_pool_and_works(tmp_path: Path) -> tuple[Path, Path]:
    pool_path = tmp_path / "vn_pool.json"
    works_path = tmp_path / "works.jsonl"
    pool_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "blinded": True,
                "counts": {"queries": 2, "dev": 1, "test": 1, "unique_pairs": 2},
                "pools": [
                    {
                        "query_id": "vn:dev:001",
                        "split": "dev",
                        "intent_family": "topic1",
                        "text_vi": "Cau hoi 1",
                        "text_en": "Question 1",
                        "pool_size": 1,
                        "candidates": [{"position": 1, "doc_id": "openalex:W1", "title": "Title 1", "year": 2022}],
                    },
                    {
                        "query_id": "vn:test:001",
                        "split": "test",
                        "intent_family": "topic2",
                        "text_vi": "Cau hoi 2",
                        "text_en": "Question 2",
                        "pool_size": 1,
                        "candidates": [{"position": 1, "doc_id": "openalex:W2", "title": "Title 2", "year": 2023}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    works_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "https://openalex.org/W1", "title": "Title 1", "abstract_inverted_index": {"hello": [0], "world": [1]}, "publication_year": 2022}),
                json.dumps({"id": "https://openalex.org/W2", "title": "Title 2", "abstract_inverted_index": {"test": [0], "abstract": [1]}, "publication_year": 2023}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return pool_path, works_path


def test_build_kit_and_merge_happy_path(tmp_path: Path) -> None:
    pool_p, works_p = _make_pool_and_works(tmp_path)
    kit_dir = tmp_path / "vn_labeling_kit_SG033"
    zip_path = tmp_path / "kit.zip"

    res = _run_cli(
        [
            "build-kit",
            "--pool", str(pool_p),
            "--works", str(works_p),
            "--out-dir", str(kit_dir),
            "--zip-out", str(zip_path),
        ]
    )
    assert res.returncode == 0, res.stderr
    assert (kit_dir / "label_tool.html").is_file()
    assert "hello world" in (kit_dir / "label_tool.html").read_text(encoding="utf-8")
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "vn_labeling_kit_SG033/label_tool.html" in names
        assert "vn_labeling_kit_SG033/templates/vn_labels_A_dev.jsonl" in names

    # Merge A and B with disagreement + export-disagreements
    fa = tmp_path / "a.jsonl"
    fb = tmp_path / "b.jsonl"
    fa.write_text(
        json.dumps({"query_id": "vn:dev:001", "doc_id": "openalex:W1", "label": 2, "annotator": "A", "round": "independent", "note": None}) + "\n",
        encoding="utf-8",
    )
    fb.write_text(
        json.dumps({"query_id": "vn:dev:001", "doc_id": "openalex:W1", "label": 1, "annotator": "B", "round": "independent", "note": None}) + "\n",
        encoding="utf-8",
    )
    dis_out = tmp_path / "dis.jsonl"
    res_dis = _run_cli(["export-disagreements", "--file-a", str(fa), "--file-b", str(fb), "--output", str(dis_out)])
    assert res_dis.returncode == 0, res_dis.stderr
    dis_row = json.loads(dis_out.read_text(encoding="utf-8").strip())
    assert dis_row["round"] == "adjudicated"
    assert dis_row["label"] is None

    # Fill adjudicated label and merge
    dis_row["label"] = 2
    dis_out.write_text(json.dumps(dis_row) + "\n", encoding="utf-8")
    merged_out = tmp_path / "merged.jsonl"
    res_merge = _run_cli(
        [
            "merge",
            "--file-a", str(fa),
            "--file-b", str(fb),
            "--adjudicated", str(dis_out),
            "--output", str(merged_out),
        ]
    )
    assert res_merge.returncode == 0, res_merge.stderr
    lines = merged_out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_merge_rejects_null_and_provenance_and_mismatch_exit_1(tmp_path: Path) -> None:
    fa = tmp_path / "a.jsonl"
    fb = tmp_path / "b.jsonl"
    out = tmp_path / "merged.jsonl"

    # 1. Null label -> exit 1
    fa.write_text(
        json.dumps({"query_id": "vn:dev:001", "doc_id": "openalex:W1", "label": None, "annotator": "A", "round": "independent"}) + "\n",
        encoding="utf-8",
    )
    fb.write_text(
        json.dumps({"query_id": "vn:dev:001", "doc_id": "openalex:W1", "label": 1, "annotator": "B", "round": "independent"}) + "\n",
        encoding="utf-8",
    )
    res_null = _run_cli(["merge", "--file-a", str(fa), "--file-b", str(fb), "--output", str(out)])
    assert res_null.returncode == 1
    assert "null label" in res_null.stderr

    # 2. Provenance leak -> exit 1
    fa.write_text(
        json.dumps({"query_id": "vn:dev:001", "doc_id": "openalex:W1", "label": 1, "annotator": "A", "round": "independent", "method": "bm25"}) + "\n",
        encoding="utf-8",
    )
    res_leak = _run_cli(["merge", "--file-a", str(fa), "--file-b", str(fb), "--output", str(out)])
    assert res_leak.returncode == 1
    assert "leaks system provenance" in res_leak.stderr

    # 3. Pair mismatch -> exit 1
    fa.write_text(
        json.dumps({"query_id": "vn:dev:002", "doc_id": "openalex:W1", "label": 1, "annotator": "A", "round": "independent"}) + "\n",
        encoding="utf-8",
    )
    res_mismatch = _run_cli(["merge", "--file-a", str(fa), "--file-b", str(fb), "--output", str(out)])
    assert res_mismatch.returncode == 1
    assert "Pair mismatch" in res_mismatch.stderr


def _rewrite_pool_ids(pool_p: Path, ids: list[str]) -> None:
    doc = json.loads(pool_p.read_text(encoding="utf-8"))
    for pool, qid in zip(doc["pools"], ids):
        pool["query_id"] = qid
    pool_p.write_text(json.dumps(doc), encoding="utf-8")


def test_build_kit_v2_namespace_counts_and_filenames(tmp_path: Path) -> None:
    pool_p, works_p = _make_pool_and_works(tmp_path)
    _rewrite_pool_ids(pool_p, ["vn2:dev:001", "vn2:test:001"])
    kit_dir = tmp_path / "vn_labeling_kit_SG033_v2"
    zip_path = tmp_path / "vn_labeling_kit_SG033_v2.zip"
    res = _run_cli(["build-kit", "--pool", str(pool_p), "--works", str(works_p),
                    "--out-dir", str(kit_dir), "--zip-out", str(zip_path)])
    assert res.returncode == 0, res.stderr
    html = (kit_dir / "label_tool.html").read_text(encoding="utf-8")
    guide = (kit_dir / "HUONG_DAN_GAN_NHAN.md").read_text(encoding="utf-8")
    assert "@@" not in html and "@@" not in guide
    assert "Dev (1 cặp" in html and "Tất cả (2 cặp)" in html
    assert "vn2_labels_${state.annotator}" in html
    assert "`1 dev = 1 cặp`" in guide and "vn2_labels_A_dev.jsonl" in guide
    assert "vn_labeling_kit_SG033_v2.zip" in guide
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "vn_labeling_kit_SG033_v2/templates/vn2_labels_B_test.jsonl" in names
    assert not any("/vn_labels_" in n for n in names)


def test_build_kit_rejects_mixed_namespaces_exit_1(tmp_path: Path) -> None:
    pool_p, works_p = _make_pool_and_works(tmp_path)
    _rewrite_pool_ids(pool_p, ["vn:dev:001", "vn2:test:001"])
    kit_dir = tmp_path / "kit_mixed"
    res = _run_cli(["build-kit", "--pool", str(pool_p), "--works", str(works_p),
                    "--out-dir", str(kit_dir), "--zip-out", str(tmp_path / "mixed.zip")])
    assert res.returncode == 1
    assert "namespaces" in res.stderr
    assert not kit_dir.exists() and not (tmp_path / "mixed.zip").exists()
