"""Agent Graph - Clean, production-ready conversation orchestration.

This module implements a simple three-node graph:
1. Classify Stage: Determine conversation stage using LLM
2. Retrieve Context: Fetch relevant examples from training data
3. Respond: Generate natural response using comprehensive prompts

All logic is handled through prompts rather than hardcoded rules.
"""

from __future__ import annotations

from typing import Any, TypedDict
import logging
import json

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from ..schemas.common import StageV2
from .rag import RAGService
from ..core.config import get_settings
from .prompts import build_complete_prompt, get_stage_prompt
from .style_profile import StyleProfile


class GraphState(TypedDict, total=False):
    """State object passed through the agent graph nodes.
    
    Attributes:
        thread_id: Unique identifier for the conversation thread
        stage: Current stage in the lead journey
        chat_history: List of previous messages
        lead_profile: Extracted information about the lead
        user_utterance: Current message from the lead
        context: Retrieved context from RAG
        reply: Generated response
        suggested_action: Action to be taken (escalation, application, etc.)
    """
    thread_id: str
    stage: StageV2
    chat_history: list[dict[str, str]]
    lead_profile: dict[str, Any]
    user_utterance: str
    context: str
    reply: str
    suggested_action: dict[str, Any] | None


class AgentGraph:
    """Main agent graph orchestrating the conversation flow.
    
    Clean, production-ready implementation that leverages LLM capabilities
    through comprehensive prompts rather than hardcoded rules.
    """
    
    def __init__(self) -> None:
        """Initialize the agent graph with LLM, RAG service, and graph structure."""
        self.logger = logging.getLogger(__name__)
        self.rag = RAGService()
        
        settings = get_settings()
        
        # Initialize LLM
        if settings.openai_api_key:
            self.llm = ChatOpenAI(
                model="gpt-5",
                temperature=1.0,  # GPT-5 only supports temperature=1.0
                api_key=settings.openai_api_key,
                max_retries=1,
                timeout=50,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
            self._model_name = "gpt-5"
        else:
            # Fallback for testing
            from .llm import LLMService
            self.llm_service = LLMService()
            self.llm = None
            self._model_name = getattr(self.llm_service, "model", "fallback")

        # Build the graph: classify_stage -> retrieve -> respond
        graph = StateGraph(GraphState)
        graph.add_node("classify_stage", self._classify_stage)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("respond", self._respond)
        
        graph.add_edge("__start__", "classify_stage")
        graph.add_edge("classify_stage", "retrieve")
        graph.add_edge("retrieve", "respond")
        graph.add_edge("respond", END)

        self.memory = MemorySaver()
        self.app = graph.compile(checkpointer=self.memory)

    # ========================================
    # Graph Node Methods
    # ========================================
    
    def _classify_stage(self, state: GraphState) -> GraphState:
        """Node 1: Classify the current stage using LLM.
        
        Uses the LLM to intelligently determine the conversation stage based on
        context rather than simple keyword matching.
        """
        user_utterance = state.get("user_utterance") or ""
        chat_history = state.get("chat_history") or []
        current_stage = state.get("stage") or StageV2.qualifying
        
        # Build a simple stage classification prompt
        stage_prompt = f"""Based on the conversation context, determine the current stage.

Current stage: {current_stage.value if hasattr(current_stage, 'value') else current_stage}

Recent conversation:
{self._format_recent_history(chat_history[-6:])}

Current message: {user_utterance}

Available stages:
- qualifying: Gathering basic info (budget, bedrooms, move date, areas)
- working: Sending options, discussing properties
- touring: Scheduling or completing property tours
- applied: Application in progress
- approved: Application approved, securing referral
- closed: Lease signed or lead went elsewhere
- post_close_nurture: Post-move follow-up

Return JSON:
{{"stage": "stage_name", "reason": "brief explanation"}}
"""

        if self.llm:
            try:
                resp = self.llm.invoke([{"role": "user", "content": stage_prompt}])
                result_text = getattr(resp, "content", "").strip()
                parsed = json.loads(result_text)
                new_stage_str = parsed.get("stage", "").lower()
                
                # Map to StageV2 enum
                stage_mapping = {
                    "qualifying": StageV2.qualifying,
                    "working": StageV2.working,
                    "touring": StageV2.touring,
                    "applied": StageV2.applied,
                    "approved": StageV2.approved,
                    "closed": StageV2.closed,
                    "post_close_nurture": StageV2.post_close_nurture,
                }
                
                state["stage"] = stage_mapping.get(new_stage_str, current_stage)
                self.logger.debug(f"Stage classified: {state['stage'].value} (reason: {parsed.get('reason', 'N/A')})")
                
            except Exception as e:
                self.logger.warning(f"Stage classification failed, keeping current: {e}")
                state["stage"] = current_stage
        else:
            # Fallback: simple keyword-based classification
            state["stage"] = self._simple_stage_classification(user_utterance, current_stage)
        
        return state

    def _simple_stage_classification(self, text: str, current: StageV2) -> StageV2:
        """Fallback stage classification using simple keywords."""
        lower = (text or "").lower()
        
        if any(k in lower for k in ["approved", "approval", "got approved"]):
            return StageV2.approved
        if any(k in lower for k in ["applied", "application"]):
            return StageV2.applied
        if any(k in lower for k in ["tour", "showing", "schedule"]):
            return StageV2.touring
        if any(k in lower for k in ["close", "closed", "lease signed"]):
            return StageV2.closed
        if any(k in lower for k in ["options", "listings", "send", "properties"]):
            return StageV2.working
        
        return current or StageV2.qualifying

    def _retrieve(self, state: GraphState) -> GraphState:
        """Node 2: Retrieve relevant context from training data using RAG.
        
        Fetches similar conversations to provide style and tone guidance.
        """
        text = state.get("user_utterance") or ""
        stage = state.get("stage")
        stage_str = stage.value if hasattr(stage, "value") else str(stage) if stage else None
        
        # Retrieve relevant documents
        docs = self.rag.retrieve(
            text,
            top_k=5,
            thread_id=state.get("thread_id"),
            stage=stage_str,
            prefer_agent=True,
            chat_history=state.get("chat_history"),
        )
        
        # Combine document text and cap length
        ctx_full = "\n".join([d.get("clean_text") or d.get("text") or "" for d in docs])
        ctx = (ctx_full[:1600]).rstrip()
        state["context"] = ctx
        
        if docs:
            self.logger.info(f"Retrieved {len(docs)} docs, context length: {len(ctx)}")
        
        return state

    def _respond(self, state: GraphState) -> GraphState:
        """Node 3: Generate response using comprehensive prompts.
        
        All behavior is driven by prompts - no hardcoded post-processing.
        """
        stage = state.get("stage") or StageV2.qualifying
        context = state.get("context") or ""
        user_utterance = state.get("user_utterance") or ""
        chat_history = state.get("chat_history") or []
        
        # Extract lead context
        lead_summary = self._extract_lead_context(context, chat_history)
        
        # Build comprehensive prompt
        stage_str = stage.value if hasattr(stage, "value") else str(stage)
        system_prompt = build_complete_prompt(
            stage=stage_str,
            lead_context=lead_summary,
            retrieved_context=context,
        )
        
        # Add style profile notes
        try:
            style_notes = StyleProfile(self.rag).build_style_profile(user_utterance, stage=stage_str)
            if style_notes:
                system_prompt += f"\n\n{style_notes}"
        except Exception:
            pass
        
        # Build messages array
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add recent chat history
        for msg in chat_history[-12:]:
            if msg.get("role") in ("user", "assistant", "system"):
                messages.append({
                    "role": msg["role"],
                    "content": msg.get("content") or ""
                })
        
        # Add current user message
        messages.append({"role": "user", "content": user_utterance})
        
        # Generate response
        reply, suggested_action = self._generate_response(messages, user_utterance, chat_history)
        
        state["reply"] = reply
        state["suggested_action"] = suggested_action
        state["escalation"] = bool(
            suggested_action and str(suggested_action.get("action", "")).startswith("escalate_")
        )
        
        return state
    
    # ========================================
    # Helper Methods
    # ========================================
    
    def _extract_lead_context(
        self,
        context: str,
        chat_history: list[dict[str, str]],
    ) -> str:
        """Extract known information about the lead from context and history."""
        try:
            # Combine context and recent history
            combined_text = context + " " + " ".join([
                m.get("content", "") for m in chat_history[-10:]
            ])
            lower = combined_text.lower()
            
            known = {}
            missing = []
            
            # Check for budget
            import re
            dollar_matches = re.findall(r'\$\s*(\d{3,4})', combined_text)
            if dollar_matches:
                known["budget"] = f"${dollar_matches[0]}"
            elif any(k in lower for k in ["budget", "afford", "price range"]):
                known["budget"] = "mentioned"
            else:
                missing.append("budget")
            
            # Check for move timing
            months = ["january", "february", "march", "april", "may", "june", 
                     "july", "august", "september", "october", "november", "december",
                     "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
            move_found = False
            for month in months:
                if month in lower:
                    known["move_timing"] = month.title()
                    move_found = True
                    break
            
            if not move_found:
                if any(k in lower for k in ["move", "moving", "asap", "soon"]):
                    known["move_timing"] = "mentioned"
                else:
                    missing.append("move_timing")
            
            # Check for bedrooms
            if any(k in lower for k in ["studio", "efficiency"]):
                known["bedrooms"] = "studio"
            elif any(k in lower for k in ["1 bed", "1bed", "1br", "one bed"]):
                known["bedrooms"] = "1br"
            elif any(k in lower for k in ["2 bed", "2bed", "2br", "two bed"]):
                known["bedrooms"] = "2br"
            elif any(k in lower for k in ["3 bed", "3bed", "3br", "three bed"]):
                known["bedrooms"] = "3br"
            elif "bedroom" in lower or "bed" in lower:
                known["bedrooms"] = "mentioned"
            else:
                missing.append("bedrooms")
            
            # Check for areas
            areas_found = []
            area_keywords = {
                "heights": "Heights", "downtown": "Downtown", "midtown": "Midtown",
                "uptown": "Uptown", "galleria": "Galleria", "katy": "Katy",
                "spring": "Spring", "pearland": "Pearland", "sugar land": "Sugar Land",
            }
            for keyword, area_name in area_keywords.items():
                if keyword in lower:
                    areas_found.append(area_name)
            
            if areas_found:
                known["areas"] = ", ".join(areas_found[:3])
            
            # Build summary
            if known or missing:
                known_items = [f"{k}: {v}" for k, v in known.items()]
                summary = "LEAD CONTEXT SUMMARY:\n"
                if known_items:
                    summary += f"Known: {', '.join(known_items)}\n"
                if missing:
                    summary += f"Still need: {', '.join(missing[:2])}\n"
                summary += "→ Don't re-ask known info. Ask for ONE missing item naturally."
                return summary
        
        except Exception as e:
            self.logger.warning(f"Failed to extract lead context: {e}")
        
        return ""
    
    def _generate_response(
        self,
        messages: list[dict[str, str]],
        user_utterance: str,
        chat_history: list[dict[str, str]],
    ) -> tuple[str, dict[str, Any] | None]:
        """Generate response using LLM."""
        if self.llm:
            try:
                resp = self.llm.invoke(messages)
                raw = getattr(resp, "content", "").strip()
                
                # Parse JSON response
                reply, suggested_action = self._parse_json_response(raw)
                
                return reply, suggested_action
            
            except Exception as e:
                self.logger.error(f"LLM generation failed: {e}")
                return self._fallback_reply(user_utterance, chat_history), None
        else:
            return self._fallback_reply(user_utterance, chat_history), None
    
    def _parse_json_response(self, raw: str) -> tuple[str, dict[str, Any] | None]:
        """Parse JSON response from LLM.
        
        Expected format:
        {
          "outgoing_message": "response text",
          "next_action_suggested": {"action": "action_name", "reason": "..."}
        }
        """
        if not raw:
            return "", None
        
        # Find JSON in response (handle extra text)
        text = raw.strip()
        start = text.find("{")
        end = text.rfind("}")
        
        if start == -1 or end == -1 or end <= start:
            return raw, None
        
        try:
            candidate = text[start:end + 1]
            parsed = json.loads(candidate)
            
            # Extract message
            msg = parsed.get("outgoing_message", "").strip()
            
            # Extract action
            action_obj = parsed.get("next_action_suggested")
            suggested_action = None
            
            if isinstance(action_obj, dict):
                action_name = str(action_obj.get("action", "")).strip().lower()
                reason = str(action_obj.get("reason", "model_suggested")).strip()
                
                if action_name:
                    suggested_action = {"action": action_name, "reason": reason}
            
            elif isinstance(action_obj, str) and action_obj.strip():
                action_name = action_obj.strip().lower()
                suggested_action = {"action": action_name, "reason": "model_suggested"}
            
            return msg or raw, suggested_action
        
        except Exception as e:
            self.logger.debug(f"Could not parse JSON response: {e}")
            return raw, None
    
    def _fallback_reply(
        self,
        user_utterance: str,
        chat_history: list[dict[str, str]],
    ) -> str:
        """Simple fallback when LLM fails."""
        lower = (user_utterance or "").lower()
        
        if any(k in lower for k in ["approved", "approval"]):
            return "Awesome! Congratulations! Can you ask them for the locator referral form?"
        
        if any(k in lower for k in ["applied", "application"]):
            return "Great! Please list me as your locator (Ashanti, AptAmigo) and text once you submit."
        
        if any(k in lower for k in ["tour", "schedule", "visit"]):
            return "I'll check availability and follow up with times."
        
        return "I'll look into that and follow up shortly."
    
    def _format_recent_history(self, history: list[dict[str, str]]) -> str:
        """Format recent chat history for stage classification."""
        lines = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")[:100]  # Truncate long messages
            if role == "user":
                lines.append(f"Lead: {content}")
            elif role == "assistant":
                lines.append(f"Ashanti: {content}")
        return "\n".join(lines) if lines else "(no history)"
    
    # ========================================
    # Main Entry Point
    # ========================================
    
    def run(self, state: GraphState, user_utterance: str) -> GraphState:
        """Execute the agent graph for a single conversation turn.
        
        Args:
            state: Current conversation state
            user_utterance: The lead's current message
        
        Returns:
            Updated state with reply and suggested_action
        """
        config = {"configurable": {"thread_id": state.get("thread_id") or "default"}}
        inputs = {**state, "user_utterance": user_utterance}
        
        # Run the graph: classify_stage -> retrieve -> respond
        output = self.app.invoke(inputs, config)
        
        return output
