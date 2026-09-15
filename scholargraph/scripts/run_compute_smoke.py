"""Execute code cells from the SG-002 notebook without requiring nbconvert.

This runner is intentionally small: it supports this repository's plain Python
notebook only and rejects IPython magics. The notebook itself writes and
validates artifacts/reports/compute_pilot.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "notebook",
        nargs="?",
        default="notebooks/compute_smoke.ipynb",
        help="Path to the plain-Python notebook",
    )
    args = parser.parse_args()
    path = Path(args.notebook).resolve()
    notebook = json.loads(path.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {"__name__": "__main__"}
    executed = 0

    for index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if any(line.lstrip().startswith(("%", "!")) for line in source.splitlines()):
            raise ValueError(f"Cell {index} contains unsupported IPython magic")
        print(f"--- executing cell {index} ---", flush=True)
        exec(compile(source, f"{path.name}#cell-{index}", "exec"), namespace)
        executed += 1

    print(f"Executed {executed} code cells from {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
