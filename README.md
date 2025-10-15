# AI Agent For Real Estate

Minimal FastAPI scaffold to build a real-estate conversation agent with training stubs.

## Getting Started

1. Create and activate a virtual environment
```bash
python -m venv .venv && .venv\\Scripts\\activate
```
2. Install dependencies
```bash
pip install -r requirements.txt
```
3. Run the API
```bash
uvicorn app.main:app --reload
```

Health check: `GET /api/healthz`

## Project Structure

```text
app/
  core/                 # config and logging
  routes/               # FastAPI routers (health, leads, training)
  schemas/              # pydantic models (lead, message, thread, stage)
  services/             # agent orchestrator skeleton
  pipelines/            # dataset builder and trainer stubs
integrations/
  composio_client.py    # placeholder for Composio integration
tests/
requirements.txt
.env.example
```

## High-level API

- `GET /api/healthz` – health check
- `GET /api/leads/stages` – list lifecycle stages
- `POST /api/leads/leads` – upsert a lead (placeholder)
- `POST /api/leads/threads` – create a thread (placeholder)
- `POST /api/training/ingest` – ingest message threads for training
- `POST /api/training/start` – start a training job (stub)

## Notes

- Integrate tool calling via Composio in `integrations/composio_client.py`
- Extend dataset transformation in `app/pipelines/dataset_builder.py`
- Replace `Trainer` with your fine-tuning or RAG pipeline

