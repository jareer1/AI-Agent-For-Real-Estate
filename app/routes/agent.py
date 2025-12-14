"""Agent API routes - Clean, production-ready endpoints.

This module provides the main API endpoints for the AI agent:
- /webhook/zapier/message: Main webhook for Zapier integration
- /agent/start: Initialize a new conversation
- /agent/reply: Generate a reply in an ongoing conversation
- /agent/action: Execute an action (email, SMS, etc.)

All business logic is handled through LLM prompts rather than hardcoded rules.
"""

from fastapi import APIRouter, Depends
from datetime import datetime

from ..core.security import require_api_key
from ..services.agent_orchestrator import AgentOrchestrator, AgentState
from ..db.mongo import messages_collection, escalations_collection
from ..services.actions import (
    should_change_stage,
    is_escalation_action,
    determine_should_send,
    default_reply_for_action,
)
from ..services.escalation_rules import detect_escalation_from_rules
from integrations.composio_client import ComposioClient
from ..services.embeddings import EmbeddingsService


# API routers
agent_router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(require_api_key)]
)

webhook_router = APIRouter(
    prefix="/webhook",
    tags=["webhook"]
)


def _build_chat_history(
    thread_id: str | None,
    payload_history: list[dict[str, str]] | None
) -> list[dict[str, str]]:
    """Build chat history from payload or database.
    
    Prefers provided chat_history in payload, falls back to DB lookup by thread_id.
    
    Args:
        thread_id: Conversation thread identifier
        payload_history: Chat history from request payload
    
    Returns:
        List of messages with role (user/assistant) and content
    """
    # Use provided history if available
    if payload_history:
        return payload_history[-20:]
    
    # Fall back to DB lookup
    if not thread_id:
        return []
    
    try:
        cursor = (
            messages_collection()
            .find(
                {"thread_id": thread_id, "clean_text": {"$exists": True, "$ne": ""}},
                {"role": 1, "clean_text": 1}
            )
            .sort("turn_index", 1)
            .limit(40)
        )
        
        mapped: list[dict[str, str]] = []
        for doc in cursor:
            role = (doc.get("role") or "").lower()
            content = doc.get("clean_text") or ""

            if not content:
                continue

            if role == "lead":
                mapped.append({"role": "user", "content": content})
            elif role == "agent":
                mapped.append({"role": "assistant", "content": content})
            elif role == "system":
                mapped.append({"role": "system", "content": content})
        
        return mapped[-20:]
    
    except Exception:
        return []


def _log_escalation(
    thread_id: str | None,
    escalation_type: str,
    escalation_reason: str,
    lead_message: str,
    ai_response: str,
    stage: str,
) -> None:
    """Log an escalation to MongoDB for human review queue.
    
    Args:
        thread_id: Conversation thread ID
        escalation_type: Type of escalation (fees, links, scheduling, etc.)
        escalation_reason: Brief description of why escalating
        lead_message: The lead's message that triggered escalation
        ai_response: The AI's response (may be empty for no-send cases)
        stage: Current conversation stage
    """
    if not thread_id or not escalation_type:
        return
    
    try:
        escalations_collection().insert_one({
            "thread_id": thread_id,
            "escalation_type": escalation_type,
            "escalation_reason": escalation_reason or "No reason provided",
            "lead_message_snippet": lead_message[:500] if lead_message else "",
            "ai_response": ai_response[:500] if ai_response else "",
            "timestamp": datetime.utcnow(),
            "stage": stage or "unknown",
            "resolved": False,
            "resolution_notes": None,
            "resolved_at": None,
            "resolved_by": None,
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to log escalation: {e}")


@webhook_router.post("/zapier/message")
def zapier_message(payload: dict) -> dict:
    """Main webhook endpoint for Zapier integration.
    
    This is the primary entry point for incoming messages from leads.
    
    Flow:
    1. Extract message and context from payload
    2. Run through agent orchestrator (LLM generates response)
    3. Determine final action (prefer LLM, fallback to safety rules)
    4. Decide whether to send message (no-send for fees/links/pricing)
    5. Log escalations to MongoDB
    6. Return response with flags
    
    Payload:
        {
            "thread_id": "unique_conversation_id",
            "text": "Lead's message",
            "chat_history": [{"role": "user"|"assistant", "content": "..."}],
            "stage": "qualifying|working|touring|...",
            "lead_profile": {"budget": 1500, "bedrooms": "2+", ...}
        }
    
    System Instruction Mode (role="system"):
        {
            "role": "system",
            "text": "Write a follow-up message after a long period of inactivity.",
            "chat_history": [...],
            "stage": "qualifying",
            "lead_profile": {"budget": 3000, "bedrooms": 3, ...}
        }
        When role="system", the text is treated as an instruction for the agent
        to generate a message (e.g., follow-up) using the provided lead_profile.
    
    Returns:
        {
            "message": "AI response text (empty if no-send)",
            "state": {...},
            "escalation": bool,
            "escalation_type": "action_name",
            "escalation_reason": "explanation",
            "should_send_message": bool,
            "stage_change": "new_stage" | null
        }
    """
    # Check if this is a system instruction (e.g., follow-up request)
    role = (payload.get("role") or "").lower()
    is_system_instruction = role == "system"
    
    # Extract payload components
    text = payload.get("text") or ""
    thread_id = payload.get("thread_id")
    chat_history = _build_chat_history(thread_id, payload.get("chat_history"))
    
    # For system instructions, add the instruction to chat history as system message
    # and use an empty user message (the agent should generate a proactive message)
    if is_system_instruction and text:
        # Add system instruction to the beginning of chat history for context
        chat_history = [{"role": "system", "content": text}] + chat_history
        # Use a placeholder to trigger response generation
        text = "[System instruction: Generate response based on context and lead profile]"
    
    # Build initial state
    state_in = payload.get("state") or {
        "thread_id": thread_id,
        "stage": payload.get("stage") or "qualifying",
        "chat_history": chat_history,
        "lead_profile": payload.get("lead_profile") or {},
    }
    
    # Run through agent orchestrator (classify stage -> retrieve -> respond)
    orchestrator = AgentOrchestrator()
    next_state = orchestrator.run_turn(state_in, text)
    
    # Log request metrics
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            "Zapier webhook: thread=%s text_len=%d history=%d reply_len=%d stage=%s",
            thread_id,
            len(text),
            len(chat_history),
            len(next_state.get("reply") or ""),
            next_state.get("stage"),
        )
    except Exception:
        pass
    
    # Determine final action: prefer LLM suggestion, fallback to safety rules
    model_suggested = next_state.get("suggested_action") or {}
    final_action = model_suggested
    action_type = (final_action.get("action") if isinstance(final_action, dict) else None) or None
    
    # Apply safety rule fallback if LLM didn't provide action
    if not action_type:
        fallback = detect_escalation_from_rules(
            user_text=text,
            chat_history=chat_history,
            stage=next_state.get("stage"),
            reply_text=next_state.get("reply") or "",
        )
        if isinstance(fallback, dict) and fallback.get("action"):
            final_action = {"action": fallback.get("action"), "reason": fallback.get("reason")}
            action_type = final_action.get("action")
    
    # Determine flags
    stage_change = should_change_stage(final_action)
    escalate = is_escalation_action(action_type)
    escalation_type = action_type if escalate else None
    escalation_reason = (
        (final_action.get("reason") if isinstance(final_action, dict) else None)
        if escalate else None
    )
    
    # Decide whether to send message (no-send for fees/links/pricing)
    should_send_message = determine_should_send(action_type, str(next_state.get("stage") or ""))
    
    # Log escalation to MongoDB for human review queue
    if escalate and thread_id:
        reply_text = next_state.get("reply") or ""
        _log_escalation(
            thread_id=thread_id,
            escalation_type=escalation_type,
            escalation_reason=escalation_reason,
            lead_message=text,
            ai_response=reply_text,
            stage=str(next_state.get("stage") or "unknown"),
        )
    
    # Handle no-send cases and provide fallback if needed
    reply_text = next_state.get("reply") or ""
    
    if should_send_message and not reply_text:
        # LLM should have provided message; use minimal fallback
        reply_text = default_reply_for_action(action_type, str(next_state.get("stage") or ""), text)
        next_state["reply"] = reply_text
    
    # Build updated chat history
    updated_history = (chat_history or []) + ([{"role": "user", "content": text}] if text else [])
    
    if should_send_message and reply_text:
        updated_history += [{"role": "assistant", "content": reply_text}]
    else:
        # Blank the reply for no-send cases
        next_state["reply"] = ""
        reply_text = ""
    
    next_state["chat_history"] = updated_history[-20:]
    
    # Return response
    return {
        "message": reply_text,
        "state": next_state,
        "stage_change": stage_change,
        "escalation": bool(escalate),
        "escalation_type": escalation_type,
        "escalation_reason": escalation_reason,
        "should_send_message": bool(should_send_message),
        # Backward-compatible fields
        "escalate": bool(escalate),
        "no_response": not should_send_message,
    }


@agent_router.post("/start")
def start_conversation(payload: dict) -> dict:
    """Initialize a new conversation thread.
    
    Creates initial state for a new lead conversation.
    
    Payload:
        {
            "thread_id": "unique_id",
            "lead_profile": {"budget": 1500, "bedrooms": "2+", "move_date": "2025-03", ...}
        }
    
    Returns:
        {"status": "started", "state": {...}}
    """
    thread_id = payload.get("thread_id")
    lead_profile = payload.get("lead_profile") or {}
    
    initial_state: AgentState = {
        "thread_id": thread_id,
        "stage": "qualifying",
        "chat_history": payload.get("chat_history") or [],
        "lead_profile": lead_profile,
    }
    
    return {"status": "started", "state": initial_state}


@agent_router.post("/reply")
def generate_reply(payload: dict) -> dict:
    """Generate a reply in an ongoing conversation.
    
    Similar to zapier_message but also persists messages to MongoDB.
    
    Payload:
        {
            "thread_id": "unique_id",
            "text": "Lead's message",
            "chat_history": [...],
            "state": {...},
            "lead_profile": {"budget": 1500, "bedrooms": "2+", ...}
        }
    
    Returns:
        {
            "message": "AI response",
            "state": {...},
            "escalation": bool,
            "should_send_message": bool
        }
    """
    user_input = payload.get("text") or ""
    thread_id = payload.get("thread_id")
    chat_history = _build_chat_history(thread_id, payload.get("chat_history"))
    
    # Build state
    state_in: AgentState = payload.get("state") or {
        "thread_id": thread_id,
        "stage": "qualifying",
        "chat_history": chat_history,
        "lead_profile": payload.get("lead_profile") or {},
    }
    
    # Run through agent
    orchestrator = AgentOrchestrator()
    next_state = orchestrator.run_turn(state_in, user_input)
    reply = next_state.get("reply") or ""
    
    # Determine final action
    model_suggested = next_state.get("suggested_action") or {}
    final_action = model_suggested
    action_type = (final_action.get("action") if isinstance(final_action, dict) else None) or None
    
    if not action_type:
        fallback = detect_escalation_from_rules(
            user_text=user_input,
            chat_history=chat_history,
            stage=next_state.get("stage"),
            reply_text=reply,
        )
        if isinstance(fallback, dict) and fallback.get("action"):
            final_action = {"action": fallback.get("action"), "reason": fallback.get("reason")}
            action_type = final_action.get("action")
    
    # Determine flags
    stage_change = should_change_stage(final_action)
    escalate = is_escalation_action(action_type)
    escalation_type = action_type if escalate else None
    escalation_reason = (
        (final_action.get("reason") if isinstance(final_action, dict) else None)
        if escalate else None
    )
    should_send_message = determine_should_send(action_type, str(next_state.get("stage") or ""))
    
    # Persist assistant message to DB if sending
    if thread_id and reply and should_send_message:
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
        
        # Generate embedding asynchronously
        try:
            EmbeddingsService().embed_and_update_messages(
                [(inserted.inserted_id, reply)],
                version="v1"
            )
        except Exception:
            pass
    
    # Log escalation
    if escalate and thread_id:
        _log_escalation(
            thread_id=thread_id,
            escalation_type=escalation_type,
            escalation_reason=escalation_reason,
            lead_message=user_input,
            ai_response=reply if should_send_message else "",
            stage=str(next_state.get("stage") or "unknown"),
        )
    
    # Build response
    updated_history = (chat_history or []) + ([{"role": "user", "content": user_input}] if user_input else [])
    
    if should_send_message and reply:
        updated_history += [{"role": "assistant", "content": reply}]
    else:
        next_state["reply"] = ""
        reply = ""
    
    next_state["chat_history"] = updated_history[-20:]
    
    return {
        "message": reply,
        "state": next_state,
        "stage_change": stage_change,
        "escalation": bool(escalate),
        "escalation_type": escalation_type,
        "escalation_reason": escalation_reason,
        "should_send_message": bool(should_send_message),
        # Backward-compatible fields
        "escalate": bool(escalate),
    }


@agent_router.post("/send_system_message")
def send_system_message(payload: dict) -> dict:
    """Send a message from a system agent in response to an escalation.

    This endpoint allows system agents to send messages that will be properly
    identified as coming from system agents rather than the AI assistant.

    Payload:
        {
            "thread_id": "unique_conversation_id",
            "message": "System agent's response message",
            "escalation_id": "optional_id_of_resolved_escalation"
        }

    Returns:
        {"status": "sent", "message_id": "..."}
    """
    thread_id = payload.get("thread_id")
    message = payload.get("message", "").strip()
    escalation_id = payload.get("escalation_id")

    if not thread_id or not message:
        return {"status": "error", "message": "thread_id and message are required"}

    try:
        # Build chat history (this will include the system message we're about to add)
        chat_history = _build_chat_history(thread_id, None)

        # Add the system message to chat history
        system_message = {"role": "system", "content": message}
        updated_history = (chat_history or []) + [system_message]

        # Store the system message in the database
        count = messages_collection().count_documents({"thread_id": thread_id})
        inserted = messages_collection().insert_one({
            "thread_id": thread_id,
            "turn_index": count,
            "role": "system",  # Use system role instead of agent
            "text": message,
            "clean_text": message,
            "timestamp": datetime.utcnow(),
            "stage": "unknown",  # We'll determine this from context
            "entities": {},
            "embedding": None,
            "embedding_model": None,
            "embedding_version": None,
            "source": "system_agent",
            "pii_hashes": {},
            "escalation_id": escalation_id,  # Link to the escalation this resolves
        })

        # Generate embedding asynchronously
        try:
            EmbeddingsService().embed_and_update_messages(
                [(inserted.inserted_id, message)],
                version="v1"
            )
        except Exception:
            pass

        # Mark escalation as resolved if escalation_id provided
        if escalation_id:
            try:
                escalations_collection().update_one(
                    {"_id": escalation_id},
                    {
                        "$set": {
                            "resolved": True,
                            "resolution_notes": f"System message sent: {message[:100]}...",
                            "resolved_at": datetime.utcnow(),
                            "resolved_by": "system_agent"
                        }
                    }
                )
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to update escalation {escalation_id}: {e}")

        return {
            "status": "sent",
            "message_id": str(inserted.inserted_id),
            "escalation_resolved": bool(escalation_id)
        }

    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to send system message: {e}")
        return {"status": "error", "message": str(e)}


@agent_router.post("/action")
def confirm_action(payload: dict) -> dict:
    """Execute an action through Composio (email, SMS, calendar, etc.).

    Payload:
        {
            "action": "request_application",
            "meta": {"recipient": "lead@example.com", "property": "The Pearl", ...}
        }

    Returns:
        {"status": "success"|"error", "result": {...}}
    """
    client = ComposioClient()
    action = payload.get("action")
    meta = payload.get("meta") or {}

    # Map action to Composio tool
    tool_map = {
        "request_application": "email.send",
    }
    tool = tool_map.get(action or "") or "email.send"

    result = client.execute(tool, meta)

    return {
        "status": result.get("status"),
        "provider": result.get("provider"),
        "action": action,
        "result": result
    }
