from fastapi import APIRouter, Depends

from ..core.security import require_api_key
from ..services.agent_orchestrator import AgentOrchestrator, AgentState
from ..db.mongo import messages_collection
from ..services.actions import should_change_stage
from integrations.composio_client import ComposioClient


agent_router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_api_key)])
# Unauthenticated webhook for Zapier (they can pass API key if desired)
webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])


@webhook_router.post("/zapier/message")
def zapier_message(payload: dict) -> dict:
    # Expecting: {thread_id, chat_history: [...], text, lead_profile}
    text = payload.get("text") or ""
    thread_id = payload.get("thread_id")
    orchestrator = AgentOrchestrator()
    state_in = payload.get("state") or {
        "thread_id": thread_id,
        "stage": payload.get("stage") or "qualifying",
        "chat_history": payload.get("chat_history") or [],
        "lead_profile": payload.get("lead_profile") or {},
    }
    next_state = orchestrator.run_turn(state_in, text)
    stage_change = should_change_stage(next_state.get("suggested_action"))
    # special controls from LLM are represented via suggested_action in this version
    return {
        "message": next_state.get("reply"),
        "state": next_state,
        "stage_change": stage_change,
        "no_response": False,
        "escalate": False,
    }


@agent_router.post("/start")
def start_conversation(payload: dict) -> dict:
    thread_id = payload.get("thread_id")
    lead_profile = payload.get("lead_profile") or {}
    initial_state: AgentState = {
        "thread_id": thread_id,
        "stage": "qualifying",  # StageV2 string for transport
        "chat_history": payload.get("chat_history") or [],
        "lead_profile": lead_profile,
    }
    return {"status": "started", "state": initial_state}


@agent_router.post("/reply")
def generate_reply(payload: dict) -> dict:
    user_input = payload.get("text") or ""
    thread_id = payload.get("thread_id")
    orchestrator = AgentOrchestrator()

    state_in: AgentState = payload.get("state") or {
        "thread_id": thread_id,
        "stage": "qualifying",
        "chat_history": payload.get("chat_history") or [],
        "lead_profile": payload.get("lead_profile") or {},
    }
    next_state = orchestrator.run_turn(state_in, user_input)
    reply = next_state.get("reply") or ""

    # Persist assistant message
    if thread_id and reply:
        count = messages_collection().count_documents({"thread_id": thread_id})
        messages_collection().insert_one({
            "thread_id": thread_id,
            "turn_index": count,
            "role": "agent",
            "text": reply,
            "clean_text": reply,
            "timestamp": None,
            "stage": str(next_state.get("stage") or "qualifying"),
            "entities": {},
            "embedding": None,
            "embedding_model": None,
            "embedding_version": None,
            "source": "generated",
            "pii_hashes": {},
        })

    # Optional: suggest action and stage change
    stage_change = should_change_stage(next_state.get("suggested_action"))

    return {"message": reply, "state": next_state, "stage_change": stage_change}


@agent_router.post("/action")
def confirm_action(payload: dict) -> dict:
    client = ComposioClient()
    action = payload.get("action")
    meta = payload.get("meta") or {}
    tool_map = {
        "schedule_tour": "calendar.create_event",
        "request_application": "email.send",
    }
    tool = tool_map.get(action or "") or "email.send"
    result = client.execute(tool, meta)
    return {"status": result.get("status"), "provider": result.get("provider"), "action": action, "result": result}


