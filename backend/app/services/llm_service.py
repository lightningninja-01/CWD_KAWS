"""
LLM service — the agentic decision-making core.

Upgraded to a native tool-calling agent using Groq API.
The LLM can either call a domain tool (e.g., calendar_create_event) or 
call `send_reply` to finalize its turn and send a message.
"""
from typing import Any
import json
from groq import AsyncGroq

from app.config.settings import get_settings
from app.exceptions.custom_exceptions import LLMReasoningError
from app.graph.state import IncomingMessage, ReplyDecision, AgentAction
from app.utils.logger import get_logger

log = get_logger(__name__)


def _to_groq_tool(tool_def: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool_def["name"],
            "description": tool_def["description"],
            "parameters": tool_def["parameters"]
        }
    }

# Tools defined in OpenAI/Groq compatible schema
SEND_REPLY_TOOL = _to_groq_tool({
    "name": "send_reply",
    "description": "Send a final response back to the user on their originating channel (WhatsApp or Gmail). Always call this when you are done.",
    "parameters": {
        "type": "object",
        "properties": {
            "reply_type": {
                "type": "string",
                "description": 'One of: "text", "image", or "document".'
            },
            "text_content": {
                "type": "string",
                "description": "The message text to send. Required."
            },
            "media_asset_key": {
                "type": "string",
                "description": "Exact key from media library if image/document, else empty string."
            },
            "sentiment_score": {
                "type": "number",
                "description": "0.0 (calm) to 1.0 (angry), based on customer tone."
            },
            "needs_human": {
                "type": "boolean",
                "description": "True if customer explicitly wants a human or is extremely frustrated."
            },
            "reasoning": {
                "type": "string",
                "description": "Brief internal rationale."
            }
        },
        "required": ["reply_type", "text_content", "sentiment_score", "needs_human", "reasoning"]
    }
})

CALENDAR_CHECK_TOOL = _to_groq_tool({
    "name": "calendar_check_availability",
    "description": "Check YOUR business's primary calendar for events to see if you are free. You already have access to this calendar. Never ask the customer to connect their calendar.",
    "parameters": {
        "type": "object",
        "properties": {
            "time_min": {"type": "string", "description": "ISO 8601 start time (e.g. 2026-09-20T10:00:00Z)"},
            "time_max": {"type": "string", "description": "ISO 8601 end time"},
            "timezone": {"type": "string", "description": "e.g. UTC, America/New_York"}
        },
        "required": ["time_min", "time_max"]
    }
})

CALENDAR_CREATE_TOOL = _to_groq_tool({
    "name": "calendar_create_event",
    "description": "Create a new event on YOUR business's primary calendar. You already have access to it.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start_time": {"type": "string", "description": "ISO 8601 start time"},
            "end_time": {"type": "string", "description": "ISO 8601 end time"},
            "timezone": {"type": "string"},
            "description": {"type": "string"},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of email addresses to invite. You MUST include the customer's email address (found in the chat history) so they receive a formal Google Calendar invite."
            }
        },
        "required": ["title", "start_time", "end_time"]
    }
})

GMAIL_SEND_TOOL = _to_groq_tool({
    "name": "gmail_send_email",
    "description": "Send a new email.",
    "parameters": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"}
        },
        "required": ["to", "subject", "body"]
    }
})

GMAIL_REPLY_TOOL = _to_groq_tool({
    "name": "gmail_reply_to_email",
    "description": "Reply to an existing email thread.",
    "parameters": {
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "The ID of the email being replied to"},
            "body": {"type": "string", "description": "The body of the reply"}
        },
        "required": ["message_id", "body"]
    }
})


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self._model = settings.groq_model
        self._handover_threshold = settings.handover_sentiment_threshold

    async def decide_action(
        self,
        *,
        system_prompt: str,
        media_library: dict[str, str],
        history: list[dict],
        incoming_message: IncomingMessage,
        tool_history: list[dict],
        media_description: str | None,
    ) -> AgentAction:
        prompt = self._build_prompt(
            system_prompt=system_prompt,
            media_library=media_library,
            history=history,
            incoming_message=incoming_message,
            tool_history=tool_history,
            media_description=media_description,
        )

        tools = [
            SEND_REPLY_TOOL,
            CALENDAR_CHECK_TOOL,
            CALENDAR_CREATE_TOOL,
            GMAIL_SEND_TOOL,
            GMAIL_REPLY_TOOL,
        ]

        import asyncio
        max_retries = 3
        backoff_seconds = 0.5

        for attempt in range(max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    tools=tools,
                    tool_choice="auto",
                )
                
                message = response.choices[0].message
                
                # Check if the model called a function
                if message.tool_calls:
                    fc = message.tool_calls[0].function
                    tool_name = fc.name
                    args = json.loads(fc.arguments) if fc.arguments else {}
                    
                    if tool_name == "send_reply":
                        decision = ReplyDecision(
                            reply_type=args.get("reply_type", "text"),
                            text_content=args.get("text_content", ""),
                            media_asset_key=args.get("media_asset_key", "") or None,
                            sentiment_score=float(args.get("sentiment_score", 0.0)),
                            needs_human=bool(args.get("needs_human", False)),
                            reasoning=args.get("reasoning", "")
                        )
                        if decision.sentiment_score >= self._handover_threshold:
                            decision.needs_human = True
                            
                        return AgentAction(
                            action_type="RESPOND",
                            reply_decision=decision
                        )
                    else:
                        return AgentAction(
                            action_type="TOOL_CALL",
                            tool_name=tool_name,
                            tool_args=args
                        )
                
                # If no function call, default to text response
                text = message.content or "I cannot answer this right now."
                return AgentAction(
                    action_type="RESPOND",
                    reply_decision=ReplyDecision(
                        reply_type="text",
                        text_content=text,
                        sentiment_score=0.0,
                        needs_human=False,
                        reasoning="Fell back to text because no function was called."
                    )
                )

            except Exception as exc:  # noqa: BLE001
                exc_str = str(exc)
                is_transient = any(status in exc_str for status in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded", "rate_limit"])
                
                if is_transient and attempt < max_retries - 1:
                    log.warning(
                        f"Groq API transient error (attempt {attempt + 1}/{max_retries}): {exc!r}. "
                        f"Retrying in {backoff_seconds}s..."
                    )
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds *= 2
                else:
                    log.error(f"Groq API failed after {attempt + 1} attempts: {exc!r}")
                    raise LLMReasoningError(str(exc)) from exc

        raise LLMReasoningError("Exhausted retries")

    def _build_prompt(
        self,
        *,
        system_prompt: str,
        media_library: dict[str, str],
        history: list[dict],
        incoming_message: IncomingMessage,
        tool_history: list[dict],
        media_description: str | None,
    ) -> str:
        media_keys_description = ", ".join(media_library.keys()) if media_library else "(none available)"
        
        history_lines = []
        for turn in history:
            content = turn["text"] or f"[{turn.get('message_type', 'message')}]"
            history_lines.append(f"{turn['sender']}: {content}")
        history_text = "\n".join(history_lines) or "(no prior messages)"
        
        tool_lines = []
        for th in tool_history:
            tool_lines.append(f"Called {th['tool_name']} with args {th.get('args')}. Result: {th.get('result', th.get('error'))}")
        tool_text = "\n".join(tool_lines) if tool_lines else "(none yet)"

        media_note = f"\nThe customer's inbound image was described as: {media_description}" if media_description else ""

        return f"""{system_prompt}

You are a WhatsApp/Gmail sales/support agent representing a business. Decide how to respond to the customer's latest message.

Channel: {incoming_message.channel}
Customer Contact (Phone/Email): {incoming_message.sender_id}
Available media assets (choose by key): {media_keys_description}

Conversation history (most recent last):
{history_text}

Customer's latest message: "{incoming_message.text_body or f'[{incoming_message.message_type} message]'}"{media_note}

Tools called so far in this turn:
{tool_text}

Instructions:
1. IMPORTANT CALENDAR RULES: You already have full access to YOUR business's Google Calendar. NEVER ask the customer to connect their calendar. You are booking meetings on YOUR calendar with the customer.
2. ATTENDEES RULE: When booking a calendar event, you MUST invite the customer by adding their email to the `attendees` list. If their Customer Contact above is an email address, use it. If they are on WhatsApp (phone number) and you don't know their email address, you MUST politely ask them for their email address FIRST before calling `calendar_create_event`.
3. If you need information from your Google Calendar or need to act, call the relevant tool (e.g., calendar_check_availability).
4. If you have enough information, or if you just completed a tool call and have the result, you MUST call `send_reply` to respond to the customer. Do not write plain text back; use the `send_reply` tool.
"""
