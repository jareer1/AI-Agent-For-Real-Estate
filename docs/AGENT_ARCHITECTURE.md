# AI Agent Architecture - Clean and Maintainable

## System Overview

The AI agent is designed to replicate Ashanti's communication style by retrieving relevant examples from training data and using them to guide response generation.

## Core Principle

> **The agent learns from examples, not rules.**
> 
> Instead of hardcoding responses, we retrieve similar past conversations from the training data and use them to guide the LLM in generating responses that match Ashanti's natural communication style.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                       │
│                  app/routes/agent.py                          │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Agent Orchestrator                               │
│           app/services/agent_orchestrator.py                  │
│                                                               │
│  • State normalization (API format ↔ Graph format)           │
│  • Response formatting                                        │
│  • Error handling                                             │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   Agent Graph                                 │
│              app/services/agent_graph.py                      │
│                                                               │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐          │
│  │  Classify  │ → │  Retrieve  │ → │  Respond   │          │
│  │   Stage    │   │  Context   │   │            │          │
│  └────────────┘   └────────────┘   └────────────┘          │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   RAG Service                                 │
│               app/services/rag.py                             │
│                                                               │
│  • Vector search in training data                            │
│  • Context ranking and filtering                             │
│  • Example retrieval                                          │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              Training Data (MongoDB)                          │
│     AI Agent Training (Messages) - Full conversations.csv    │
│                                                               │
│  • Embedded conversations                                    │
│  • Agent and lead messages                                   │
│  • Stage labels                                              │
│  • Thread IDs                                                │
└──────────────────────────────────────────────────────────────┘
```

## Detailed Flow

### 1. Conversation Turn Flow

```
┌─────────────────┐
│  Lead Message   │
│  "Looking for   │
│   a 2BR in      │
│   Heights"      │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 1: CLASSIFY STAGE                                  │
├─────────────────────────────────────────────────────────┤
│ Keywords: "looking", "2BR", "Heights"                   │
│ → Stage: QUALIFYING (gathering requirements)            │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 2: RETRIEVE CONTEXT                                │
├─────────────────────────────────────────────────────────┤
│ Vector search in training data:                         │
│ • Query: "looking for a 2BR in Heights"                 │
│ • Stage filter: qualifying                              │
│ • Prefer: agent messages                                │
│                                                          │
│ Retrieved examples (top 8):                             │
│ 1. "Got it! What's your move timeline?"                 │
│ 2. "Perfect. What's your budget range?"                 │
│ 3. "Heights is great! When do you need to move?"        │
│ 4. "2-bed, got it. Do you have parking/pet needs?"      │
│ ... (4 more examples)                                   │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 3: RESPOND                                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ 3a. Build Prompt:                                       │
│   ┌──────────────────────────────────────────────┐    │
│   │ • Base system prompt (Ashanti's identity)    │    │
│   │ • Stage guidance (qualifying instructions)   │    │
│   │ • Lead context summary (known: location,     │    │
│   │   bedrooms; missing: budget, move timing)    │    │
│   │ • Retrieved examples (8 similar responses)   │    │
│   │ • Few-shot examples (2 lead→agent pairs)     │    │
│   │ • Chat history (last 12 messages)            │    │
│   │ • Current message                             │    │
│   └──────────────────────────────────────────────┘    │
│                                                          │
│ 3b. Generate Response:                                  │
│   ┌──────────────────────────────────────────────┐    │
│   │ LLM (GPT-4o-mini) processes prompt          │    │
│   │ → "Perfect! Heights has great options.       │    │
│   │    What's your move timeline?"               │    │
│   └──────────────────────────────────────────────┘    │
│                                                          │
│ 3c. Detect Actions:                                     │
│   ┌──────────────────────────────────────────────┐    │
│   │ No action needed (still qualifying)          │    │
│   └──────────────────────────────────────────────┘    │
│                                                          │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Agent Reply    │
│  "Perfect!      │
│   Heights has   │
│   great options.│
│   What's your   │
│   move timeline?"│
└─────────────────┘
```

## Component Details

### Agent Graph (`agent_graph.py`)

The main orchestrator of the conversation flow.

#### **Node 1: Classify Stage**
```python
def _classify_stage(self, state: GraphState) -> GraphState:
    """Determine conversation stage from keywords."""
    # Keywords → Stage mapping:
    # "tour", "showing" → touring
    # "apply", "application" → applied
    # "approved", "approval" → approved
    # "budget", "move", "bed" → qualifying
    # etc.
```

**Purpose**: Know where the lead is in their journey to provide appropriate guidance.

**Output**: One of 7 stages:
1. `qualifying` - Gathering requirements
2. `working` - Sharing options, getting favorites
3. `touring` - Scheduling/following up on tours
4. `applied` - Application in progress
5. `approved` - Approved, getting lease details
6. `closed` - Lease signed or lost
7. `post_close_nurture` - Post-move check-ins

---

#### **Node 2: Retrieve Context**
```python
def _retrieve(self, state: GraphState) -> GraphState:
    """Fetch relevant examples from training data."""
    # RAG retrieval from training data:
    # • Vector similarity search
    # • Filter by stage, thread, role
    # • Rank by relevance + recency + thread match
    # • Return top 8 documents
```

**Purpose**: Get examples of how Ashanti responds in similar situations.

**Retrieval Strategy**:
- **Primary**: Vector similarity (semantic matching)
- **Boost**: Same thread (+0.20 score)
- **Boost**: Same stage (+0.08 score)
- **Boost**: Agent role (+0.05 score)
- **Boost**: Recent messages (+0.01 × recency)

**Output**: 8 text snippets like:
```
"Got it! What's your move timeline?"
"Perfect. What's your budget range?"
"Heights is great! When do you need to move?"
...
```

---

#### **Node 3: Respond**
```python
def _respond(self, state: GraphState) -> GraphState:
    """Generate response in Ashanti's style."""
    # 1. Build prompt with all context
    # 2. Generate response via LLM
    # 3. Detect suggested actions
```

**Purpose**: Create a natural, Ashanti-style response using all available context.

**Process**:
1. **Prompt Building** (`_build_prompt_messages`)
   - System prompt with Ashanti's identity
   - Stage-specific instructions
   - Lead context summary
   - Retrieved examples
   - Few-shot dialogue pairs
   - Recent chat history

2. **Response Generation** (`_generate_response`)
   - Invoke LLM with full context
   - Extract message from JSON if needed
   - Handle errors gracefully

3. **Action Detection** (`_detect_suggested_action`)
   - Look for tour scheduling keywords
   - Look for application keywords
   - Look for pricing escalation phrases

**Output**: 
- `reply`: Natural response text
- `suggested_action`: Optional action hint

---

### Helper Methods

#### `_get_stage_guidance(stage)`
Returns clear instructions for each stage:

```
QUALIFYING STAGE:
Focus on gathering essential info conversationally: move timeline, 
budget, bedrooms, preferred areas.
Ask ONE question at a time. Don't ask for info already in context.
Keep it natural and warm, like a helpful friend.
```

#### `_extract_lead_context(context, history)`
Analyzes context to identify:
- **Known**: Budget, move timing, bedrooms, areas, properties
- **Missing**: What to ask next

Generates summary:
```
LEAD CONTEXT SUMMARY:
Known: budget, bedrooms, areas
Still need: move_timing
→ Don't re-ask known info. Move the conversation forward.
```

#### `_get_dialogue_examples(utterance, stage)`
Retrieves 1-2 lead→agent pairs for few-shot learning:

```
User: "Looking for 2BR in Heights"
Assistant: "Perfect! What's your move timeline?"

User: "End of June"
Assistant: "Got it! What's your budget range?"
```

#### `_detect_suggested_action(reply, stage)`
Identifies actions from keywords:

| Keywords | Stage | Action |
|----------|-------|--------|
| "schedule", "tour", "showing" | touring/working | `schedule_tour` |
| "apply", "application" | working/applied | `request_application` |
| "I'll check" + "price" | any | `escalate_pricing` |

---

### RAG Service (`rag.py`)

Handles all retrieval from training data.

#### **Method: `retrieve()`**

```python
def retrieve(
    query: str,
    top_k: int = 10,
    thread_id: Optional[str] = None,
    stage: Optional[str] = None,
    prefer_agent: bool = False,
    chat_history: Optional[list] = None,
) -> list[dict]:
```

**Process**:
1. **Enrich Query**: Add stage context + recent history
2. **Generate Embedding**: Convert to vector using OpenAI embeddings
3. **Vector Search**: MongoDB Atlas vector search
   - Search in same thread (candidate_k=60)
   - Search globally (candidate_k=60)
4. **Re-rank**: Apply boosts for thread, stage, role, recency
5. **Return**: Top K most relevant documents

**Example**:
```python
query = "Looking for 2BR in Heights"
stage = "qualifying"
thread_id = "thread_123"

# Enriched query:
# "[stage:qualifying] user: Looking for 2BR in Heights"

# Retrieved docs:
[
  {
    "text": "Perfect! What's your move timeline?",
    "role": "agent",
    "stage": "qualifying",
    "score": 0.89,
    "thread_id": "thread_456"
  },
  # ... 7 more
]
```

---

### Agent Orchestrator (`agent_orchestrator.py`)

Simple bridge between API and graph.

```python
class AgentOrchestrator:
    def run_turn(self, state: AgentState, user_utterance: str) -> AgentState:
        # 1. Normalize state format
        # 2. Run graph
        # 3. Format output
        # 4. Return response
```

**Responsibilities**:
- State format conversion (API ↔ Graph)
- Stage normalization (enum → string)
- Error boundary

---

## Data Flow Diagram

```
Lead Message: "Looking for 2BR in Heights, budget $1500"
                         ↓
                  [Classify Stage]
                         ↓
              Stage: qualifying (keywords: "looking", "2BR")
                         ↓
                   [Retrieve Context]
                         ↓
    ┌────────────────────────────────────────────────┐
    │ Vector Search in Training Data:                │
    │                                                 │
    │ Embedding query:                                │
    │ "[stage:qualifying] Looking for 2BR in Heights, │
    │  budget $1500"                                  │
    │                                                 │
    │ Top matches:                                    │
    │ 1. "Got it! What's your move timeline?" (0.91) │
    │ 2. "Perfect! When do you need to be in?" (0.89)│
    │ 3. "Any must-haves? Parking, pets?" (0.85)     │
    │ 4. "Heights has great options! Timeline?" (0.84)│
    │ ... (4 more)                                    │
    └────────────────────────────────────────────────┘
                         ↓
                [Extract Lead Context]
                         ↓
    ┌────────────────────────────────────────────────┐
    │ Known: budget ($1500), bedrooms (2), area      │
    │        (Heights)                                │
    │ Missing: move_timing                            │
    │ → Ask for move timeline next                   │
    └────────────────────────────────────────────────┘
                         ↓
                  [Build Prompt]
                         ↓
    ┌────────────────────────────────────────────────┐
    │ System: You are Ashanti, apartment locator...  │
    │                                                 │
    │ Stage Guidance: QUALIFYING - gather timeline,  │
    │ budget, beds, location. Ask ONE question.      │
    │                                                 │
    │ Lead Context: Known [budget, bedrooms, area];  │
    │ Missing [move_timing]                           │
    │                                                 │
    │ Retrieved Examples:                             │
    │ - "Got it! What's your move timeline?"         │
    │ - "Perfect! When do you need to be in?"        │
    │ - "Any must-haves? Parking, pets?"             │
    │ ...                                             │
    │                                                 │
    │ User: Looking for 2BR in Heights, budget $1500 │
    └────────────────────────────────────────────────┘
                         ↓
                 [Generate Response]
                         ↓
                  LLM (GPT-4o-mini)
                         ↓
    ┌────────────────────────────────────────────────┐
    │ "Perfect! Heights has great options in that    │
    │  range. What's your move timeline?"            │
    └────────────────────────────────────────────────┘
                         ↓
                [Detect Actions]
                         ↓
              No action (still qualifying)
                         ↓
    ┌────────────────────────────────────────────────┐
    │ Response:                                       │
    │ {                                               │
    │   "reply": "Perfect! Heights has great options │
    │             in that range. What's your move    │
    │             timeline?",                         │
    │   "suggested_action": null,                     │
    │   "stage": "qualifying"                         │
    │ }                                               │
    └────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. RAG Over Rules
**Why**: Ashanti's style is learned from examples, not hardcoded rules. This makes the agent adaptable and natural.

### 2. Simple 3-Node Graph
**Why**: Easy to understand, debug, and maintain. Each node has a clear purpose.

### 3. Stage-Based Guidance
**Why**: Different stages require different approaches. Clear stage guidance helps the LLM adapt.

### 4. Context Extraction
**Why**: Avoid redundant questions. Show the lead we remember what they told us.

### 5. Few-Shot Learning
**Why**: Provide concrete examples of Ashanti's style to guide tone and structure.

### 6. Action Detection
**Why**: Identify when human intervention or specific actions are needed.

## Configuration

### LLM Settings
```python
ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.5,      # Balanced creativity/consistency
    top_p=0.8,            # Focus on likely tokens
    frequency_penalty=0.3, # Reduce repetition
    presence_penalty=0.5,  # Encourage topic diversity
)
```

### RAG Settings
```python
# Retrieval tuning
candidate_k = 60           # Candidates per search
top_k = 8                  # Final results
boost_thread = 0.20        # Same thread boost
boost_stage = 0.08         # Same stage boost
boost_agent_role = 0.05    # Agent message boost
boost_recent_turn = 0.01   # Recency boost
```

## Testing Strategy

### Unit Tests
```python
# Test individual methods
test_classify_stage()
test_extract_lead_context()
test_detect_suggested_action()
test_get_stage_guidance()
```

### Integration Tests
```python
# Test full flow
test_full_conversation_turn()
test_stage_transitions()
test_rag_retrieval()
```

### End-to-End Tests
```python
# Test real scenarios
test_qualifying_conversation()
test_touring_conversation()
test_application_support()
```

## Monitoring

### Key Metrics
- **Response time**: Time from input to output
- **RAG relevance**: Average similarity score of retrieved docs
- **Stage accuracy**: Correct stage classification rate
- **Action detection**: Precision/recall of suggested actions

### Logging
```python
# Each node logs key information
logger.info(f"Stage classified: {stage}")
logger.info(f"Retrieved {len(docs)} docs, context length: {len(ctx)}")
logger.debug(f"Top docs: {meta}")
logger.info(f"Generated response: {len(reply)} chars")
```

## Summary

The refactored agent is:
- **Simple**: 3-node graph with clear flow
- **Maintainable**: Focused methods, comprehensive docs
- **Effective**: Learns from examples via RAG
- **Testable**: Modular design, easy to unit test
- **Debuggable**: Clear logging at each step
- **Production-Ready**: Robust error handling, fallbacks

The architecture achieves the core goal: **Replicate Ashanti's communication style by learning from training data.**

