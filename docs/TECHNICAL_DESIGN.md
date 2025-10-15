## Technical Design — Backend for AI Leasing Agent

### Goals & Requirements
- Ingest historical CSV conversations and convert to normalized threads/messages ready for RAG and fine-tuning.
- MongoDB Atlas as primary store; MongoDB Vector Search for embeddings.
- REST API for CRM/Zapier: start conversation, generate replies, suggest listings, schedule tours, maintain state.
- Two modes: RAG default; optional fine-tuned model for deterministic patterns.
- Full audit trail, human-in-the-loop, retraining pipeline.

### System Overview (High-Level Flow)
- Ingest CSV -> Clean/Segment -> Metadata Extract -> Embed -> Store (Mongo + vector index)
- Serve: Query -> Retrieve (vector search) -> Generate (LLM) -> Optional action via Zapier -> Log + Feedback

### Data Ingestion & Cleansing
- Endpoint (future): POST /api/training/ingest-csv or CLI job accepts CSV file/path.
- Validate columns: role, text/message, timestamp, optional thread_id.
- Segmentation: two empty rows separate threads; assign thread_id and turn_index.
- Normalization: trim, NFKC, newline unify, dedupe, punctuation normalization.
- Role mapping: map to agent/lead; infer if prefixed labels present.
- Timestamp: parse to ISO-8601 UTC; log if missing.
- PII: hash emails/phones; redact addresses; optional secure PII vault for re-id.
- Entity extraction: budget, move_date, areas, bedrooms, pets, preferences.
- Stage labeling: heuristics + lightweight classifier (qualifying, sending_list, selecting_favorites, touring, applying, approval, post_close, renewal).
- Outputs: raw_messages, messages, threads collections.

### Data Modeling (MongoDB)
- threads
```
{
  _id: ObjectId("..."),
  thread_id: "csv-0001",
  lead_profile: {
    name_hash: "sha256(...)",
    email_hash: "sha256(...)",
    phone_hash: "sha256(...)",
    budget: 1800,
    move_date: "2025-05-31",
    preferred_areas: ["Katy", "Cypress", "Memorial"]
  },
  labels: ["qualified", "touring"],
  message_count: 18,
  first_message_ts: "2025-01-21T13:00:00Z",
  last_message_ts: "2025-04-15T15:30:00Z",
  summary: "Remote worker, 2BR under $1800, move end of May",
  source_file: "conversations.csv"
}
```
- messages
```
{
  _id: ObjectId("..."),
  thread_id: "csv-0001",
  turn_index: 3,
  role: "agent",
  text: "Got it. I have your budget at 2 bedrooms under $1800...",
  clean_text: "...",
  timestamp: "2025-01-21T13:05:00Z",
  stage: "qualifying",
  entities: { budget: 1800 },
  embedding: [0.00123, -0.2334, ...],
  embedding_model: "openai-text-embedding-3-large",
  embedding_version: "v1",
  source: "csv",
  pii_hashes: { email: "sha256(...)" }
}
```
- Indexes
```
db.messages.createIndex({ thread_id: 1, turn_index: 1 })
db.messages.createIndex({ stage: 1, timestamp: -1 })
db.messages.createIndex({ role: 1 })
```
- Vector index (Atlas)
```
{
  "mappings": {
    "dynamic": true,
    "fields": {
      "embedding": {
        "type": "knnVector",
        "dimensions": 3072,
        "similarity": "cosine"
      }
    }
  }
}
```

### Embeddings Pipeline
- Model: OpenAI text-embedding-3-large (configurable).
- Chunking: per message; for long messages 256–512 tokens with 50-token overlap.
- Batching: 100–500 items per request depending on limits; retry/backoff.
- Storage: upsert embedding + model/version to messages; track runs in embedding_manifest.
- Versioning: increment embedding_version on model/strategy change.

### Retrieval / RAG Flow
- Create query embedding -> vector search topK (e.g., 10) -> filter/rank (recency, role, stage) -> prompt template -> LLM generate.
- Prompt template (system/user/instruction):
```
SYSTEM: You are a professional apartment leasing agent. Use the context below.
CONTEXT: <retrieved messages + thread summary>
USER: <user query>
INSTRUCTION: Provide a short friendly reply and the next step. If scheduling is requested, propose 3 time slots.
```
- Action extraction: detect schedule_tour/request_docs/mark_favorite/apply_now; enqueue Zapier webhook.

### Training & Fine-tuning Flow
- RAG-first default; optional supervised fine‑tune with JSONL prompt/completion pairs.
- Build examples from adjacent turn windows; include stage and entities for conditioning.
- Track dataset/model/prompt versions; evaluate before deploy.

### API Design (Endpoints)
- GET /api/healthz
- GET /api/leads/stages
- POST /api/leads/leads (upsert lead)
- POST /api/leads/threads (create thread)
- POST /api/training/ingest (normalized threads)
- POST /api/training/start (start embeddings/training job)
- Future conversation endpoints:
  - POST /api/agent/start
  - POST /api/agent/reply
  - POST /api/agent/action

### Zapier Integration
- Outbound: schedule tour, send SMS/email, create calendar event (via Composio tools).
- Inbound: new lead/message webhooks; verify with HMAC; idempotency keys.

### Deployment & Infra
- FastAPI + Uvicorn/Gunicorn; containerized; MongoDB Atlas (vector search enabled).
- Background workers (Celery/RQ) for ingestion, embedding, training; task queue (Redis).
- Config via env; secrets in env/secret manager.

### Security, Privacy & Compliance
- JWT auth for API; scopes per route; rate limiting.
- PII hashing; optional encrypted PII vault; audit logs for access and actions.
- Data retention policies; per-tenant separation if needed.

### Monitoring, Testing & Metrics
- Structured logs; tracing IDs; request/latency/error metrics.
- Track token usage, embedding costs, retrieval hit-rate, reply CSAT, action success.
- Unit/integration tests; red-team safety tests; synthetic convo tests.

### Operational Notes
- Retraining cadence: on demand or nightly; maintain versions for rollback.
- Cost controls: batch size, cache embeddings, topK tuning, prompt compression.

### Appendix
- Example prompt/completion JSONL (fine-tune):
```
{"prompt": "Lead: I need to move end of May...\nAgent:", "completion": "Got it! I have your move date..."}
```
- Example find similar query:
```
db.messages.aggregate([
  { $search: {
      knnBeta: {
        vector: <queryEmbedding>,
        path: "embedding",
        k: 10
      }
  }},
  { $project: { text: 1, stage: 1, score: { $meta: "searchScore" } } }
])
```
