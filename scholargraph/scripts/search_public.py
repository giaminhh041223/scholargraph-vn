#!/usr/bin/env python
"""Production public-search CLI; init-storage is explicit and side-effectful."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scholargraph.public_search.contracts import SearchError, SearchEnvelope, SearchRequest, error_http_status, read_json
from scholargraph.public_search.service import PublicSearchService, ServiceError
from scholargraph.public_search.store import StoreError, initialize_store


def _failure(error: SearchError) -> int:
    print("FAIL: " + json.dumps({"schema_version": 1, "contract_version": "1.0.0", "overall": "failed",
                      "snapshot": None, "errors": [error.model_dump(mode="json")],
                      "stale": False, "cached": False}, ensure_ascii=False), file=sys.stderr)
    return 1


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can include raw input; use the structured CLI failure.
        raise ValueError("invalid CLI arguments")


def _service(args):
    root = Path(args.project_root).resolve()
    config = Path(args.config) if args.config else root / "configs" / "public_search.json"
    return PublicSearchService(root, config)


def _request(args) -> SearchRequest:
    if args.request is not None:
        payload = read_json(Path(args.request))
    else:
        if args.query is None:
            raise ValueError("missing --request or --query")
        sources = [item.strip() for item in args.sources.split(",")]
        def integer(raw, name):
            if raw is None or not raw.lstrip("-").isdigit():
                raise ValueError(f"invalid {name}")
            return int(raw)
        payload = {"query": args.query, "sources": sources,
                   "top_k": integer(args.top_k, "top_k"),
                   "cap_per_source": integer(args.cap_per_source, "cap_per_source"),
                   "year_from": integer(args.year_from, "year_from") if args.year_from is not None else None,
                   "year_to": integer(args.year_to, "year_to") if args.year_to is not None else None,
                   "refresh": args.refresh}
    return SearchRequest.model_validate(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="ScholarGraph public paper search")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--config", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-storage")
    search = sub.add_parser("search")
    search.add_argument("--request")
    search.add_argument("--query")
    search.add_argument("--sources", default="openalex,arxiv")
    search.add_argument("--top-k", default="20")
    search.add_argument("--cap-per-source", default="50")
    search.add_argument("--year-from")
    search.add_argument("--year-to")
    search.add_argument("--refresh", action="store_true")
    result = sub.add_parser("results")
    result.add_argument("snapshot_id")
    library = sub.add_parser("library")
    library.add_argument("--offset", type=int, default=0)
    library.add_argument("--limit", type=int, default=50)
    export = sub.add_parser("export")
    export.add_argument("--format", choices=["json", "bibtex"], required=True)
    return parser


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "init-storage":
            root = Path(args.project_root).resolve()
            config = Path(args.config) if args.config else root / "configs" / "public_search.json"
            from scholargraph.public_search.contracts import load_config
            config_model = load_config(config)
            store = initialize_store(root, config_model)
            store.close()
            print(json.dumps({"status": "INITIALIZED", "contract_version": "1.0.0"}))
            return 0
        service = _service(args)
        if args.command == "search":
            envelope = service.search(_request(args))
            print(envelope.model_dump_json())
            return 0 if not envelope.errors else 1
        if args.command == "results":
            envelope = service.results(args.snapshot_id)
            print(envelope.model_dump_json())
            return 0 if envelope.overall in {"success", "empty"} else 1
        if args.command == "library":
            entries = service.library(args.offset, args.limit)
            print(json.dumps({"contract_version": "1.0.0", "entries": [e.model_dump(mode="json") for e in entries], "errors": []}, ensure_ascii=False))
            return 0
        if args.command == "export":
            body = service.export_library(args.format)
            sys.stdout.buffer.write(body)
            if args.format == "json":
                sys.stdout.write("\n")
            return 0
        raise ValueError("unknown command")
    except ServiceError as exc:
        return _failure(exc.error)
    except StoreError as exc:
        return _failure(exc.error)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _failure(SearchError(kind="request", message="invalid or missing CLI input", source=None,
                                    retry_after_seconds=None, record_index=None))


if __name__ == "__main__":
    # JSON bytes must be UTF-8 even when Windows redirects a legacy code page.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
