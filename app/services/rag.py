from typing import Any

from .embeddings import EmbeddingsService
from ..db.mongo import messages_collection


class RAGService:
    def __init__(self) -> None:
        self.embedder = EmbeddingsService()

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """
        Retrieve relevant documents using vector similarity search.
        
        Args:
            query: Search query string
            top_k: Number of documents to return (max 100)
            
        Returns:
            List of relevant documents with metadata
        """
        # Validate inputs
        if not query or not query.strip():
            return []
        
        top_k = min(max(top_k, 1), 100)  # Ensure top_k is between 1 and 100
        
        # Check if embeddings service is available
        if not self.embedder.client:
            print("Embeddings service not available, using recent documents")
            return self._get_recent_documents(top_k)
        
        try:
            # Generate query embedding
            query_embedding = self.embedder.embed_texts([query.strip()])[0]
            if not query_embedding or len(query_embedding) == 0:
                print("Failed to generate query embedding")
                return self._get_recent_documents(top_k)
            
            # Perform vector search
            results = self._vector_search(query_embedding, top_k)
            if results:
                print(f"✅ Vector search successful: retrieved {len(results)} documents")
                return results
            else:
                print("Vector search returned no results, using recent documents")
                return self._get_recent_documents(top_k)
                
        except Exception as e:
            print(f"Vector search failed: {e}")
            return self._get_recent_documents(top_k)

    def _vector_search(self, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        """Perform vector similarity search using MongoDB Atlas Vector Search."""
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "default",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": top_k * 4,  # Retrieve more candidates for better results
                    "limit": top_k
                }
            },
            {
                "$project": {
                    "text": 1,
                    "clean_text": 1,
                    "stage": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]
        
        return list(messages_collection().aggregate(pipeline))

    def _get_recent_documents(self, top_k: int) -> list[dict[str, Any]]:
        """Get recent documents as fallback when embeddings are not available."""
        try:
            return list(
                messages_collection().find(
                    {"clean_text": {"$exists": True, "$ne": ""}},
                    {"text": 1, "clean_text": 1, "stage": 1, "timestamp": 1}
                ).sort("timestamp", -1).limit(top_k)
            )
        except Exception as e:
            print(f"Failed to retrieve recent documents: {e}")
            return []


