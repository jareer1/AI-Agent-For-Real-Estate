from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional

import httpx

from .builder import build_test_items, TestItem
from .scorer import score_item
from .utils import stable_id


def _iter_sample(items: List[TestItem], limit: Optional[int]) -> Iterable[TestItem]:
    if limit is None or limit >= len(items):
        return items
    return items[:limit]


def call_zapier(endpoint: str, item: TestItem, timeout: float = 30.0) -> str:
    # Payload aligned with our FastAPI webhook: /api/webhook/zapier/message
    payload = {
        "thread_id": item.thread_id,
        "chat_history": item.context,
        "text": item.lead,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
        # Accept our API shape {message: "..."} or generic {response: "..."}
        if isinstance(data, dict):
            if "message" in data:
                return str(data["message"]) or ""
            if "response" in data:
                return str(data["response"]) or ""
        if isinstance(data, str):
            return data
        return json.dumps(data)


def run_eval(
    csv_path: Path,
    endpoint: str,
    out_path: Path,
    limit: Optional[int] = None,
) -> None:
    items = build_test_items(csv_path)
    results = []
    for item in _iter_sample(items, limit):
        try:
            prediction = call_zapier(endpoint, item)
        except Exception as e:
            prediction = f"__ERROR__: {e}"
        scores = score_item(prediction, item.target_agent)
        rid = stable_id([str(item.thread_id), str(item.turn_id), item.lead[:64]])
        results.append(
            {
                "id": rid,
                "thread_id": item.thread_id,
                "turn_id": item.turn_id,
                "lead": item.lead,
                "target_agent": item.target_agent,
                "prediction": prediction,
                "scores": scores,
            }
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(jsonl_path: Path) -> dict:
    totals: List[dict] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            totals.append(obj["scores"])  # type: ignore
    if not totals:
        return {}
    keys = totals[0].keys()
    agg = {k: sum(t[k] for t in totals) / len(totals) for k in keys}
    return agg


