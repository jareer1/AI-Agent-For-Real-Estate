from fastapi import APIRouter, Depends, File, UploadFile

from ..schemas.common import Thread
from ..core.security import require_api_key
from ..services.ingestion import ingest_csv
from ..services.embeddings import EmbeddingsService
from ..db.mongo import messages_collection

training_router = APIRouter(prefix="/training", tags=["training"], dependencies=[Depends(require_api_key)])


@training_router.post("/ingest")
def ingest_threads(threads: list[Thread]) -> dict:
    # Placeholder: accept dataset
    return {"received": len(threads)}


@training_router.post("/start")
def start_training_job(mode: str = "rag") -> dict:
    """Start training job - supports 'rag' and 'fine_tune' modes"""
    from ..pipelines.trainer import Trainer
    
    trainer = Trainer()
    result = trainer.train(mode=mode)
    return result


@training_router.post("/train-rag")
def train_rag_system() -> dict:
    """Train RAG system by generating embeddings for all messages"""
    from ..pipelines.trainer import Trainer
    
    trainer = Trainer()
    result = trainer.train_rag_system()
    return result


@training_router.post("/train-fine-tune")
def train_fine_tuned_model() -> dict:
    """Train a fine-tuned model from conversation data"""
    from ..pipelines.trainer import Trainer
    
    trainer = Trainer()
    result = trainer.train(mode="fine_tune")
    return result


@training_router.get("/evaluate")
def evaluate_model(mode: str = "rag") -> dict:
    """Evaluate trained model performance"""
    from ..pipelines.trainer import Trainer
    
    trainer = Trainer()
    result = trainer.evaluate_model(mode=mode)
    return result


@training_router.get("/dataset-stats")
def get_dataset_stats() -> dict:
    """Get statistics about the training dataset"""
    from ..db.mongo import messages_collection, threads_collection
    from ..pipelines.dataset_builder import DatasetBuilder
    
    # Basic stats
    total_messages = messages_collection().count_documents({})
    total_threads = threads_collection().count_documents({})
    # Count messages that have embeddings (MongoDB queries aren't working properly, so count manually)
    embedded_messages = 0
    for doc in messages_collection().find({}, {"embedding": 1}):
        embedding = doc.get("embedding")
        if embedding and isinstance(embedding, list) and len(embedding) > 0:
            embedded_messages += 1
    
    # Role distribution
    agent_messages = messages_collection().count_documents({"role": "agent"})
    lead_messages = messages_collection().count_documents({"role": "lead"})
    
    # Stage distribution
    stage_pipeline = [
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    stage_distribution = list(messages_collection().aggregate(stage_pipeline))
    
    return {
        "total_messages": total_messages,
        "total_threads": total_threads,
        "embedded_messages": embedded_messages,
        "embedding_coverage": embedded_messages / total_messages if total_messages > 0 else 0,
        "role_distribution": {
            "agent": agent_messages,
            "lead": lead_messages
        },
        "stage_distribution": stage_distribution
    }


@training_router.post("/ingest-csv")
async def ingest_csv_endpoint(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    result = ingest_csv(content, source_file=file.filename)
    # Trigger embeddings for newly inserted messages lacking vectors
    to_embed = list(messages_collection().find({"embedding": None}, {"_id": 1, "clean_text": 1}).limit(1000))
    # Filter out empty or None texts - OpenAI API doesn't accept empty strings
    pairs = [(doc["_id"], doc.get("clean_text") or "") for doc in to_embed if doc.get("clean_text") and doc.get("clean_text").strip()]
    if pairs:
        EmbeddingsService().embed_and_update_messages(pairs, version="v1")
    return {**result, "embedded": len(pairs)}


