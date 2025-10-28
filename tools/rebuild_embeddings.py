from __future__ import annotations

"""
Maintenance utility: reset embeddings, optionally purge prior CSV-ingested data,
reingest a CSV, and re-embed all messages in batches.

Usage (PowerShell):
  .\venv\Scripts\python.exe -m tools.rebuild_embeddings "AI Agent Training (Messages) - Full conversations.csv" --purge
"""

import argparse
import os
from typing import Any

from app.db.mongo import messages_collection, threads_collection, raw_messages_collection
from app.services.embeddings import EmbeddingsService
from app.services.ingestion import ingest_csv


def purge_csv_data() -> dict[str, Any]:
    # Best effort: remove embeddings and CSV-sourced docs
    msgs = messages_collection()
    thrs = threads_collection()
    raws = raw_messages_collection()

    # Delete only CSV-sourced messages/threads to avoid wiping generated or other sources
    msg_del = msgs.delete_many({"source": "csv"})
    thr_del = thrs.delete_many({"source_file": {"$exists": True}})
    raw_del = raws.delete_many({})
    return {
        "messages_deleted": msg_del.deleted_count,
        "threads_deleted": thr_del.deleted_count,
        "raw_deleted": raw_del.deleted_count,
    }


def reset_all_embeddings() -> int:
    # Set embedding fields to None for all messages
    res = messages_collection().update_many(
        {},
        {"$set": {"embedding": None, "embedding_model": None, "embedding_version": None}},
    )
    return res.modified_count


def embed_all_missing(batch_size: int = 500) -> int:
    svc = EmbeddingsService()
    total = 0
    while True:
        to_embed = list(
            messages_collection().find({"embedding": None}, {"_id": 1, "clean_text": 1}).limit(batch_size)
        )
        if not to_embed:
            break
        pairs = [
            (doc["_id"], (doc.get("clean_text") or "").strip())
            for doc in to_embed
            if (doc.get("clean_text") or "").strip()
        ]
        if not pairs:
            break
        total += svc.embed_and_update_messages(pairs, version="v1")
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=str, help="Path to conversations CSV")
    parser.add_argument("--purge", action="store_true", help="Purge prior CSV data before reingest")
    args = parser.parse_args()

    csv_path = args.csv_path
    if not os.path.exists(csv_path):
        raise SystemExit(f"CSV not found: {csv_path}")

    if args.purge:
        stats = purge_csv_data()
        print(f"Purged: {stats}")

    # Reset embeddings across the board (optional safety)
    reset_count = reset_all_embeddings()
    print(f"Reset embeddings on {reset_count} docs")

    # Ingest CSV bytes
    with open(csv_path, "rb") as f:
        content = f.read()
    result = ingest_csv(content, source_file=os.path.basename(csv_path))
    print(f"Ingested: {result}")

    # Embed missing
    embedded = embed_all_missing(batch_size=500)
    print(f"Embedded messages: {embedded}")


if __name__ == "__main__":
    main()



