"""
LangGraph state definition.

Every node reads/writes a well-typed slice of this state — no ad-hoc dict
mutation. `error` is a first-class field so any node can short-circuit
gracefully (the Dispatcher sends a fallback message) instead of the graph
crashing and leaving the customer with no response and typing stuck ON.
"""
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class IncomingMessage(BaseModel):
    """Normalized inbound message — decoupled from raw webhook shapes."""

    meta_message_id: str
    from_phone: str # Will hold email address if channel is gmail
    channel: Literal["whatsapp", "gmail"] = "whatsapp"
    message_type: Literal["text", "image", "document", "email"]
    text_body: str | None = None
    media_id: str | None = None
    media_mime_type: str | None = None


class ReplyDecision(BaseModel):
    """Structured output for the final text/media reply."""

    reply_type: Literal["text", "image", "document"]
    text_content: str = Field(description="The message text. Always populated.")
    media_asset_key: str | None = Field(default=None)
    sentiment_score: float = Field(ge=0.0, le=1.0, default=0.0)
    needs_human: bool = Field(default=False)
    reasoning: str = Field(default="")


class AgentAction(BaseModel):
    """Unified action abstraction from the agent."""
    action_type: Literal["RESPOND", "TOOL_CALL", "HUMAN_APPROVAL", "HANDOVER"]
    
    # Populated if action_type == "RESPOND" or "HANDOVER"
    reply_decision: ReplyDecision | None = None
    
    # Populated if action_type == "TOOL_CALL"
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    
    # Populated if action_type == "HUMAN_APPROVAL"
    approval_metadata: dict[str, Any] | None = None


class DispatchResult(BaseModel):
    success: bool
    meta_message_id: str | None = None
    error_message: str | None = None


class ConversationState(TypedDict, total=False):
    tenant_id: str
    session_id: str
    customer_phone: str
    phone_number_id: str
    channel: Literal["whatsapp", "gmail"]

    incoming_message: IncomingMessage
    inbound_message_doc_id: str

    tenant_system_prompt: str
    media_library: dict[str, str]
    history: list[dict[str, Any]]
    
    # --- Tool Execution State ---
    tool_history: list[dict[str, Any]]  # Tracks tools called during this turn
    agent_action: AgentAction | None
    
    media_description: str | None
    reply_decision: ReplyDecision
    dispatch_result: DispatchResult
    error: str | None


