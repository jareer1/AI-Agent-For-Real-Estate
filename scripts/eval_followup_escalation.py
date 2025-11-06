from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict

from app.services.followup_detector import FollowUpPromiseDetector


def eval_from_jsonl(path: Path) -> None:
    detector = FollowUpPromiseDetector()
    total = 0
    detected_true = 0
    ids_should_escalate: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row: Dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            text = (row.get("prediction") or "").strip()
            row_id = str(row.get("id") or total)
            fu = detector.detect(text)
            if fu.get("is_followup") and float(fu.get("confidence", 0.0)) >= 0.6:
                detected_true += 1
                ids_should_escalate.append(row_id)
    print("Follow-up Escalation Evaluation (prediction-based)")
    print(f"Total rows: {total}")
    print(f"Detected follow-up: {detected_true}")
    if ids_should_escalate:
        print("IDs where escalation should be TRUE:")
        for rid in ids_should_escalate:
            print(f" - {rid}")


def eval_from_csv(path: Path) -> None:
    # Expect columns: id, ..., escalation, should_send_message
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        total = 0
        esc_true = 0
        send_true = 0
        for row in reader:
            total += 1
            if str(row.get("escalation", "")).strip().lower() in {"true", "1", "yes"}:
                esc_true += 1
            if str(row.get("should_send_message", "")).strip().lower() in {"true", "1", "yes"}:
                send_true += 1
        print("CSV Summary:")
        print(f"Rows: {total}")
        print(f"Escalation true: {esc_true}")
        print(f"Should send true: {send_true}")


def main(path: str = ".reports/client_evaluation.csv") -> int:
    file_path = Path(path)
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return 1
    if file_path.suffix.lower() == ".jsonl":
        eval_from_jsonl(file_path)
    else:
        eval_from_csv(file_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) > 1 else main())



