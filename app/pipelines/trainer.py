import json
from typing import Any, Dict, List
from openai import OpenAI
from ..core.config import get_settings
from ..services.embeddings import EmbeddingsService
from .dataset_builder import DatasetBuilder


class Trainer:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.embeddings_service = EmbeddingsService()
        self.dataset_builder = DatasetBuilder()

    def train_rag_system(self) -> dict:
        """Train the RAG system by ensuring all messages have embeddings"""
        from ..db.mongo import messages_collection
        
        # Get messages without embeddings
        messages_to_embed = list(messages_collection().find(
            {"embedding": None}, 
            {"_id": 1, "clean_text": 1}
        ).limit(1000))
        
        if not messages_to_embed:
            return {"status": "completed", "message": "All messages already have embeddings"}
        
        # Generate embeddings - filter out empty texts
        pairs = [(doc["_id"], doc.get("clean_text") or "") for doc in messages_to_embed if doc.get("clean_text") and doc.get("clean_text").strip()]
        embedded_count = self.embeddings_service.embed_and_update_messages(pairs, version="v1")
        
        return {
            "status": "completed", 
            "embedded_messages": embedded_count,
            "total_messages": len(messages_to_embed)
        }

    def train_fine_tuned_model(self, training_data: List[Dict[str, Any]]) -> dict:
        """Create a fine-tuned model from conversation data"""
        if not self.client:
            return {"status": "error", "message": "OpenAI client not configured"}
        
        # Prepare training data in OpenAI format
        jsonl_data = []
        for sample in training_data:
            jsonl_data.append({
                "prompt": sample["prompt"],
                "completion": sample["completion"]
            })
        
        # Convert to JSONL string
        jsonl_string = "\n".join([json.dumps(item) for item in jsonl_data])
        
        # Save training file
        training_file_name = f"training_data_{len(training_data)}_samples.jsonl"
        with open(training_file_name, "w") as f:
            f.write(jsonl_string)
        
        try:
            # Upload file to OpenAI
            with open(training_file_name, "rb") as f:
                file_response = self.client.files.create(
                    file=f,
                    purpose="fine-tune"
                )
            
            # Start fine-tuning job
            fine_tune_response = self.client.fine_tuning.jobs.create(
                training_file=file_response.id,
                model="gpt-3.5-turbo",
                hyperparameters={
                    "n_epochs": 3,
                    "batch_size": 1,
                    "learning_rate_multiplier": 0.1
                }
            )
            
            return {
                "status": "started",
                "fine_tune_job_id": fine_tune_response.id,
                "training_file_id": file_response.id,
                "samples_trained": len(training_data)
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def train(self, dataset: dict = None, mode: str = "rag") -> dict:
        """Main training method - supports both RAG and fine-tuning modes"""
        
        if mode == "rag":
            return self.train_rag_system()
        
        elif mode == "fine_tune":
            # Build training dataset from existing conversations
            from ..db.mongo import threads_collection
            threads = list(threads_collection().find().limit(100))
            
            # Convert to Thread objects for dataset builder
            from ..schemas.common import Thread, Lead, Stage
            thread_objects = []
            for thread_data in threads:
                # Create minimal Thread object for dataset building
                thread_obj = Thread(
                    id=thread_data["thread_id"],
                    lead=Lead(
                        id=thread_data["thread_id"],
                        full_name="Unknown",
                        phone="",
                        email="unknown@example.com"
                    ),
                    stage=Stage.first_contact,
                    events=[]
                )
                thread_objects.append(thread_obj)
            
            # Build supervised dataset
            dataset_result = self.dataset_builder.build_supervised_dataset(thread_objects)
            
            if dataset_result["samples"] == 0:
                return {"status": "error", "message": "No training samples found"}
            
            # Train fine-tuned model
            return self.train_fine_tuned_model(dataset_result["training_data"])
        
        else:
            return {"status": "error", "message": f"Unknown training mode: {mode}"}

    def evaluate_model(self, mode: str = "rag") -> dict:
        """Evaluate the trained model performance"""
        if mode == "rag":
            # Build RAG evaluation dataset
            rag_data = self.dataset_builder.build_rag_training_data()
            
            # Simple evaluation - check if we can retrieve relevant context
            from ..services.rag import RAGService
            rag_service = RAGService()
            
            correct_retrievals = 0
            total_queries = 0
            
            for sample in rag_data["rag_training_data"][:10]:  # Test on first 10 samples
                query = sample["query"]
                expected_context = sample["expected_context"]
                
                # Retrieve similar messages
                retrieved = rag_service.retrieve(query, top_k=3)
                
                # Simple check if expected context is in retrieved results
                retrieved_texts = [r.get("clean_text", "") for r in retrieved]
                if any(expected_context in text for text in retrieved_texts):
                    correct_retrievals += 1
                
                total_queries += 1
            
            accuracy = correct_retrievals / total_queries if total_queries > 0 else 0
            
            return {
                "mode": "rag",
                "accuracy": accuracy,
                "correct_retrievals": correct_retrievals,
                "total_queries": total_queries,
                "evaluation_samples": len(rag_data["rag_training_data"])
            }
        
        return {"status": "error", "message": f"Evaluation not implemented for mode: {mode}"}


