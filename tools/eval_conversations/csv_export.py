from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from .analysis import load_results


def export_to_csv(jsonl_path: Path, csv_path: Path) -> None:
    """Export evaluation results to CSV with accuracy scores and details."""
    rows = load_results(jsonl_path)
    if not rows:
        return
    
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Headers
        writer.writerow([
            "thread_id",
            "turn_id", 
            "lead_message",
            "target_agent_response",
            "model_response",
            "total_score",
            "cosine_similarity",
            "rouge_l_score",
            "action_match",
            "entity_overlap",
            "style_score",
            "accuracy_pass_0.7",
            "accuracy_pass_0.5",
            "response_length",
            "target_length",
            "response_quality"
        ])
        
        for row in rows:
            scores = row.get("scores", {})
            total_score = scores.get("total", 0.0)
            
            writer.writerow([
                row.get("thread_id", ""),
                row.get("turn_id", ""),
                (row.get("lead", "") or "").replace("\n", " ").replace("\r", " "),
                (row.get("target_agent", "") or "").replace("\n", " ").replace("\r", " "),
                (row.get("prediction", "") or "").replace("\n", " ").replace("\r", " "),
                f"{total_score:.4f}",
                f"{scores.get('cosine', 0.0):.4f}",
                f"{scores.get('rougeL', 0.0):.4f}",
                f"{scores.get('action_match', 0.0):.4f}",
                f"{scores.get('entity', 0.0):.4f}",
                f"{scores.get('style', 0.0):.4f}",
                "PASS" if total_score >= 0.7 else "FAIL",
                "PASS" if total_score >= 0.5 else "FAIL",
                len(row.get("prediction", "") or ""),
                len(row.get("target_agent", "") or ""),
                "HIGH" if total_score >= 0.7 else "MEDIUM" if total_score >= 0.5 else "LOW"
            ])
