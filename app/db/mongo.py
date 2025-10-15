from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection

from ..core.config import get_settings


_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = MongoClient(settings.mongo_uri)
    return _client


def get_db():
    settings = get_settings()
    return get_client()[settings.mongo_db]


def messages_collection() -> Collection:
    return get_db()["messages"]


def threads_collection() -> Collection:
    return get_db()["threads"]


def raw_messages_collection() -> Collection:
    return get_db()["raw_messages"]


def ensure_indexes() -> None:
    msgs = messages_collection()
    thrs = threads_collection()
    msgs.create_index([("thread_id", 1), ("turn_index", 1)])
    msgs.create_index([("stage", 1), ("timestamp", -1)])
    msgs.create_index([("role", 1)])
    thrs.create_index([("thread_id", 1)], unique=True)


