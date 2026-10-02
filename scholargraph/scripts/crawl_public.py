#!/usr/bin/env python
"""Production CLI for bounded JOSS site crawling (EXT-10).

Usage:
  python scripts/crawl_public.py --project-root . --config configs/public_site_joss.json --run-dir data/public_search/joss/runs/run-01 [--resume] [--query "topic"]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Bootstrap project root src directory before any scholargraph imports
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scholargraph.public_search.site_crawler import (
    CrawlerError,
    JossCrawler,
    load_joss_config,
)


class _ArgumentParser(argparse.ArgumentParser):
    """Custom parser ensuring structured JSON failure output on argument errors."""

    def error(self, message: str) -> None:
        err_payload = {
            "status": "failed",
            "site_id": "joss",
            "run_dir": None,
            "error": {
                "kind": "usage_error",
                "message": f"CLI argument error: {message}",
            },
            "counters": None,
        }
        print(json.dumps(err_payload, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(description="ScholarGraph JOSS paper HTML crawler")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Path to project root directory (default: .)",
    )
    parser.add_argument(
        "--config",
        default="configs/public_site_joss.json",
        help="Path to JOSS site configuration JSON",
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to output run directory beneath data_root",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted or complete run from --run-dir",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Optional local substring query to filter harvested records by title or author",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    crawler: JossCrawler | None = None
    run_dir: Path | None = None

    try:
        # Validate query parameter before any network or crawler action
        if args.query is not None:
            q_raw = args.query.strip()
            if not q_raw:
                raise ValueError("Query cannot be empty or whitespace only")
            if len(q_raw) > 500:
                raise ValueError("Query length exceeds maximum limit of 500 characters")

        project_root = Path(args.project_root).absolute()
        cfg_arg = Path(args.config)
        cfg_path = cfg_arg if cfg_arg.is_absolute() else project_root / cfg_arg

        run_arg = Path(args.run_dir)
        run_dir = run_arg if run_arg.is_absolute() else project_root / run_arg

        config = load_joss_config(cfg_path)
        crawler = JossCrawler(
            project_root=project_root,
            config=config,
            run_dir=run_dir,
            resume=args.resume,
        )

        with crawler:
            result = crawler.crawl()

        # Local post-crawl query filter (filters returned records, retains storage provenance)
        if args.query is not None and args.query.strip():
            q_clean = args.query.strip().lower()
            matching_records = [
                rec for rec in result["records"]
                if q_clean in str(rec["title"]).lower()
                or any(q_clean in str(a).lower() for a in rec["authors"])
            ]
            result["records"] = matching_records
            result["records_count"] = len(matching_records)

        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    except Exception as exc:
        err_kind = getattr(exc, "kind", type(exc).__name__)
        counters = crawler.counters.model_dump() if crawler is not None and crawler.checkpoint_loaded else None
        err_payload = {
            "status": "failed",
            "site_id": "joss",
            "run_dir": str(run_dir) if run_dir is not None else None,
            "error": {
                "kind": err_kind,
                "message": str(exc),
            },
            "counters": counters,
        }
        print(json.dumps(err_payload, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Ensure Windows console / pipes use UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main())
