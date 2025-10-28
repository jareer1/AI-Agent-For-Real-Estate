# Quick Start Guide - AI Agent for Real Estate

## What This Agent Does

Replicates **Ashanti's communication style** for apartment hunting conversations using:
- **RAG (Retrieval-Augmented Generation)**: Learns from training data
- **Stage-aware responses**: Adapts to conversation progress
- **Context tracking**: Remembers what leads have told us

## 5-Minute Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
OPENAI_API_KEY=sk-your-key-here
MONGODB_URI=mongodb+srv://your-connection-string
MONGODB_DB_NAME=real_estate_agent
AGENT_MODE=default
LOG_LEVEL=INFO
```

### 3. Ingest Training Data

```bash
# Start the API
uvicorn app.main:app --reload

# Ingest conversations (in another terminal)
curl -X POST http://localhost:8000/api/training/ingest \
  -H "Content-Type: application/json" \
  -d '{"csv_path": "AI Agent Training (Messages) - Full conversations.csv"}'
```

### 4. Test the Agent

```bash
# Send a test message
curl -X POST http://localhost:8000/api/agent/message \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "test_123",
    "user_message": "Looking for a 2BR in Heights, budget $1500"
  }'
```

Expected response:
```json
{
  "reply": "Perfect! Heights has great options in that range. What's your move timeline?",
  "stage": "qualifying",
  "suggested_action": null
}
```

## How It Works (Simple View)

```
1. User sends message: "Looking for 2BR in Heights"
                 ↓
2. Agent classifies stage: "qualifying"
                 ↓
3. RAG retrieves similar conversations from training data
                 ↓
4. Agent generates response in Ashanti's style
                 ↓
5. Response: "Perfect! What's your move timeline?"
```

## Architecture (One Page)

### Three-Node Graph

```
┌──────────────────┐
│ Classify Stage   │  Determines conversation stage
│                  │  (qualifying, working, touring, etc.)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Retrieve Context │  Fetches relevant examples from
│                  │  training data using vector search
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Respond          │  Generates reply in Ashanti's style
│                  │  using LLM + retrieved context
└──────────────────┘
```

### Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `app/services/agent_graph.py` | Main agent logic | ~495 |
| `app/services/agent_orchestrator.py` | API bridge | ~94 |
| `app/services/rag.py` | RAG retrieval | ~418 |
| `app/services/prompts.py` | System prompts | ~116 |

### 7 Conversation Stages

1. **Qualifying** - Gather requirements (budget, timing, beds, location)
2. **Working** - Share options, get favorites
3. **Touring** - Schedule and follow up on tours
4. **Applied** - Support application process
5. **Approved** - Celebrate, get lease details
6. **Closed** - Wrap up (won or lost)
7. **Post-Close** - Nurture, referrals, renewals

## Key Methods (Developer Reference)

### `agent_graph.py`

```python
# Main nodes
_classify_stage()  # Keyword-based stage detection
_retrieve()        # RAG from training data (top 8 docs)
_respond()         # Generate reply using LLM

# Helper methods
_build_prompt_messages()       # Assemble full prompt
_get_stage_guidance()          # Stage-specific instructions
_extract_lead_context()        # Known vs missing info
_get_dialogue_examples()       # Few-shot examples
_generate_response()           # LLM invocation
_extract_message_from_json()   # Parse JSON output
_detect_suggested_action()     # Identify actions
```

### `rag.py`

```python
retrieve()                    # Main retrieval method
_vector_search()              # MongoDB Atlas search
_rerank_and_trim()           # Apply boosts and trim
retrieve_agent_examples()     # Style examples
retrieve_dialogue_examples()  # Few-shot pairs
```

## Common Tasks

### Add a New Stage

1. **Update enum** (`app/schemas/common.py`):
```python
class StageV2(str, Enum):
    # ... existing stages
    new_stage = "new_stage"
```

2. **Add guidance** (`app/services/agent_graph.py`):
```python
def _get_stage_guidance(self, stage: StageV2) -> str:
    stage_guidance = {
        # ... existing stages
        StageV2.new_stage: (
            "NEW STAGE:\n"
            "Instructions for this stage..."
        ),
    }
```

3. **Update keywords** (`app/schemas/common.py`):
```python
def map_text_to_stage_v2(text: str, current: StageV2 | None = None) -> StageV2:
    lower = (text or "").lower()
    if any(k in lower for k in ["keyword1", "keyword2"]):
        return StageV2.new_stage
```

### Modify Context Extraction

Edit `_extract_lead_context()` in `agent_graph.py`:

```python
# Add new field extraction
if any(keyword in lower for keyword in ["parking", "garage"]):
    known["parking"] = "mentioned"
```

### Adjust RAG Weights

Edit `rag.py`:

```python
self.boost_thread = 0.30     # ↑ More thread-specific results
self.boost_stage = 0.15      # ↑ More stage-specific results
self.boost_agent_role = 0.10 # ↑ More agent examples
```

### Change LLM Settings

Edit `agent_graph.py`:

```python
self.llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,      # ↑ More creative
    # or
    temperature=0.3,      # ↓ More consistent
)
```

## Debugging

### Check Retrieval Quality

Look at logs:
```
INFO:app.services.rag:Retrieved 8 docs, context length: 1247
DEBUG:app.services.rag:Top docs: [
  {'role': 'agent', 'stage': 'qualifying', 'score': 0.891},
  {'role': 'agent', 'stage': 'qualifying', 'score': 0.867},
  ...
]
```

### Check Stage Classification

```python
from app.schemas.common import map_text_to_stage_v2

stage = map_text_to_stage_v2("Looking for 2BR")
print(stage)  # Should be: qualifying
```

### Test Individual Methods

```python
from app.services.agent_graph import AgentGraph

graph = AgentGraph()

# Test context extraction
context = "Budget is $1500, looking for 2 bed in Heights"
summary = graph._extract_lead_context(context, [])
print(summary)

# Test action detection
reply = "Let's schedule a tour for Friday"
action = graph._detect_suggested_action(reply, StageV2.touring)
print(action)  # {'action': 'schedule_tour'}
```

## Performance Tips

### 1. Cache Embeddings
Training data embeddings are cached in MongoDB. Don't regenerate unless data changes.

### 2. Limit RAG Results
Current: `top_k=8`. Increase for more context, decrease for faster responses.

### 3. Optimize Prompt Length
Current: Last 12 messages + 2 few-shot examples. Adjust if hitting token limits.

### 4. Monitor LLM Costs
Track token usage:
```python
# In _generate_response()
print(f"Tokens used: {resp.usage}")  # If using OpenAI SDK
```

## Testing Checklist

- [ ] Agent classifies stages correctly
- [ ] RAG retrieves relevant examples
- [ ] Responses match Ashanti's style
- [ ] Context extraction works (no redundant questions)
- [ ] Action detection works (tours, applications, pricing)
- [ ] Handles acknowledgments properly ("okay", "thanks")
- [ ] Maintains conversation continuity
- [ ] Error handling works (no crashes)

## Resources

- **Full Architecture**: [`docs/AGENT_ARCHITECTURE.md`](AGENT_ARCHITECTURE.md)
- **Refactoring Details**: [`docs/AGENT_GRAPH_REFACTORING.md`](AGENT_GRAPH_REFACTORING.md)
- **Code Comparison**: [`docs/REFACTORING_COMPARISON.md`](REFACTORING_COMPARISON.md)
- **API Documentation**: README.md

## Support

For issues or questions:
1. Check the documentation (this guide + architecture docs)
2. Review logs for error messages
3. Test individual components (see Debugging section)
4. Check MongoDB connection and data

## Summary

✅ **Clean architecture**: 3-node graph, focused methods
✅ **Production-ready**: Error handling, logging, documentation
✅ **Easy to extend**: Add stages, modify extraction, adjust retrieval
✅ **Well-tested**: Unit testable, integration testable
✅ **Maintainable**: Comprehensive docs, clear code structure

**Goal achieved**: Replicate Ashanti's style using RAG from training data. 🎯

