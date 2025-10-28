from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


CSV_HEADERS = [
    "Role",
    "Message",
    "Images/ Voice Messages/ etc",
    "Channel",
    "Event Marker",
    "Date of message",
    "Notes",
]


@dataclass
class CsvRow:
    role: str
    message: str
    attachments: str
    channel: str
    event_marker: str
    date: str
    notes: str


def _is_blank_row(row: CsvRow) -> bool:
    return (
        (row.role.strip() == "")
        and (row.message.strip() == "")
        and (row.attachments.strip() == "")
        and (row.channel.strip() == "")
        and (row.event_marker.strip() == "")
        and (row.date.strip() == "")
        and (row.notes.strip() == "")
    )


def _is_reaction_or_non_textual(message: str, attachments: str) -> bool:
    text = (message or "").strip()
    if attachments and not text:
        return True
    lowered = text.lower()
    prefixes = (
        "loved ",
        "liked ",
        "emphasized ",
        "reacted ",
        "questioned ",
        "removed a heart",
        "laughed at ",
        "disliked ",
    )
    return lowered.startswith(prefixes)


def read_csv_rows(csv_path: Path) -> List[CsvRow]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows: List[CsvRow] = []
        for raw in reader:
            # Guard against missing headers or extra columns
            role = (raw.get("Role") or "").strip()
            message = raw.get("Message") or ""
            rows.append(
                CsvRow(
                    role=role,
                    message=message,
                    attachments=raw.get("Images/ Voice Messages/ etc") or "",
                    channel=raw.get("Channel") or "",
                    event_marker=raw.get("Event Marker") or "",
                    date=raw.get("Date of message") or "",
                    notes=raw.get("Notes") or "",
                )
            )
        return rows


def split_threads(rows: Iterable[CsvRow]) -> List[List[CsvRow]]:
    """Split into threads using two consecutive blank rows as a separator."""
    threads: List[List[CsvRow]] = []
    current: List[CsvRow] = []
    blank_streak = 0
    for row in rows:
        if _is_blank_row(row):
            blank_streak += 1
            if blank_streak >= 2:
                if current:
                    threads.append(current)
                current = []
                blank_streak = 0
            continue
        else:
            blank_streak = 0
        current.append(row)
    if current:
        threads.append(current)
    return threads


@dataclass
class Turn:
    role: str  # "agent" | "lead" | other
    content: str


@dataclass
class LeadTargetPair:
    lead_turn_idx: int
    lead: Turn
    target_agent: str
    context: List[Turn]


def normalize_role(role: str) -> str:
    r = (role or "").strip().lower()
    if r == "agent":
        return "agent"
    if r == "lead":
        return "lead"
    return r or "other"


def to_turns(thread: List[CsvRow]) -> List[Turn]:
    turns: List[Turn] = []
    for r in thread:
        if _is_reaction_or_non_textual(r.message, r.attachments):
            continue
        role = normalize_role(r.role)
        if not r.message.strip():
            continue
        turns.append(Turn(role=role, content=r.message.strip()))
    return turns


def build_pairs(turns: List[Turn], max_history_messages: Optional[int] = None) -> List[LeadTargetPair]:
    pairs: List[LeadTargetPair] = []
    n = len(turns)
    for i, t in enumerate(turns):
        if t.role != "lead":
            continue
        # Find next substantive Agent message(s) until next Lead
        j = i + 1
        agent_responses: List[str] = []
        while j < n and turns[j].role != "lead":
            if turns[j].role == "agent":
                agent_responses.append(turns[j].content)
            j += 1
        target = " \n\n".join(agent_responses).strip()
        if not target:
            # Skip items with no gold target
            continue
        # Context: prior turns
        context = turns[:i]
        if max_history_messages is not None and len(context) > max_history_messages:
            context = context[-max_history_messages:]
        pairs.append(
            LeadTargetPair(
                lead_turn_idx=i,
                lead=t,
                target_agent=target,
                context=context,
            )
        )
    return pairs


