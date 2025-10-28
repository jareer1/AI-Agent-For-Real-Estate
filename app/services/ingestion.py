import csv
import hashlib
import re
from datetime import datetime, timezone
from io import StringIO, TextIOWrapper
from typing import Any

import chardet

from ..db.mongo import raw_messages_collection, messages_collection, threads_collection
from ..schemas.common import Role, Stage


ROLE_MAP = {
    "agent": Role.agent.value,
    "lead": Role.lead.value,
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)  # zero-width
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([!?\.]){2,}", r"\1", text)
    return text


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
DOLLAR_RE = re.compile(r"\$?\b(\d{3,5})\b")
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\bMay\b|\bJune\b|\bJuly\b|\bAug\b|\bSept\b|\bOctober\b|\bNov\b|\bDec\b)\b", re.IGNORECASE)


def _redact_pii(text: str) -> tuple[str, dict[str, str]]:
    pii: dict[str, str] = {}

    def repl_email(m: re.Match[str]) -> str:
        v = m.group(0)
        h = _sha256(v)
        pii.setdefault("emails", h)
        return f"[EMAIL_HASH:{h}]"

    def repl_phone(m: re.Match[str]) -> str:
        v = m.group(0)
        h = _sha256(v)
        pii.setdefault("phones", h)
        return f"[PHONE_HASH:{h}]"

    text = EMAIL_RE.sub(repl_email, text)
    text = PHONE_RE.sub(repl_phone, text)
    return text, pii


def _infer_stage(text: str) -> Stage:
    lower = text.lower()
    if any(k in lower for k in ["apply", "application"]):
        return Stage.applying
    if any(k in lower for k in ["approved", "approval"]):
        return Stage.approval
    if any(k in lower for k in ["tour", "schedule", "showing"]):
        return Stage.touring
    if any(k in lower for k in ["list", "sending", "sent over"]):
        return Stage.sending_list
    if any(k in lower for k in ["favorite", "top", "select"]):
        return Stage.selecting_favorites
    if any(k in lower for k in ["renewal", "renew"]):
        return Stage.renewal
    if any(k in lower for k in ["congrats", "move in", "post-close", "referral"]):
        return Stage.post_close
    return Stage.first_contact


def _extract_entities(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    # budget
    m = DOLLAR_RE.search(text.replace(",", ""))
    if m:
        try:
            entities["budget"] = int(m.group(1))
        except ValueError:
            pass
    # move_date (very rough)
    if DATE_RE.search(text):
        entities["has_date_mention"] = True
    return entities


def _parse_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            continue
    return None


def _decode_file_with_encoding_detection(file_bytes: bytes) -> str:
    """
    Detect the encoding of the file and decode it to a string.
    Falls back to common encodings if detection fails.
    """
    # First, try to detect the encoding
    detected = chardet.detect(file_bytes)
    encoding = detected.get('encoding', 'utf-8')
    confidence = detected.get('confidence', 0)
    
    # If confidence is low or encoding is None, try common encodings
    if confidence < 0.7 or encoding is None:
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16']
        if encoding and encoding not in encodings_to_try:
            encodings_to_try.insert(0, encoding)
    else:
        encodings_to_try = [encoding]
    
    # Try each encoding until one works
    for enc in encodings_to_try:
        try:
            return file_bytes.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    # If all else fails, use utf-8 with error replacement
    return file_bytes.decode('utf-8', errors='replace')


def ingest_csv(file_bytes: bytes, source_file: str) -> dict:
    # Use encoding detection to properly decode the file
    file_content = _decode_file_with_encoding_detection(file_bytes)
    raw = StringIO(file_content)
    reader = csv.DictReader(raw)

    threads: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []

    current_thread_id: str | None = None
    turn_index = 0
    empty_row_streak = 0
    auto_thread_counter = 0
    # Maintain rolling context per thread (role-labeled clean_text)
    context_buffers: dict[str, list[str]] = {}

    for row in reader:
        # Clean the row to remove None keys (MongoDB doesn't allow None keys)
        cleaned_row = {k: v for k, v in row.items() if k is not None}
        
        # capture raw
        raw_rows.append({"row": cleaned_row, "source_file": source_file, "ingested_at": datetime.now(timezone.utc).isoformat()})

        # detect empty separator - check if all key fields are empty
        key_fields = ["Role", "Message", "Date of message"]
        is_empty_row = all(not (cleaned_row.get(field) or "").strip() for field in key_fields)
        
        if is_empty_row:
            empty_row_streak += 1
            if empty_row_streak >= 2:
                # Reset thread when we hit 2+ consecutive empty rows
                current_thread_id = None
                turn_index = 0
            continue
        empty_row_streak = 0

        text = _normalize_text(cleaned_row.get("Message") or cleaned_row.get("message") or cleaned_row.get("text") or "")
        norm_text, pii = _redact_pii(text)
        role_raw = (cleaned_row.get("Role") or cleaned_row.get("role") or "").strip().lower()
        role = ROLE_MAP.get(role_raw, Role.lead.value if role_raw == "user" else Role.agent.value if role_raw == "assistant" else Role.lead.value)
        ts = _parse_timestamp(cleaned_row.get("Date of message") or cleaned_row.get("timestamp"))

        thread_id = (cleaned_row.get("thread_id") or cleaned_row.get("conversation_id") or None)
        if not thread_id:
            if current_thread_id is None:
                auto_thread_counter += 1
                current_thread_id = f"csv-{auto_thread_counter:05d}"
                print(f"Starting new conversation thread: {current_thread_id}")
            thread_id = current_thread_id
        else:
            if current_thread_id != thread_id:
                current_thread_id = thread_id
                turn_index = 0
                print(f"Switching to thread: {thread_id}")

        stage = _infer_stage(norm_text)
        entities = _extract_entities(norm_text)

        # Build context window (last N prior turns within thread)
        ctx_buf = context_buffers.get(thread_id) or []
        window = 8
        prior_ctx = ctx_buf[-window:]
        labeled = f"{role}:{norm_text}" if role in (Role.agent.value, Role.lead.value) else norm_text
        context_text = (" | ".join(prior_ctx + [labeled])).strip()

        msg_doc = {
            "thread_id": thread_id,
            "turn_index": turn_index,
            "role": role,
            "text": text,
            "clean_text": norm_text,
            "timestamp": ts,
            "stage": stage.value,
            "entities": entities,
            "embedding": None,
            "context_text": context_text,
            "embedding_model": None,
            "embedding_version": None,
            "source": "csv",
            "source_file": source_file,
            "pii_hashes": pii,
        }
        messages.append(msg_doc)
        turn_index += 1

        # Update context buffer with labeled line
        if thread_id:
            buf = context_buffers.setdefault(thread_id, [])
            buf.append(labeled)

    # Derive threads summary with better context
    by_thread: dict[str, list[dict[str, Any]]] = {}
    for m in messages:
        by_thread.setdefault(m["thread_id"], []).append(m)
    
    for tid, items in by_thread.items():
        items_sorted = sorted(items, key=lambda x: x["turn_index"])
        first_ts = next((i.get("timestamp") for i in items_sorted if i.get("timestamp")), None)
        last_ts = next((i.get("timestamp") for i in reversed(items_sorted) if i.get("timestamp")), None)
        
        # Generate a simple summary from the first few messages
        summary_parts = []
        for item in items_sorted[:3]:  # First 3 messages for context
            if item["role"] == "lead" and item["clean_text"]:
                # Extract key info from lead messages
                text = item["clean_text"][:100]  # First 100 chars
                summary_parts.append(f"Lead: {text}")
        
        summary = " | ".join(summary_parts) if summary_parts else f"Conversation with {len(items_sorted)} messages"
        
        # Collect unique stages
        stages = list({i["stage"] for i in items_sorted})
        
        threads.append({
            "thread_id": tid,
            "labels": stages,
            "message_count": len(items_sorted),
            "first_message_ts": first_ts,
            "last_message_ts": last_ts,
            "summary": summary,
            "source_file": source_file,
            "conversation_length": len(items_sorted),
            "primary_stage": stages[0] if stages else "first_contact"
        })

    # Persist
    if raw_rows:
        raw_messages_collection().insert_many(raw_rows)
    if messages:
        messages_collection().insert_many(messages)
    if threads:
        # upsert by thread_id to avoid duplicates on repeated ingests
        for t in threads:
            threads_collection().update_one({"thread_id": t["thread_id"]}, {"$set": t}, upsert=True)

    return {"threads": len(threads), "messages": len(messages), "raw": len(raw_rows)}


