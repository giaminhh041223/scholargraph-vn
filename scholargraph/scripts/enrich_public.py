#!/usr/bin/env python
"""Crossref exact DOI enrichment; no benchmark inputs, separate from search v1."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scholargraph.public_search.crossref import CrossrefError, enrich


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid CLI arguments")


def main(argv=None):
    try:
        parser = Parser(description="Enrich one DOI via Crossref public anonymous pool")
        parser.add_argument("--project-root", default=".")
        parser.add_argument("--config", default="configs/public_crossref.json")
        selector = parser.add_mutually_exclusive_group(required=True)
        selector.add_argument("--doi")
        selector.add_argument("--record-json")
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--payload", help="synthetic offline parser fixture; never live provenance")
        args = parser.parse_args(argv)
        root = Path(args.project_root).resolve()
        def path(value):
            candidate = Path(value)
            return candidate if candidate.is_absolute() else root / candidate
        result = enrich(root, path(args.config), path(args.output_dir), doi=args.doi,
                        record_path=path(args.record_json) if args.record_json is not None else None,
                        payload_path=path(args.payload) if args.payload is not None else None)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result["status"] == "success" else 1
    except (OSError, ValueError, TypeError) as exc:
        error = {"kind": exc.kind if isinstance(exc, CrossrefError) else "request",
                 "message": str(exc) if isinstance(exc, CrossrefError) else "invalid arguments/resource or existing output directory"}
        print(json.dumps({"status": "failed", "error": error}))
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
