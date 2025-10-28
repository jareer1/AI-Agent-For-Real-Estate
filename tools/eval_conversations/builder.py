from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .csv_parser import read_csv_rows, split_threads, to_turns, build_pairs, Turn


@dataclass
class TestItem:
    thread_id: int
    turn_id: int
    context: List[Dict[str, str]]  # [{role, content}]
    lead: str
    target_agent: str


def _to_json_turns(turns: Iterable[Turn]) -> List[Dict[str, str]]:
    return [{"role": t.role, "content": t.content} for t in turns]


def build_test_items(
    csv_path: Path,
    max_history_messages: Optional[int] = 12,
) -> List[TestItem]:
    rows = read_csv_rows(csv_path)
    threads = split_threads(rows)
    items: List[TestItem] = []
    for thread_idx, thread in enumerate(threads):
        turns = to_turns(thread)
        pairs = build_pairs(turns, max_history_messages=max_history_messages)
        for p_idx, p in enumerate(pairs):
            # Build proper conversation history including the current lead message
            conversation_history = []
            
            # Add previous turns (agent/lead pairs)
            for prev_turn in p.context:
                if prev_turn.role == "agent":
                    conversation_history.append({"role": "assistant", "content": prev_turn.content})
                elif prev_turn.role == "lead":
                    conversation_history.append({"role": "user", "content": prev_turn.content})
            
            items.append(
                TestItem(
                    thread_id=thread_idx,
                    turn_id=p_idx,
                    context=conversation_history,
                    lead=p.lead.content,
                    target_agent=p.target_agent,
                )
            )
    return items


