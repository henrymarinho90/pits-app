"""Print total elapsed_time and the top-N slowest nodes of a dbt run_results.json (D110)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "transform" / "target" / "run_results.json"
TOP_N = 10


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PATH
    if not path.is_file():
        print(f"error: {path} not found", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", [])
    print(f"elapsed_time_s: {data['elapsed_time']:.3f}")
    print(f"nodes: {len(results)}")
    top = sorted(results, key=lambda r: r["execution_time"], reverse=True)[:TOP_N]
    for r in top:
        print(f"{r['execution_time']:8.3f}s  {r['status']:<8} {r['unique_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
