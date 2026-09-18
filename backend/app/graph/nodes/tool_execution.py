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
        # Since we use customer_phone as a proxy for user in this simple setup,
        # or we might need an actual user_id. For now we will use customer_phone
        # or maybe the system allows the agent owner to execute on behalf of tenant.
        # Wait, the prompt says "User-level Google Integration". Let's pass the customer_phone as user_id for now, 
        # or a hardcoded 'admin' user id if this is the business owner's tools.
        # Let's assume the tenant is the one who connected OAuth, so user_id = tenant_id for single-user tenants,
        # or if we have a real user_id we should use it. For WhatsApp webhook, the "user" is the business owner.
        # So we'll use `tenant_id` as the `user_id` representing the business owner's connection for now.
        user_id = tenant_id
        if tenant_id == "demo_tenant":
            user_id = "demo_user"
        
        log.info(f"Executing tool {tool_name} with args {tool_args}")
        
        tool_history = state.get("tool_history", [])
        
        try:
            if tool_name not in TOOLS:
                raise ValueError(f"Unknown tool: {tool_name}")
                
            func = TOOLS[tool_name]
            
            # Execute
            result = await func(tenant_id=tenant_id, user_id=user_id, **tool_args)
            
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
