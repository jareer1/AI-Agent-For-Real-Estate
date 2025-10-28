from typing import Any, Optional
import logging

from .embeddings import EmbeddingsService
from ..db.mongo import messages_collection


class RAGService:
    def __init__(self) -> None:
        self.embedder = EmbeddingsService()
        self.logger = logging.getLogger(__name__)
        # Retrieval tuning (conservative weights; vector score dominates)
        self.candidate_k = 60
        self.boost_thread = 0.20
        self.boost_stage = 0.08
        self.boost_agent_role = 0.05
        self.boost_recent_turn = 0.01  # multiplied by normalized recency

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        *,
        thread_id: Optional[str] = None,
        stage: Optional[str] = None,
        prefer_agent: bool = False,
        chat_history: Optional[list[dict[str, str]]] = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant documents using vector similarity search.
        
        Args:
            query: Search query string
            top_k: Number of documents to return (max 100)
            thread_id: If provided, prefer results from this conversation
            stage: If provided, prefer results matching stage
            prefer_agent: If True, prefer messages authored by agent
            chat_history: Optional recent messages to enrich the query
            
        Returns:
            List of relevant documents with metadata
        """
        # Validate inputs
        if not query or not query.strip():
            return []
        
        top_k = min(max(top_k, 1), 100)  # Ensure top_k is between 1 and 100
        
        # Check if embeddings service is available
        if not self.embedder.client:
            try:
                from ..db.mongo import messages_collection
                total_docs = messages_collection().count_documents({})
                embedded_docs = messages_collection().count_documents({"embedding": {"$type": "array"}})
                self.logger.info("RAG retrieve: No embedder client; using recent docs. total=%s embedded=%s", total_docs, embedded_docs)
            except Exception:
                pass
            print("Embeddings service not available, using recent documents")
            role = "agent" if prefer_agent else None
            results = (
                self._get_recent_documents_by_thread(thread_id, top_k, role)
                if thread_id
                else self._get_recent_documents(top_k, role)
            )
            # Safety post-filter
            if prefer_agent:
                results = [d for d in results if (d.get("role") or "").lower() == "agent"]
            return results
        
        try:
            # Generate query embedding
            enriched_query = self._build_query_text(query, chat_history, stage)
            try:
                self.logger.info(
                    "RAG retrieve: thread_id=%s stage=%s prefer_agent=%s top_k=%s query='%s'",
                    thread_id, stage, prefer_agent, top_k, enriched_query[:200]
                )
            except Exception:
                pass
            query_embedding = self.embedder.embed_texts([enriched_query.strip()])[0]
            if not query_embedding or len(query_embedding) == 0:
                print("Failed to generate query embedding")
                return (
                    self._get_recent_documents_by_thread(thread_id, top_k)
                    if thread_id
                    else self._get_recent_documents(top_k)
                )
            
            # Perform vector search: prefer thread candidates first (no stage/role filter),
            # then global candidates. We'll re-rank and trim afterward.
            thread_filters: dict[str, Any] | None = {"thread_id": thread_id} if thread_id else None
            results_thread = self._vector_search(query_embedding, self.candidate_k, thread_filters)
            global_filters: dict[str, Any] | None = None
            results_global = self._vector_search(query_embedding, self.candidate_k, global_filters)
            results = (results_thread or []) + (results_global or [])
            try:
                self.logger.info(
                    "RAG vector search: candidates thread=%s global=%s total=%s",
                    len(results_thread or []), len(results_global or []), len(results or []),
                )
            except Exception:
                pass
            # Re-rank with soft preferences and trim to top_k
            if results:
                ranked = self._rerank_and_trim(results, top_k, thread_id, stage, prefer_agent)
                try:
                    top_meta = [
                        {
                            "role": d.get("role"),
                            "stage": d.get("stage"),
                            "score": d.get("score"),
                            "thread_id": d.get("thread_id"),
                        }
                        for d in ranked[:5]
                    ]
                    self.logger.info("RAG vector search: reranked top=%s meta=%s", len(ranked), top_meta)
                except Exception:
                    pass
                return ranked
            # No good results → prefer recent within-thread if available
            recent = self._get_recent_documents_by_thread(thread_id, top_k, "agent" if prefer_agent else None) if thread_id else None
            if recent:
                if prefer_agent:
                    recent = [d for d in recent if (d.get("role") or "").lower() == "agent"]
                return recent
            else:
                print("Vector search returned no results, using recent documents")
                try:
                    self.logger.warning("RAG vector search: zero results for thread_id=%s stage=%s; falling back to recent", thread_id, stage)
                except Exception:
                    pass
                recent_global = self._get_recent_documents(top_k, "agent" if prefer_agent else None)
                if prefer_agent:
                    recent_global = [d for d in recent_global if (d.get("role") or "").lower() == "agent"]
                return recent_global
                
        except Exception as e:
            print(f"Vector search failed: {e}")
            try:
                self.logger.exception("RAG vector search failed: %s", e)
            except Exception:
                pass
            role = "agent" if prefer_agent else None
            results = (
                self._get_recent_documents_by_thread(thread_id, top_k, role)
                if thread_id
                else self._get_recent_documents(top_k, role)
            )
            if prefer_agent:
                results = [d for d in results if (d.get("role") or "").lower() == "agent"]
            return results

    def _vector_search(
        self,
        query_embedding: list[float],
        top_k: int,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search using MongoDB Atlas Vector Search."""
        # Single embedding path: use unified embedding (built from context_text when available)
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "default",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": max(top_k * 10, 200),
                    "limit": max(top_k, 60),
                }
            },
        ]
        if filters:
            pipeline.append({"$match": filters})
        pipeline.extend(
            [
                {
                    "$project": {
                        "text": 1,
                        "clean_text": 1,
                        "context_text": 1,
                        "role": 1,
                        "stage": 1,
                        "thread_id": 1,
                        "turn_index": 1,
                        "timestamp": 1,
                        "source_file": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
                {"$limit": top_k},
            ]
        )
        return list(messages_collection().aggregate(pipeline))

    def _map_stage_v2_to_legacy_str(self, stage: Optional[str]) -> Optional[str]:
        if not stage:
            return None
        s = (stage or "").lower()
        mapping = {
            "qualifying": "first_contact",
            "working": "sending_list",
            "touring": "touring",
            "applied": "applying",
            "approved": "approval",
            "closed": "post_close",
            "post_close_nurture": "post_close",
        }
        return mapping.get(s, None)

    def _rerank_and_trim(
        self,
        docs: list[dict[str, Any]],
        top_k: int,
        thread_id: Optional[str],
        stage_v2: Optional[str],
        prefer_agent: bool,
    ) -> list[dict[str, Any]]:
        # Compute a simple composite score; preserve original as _vscore
        stage_legacy = self._map_stage_v2_to_legacy_str(stage_v2)
        # recency normalization by turn_index if available
        max_turn = max((d.get("turn_index") or 0 for d in docs), default=0) or 1
        ranked: list[tuple[float, dict[str, Any]]] = []
        for d in docs:
            vscore = float(d.get("score") or 0.0)
            bonus = 0.0
            if thread_id and d.get("thread_id") == thread_id:
                bonus += self.boost_thread
            if stage_legacy and (d.get("stage") or "").lower() == stage_legacy:
                bonus += self.boost_stage
            if prefer_agent and (d.get("role") or "").lower() == "agent":
                bonus += self.boost_agent_role
            t = d.get("turn_index") or 0
            if isinstance(t, int) and max_turn:
                recency = min(max(t / max_turn, 0.0), 1.0)
                bonus += recency * self.boost_recent_turn
            ranked.append((vscore + bonus, d))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in ranked[:top_k]]

    def _get_recent_documents(self, top_k: int, role: Optional[str] = None) -> list[dict[str, Any]]:
        """Get recent documents as fallback when embeddings are not available."""
        try:
            query: dict[str, Any] = {"clean_text": {"$exists": True, "$ne": ""}}
            if role:
                query["role"] = role
            return list(
                messages_collection().find(
                    query,
                    {"text": 1, "clean_text": 1, "role": 1, "stage": 1, "timestamp": 1}
                ).sort("timestamp", -1).limit(top_k)
            )
        except Exception as e:
            print(f"Failed to retrieve recent documents: {e}")
            return []

    def _get_recent_documents_by_thread(self, thread_id: Optional[str], top_k: int, role: Optional[str] = None) -> list[dict[str, Any]]:
        if not thread_id:
            return []
        try:
            query: dict[str, Any] = {"thread_id": thread_id, "clean_text": {"$exists": True, "$ne": ""}}
            if role:
                query["role"] = role
            return list(
                messages_collection().find(
                    query,
                    {"text": 1, "clean_text": 1, "role": 1, "stage": 1, "timestamp": 1}
                ).sort("turn_index", -1).limit(top_k)
            )
        except Exception as e:
            print(f"Failed to retrieve thread documents: {e}")
            return []

    def _build_query_text(
        self,
        user_query: str,
        chat_history: Optional[list[dict[str, str]]],
        stage: Optional[str],
    ) -> str:
        """Compose a richer query from recent turns and stage to improve retrieval."""
        parts: list[str] = []
        if stage:
            parts.append(f"[stage:{stage}]")
        if chat_history:
            # take last 3 turns
            recent = chat_history[-3:]
            for m in recent:
                role = m.get("role") or ""
                content = (m.get("content") or "").strip()
                if content:
                    parts.append(f"{role}: {content}")
        parts.append(user_query.strip())
        return " \n ".join(parts)

    def retrieve_agent_examples(self, query: str, stage: Optional[str] = None, top_k: int = 3, prefer_additional: bool = True) -> list[str]:
        """Retrieve example agent responses to guide tone/style.

        Attempts vector retrieval, then filters for role==agent and matching stage.
        Falls back to recent agent messages if embeddings are unavailable.
        """
        if not query or not query.strip():
            return []
        # First, retrieve broadly without enforcing role at the vector stage to avoid empty results
        docs = self.retrieve(query, top_k=top_k * 20, prefer_agent=False, stage=stage)
        # Prefer samples originating from the Additional conversations dataset if requested
        if prefer_additional:
            preferred: list[dict[str, Any]] = []
            others: list[dict[str, Any]] = []
            for d in docs:
                src = (d.get("source_file") or "").lower()
                (preferred if "additional conversations" in src else others).append(d)
            docs = preferred + others
        examples: list[str] = []
        # Prefer exact stage match if provided
        for d in docs:
            if (d.get("role") or "").lower() != "agent":
                continue
            if stage and (d.get("stage") or "").lower() != (stage or "").lower():
                continue
            txt = d.get("clean_text") or d.get("text") or ""
            if txt:
                examples.append(txt)
            if len(examples) >= top_k:
                return examples[:top_k]
        # Relax stage constraint if not enough
        if len(examples) < top_k:
            for d in docs:
                if (d.get("role") or "").lower() != "agent":
                    continue
                txt = d.get("clean_text") or d.get("text") or ""
                if txt and txt not in examples:
                    examples.append(txt)
                if len(examples) >= top_k:
                    break
        # Fallback to recent agent messages
        if len(examples) < top_k:
            try:
                recent = list(
                    messages_collection().find(
                        {"clean_text": {"$exists": True, "$ne": ""}, "role": "agent"},
                        {"clean_text": 1, "text": 1, "stage": 1}
                    ).sort("timestamp", -1).limit(top_k * 4)
                )
                for r in recent:
                    if stage and (r.get("stage") or "").lower() != (stage or "").lower():
                        continue
                    txt = r.get("clean_text") or r.get("text") or ""
                    if txt:
                        examples.append(txt)
                    if len(examples) >= top_k:
                        break
            except Exception:
                pass
        return examples[:top_k]

    def retrieve_dialogue_examples(
        self,
        query: str,
        stage: Optional[str] = None,
        top_k: int = 3,
        prefer_additional: bool = True,
    ) -> list[dict[str, str]]:
        """Retrieve short lead→agent example pairs to steer style/content.

        Returns list of {"lead": str, "agent": str} pairs.
        """
        if not query or not query.strip():
            return []
        # Start with broader retrieval (no role filter), then pick agent docs and backtrack to previous lead turn
        docs = self.retrieve(query, top_k=top_k * 40, prefer_agent=False, stage=stage)
        pairs: list[dict[str, str]] = []
        seen: set[tuple[str, int]] = set()
        try:
            from ..db.mongo import messages_collection
            for d in docs:
                if (d.get("role") or "").lower() != "agent":
                    continue
                tid = d.get("thread_id")
                ti = d.get("turn_index")
                if tid is None or ti is None:
                    continue
                key = (str(tid), int(ti))
                if key in seen:
                    continue
                seen.add(key)
                # fetch prior lead message in same thread
                lead = messages_collection().find_one(
                    {"thread_id": tid, "turn_index": {"$lt": ti}, "role": "lead", "clean_text": {"$exists": True, "$ne": ""}},
                    sort=[("turn_index", -1)],
                    projection={"clean_text": 1},
                )
                if not lead:
                    continue
                lead_text = lead.get("clean_text") or lead.get("text") or ""
                agent_text = d.get("clean_text") or d.get("text") or ""
                if not lead_text or not agent_text:
                    continue
                # Prefer examples from Additional conversations first if requested
                if prefer_additional:
                    src = (d.get("source_file") or "").lower()
                    pref = "additional conversations" in src
                else:
                    pref = False
                pairs.append({"lead": lead_text, "agent": agent_text, "_pref": "1" if pref else "0"})
                if len(pairs) >= top_k * 3:
                    break
        except Exception:
            return []
        # Reorder to prefer preferred source, then truncate
        pairs.sort(key=lambda p: p.get("_pref", "0"), reverse=True)
        out = []
        for p in pairs:
            out.append({"lead": p["lead"], "agent": p["agent"]})
            if len(out) >= top_k:
                break
        return out


