from fastapi import APIRouter, Depends

from ..core.security import require_api_key
from ..services.agent_orchestrator import AgentOrchestrator, AgentState
from ..db.mongo import messages_collection
from ..services.actions import should_change_stage
from integrations.composio_client import ComposioClient
from ..services.embeddings import EmbeddingsService


agent_router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_api_key)])
# Unauthenticated webhook for Zapier (they can pass API key if desired)
webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])


def _build_chat_history(thread_id: str | None, payload_history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """Prefer provided chat history; fallback to DB by thread.

    Returns list of {role:"user"|"assistant", content:str}
    """
    history = payload_history or []
    if history:
        return history[-20:]
    if not thread_id:
        return []
    try:
        cur = (
            messages_collection()
            .find({"thread_id": thread_id, "clean_text": {"$exists": True, "$ne": ""}}, {"role": 1, "clean_text": 1})
            .sort("turn_index", 1)
            .limit(40)
        )
        mapped: list[dict[str, str]] = []
        for d in cur:
            role = (d.get("role") or "").lower()
            content = d.get("clean_text") or ""
            if not content:
                continue
            if role == "lead":
                mapped.append({"role": "user", "content": content})
            elif role == "agent":
                mapped.append({"role": "assistant", "content": content})
        return mapped[-20:]
    except Exception:
        return []


@webhook_router.post("/zapier/message")
def zapier_message(payload: dict) -> dict:
    # Expecting: {thread_id, chat_history: [...], text, lead_profile}
    text = payload.get("text") or ""
    thread_id = payload.get("thread_id")
    orchestrator = AgentOrchestrator()
    chat_history = _build_chat_history(thread_id, (payload.get("chat_history") or []))
    state_in = payload.get("state") or {
        "thread_id": thread_id,
        "stage": payload.get("stage") or "qualifying",
        "chat_history": chat_history,
        "lead_profile": payload.get("lead_profile") or {},
    }
    next_state = orchestrator.run_turn(state_in, text)
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            "Zapier webhook: thread_id=%s text_len=%s history=%s reply_len=%s context_len=%s stage=%s",
            thread_id,
            len(text or ""),
            len(chat_history or []),
            len((next_state.get("reply") or "")),
            len((next_state.get("context") or "")),
            next_state.get("stage"),
        )
    except Exception:
        pass
    stage_change = should_change_stage(next_state.get("suggested_action"))
    escalate = (next_state.get("suggested_action") or {}).get("action") == "escalate_pricing"
    # Return updated chat history including this turn
    reply_text = next_state.get("reply") or ""
    updated_history = (chat_history or []) + ([{"role": "user", "content": text}] if text else []) + (
        [{"role": "assistant", "content": reply_text}] if reply_text else []
    )
    next_state["chat_history"] = updated_history[-20:]
    # special controls from LLM are represented via suggested_action in this version
    return {
        "message": next_state.get("reply"),
        "state": next_state,
        "stage_change": stage_change,
        "no_response": False,
        "escalate": escalate,
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

    chat_history = _build_chat_history(thread_id, (payload.get("chat_history") or []))
    state_in: AgentState = payload.get("state") or {
        "thread_id": thread_id,
        "stage": "qualifying",
        "chat_history": chat_history,
        "lead_profile": payload.get("lead_profile") or {},
    }
    next_state = orchestrator.run_turn(state_in, user_input)
    reply = next_state.get("reply") or ""

    # Persist assistant message
    if thread_id and reply:
        count = messages_collection().count_documents({"thread_id": thread_id})
        inserted = messages_collection().insert_one({
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
        # Best-effort: embed the generated reply immediately so it becomes retrievable
        try:
            EmbeddingsService().embed_and_update_messages([(inserted.inserted_id, reply)], version="v1")
        except Exception:
            # Fail silently; background jobs can re-embed later
            pass

    # Optional: suggest action and stage change
    stage_change = should_change_stage(next_state.get("suggested_action"))

    escalate = (next_state.get("suggested_action") or {}).get("action") == "escalate_pricing"
    # Return updated chat history including this turn
    updated_history = (chat_history or []) + ([{"role": "user", "content": user_input}] if user_input else []) + (
        [{"role": "assistant", "content": reply}] if reply else []
    )
    next_state["chat_history"] = updated_history[-20:]

    return {"message": reply, "state": next_state, "stage_change": stage_change, "escalate": escalate}


@agent_router.post("/action")
def confirm_action(payload: dict) -> dict:
    client = ComposioClient()
    action = payload.get("action")
    meta = payload.get("meta") or {}
    tool_map = {
        "request_application": "email.send",
    }
    tool = tool_map.get(action or "") or "email.send"
    result = client.execute(tool, meta)
    return {"status": result.get("status"), "provider": result.get("provider"), "action": action, "result": result}


