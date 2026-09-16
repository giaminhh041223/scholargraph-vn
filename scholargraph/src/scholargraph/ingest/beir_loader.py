"""Read immutable BEIR snapshots without depending on the BEIR Python package.

The loader intentionally reads only local files.  Downloading, unpacking and the
archive hashes are recorded in ``data/manifests``; retrieval code must not turn a
network outage or a changed upstream archive into an implicit data update.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import json
from pathlib import Path
from typing import Dict, Mapping, Sequence

from scholargraph.data.schemas import Paper, Qrel, Query, make_canonical_id


SUPPORTED_DATASETS = frozenset({"scifact", "scidocs"})
_CORPUS_FILENAME = "corpus.jsonl"
_QUERIES_FILENAME = "queries.jsonl"


class BeirDataError(ValueError):
    """Raised when a local BEIR snapshot violates its expected format."""


@dataclass(frozen=True)
class BeirDataset:
    """A single BEIR dataset split with lossless internal ID namespacing.

    ``corpus`` and ``queries`` contain only the documents and queries available
    to the requested split.  The raw BEIR identifier is retained in each
    object's metadata, while ``qrels`` uses the same canonical IDs as those
    objects.  This prevents a dataset ID collision in a multi-dataset index.
    """

    name: str
    split: str
    corpus: Mapping[str, Paper]
    queries: Mapping[str, Query]
    qrels: Mapping[str, Mapping[str, int]]
    qrel_records: Sequence[Qrel]


def canonical_beir_id(dataset: str, raw_id: str) -> str:
    """Return the lossless project ID for a raw BEIR corpus/query ID."""
    _validate_dataset(dataset)
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise BeirDataError("BEIR raw ID must be a non-empty string.")
    return make_canonical_id(f"beir:{dataset}", raw_id)


def raw_beir_id(dataset: str, canonical_id: str) -> str:
    """Recover a raw BEIR ID, rejecting an ID belonging to another dataset."""
    _validate_dataset(dataset)
    prefix = f"beir:{dataset}:"
    if not canonical_id.startswith(prefix):
        raise BeirDataError(
            f"ID '{canonical_id}' does not belong to BEIR dataset '{dataset}'."
        )
    raw_id = canonical_id[len(prefix) :]
    if not raw_id:
        raise BeirDataError("Canonical BEIR ID has an empty raw component.")
    return raw_id


def sha256_file(path: Path | str) -> str:
    """Return the SHA-256 checksum of one snapshot file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path | str, expected_sha256: str) -> bool:
    """Compare a local file with a manifest checksum (case-insensitively)."""
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise ValueError("expected_sha256 must be a 64-character hexadecimal SHA-256.")
    return sha256_file(path) == expected


class BeirLoader:
    """Load corpus, split-specific queries and qrels from a frozen BEIR folder."""

    def __init__(self, raw_root: Path | str) -> None:
        self.raw_root = Path(raw_root)

    def available_splits(self, dataset: str) -> tuple[str, ...]:
        """Return the split names physically present in the local snapshot."""
        dataset_path = self._dataset_path(dataset)
        qrels_path = dataset_path / "qrels"
        if not qrels_path.is_dir():
            raise BeirDataError(f"Missing qrels directory: {qrels_path}")
        return tuple(sorted(item.stem for item in qrels_path.glob("*.tsv") if item.is_file()))

    def load(self, dataset: str, split: str) -> BeirDataset:
        """Load a local snapshot split, never downloading or synthesizing records."""
        _validate_dataset(dataset)
        if not split or not split.strip():
            raise BeirDataError("BEIR split must be a non-empty string.")
        split = split.strip()
        dataset_path = self._dataset_path(dataset)
        corpus = self._read_corpus(dataset, dataset_path / _CORPUS_FILENAME)
        raw_queries = self._read_queries(dataset, dataset_path / _QUERIES_FILENAME)
        qrels_path = dataset_path / "qrels" / f"{split}.tsv"
        qrels, records = self._read_qrels(dataset, qrels_path, corpus, raw_queries)
        selected_query_ids = set(qrels)
        queries = {query_id: raw_queries[query_id] for query_id in selected_query_ids}
        return BeirDataset(
            name=dataset,
            split=split,
            corpus=corpus,
            queries=queries,
            qrels=qrels,
            qrel_records=tuple(records),
        )

    def _dataset_path(self, dataset: str) -> Path:
        _validate_dataset(dataset)
        dataset_path = self.raw_root / dataset
        if not dataset_path.is_dir():
            raise BeirDataError(
                f"BEIR dataset '{dataset}' is not installed at '{dataset_path}'. "
                "Restore the frozen archive recorded in its manifest; do not silently download it."
            )
        return dataset_path

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        if not path.is_file():
            raise BeirDataError(f"Missing BEIR JSONL file: {path}")
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise BeirDataError(f"Blank line in {path} at line {line_number}.")
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise BeirDataError(
                        f"Invalid JSON in {path} at line {line_number}: {exc.msg}"
                    ) from exc
                if not isinstance(row, dict):
                    raise BeirDataError(f"JSONL row in {path} at line {line_number} is not an object.")
                rows.append(row)
        return rows

    def _read_corpus(self, dataset: str, path: Path) -> Dict[str, Paper]:
        corpus: Dict[str, Paper] = {}
        for line_number, row in enumerate(self._read_jsonl(path), start=1):
            raw_id = _required_string(row, "_id", path, line_number)
            canonical_id = canonical_beir_id(dataset, raw_id)
            if canonical_id in corpus:
                raise BeirDataError(f"Duplicate corpus ID '{raw_id}' in {path} at line {line_number}.")
            title = row.get("title")
            if title is None:
                title = ""
            text = row.get("text")
            if text is None:
                text = ""
            if not isinstance(title, str) or not isinstance(text, str):
                raise BeirDataError(f"Corpus row '{raw_id}' in {path} has non-string title or text.")
            # Paper requires a non-empty title.  BEIR permits a missing title;
            # represent a text-only record as title=text and abstract="" so
            # Paper.text_content() still reconstructs the source text exactly
            # once.  A document with neither title nor text is malformed for
            # retrieval.
            has_title = bool(title.strip())
            normalized_title = title.strip() or text.strip()
            if not normalized_title:
                raise BeirDataError(f"Corpus row '{raw_id}' in {path} has neither title nor text.")
            metadata = row.get("metadata", {})
            if not isinstance(metadata, dict):
                raise BeirDataError(f"Corpus metadata for '{raw_id}' in {path} is not an object.")
            year = metadata.get("year")
            if isinstance(year, str) and year.isdigit():
                year = int(year)
            if not isinstance(year, int):
                year = None
            corpus[canonical_id] = Paper(
                id=canonical_id,
                title=normalized_title,
                abstract=text.strip() if has_title else "",
                year=year,
                authors=tuple(str(author) for author in metadata.get("authors", []) if str(author).strip()),
                venue=None,
                references=(),
                synthetic=False,
            )
        if not corpus:
            raise BeirDataError(f"BEIR corpus is empty: {path}")
        return corpus

    def _read_queries(self, dataset: str, path: Path) -> Dict[str, Query]:
        queries: Dict[str, Query] = {}
        for line_number, row in enumerate(self._read_jsonl(path), start=1):
            raw_id = _required_string(row, "_id", path, line_number)
            canonical_id = canonical_beir_id(dataset, raw_id)
            if canonical_id in queries:
                raise BeirDataError(f"Duplicate query ID '{raw_id}' in {path} at line {line_number}.")
            text = _required_string(row, "text", path, line_number)
            queries[canonical_id] = Query(
                id=canonical_id,
                text=text,
                language="en",
                metadata={"beir_raw_id": raw_id, "dataset": dataset},
                synthetic=False,
            )
        if not queries:
            raise BeirDataError(f"BEIR queries are empty: {path}")
        return queries

    def _read_qrels(
        self,
        dataset: str,
        path: Path,
        corpus: Mapping[str, Paper],
        queries: Mapping[str, Query],
    ) -> tuple[Dict[str, Dict[str, int]], list[Qrel]]:
        if not path.is_file():
            raise BeirDataError(f"Missing BEIR qrels split: {path}")
        qrels: Dict[str, Dict[str, int]] = {}
        records: list[Qrel] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            expected_fields = ["query-id", "corpus-id", "score"]
            if reader.fieldnames != expected_fields:
                raise BeirDataError(
                    f"Unexpected qrels header in {path}: {reader.fieldnames!r}; expected {expected_fields!r}."
                )
            for line_number, row in enumerate(reader, start=2):
                raw_query_id = _required_string(row, "query-id", path, line_number)
                raw_doc_id = _required_string(row, "corpus-id", path, line_number)
                try:
                    score = int(_required_string(row, "score", path, line_number))
                except ValueError as exc:
                    raise BeirDataError(f"Non-integer qrel score in {path} at line {line_number}.") from exc
                if score < 0 or score > 2:
                    raise BeirDataError(
                        f"Qrel score {score} in {path} at line {line_number} is outside [0, 2]."
                    )
                query_id = canonical_beir_id(dataset, raw_query_id)
                doc_id = canonical_beir_id(dataset, raw_doc_id)
                if query_id not in queries:
                    raise BeirDataError(f"Qrel query '{raw_query_id}' in {path} is absent from queries.jsonl.")
                if doc_id not in corpus:
                    raise BeirDataError(f"Qrel document '{raw_doc_id}' in {path} is absent from corpus.jsonl.")
                per_query = qrels.setdefault(query_id, {})
                if doc_id in per_query:
                    raise BeirDataError(
                        f"Duplicate qrel ({raw_query_id}, {raw_doc_id}) in {path} at line {line_number}."
                    )
                per_query[doc_id] = score
                records.append(Qrel(query_id=query_id, doc_id=doc_id, score=score, synthetic=False))
        if not qrels:
            raise BeirDataError(f"BEIR qrels split is empty: {path}")
        return qrels, records


def _validate_dataset(dataset: str) -> None:
    if dataset not in SUPPORTED_DATASETS:
        supported = ", ".join(sorted(SUPPORTED_DATASETS))
        raise BeirDataError(f"Unsupported BEIR dataset '{dataset}'. Supported datasets: {supported}.")


def _required_string(row: Mapping[str, object], key: str, path: Path, line_number: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BeirDataError(f"Missing or empty '{key}' in {path} at line {line_number}.")
    return value.strip()
