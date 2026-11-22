"""Measure one public research command in a fresh process.

The command prints its normal JSON first and a final ``memory_probe`` JSON record.
It measures Python allocations, not total Windows process RSS or destination capacity.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import tracemalloc

from marketintel.research import main as research_main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("research_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    research_args = list(args.research_args)
    if research_args[:1] == ["--"]:
        research_args = research_args[1:]
    if not research_args:
        parser.error("pass a public marketintel.research command after --")
    tracemalloc.start()
    started = time.perf_counter()
    result = research_main(research_args)
    _, peak = tracemalloc.get_traced_memory()
    elapsed = time.perf_counter() - started
    tracemalloc.stop()
    print(
        json.dumps(
            {
                "memory_probe": {
                    "python_peak_allocated_bytes": peak,
                    "elapsed_seconds": round(elapsed, 6),
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "command": research_args[0],
                    "exit_code": result,
                }
            },
            sort_keys=True,
        )
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
