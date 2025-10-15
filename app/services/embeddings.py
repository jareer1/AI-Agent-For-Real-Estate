from typing import Any
from openai import OpenAI

from ..core.config import get_settings


class EmbeddingsService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.model = "text-embedding-3-large"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.client:
            return [[0.0] * 10 for _ in texts]
        
        # Filter out empty or None texts - OpenAI API doesn't accept them
        valid_texts = [text for text in texts if text and text.strip()]
        if not valid_texts:
            return []
            
        resp = self.client.embeddings.create(model=self.model, input=valid_texts)
        return [d.embedding for d in resp.data]

    def embed_and_update_messages(self, message_ids_and_texts: list[tuple[Any, str]], version: str = "v1") -> int:
        if not message_ids_and_texts:
            return 0
        
        # Filter out empty texts before processing
        valid_pairs = [(mid, text) for mid, text in message_ids_and_texts if text and text.strip()]
        if not valid_pairs:
            return 0
            
        texts = [t for _, t in valid_pairs]
        vectors = self.embed_texts(texts)
        
        if not vectors:
            return 0
            
        from ..db.mongo import messages_collection
        for (mid, _), vec in zip(valid_pairs, vectors):
            messages_collection().update_one(
                {"_id": mid},
                {"$set": {"embedding": vec, "embedding_model": self.model, "embedding_version": version}},
            )
        return len(vectors)


