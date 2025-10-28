from __future__ import annotations

import argparse
from pathlib import Path

from .csv_export import export_to_csv
from .analysis import summarize_file


def main() -> None:
    ap = argparse.ArgumentParser(description="Export evaluation results to CSV")
    ap.add_argument("jsonl", type=Path, help="Input JSONL file")
    ap.add_argument("csv", type=Path, help="Output CSV file")
    ap.add_argument("--summary", action="store_true", help="Print summary after export")
    args = ap.parse_args()

    export_to_csv(args.jsonl, args.csv)
    print(f"Exported to {args.csv}")
    
    if args.summary:
        summary = summarize_file(args.jsonl)
        print("\nSUMMARY:")
        print(summary)


if __name__ == "__main__":
    main()
