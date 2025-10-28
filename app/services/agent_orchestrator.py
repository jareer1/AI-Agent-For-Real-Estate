"""Agent Orchestrator - High-level interface for the agent graph.

This module provides a clean interface between the API layer and the agent graph,
handling state normalization and response formatting.
"""

from typing import Any, TypedDict

from ..schemas.common import Thread, StageV2, map_stage_v2_to_legacy
from .agent_graph import AgentGraph, GraphState


class AgentState(TypedDict, total=False):
    """State object for agent orchestration.
    
    This is the external-facing state format used by API routes and services.
    """
    thread_id: str
    stage: StageV2
    chat_history: list[dict[str, str]]  # [{role, content}]
    lead_profile: dict[str, Any]
    suggested_action: dict[str, Any] | None
    reply: str | None
    context: str | None


class AgentOrchestrator:
    """Orchestrates agent interactions and manages state transformations.
    
    The orchestrator serves as a bridge between external API requests and the
    internal agent graph, ensuring proper state format and response structure.
    """
    
    def __init__(self) -> None:
        """Initialize the orchestrator with an agent graph."""
        self.graph = AgentGraph()

    def run_turn(self, state: AgentState, user_utterance: str) -> AgentState:
        """Execute a single conversation turn.
        
        Takes the current conversation state and lead's message, runs it through
        the agent graph, and returns an updated state with the response.
        
        Args:
            state: Current conversation state
            user_utterance: The lead's message
        
        Returns:
            Updated state with agent's reply and suggested action
        """
        # Convert to internal GraphState format
        graph_state: GraphState = {
            "thread_id": state.get("thread_id") or "",
            "stage": state.get("stage") or StageV2.qualifying,
            "chat_history": state.get("chat_history") or [],
            "lead_profile": state.get("lead_profile") or {},
        }
        
        # Run the agent graph
        output = self.graph.run(graph_state, user_utterance)
        
        # Normalize stage to string for JSON serialization
        stage_out = output.get("stage")
        stage_str = stage_out.value if isinstance(stage_out, StageV2) else str(stage_out or "qualifying")
        
        # Return normalized state
        return {
            "thread_id": output.get("thread_id") or state.get("thread_id") or "",
            "stage": stage_str,
            "chat_history": graph_state.get("chat_history") or [],
            "lead_profile": graph_state.get("lead_profile") or {},
            "suggested_action": output.get("suggested_action"),
            "reply": output.get("reply"),
            "context": output.get("context"),
        }

    def route_stage(self, thread: Thread):
        """Map stage to legacy format for backward compatibility.
        
        Args:
            thread: Thread object with stage information
        
        Returns:
            Legacy stage enum value
        """
        stage_v2 = (
            StageV2(thread.stage.value) 
            if hasattr(thread.stage, "value") 
            else StageV2.qualifying
        )
        return map_stage_v2_to_legacy(stage_v2)


