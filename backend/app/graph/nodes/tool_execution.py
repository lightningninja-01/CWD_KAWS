from typing import Callable

from app.graph.dependencies import GraphDependencies
from app.graph.state import ConversationState
from app.services.tools.calendar_tools import (
    calendar_check_availability,
    calendar_create_event,
    calendar_update_event,
    calendar_cancel_event
)
from app.services.tools.gmail_tools import (
    gmail_search_messages,
    gmail_get_message,
    gmail_send_email,
    gmail_reply_to_email
)
from app.utils.logger import get_logger

log = get_logger(__name__)

# Map tool names to actual functions
TOOLS = {
    "calendar_check_availability": calendar_check_availability,
    "calendar_create_event": calendar_create_event,
    "calendar_update_event": calendar_update_event,
    "calendar_cancel_event": calendar_cancel_event,
    "gmail_search_messages": gmail_search_messages,
    "gmail_get_message": gmail_get_message,
    "gmail_send_email": gmail_send_email,
    "gmail_reply_to_email": gmail_reply_to_email,
}

def build_tool_execution_node(deps: GraphDependencies) -> Callable[[ConversationState], dict]:
    """
    Executes the tool requested by the LLM and appends the result to tool_history.
    """
    async def tool_execution_node(state: ConversationState) -> dict:
        if "error" in state:
            return {}

        action = state.get("agent_action")
        if not action or action.action_type != "TOOL_CALL":
            return {}

        tool_name = action.tool_name
        tool_args = action.tool_args or {}
        
        tenant_id = state["tenant_id"]
        # For the Showcase MVP: Since the frontend only allows connecting Google to the 
        # "demo_tenant" / "demo_user", we route all tool executions to this single integration.
        # Once a real Admin dashboard is built to connect actual tenants, this should revert 
        # to using the actual tenant_id and user_id.
        integration_tenant = "demo_tenant"
        integration_user = "demo_user"
        
        log.info(f"Executing tool {tool_name} with args {tool_args}")
        
        tool_history = state.get("tool_history", [])
        
        try:
            if tool_name not in TOOLS:
                raise ValueError(f"Unknown tool: {tool_name}")
                
            func = TOOLS[tool_name]
            
            # Execute
            result = await func(tenant_id=integration_tenant, user_id=integration_user, **tool_args)
            
            tool_history.append({
                "tool_name": tool_name,
                "args": tool_args,
                "result": result,
                "status": "success"
            })
            log.info(f"Tool {tool_name} succeeded.")
            
        except Exception as e:
            log.error(f"Tool {tool_name} failed: {e}")
            tool_history.append({
                "tool_name": tool_name,
                "args": tool_args,
                "error": str(e),
                "status": "error"
            })
            
        return {"tool_history": tool_history}

    return tool_execution_node
