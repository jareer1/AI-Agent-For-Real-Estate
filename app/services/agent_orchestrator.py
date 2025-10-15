from typing import Any, TypedDict

from ..schemas.common import Thread, StageV2, map_stage_v2_to_legacy
from .agent_graph import AgentGraph, GraphState


class AgentState(TypedDict, total=False):
    thread_id: str
    stage: StageV2
    chat_history: list[dict[str, str]]  # [{role, content}]
    lead_profile: dict[str, Any]
    suggested_action: dict[str, Any] | None
    reply: str | None


class AgentOrchestrator:
    def __init__(self) -> None:
        self.graph = AgentGraph()

    def run_turn(self, state: AgentState, user_utterance: str) -> AgentState:
        # Normalize incoming state to GraphState
        gstate: GraphState = {
            "thread_id": state.get("thread_id") or "",
            "stage": state.get("stage") or StageV2.qualifying,
            "chat_history": state.get("chat_history") or [],
            "lead_profile": state.get("lead_profile") or {},
        }
        out = self.graph.run(gstate, user_utterance)
        # Ensure JSON-serializable stage
        stage_out = out.get("stage")
        stage_str = stage_out.value if isinstance(stage_out, StageV2) else stage_out
        return {
            "thread_id": out.get("thread_id") or state.get("thread_id") or "",
            "stage": stage_str or "qualifying",
            "chat_history": gstate.get("chat_history") or [],
            "lead_profile": gstate.get("lead_profile") or {},
            "suggested_action": out.get("suggested_action"),
            "reply": out.get("reply"),
        }

    def route_stage(self, thread: Thread):
        # Keep method for backward compatibility with legacy routes
        return map_stage_v2_to_legacy(StageV2(thread.stage.value) if hasattr(thread.stage, "value") else StageV2.qualifying)


