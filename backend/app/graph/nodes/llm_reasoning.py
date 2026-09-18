"""
LLM Reasoning Node - the agentic core. Decides reply type (text/image/
document), which media asset to use (if any), and scores sentiment for
the handover bonus feature.
"""
from typing import Any

from app.graph.dependencies import GraphDependencies
from app.graph.state import ConversationState, ReplyDecision, AgentAction
from app.utils.logger import get_logger

log = get_logger(__name__)

FALLBACK_REPLY = (
    "Sorry, I'm having trouble generating a full response right now. "
    "I've received your message and our team will follow up shortly."
)


def build_llm_reasoning_node(deps: GraphDependencies):
    async def llm_reasoning(state: ConversationState) -> dict[str, Any]:
        tenant_id = state["tenant_id"]
        session_id = state["session_id"]
        node_log = get_logger(__name__, tenant_id=tenant_id, session_id=session_id)

        try:
            # Check if there is an error in tool execution to inject into reasoning
            # We already have tool_history in state
            action = await deps.llm_service.decide_action(
                system_prompt=state["tenant_system_prompt"],
                media_library=state["media_library"],
                history=state["history"],
                incoming_message=state["incoming_message"],
                tool_history=state.get("tool_history", []),
                media_description=state.get("media_description"),
            )
        except Exception as exc:  # noqa: BLE001
            node_log.error(f"LLM reasoning failed; sending fallback reply: {exc!r}")
            # Fallback to dispatching a standard error reply
            reply = ReplyDecision(
                reply_type="text",
                text_content=FALLBACK_REPLY,
                sentiment_score=0.0,
                needs_human=False,
                reasoning=f"Fallback reply because LLM reasoning failed: {exc!r}",
            )
            action = AgentAction(action_type="RESPOND", reply_decision=reply)

        if action.action_type == "RESPOND":
            node_log.info(
                f"LLM decided to RESPOND: reply_type={action.reply_decision.reply_type} "
                f"sentiment={action.reply_decision.sentiment_score:.2f} needs_human={action.reply_decision.needs_human}"
            )
            # Maintain backward compatibility for the dispatcher node which expects `reply_decision`
            return {"agent_action": action, "reply_decision": action.reply_decision}
        elif action.action_type == "TOOL_CALL":
            node_log.info(f"LLM decided to call TOOL: {action.tool_name}")
            return {"agent_action": action}
        else:
            return {"agent_action": action}

    return llm_reasoning


def route_agent_action(state: ConversationState) -> str:
    """Conditional-edge router based on the AgentAction."""
    action = state.get("agent_action")
    if not action:
        return "dispatch" # Fallback
        
    if action.action_type == "TOOL_CALL":
        return "tool_execution"
    elif action.action_type == "HUMAN_APPROVAL":
        # For now, pause/end (Phase 5). Will wire properly when adding approval node.
        return "dispatch" 
    elif action.action_type == "RESPOND":
        decision = state.get("reply_decision")
        if decision and decision.needs_human:
            return "handover"
        return "dispatch"
    
    return "dispatch"
