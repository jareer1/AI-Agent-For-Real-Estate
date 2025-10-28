from __future__ import annotations

from typing import Any, TypedDict
import logging
import re

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from ..schemas.common import StageV2, map_text_to_stage_v2
from .rag import RAGService
from ..core.config import get_settings
from .prompts import get_system_prompt

# Pattern to strip most emoji symbols from generated text
_EMOJI_PATTERN = re.compile(r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAD6\U0001FAE0-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]+")


class GraphState(TypedDict, total=False):
    """State object passed through the agent graph nodes.
    
    Attributes:
        thread_id: Unique identifier for the conversation thread
        stage: Current stage in the lead journey (qualifying, working, touring, etc.)
        chat_history: List of previous messages in the conversation
        lead_profile: Extracted information about the lead (budget, move date, etc.)
        user_utterance: Current message from the lead
        context: Retrieved context from RAG for response generation
        reply: Generated response from the agent
        suggested_action: Optional action to be taken (escalate_pricing, request_application, etc.)
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
    
    The graph follows a simple three-node pipeline:
    1. Classify Stage: Determine the current stage in the lead journey
    2. Retrieve Context: Use RAG to fetch relevant examples from training data
    3. Respond: Generate a response in Ashanti's style using context and prompts
    """
    
    def __init__(self) -> None:
        """Initialize the agent graph with LLM, RAG service, and graph structure."""
        self.logger = logging.getLogger(__name__)
        self.rag = RAGService()
        
        settings = get_settings()
        
        # Initialize LLM with API key if available
        if settings.openai_api_key:
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.5,
                api_key=settings.openai_api_key,
                top_p=0.8,
                frequency_penalty=0.3,
                presence_penalty=0.5,
            )
        else:
            # Fallback LLM service for testing
            from .llm import LLMService
            self.llm_service = LLMService()
            self.llm = None

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
        """Node 1: Classify the current stage based on user utterance.
        
        Uses keyword matching to determine where the lead is in their journey
        (qualifying, working, touring, applied, approved, closed, post_close_nurture).
        """
        text = state.get("user_utterance") or ""
        stage = map_text_to_stage_v2(text, state.get("stage"))
        state["stage"] = stage
        self.logger.debug(f"Stage classified: {stage.value if hasattr(stage, 'value') else stage}")
        return state

    def _retrieve(self, state: GraphState) -> GraphState:
        """Node 2: Retrieve relevant context from training data using RAG.
        
        Fetches similar conversations from the training data to provide examples
        of how Ashanti responds in similar situations. Prefers agent messages
        and matches by thread, stage, and semantic similarity.
        """
        text = state.get("user_utterance") or ""
        stage = state.get("stage")
        stage_str = stage.value if hasattr(stage, "value") else str(stage) if stage else None
        
        # Retrieve relevant documents from training data
        docs = self.rag.retrieve(
            text,
            top_k=8,
            thread_id=state.get("thread_id"),
            stage=stage_str,
            prefer_agent=True,
            chat_history=state.get("chat_history"),
        )
        
        # Combine document text into context string
        ctx = "\n".join([d.get("clean_text") or d.get("text") or "" for d in docs])
        state["context"] = ctx
        
        # Log retrieval summary for debugging
        if docs:
            meta = [
                {
                    "role": d.get("role"),
                    "stage": d.get("stage"),
                    "score": round(d.get("score", 0), 3),
                    "thread": d.get("thread_id", "")[:8],
                }
                for d in docs[:3]
            ]
            self.logger.info(f"Retrieved {len(docs)} docs, context length: {len(ctx)}")
            self.logger.debug(f"Top docs: {meta}")
        
        return state

    def _respond(self, state: GraphState) -> GraphState:
        """Node 3: Generate a response in Ashanti's style.
        
        Uses the base system prompt, stage-specific guidance, lead context, and
        retrieved examples to generate a natural, conversational response that
        mimics Ashanti's communication style.
        """
        stage = state.get("stage") or StageV2.qualifying
        context = state.get("context") or ""
        user_utterance = state.get("user_utterance") or ""
        chat_history = state.get("chat_history") or []
        
        # Build the prompt with all components
        messages = self._build_prompt_messages(
            stage=stage,
            context=context,
            user_utterance=user_utterance,
            chat_history=chat_history,
        )
        
        # Generate response using LLM
        reply = self._generate_response(messages, context)
        
        # Detect any suggested actions based on the reply
        suggested_action = self._detect_suggested_action(reply, stage)
        
        state["reply"] = reply
        state["suggested_action"] = suggested_action
        return state
    
    # ========================================
    # Helper Methods for Response Generation
    # ========================================
    def _sanitize_style(self, text: str) -> str:
        """Remove emojis and tame punctuation to match preferred tone."""
        if not text:
            return text
        try:
            # Remove zero-width characters and emojis; collapse excessive exclamations
            text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
            text = _EMOJI_PATTERN.sub("", text)
            text = re.sub(r"!{2,}", "!", text)
            return text.strip()
        except Exception:
            return text
    
    def _build_prompt_messages(
        self,
        stage: StageV2,
        context: str,
        user_utterance: str,
        chat_history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Build the complete message array for the LLM.
        
        Combines:
        - Base system prompt with Ashanti's identity and instructions
        - Stage-specific guidance
        - Extracted lead context summary
        - Retrieved style examples
        - Few-shot dialogue examples
        - Recent chat history
        - Current user utterance
        """
        # Get base system prompt
        base_prompt = get_system_prompt()
        
        # Get stage-specific instructions
        stage_guidance = self._get_stage_guidance(stage)
        
        # Extract lead context summary
        lead_summary = self._extract_lead_context(context, chat_history)
        
        # Build system message
        system_content = f"{base_prompt}\n\n{stage_guidance}"
        
        if lead_summary:
            system_content += f"\n\n{lead_summary}"
        
        if context:
            system_content += f"\n\nRetrieved Context (similar past conversations):\n{context}"
        
        messages = [{"role": "system", "content": system_content}]
        
        # Add few-shot dialogue examples for style guidance
        dialogue_examples = self._get_dialogue_examples(user_utterance, stage)
        messages.extend(dialogue_examples)
        
        # Add recent chat history (last 12 messages)
        for msg in chat_history[-12:]:
            if msg.get("role") in ("user", "assistant", "system"):
                messages.append({
                    "role": msg["role"],
                    "content": msg.get("content") or ""
                })
        
        # Add current user message
        messages.append({"role": "user", "content": user_utterance})
        
        return messages
    
    def _get_stage_guidance(self, stage: StageV2) -> str:
        """Get stage-specific instructions for response generation."""
        stage_guidance = {
            StageV2.qualifying: (
                "QUALIFYING STAGE:\n"
                "Focus on gathering essential info conversationally: move timeline, budget, bedrooms, preferred areas.\n"
                "Ask ONE question at a time. Don't ask for info already in context.\n"
                "Keep it natural and warm, like a helpful friend."
            ),
            StageV2.working: (
                "WORKING STAGE:\n"
                "The lead has provided basics. Share property options, ask for favorites, or offer to send more.\n"
                "Check if they've reviewed what you sent. Move toward scheduling tours."
            ),
            StageV2.touring: (
                "TOURING STAGE:\n"
                "Propose specific tour times, confirm availability, or follow up on completed tours.\n"
                "Ask how tours went and which properties stood out."
            ),
            StageV2.applied: (
                "APPLIED STAGE:\n"
                "Application is in progress. Check status, offer help with documents.\n"
                "Ensure they listed Ashanti/AptAmigo on the application."
            ),
            StageV2.approved: (
                "APPROVED STAGE:\n"
                "Celebrate! Confirm lease details, share move-in info.\n"
                "Request lease start date for rebate processing."
            ),
            StageV2.closed: (
                "CLOSED STAGE:\n"
                "Lease signed or lost. If won, congratulate and offer post-move support.\n"
                "If lost, thank them and stay connected for future needs."
            ),
            StageV2.post_close_nurture: (
                "POST-CLOSE NURTURE:\n"
                "Check in warmly, ask for referrals (gently), offer renewal support.\n"
                "Keep it light and helpful, not pushy."
            ),
        }
        
        return stage_guidance.get(stage, stage_guidance[StageV2.qualifying])
    
    def _extract_lead_context(
        self,
        context: str,
        chat_history: list[dict[str, str]],
    ) -> str:
        """Extract what we know about the lead from context and history.
        
        Identifies known information (budget, move timing, bedrooms, areas, properties)
        and what's still missing, to avoid redundant questions and guide next steps.
        """
        try:
            # Combine context and recent history
            combined_text = context + " " + " ".join([
                m.get("content", "") for m in chat_history[-10:]
            ])
            lower = combined_text.lower()
            
            known = {}
            missing = []
            
            # Check for budget info
            if any(keyword in lower for keyword in [
                "$", "budget", "price", "rent",
                "1200", "1400", "1500", "1800", "2000"
            ]):
                known["budget"] = "mentioned"
            else:
                missing.append("budget")
            
            # Check for move timing
            if any(keyword in lower for keyword in [
                "move", "move-in", "lease end", "lease ending",
                "may", "june", "july", "august", "month"
            ]):
                known["move_timing"] = "mentioned"
            else:
                missing.append("move_timing")
            
            # Check for bedroom preferences
            if any(keyword in lower for keyword in [
                "bedroom", "bed", "1/1", "2/2", "studio", "1 bed", "2 bed"
            ]):
                known["bedrooms"] = "mentioned"
            else:
                missing.append("bedrooms")
            
            # Check for area preferences
            if any(keyword in lower for keyword in [
                "heights", "downtown", "katy", "galleria", "midtown",
                "spring", "humble", "area", "location"
            ]):
                known["areas"] = "mentioned"
            
            # Check for property mentions
            properties = []
            for prop in ["harlow", "pearl", "district", "broadstone", "filament",
                        "lenox", "peri", "espria", "everlee", "crawford"]:
                if prop in lower:
                    properties.append(prop.title())
            
            if properties:
                known["properties"] = ", ".join(properties[:3])
            
            # Build summary
            if known or missing:
                known_items = [
                    f"{k}: {v}" if v != "mentioned" else k
                    for k, v in known.items()
                ]
                summary = "LEAD CONTEXT SUMMARY:\n"
                if known_items:
                    summary += f"Known: {', '.join(known_items)}\n"
                if missing:
                    summary += f"Still need: {', '.join(missing[:2])}\n"
                summary += "→ Don't re-ask known info. Move the conversation forward."
                return summary
        
        except Exception as e:
            self.logger.warning(f"Failed to extract lead context: {e}")
        
        return ""
    
    def _get_dialogue_examples(
        self,
        user_utterance: str,
        stage: StageV2,
    ) -> list[dict[str, str]]:
        """Retrieve few-shot dialogue examples for style guidance.
        
        Returns 1-2 lead→agent message pairs from similar situations to guide
        tone and structure (not for copying verbatim).
        """
        try:
            stage_str = stage.value if hasattr(stage, "value") else str(stage)
            pairs = self.rag.retrieve_dialogue_examples(
                query=user_utterance,
                stage=stage_str,
                top_k=2,
                prefer_additional=True,
            )
            
            messages = []
            for pair in pairs:
                lead_msg = pair.get("lead", "").strip()
                agent_msg = pair.get("agent", "").strip()
                if lead_msg and agent_msg:
                    messages.append({"role": "user", "content": lead_msg})
                    messages.append({"role": "assistant", "content": agent_msg})
            
            return messages
        
        except Exception as e:
            self.logger.warning(f"Failed to retrieve dialogue examples: {e}")
            return []
    
    def _generate_response(
        self,
        messages: list[dict[str, str]],
        context: str,
    ) -> str:
        """Generate response using LLM with fallback to simple generation."""
        if self.llm:
            try:
                resp = self.llm.invoke(messages)
                reply = getattr(resp, "content", "").strip()
                
                # Extract outgoing message if response is in JSON format
                reply = self._extract_message_from_json(reply)
                reply = self._sanitize_style(reply)
                return reply
            
            except Exception as e:
                self.logger.error(f"LLM generation failed: {e}")
                return "I'd be happy to help! Let me know what you're looking for."
        
        else:
            # Fallback LLM service for testing
            user_content = messages[-1]["content"] if messages else ""
            return self._sanitize_style(self.llm_service.generate(user_content, context))
    
    def _extract_message_from_json(self, reply: str) -> str:
        """Extract outgoing_message from JSON response if present.
        
        The system prompt requests JSON output with reasoning_steps, outgoing_message,
        crm_stage, and next_action_suggested. If the LLM returns JSON, extract the
        actual message text.
        """
        if not reply or not reply.strip().startswith("{"):
            return reply
        
        try:
            import json
            parsed = json.loads(reply)
            
            # Extract the actual message
            if "outgoing_message" in parsed:
                return parsed["outgoing_message"].strip()
        
        except Exception as e:
            self.logger.debug(f"Could not parse JSON response: {e}")
        
        return reply
    
    def _detect_suggested_action(
        self,
        reply: str,
        stage: StageV2,
    ) -> dict[str, Any] | None:
        """Detect if any action should be suggested based on the response.

        Looks for keywords indicating:
        - request_application: application-related language
        - escalate_pricing: pricing uncertainty ("I'll check", "let me confirm")
        """
        lower_reply = reply.lower()
        
        # Application intent
        if stage in (StageV2.working, StageV2.applied):
            if any(keyword in lower_reply for keyword in [
                "apply", "application", "submit"
            ]):
                return {"action": "request_application"}
        
        # Escalate pricing (only if explicitly stating uncertainty)
        pricing_keywords = ["price", "pricing", "fee", "rate", "cost"]
        uncertainty_phrases = ["i'll confirm", "i'll check", "let me confirm", "let me check"]
        
        if (any(phrase in lower_reply for phrase in uncertainty_phrases) and
            any(keyword in lower_reply for keyword in pricing_keywords)):
            return {"action": "escalate_pricing"}
        
        return None

    # ========================================
    # Main Entry Point
    # ========================================
    
    def run(self, state: GraphState, user_utterance: str) -> GraphState:
        """Execute the agent graph for a single conversation turn.
        
        Args:
            state: Current conversation state (thread_id, stage, chat_history, etc.)
            user_utterance: The lead's current message
        
        Returns:
            Updated state with reply and suggested_action
        """
        config = {"configurable": {"thread_id": state.get("thread_id") or "default"}}
        inputs = {**state, "user_utterance": user_utterance}
        
        # Run the graph: classify_stage -> retrieve -> respond
        output = self.app.invoke(inputs, config)
        
        return output


