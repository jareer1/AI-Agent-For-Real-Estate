from __future__ import annotations

import argparse
from pathlib import Path

from .runner import run_eval, summarize


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate Zapier endpoint against CSV gold data")
    ap.add_argument("csv", type=Path, help="Path to Additional conversations CSV")
    ap.add_argument("endpoint", type=str, help="Zapier endpoint URL")
    ap.add_argument("out", type=Path, help="Output JSONL path")
    ap.add_argument("--limit", type=int, default=None, help="Optional limit of test items")
    ap.add_argument("--summary", action="store_true", help="Print summary after run")
    args = ap.parse_args()

    run_eval(args.csv, args.endpoint, args.out, limit=args.limit)
    if args.summary:
        agg = summarize(args.out)
        if agg:
            print(agg)


if __name__ == "__main__":
    main()


