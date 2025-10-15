from typing import Any

from .embeddings import EmbeddingsService
from ..db.mongo import messages_collection


class RAGService:
    def __init__(self) -> None:
        self.embedder = EmbeddingsService()

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        # If embeddings are not configured, fallback to recent messages
        if not self.embedder.client:
            return list(messages_collection().find({}, {"text": 1, "stage": 1}).sort("timestamp", -1).limit(top_k))

        q_emb = self.embedder.embed_texts([query])[0]
        pipeline = [
            {
                "$search": {
                    "knnBeta": {
                        "vector": q_emb,
                        "path": "embedding",
                        "k": top_k,
                    }
                }
            },
            {"$project": {"text": 1, "clean_text": 1, "stage": 1, "score": {"$meta": "searchScore"}}},
            {"$limit": top_k},
        ]
        return list(messages_collection().aggregate(pipeline))


