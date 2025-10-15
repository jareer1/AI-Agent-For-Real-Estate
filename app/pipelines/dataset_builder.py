from typing import Any
from ..schemas.common import Thread, StageV2, Role
from ..db.mongo import messages_collection, threads_collection


class DatasetBuilder:
    def __init__(self) -> None:
        pass

    def build_supervised_dataset(self, threads: list[Thread]) -> dict:
        """Transform message threads into training samples for fine-tuning"""
        training_samples = []
        
        for thread in threads:
            # Get all messages for this thread ordered by turn_index
            messages = list(messages_collection().find(
                {"thread_id": thread.id}
            ).sort("turn_index", 1))
            
            # Create conversation windows for training
            for i in range(len(messages) - 1):
                current_msg = messages[i]
                next_msg = messages[i + 1]
                
                # Only train on agent responses to lead messages
                if (current_msg["role"] == Role.lead.value and 
                    next_msg["role"] == Role.agent.value):
                    
                    # Build context from previous messages
                    context_messages = messages[:i+1]
                    context = self._build_context(context_messages)
                    
                    training_sample = {
                        "prompt": f"Context: {context}\nLead: {current_msg['clean_text']}\nAgent:",
                        "completion": next_msg['clean_text'],
                        "stage": current_msg.get("stage", "qualifying"),
                        "entities": current_msg.get("entities", {})
                    }
                    training_samples.append(training_sample)
        
        return {
            "samples": len(training_samples),
            "training_data": training_samples
        }
    
    def _build_context(self, messages: list[dict[str, Any]], max_context: int = 3) -> str:
        """Build conversation context from recent messages"""
        recent_messages = messages[-max_context:] if len(messages) > max_context else messages
        
        context_parts = []
        for msg in recent_messages:
            role = "Lead" if msg["role"] == Role.lead.value else "Agent"
            context_parts.append(f"{role}: {msg['clean_text']}")
        
        return " | ".join(context_parts)
    
    def build_rag_training_data(self) -> dict:
        """Build data for RAG system training and evaluation"""
        # Get sample conversations for RAG testing
        threads = list(threads_collection().find().limit(100))
        
        rag_samples = []
        for thread in threads:
            thread_id = thread["thread_id"]
            messages = list(messages_collection().find(
                {"thread_id": thread_id}
            ).sort("turn_index", 1))
            
            # Create query-response pairs for RAG evaluation
            for i, msg in enumerate(messages):
                if msg["role"] == Role.lead.value and i > 0:
                    # Use previous context as query, current message as expected response context
                    context_messages = messages[:i]
                    query = msg["clean_text"]
                    
                    rag_sample = {
                        "query": query,
                        "expected_context": self._build_context(context_messages),
                        "thread_id": thread_id,
                        "stage": msg.get("stage", "qualifying")
                    }
                    rag_samples.append(rag_sample)
        
        return {
            "rag_samples": len(rag_samples),
            "rag_training_data": rag_samples
        }


