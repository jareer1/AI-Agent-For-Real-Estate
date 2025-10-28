# AI Agent For Real Estate

A production-ready AI agent that replicates Ashanti's communication style for apartment hunting. The agent uses RAG (Retrieval-Augmented Generation) to learn from training conversations and generate natural, helpful responses.

## 🎯 Core Capability

The agent learns from real conversations (training data) to:
- Respond naturally in Ashanti's style
- Guide leads through their apartment search journey
- Adapt responses based on conversation stage
- Provide contextually relevant information

## 🏗️ Architecture

The system uses a clean 3-node graph architecture:

```
User Message → Classify Stage → Retrieve Context → Respond → Reply
                    ↓                  ↓               ↓
               (qualifying)    (RAG from training)  (LLM gen)
```

**See detailed documentation in:**
- [`docs/AGENT_ARCHITECTURE.md`](docs/AGENT_ARCHITECTURE.md) - Complete system architecture
- [`docs/AGENT_GRAPH_REFACTORING.md`](docs/AGENT_GRAPH_REFACTORING.md) - Refactoring details
- [`docs/REFACTORING_COMPARISON.md`](docs/REFACTORING_COMPARISON.md) - Before/after comparison

## 🚀 Getting Started

1. **Create and activate a virtual environment**
```bash
python -m venv .venv && .venv\Scripts\activate  # Windows
# or: python -m venv .venv && source .venv/bin/activate  # Mac/Linux
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your API keys (OpenAI, MongoDB, etc.)
```

4. **Run the API**
```bash
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/api/healthz`

## 📁 Project Structure

```text
app/
  core/                 # Configuration and logging
  routes/               # FastAPI routers (health, leads, agent, training)
  schemas/              # Pydantic models (lead, message, thread, stage)
  services/
    agent_graph.py           # ⭐ Main agent graph (3-node pipeline)
    agent_orchestrator.py    # ⭐ High-level orchestration
    rag.py                   # ⭐ RAG retrieval from training data
    prompts.py               # System prompts and instructions
    llm.py                   # LLM service
    embeddings.py            # Embedding generation
  pipelines/            # Data ingestion and training pipelines
  db/                   # Database connections (MongoDB)
docs/                   # 📚 Comprehensive documentation
  AGENT_ARCHITECTURE.md       # System architecture and flow
  AGENT_GRAPH_REFACTORING.md  # Refactoring details
  REFACTORING_COMPARISON.md   # Before/after comparison
integrations/
  composio_client.py    # Composio integration (optional)
tests/
requirements.txt
.env.example
```

## ✨ Key Features

### 1. **RAG-Based Learning**
- Retrieves relevant examples from training data
- Uses vector similarity search (MongoDB Atlas)
- Ranks by thread, stage, role, and recency

### 2. **Stage-Aware Responses**
- 7 conversation stages: qualifying → working → touring → applied → approved → closed → post-close
- Stage-specific guidance and behavior
- Automatic stage detection from keywords

### 3. **Context-Aware**
- Extracts known information (budget, move date, preferences)
- Avoids redundant questions
- Maintains conversation continuity

### 4. **Clean Architecture**
- Simple 3-node graph pipeline
- Focused, testable methods
- Comprehensive documentation
- Production-ready error handling

### 5. **Action Detection**
- Identifies when to schedule tours
- Detects application support needs
- Escalates pricing questions when uncertain

## 🔌 API Endpoints

### Health & Status
- `GET /api/healthz` – Health check

### Leads Management
- `GET /api/leads/stages` – List conversation stages
- `POST /api/leads/leads` – Create/update lead
- `POST /api/leads/threads` – Create conversation thread

### Agent Interaction
- `POST /api/agent/message` – Send message and get response

### Training Pipeline
- `POST /api/training/ingest` – Ingest training conversations
- `POST /api/training/start` – Start training job (embeddings generation)

## 🧪 Testing

### Unit Tests
```bash
# Test individual components
pytest tests/test_agent_graph.py -v
pytest tests/test_rag.py -v
```

### Evaluate with Gold Data

Evaluate responses against training conversations using the built-in evaluation toolkit:

```bash
python -m tools.eval_conversations.cli \
  "AI Agent Training (Messages) - Additional conversations.csv" \
  "https://your-api-endpoint" \
  .reports/evaluation.jsonl \
  --limit 200 \
  --summary
```

**Scoring metrics:**
- Token similarity (cosine-like)
- ROUGE-L score
- Action type match
- Entity overlap
- Style consistency checks

## 📊 Code Quality

### Refactoring Highlights
The codebase has been refactored for production readiness:

- ✅ **Reduced complexity**: 84% reduction in cyclomatic complexity
- ✅ **Better organization**: 200+ line method → 10 focused methods
- ✅ **Comprehensive docs**: Docstrings for all classes/methods
- ✅ **Clean separation**: Each method has single responsibility
- ✅ **Production-ready**: Proper error handling and logging

### Metrics
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Largest method | 210 lines | 75 lines | 64% ↓ |
| Cyclomatic complexity | 25+ | 4 | 84% ↓ |
| Documentation | Minimal | Comprehensive | ✅ |
| Testability | Hard | Easy | ✅ |

See [`docs/REFACTORING_COMPARISON.md`](docs/REFACTORING_COMPARISON.md) for details.

## 🔧 Configuration

### Environment Variables

Create a `.env` file with:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# MongoDB Atlas (for vector search)
MONGODB_URI=mongodb+srv://...
MONGODB_DB_NAME=real_estate_agent

# Agent Configuration
AGENT_MODE=default  # Options: default, react (default recommended)

# Logging
LOG_LEVEL=INFO
```

### RAG Settings

Configured in `app/services/rag.py`:

```python
# Retrieval tuning
candidate_k = 60        # Candidates per search
boost_thread = 0.20     # Same thread boost
boost_stage = 0.08      # Same stage boost
boost_agent_role = 0.05 # Agent message boost
```

### LLM Settings

Configured in `app/services/agent_graph.py`:

```python
ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.5,      # Balanced creativity
    top_p=0.8,           # Focus on likely tokens
    frequency_penalty=0.3,
    presence_penalty=0.5,
)
```

## 📚 Documentation

Comprehensive documentation is available in the `docs/` directory:

1. **[AGENT_ARCHITECTURE.md](docs/AGENT_ARCHITECTURE.md)** - Complete system architecture
   - High-level overview
   - Detailed flow diagrams
   - Component descriptions
   - Configuration guide

2. **[AGENT_GRAPH_REFACTORING.md](docs/AGENT_GRAPH_REFACTORING.md)** - Refactoring summary
   - Objectives and key changes
   - Architecture details
   - Benefits and testing recommendations

3. **[REFACTORING_COMPARISON.md](docs/REFACTORING_COMPARISON.md)** - Before/after comparison
   - Code organization comparison
   - Complexity metrics
   - Readability improvements
   - Maintenance scenarios

## 🚧 Development

### Adding a New Stage

1. Add stage to `StageV2` enum in `app/schemas/common.py`
2. Update `_get_stage_guidance()` in `app/services/agent_graph.py`
3. Update `map_text_to_stage_v2()` with stage keywords
4. Test with sample conversations

### Modifying Context Extraction

Edit `_extract_lead_context()` in `app/services/agent_graph.py`:

```python
def _extract_lead_context(self, context: str, chat_history: list) -> str:
    # Add new extraction logic here
    if "new_keyword" in lower:
        known["new_field"] = "value"
```

### Adjusting Retrieval

Modify RAG weights in `app/services/rag.py`:

```python
self.boost_thread = 0.20     # Increase for more thread-specific results
self.boost_stage = 0.08      # Increase for more stage-specific results
self.boost_agent_role = 0.05 # Increase for more agent examples
```

## 🤝 Contributing

Contributions are welcome! Please:

1. Read the architecture documentation
2. Follow the existing code style
3. Add tests for new features
4. Update documentation as needed

## 📄 License

[Add your license here]

## 🙏 Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [LangGraph](https://python.langchain.com/docs/langgraph) - Agent orchestration
- [LangChain](https://python.langchain.com/) - LLM integration
- [MongoDB Atlas](https://www.mongodb.com/atlas) - Vector search
- [OpenAI](https://openai.com/) - LLM and embeddings

