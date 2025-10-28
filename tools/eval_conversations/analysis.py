from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from .scorer import _label_action


def load_results(jsonl_path: Path) -> List[dict]:
    rows: List[dict] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def action_breakdown(rows: List[dict]) -> Dict[str, Dict[str, float]]:
    buckets: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        ref = r.get("target_agent", "")
        total = float(r.get("scores", {}).get("total", 0.0))
        label = _label_action(ref)
        buckets[label].append(total)
    summary: Dict[str, Dict[str, float]] = {}
    for k, vals in buckets.items():
        if not vals:
            continue
        summary[k] = {
            "count": float(len(vals)),
            "mean": sum(vals) / len(vals),
            "pass@.7": float(sum(1 for v in vals if v >= 0.7) / len(vals)),
            "pass@.5": float(sum(1 for v in vals if v >= 0.5) / len(vals)),
        }
    return summary


def worst_cases(rows: List[dict], k: int = 10) -> List[dict]:
    sorted_rows = sorted(rows, key=lambda r: float(r.get("scores", {}).get("total", 0.0)))
    return sorted_rows[:k]


def summarize_file(jsonl_path: Path) -> dict:
    rows = load_results(jsonl_path)
    if not rows:
        return {}
    totals = [float(r.get("scores", {}).get("total", 0.0)) for r in rows]
    overall = {
        "count": len(totals),
        "mean": sum(totals) / len(totals),
        "median": sorted(totals)[len(totals) // 2],
        "pass@.7": sum(1 for v in totals if v >= 0.7) / len(totals),
        "pass@.5": sum(1 for v in totals if v >= 0.5) / len(totals),
    }
    by_action = action_breakdown(rows)
    worst = worst_cases(rows, k=min(10, len(rows)))
    return {"overall": overall, "by_action": by_action, "worst": worst}


