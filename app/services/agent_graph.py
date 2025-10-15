from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from ..schemas.common import StageV2, map_text_to_stage_v2
from .rag import RAGService
from ..core.config import get_settings
from .prompts import get_system_prompt


class GraphState(TypedDict, total=False):
    thread_id: str
    stage: StageV2
    chat_history: list[dict[str, str]]
    lead_profile: dict[str, Any]
    user_utterance: str
    context: str
    reply: str
    suggested_action: dict[str, Any] | None


class AgentGraph:
    def __init__(self) -> None:
        self.rag = RAGService()
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.4)

        settings = get_settings()
        self.mode = settings.agent_mode

        if self.mode == "react":
            # Prebuilt ReAct agent with minimal tools (RAG retrieval tool)
            def retrieve_tool(query: str) -> str:  # simple tool signature
                docs = self.rag.retrieve(query, top_k=6)
                return "\n".join([d.get("clean_text") or d.get("text") or "" for d in docs])

            def rag_tool(state: GraphState) -> dict:
                q = state.get("user_utterance") or ""
                return {"messages": [("tool", retrieve_tool(q))]}

            tools = []  # We keep an empty list; retrieval is handled via context injection in call
            system_prompt = get_system_prompt()
            self.app = create_react_agent(model=self.llm, tools=tools, state_modifier=system_prompt)
            self.memory = MemorySaver()
        else:
            graph = StateGraph(GraphState)
            graph.add_node("classify_stage", self._classify_stage)
            graph.add_node("retrieve", self._retrieve)
            graph.add_node("respond", self._respond)
            graph.add_edge("classify_stage", "retrieve")
            graph.add_edge("retrieve", "respond")
            graph.add_edge("respond", END)

            self.memory = MemorySaver()
            self.app = graph.compile(checkpointer=self.memory)

    # Nodes
    def _classify_stage(self, state: GraphState) -> GraphState:
        text = state.get("user_utterance") or ""
        stage = map_text_to_stage_v2(text, state.get("stage"))
        state["stage"] = stage
        return state

    def _retrieve(self, state: GraphState) -> GraphState:
        text = state.get("user_utterance") or ""
        docs = self.rag.retrieve(text, top_k=8)
        ctx = "\n".join([d.get("clean_text") or d.get("text") or "" for d in docs])
        state["context"] = ctx
        return state

    def _respond(self, state: GraphState) -> GraphState:
        stage: StageV2 = state.get("stage") or StageV2.qualifying
        system_by_stage: dict[StageV2, str] = {
            StageV2.qualifying: "Focus on gathering timeline, budget, beds/baths, location. Ask 1-2 concise questions.",
            StageV2.working: "Share curated options. Confirm preferences. Offer next steps.",
            StageV2.touring: "Propose tour slots. Confirm availability and location.",
            StageV2.applied: "Confirm application steps. Offer help with docs.",
            StageV2.approved: "Share move-in details and lease signing next steps.",
            StageV2.closed: "Congratulate and set expectations. Offer help post move-in.",
            StageV2.post_close_nurture: "Provide value, request referrals, and offer renewal help later.",
        }
        system = system_by_stage[stage]
        context = state.get("context") or ""
        user_utterance = state.get("user_utterance") or ""

        base = get_system_prompt()
        messages = [
            {"role": "system", "content": base + "\n\n" + system + ("\nContext:\n" + context if context else "")},
        ]
        for m in state.get("chat_history") or []:
            if m.get("role") in ("user", "assistant", "system"):
                messages.append({"role": m["role"], "content": m.get("content") or ""})
        messages.append({"role": "user", "content": user_utterance})

        resp = self.llm.invoke(messages)
        reply = getattr(resp, "content", "")

        # naive action suggestion
        suggested_action = None
        lower = reply.lower()
        if any(k in lower for k in ["schedule", "tour", "showing"]) and stage in (StageV2.touring, StageV2.working):
            suggested_action = {"action": "schedule_tour"}
        elif any(k in lower for k in ["apply", "application"]) and stage in (StageV2.working, StageV2.applied):
            suggested_action = {"action": "request_application"}

        state["reply"] = reply
        state["suggested_action"] = suggested_action
        return state

    def run(self, state: GraphState, user_utterance: str) -> GraphState:
        config = {"configurable": {"thread_id": state.get("thread_id") or "default"}}
        inputs = {**state, "user_utterance": user_utterance}
        if self.mode == "react":
            # Use messages state expected by prebuilt agent
            messages = []
            for m in state.get("chat_history") or []:
                role = m.get("role")
                content = m.get("content") or ""
                if role in ("user", "assistant", "system"):
                    messages.append((role, content))
            # Inject simple retrieval into system as context hint
            ctx = self.rag.retrieve(user_utterance, top_k=6)
            context = "\n".join([d.get("clean_text") or d.get("text") or "" for d in ctx])
            messages = [("system", "Use the following context if helpful:\n" + context)] + messages + [("user", user_utterance)]
            resp = self.app.invoke({"messages": messages}, config)
            # The prebuilt returns messages state; pick the last assistant message
            reply = ""
            try:
                reply = resp["messages"][-1].content  # type: ignore[index]
            except Exception:
                pass
            stage = map_text_to_stage_v2(user_utterance, state.get("stage"))
            return {**state, "user_utterance": user_utterance, "reply": reply, "stage": stage, "suggested_action": None}
        out = self.app.invoke(inputs, config)
        return out


