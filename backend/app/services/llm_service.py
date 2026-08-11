"""
LLM service — the agentic decision-making core.

Uses Gemini's structured JSON output rather than
free-text + regex parsing, so the LLM Reasoning node always receives a
validated ReplyDecision or a clear failure — never a half-parseable string.
"""
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.exceptions.custom_exceptions import LLMReasoningError
from app.graph.state import IncomingMessage, ReplyDecision
from app.utils.logger import get_logger

log = get_logger(__name__)


class GeminiReplyDecision(BaseModel):
    """Gemini-compatible response schema.

    google-genai 0.3.0 rejects nullable/union fields in response_schema, so
    media_asset_key uses an empty string for "no media" and is normalized back
    to ReplyDecision at the service boundary.
    """

    reply_type: str = Field(description='One of: "text", "image", or "document".')
    text_content: str = Field(description="The message text. Always populated, even for media replies.")
    media_asset_key: str = Field(
        default="",
        description="Exact media key for image/document replies, or an empty string for text replies.",
    )
    sentiment_score: float = Field(
        ge=0.0,
        le=1.0,
        description="0.0 = calm/satisfied, 1.0 = highly frustrated.",
    )
    needs_human: bool = Field(default=False)
    reasoning: str = Field(default="", description="Brief internal rationale.")


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model
        self._handover_threshold = settings.handover_sentiment_threshold

    async def decide_reply(
        self,
        *,
        system_prompt: str,
        media_library: dict[str, str],
        history: list[dict],
        incoming_message: IncomingMessage,
        media_description: str | None,
    ) -> ReplyDecision:
        prompt = self._build_prompt(
            system_prompt=system_prompt,
            media_library=media_library,
            history=history,
            incoming_message=incoming_message,
            media_description=media_description,
        )

        import asyncio
        max_retries = 3
        backoff_seconds = 0.5

        for attempt in range(max_retries):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiReplyDecision,
                        temperature=0.3,
                    ),
                )
                parsed = response.parsed
                if not parsed:
                    raise LLMReasoningError("Gemini returned empty or invalid response.")
                decision = self._normalize_decision(parsed)
                break
            except Exception as exc:  # noqa: BLE001
                exc_str = str(exc)
                is_transient = any(status in exc_str for status in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded"])
                
                if is_transient and attempt < max_retries - 1:
                    log.warning(
                        f"Gemini API transient error (attempt {attempt + 1}/{max_retries}): {exc!r}. "
                        f"Retrying in {backoff_seconds}s..."
                    )
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds *= 2  # Exponential backoff
                else:
                    log.error(f"Gemini API failed after {attempt + 1} attempts: {exc!r}")
                    raise LLMReasoningError(str(exc)) from exc

        # Belt-and-suspenders: sentiment threshold enforced in code too, not
        # solely trusted from the model's own needs_human flag.
        if decision.sentiment_score >= self._handover_threshold:
            decision.needs_human = True

        return decision

    def _normalize_decision(self, decision: GeminiReplyDecision | ReplyDecision) -> ReplyDecision:
        media_asset_key = decision.media_asset_key.strip() or None
        return ReplyDecision(
            reply_type=decision.reply_type,
            text_content=decision.text_content,
            media_asset_key=media_asset_key,
            sentiment_score=decision.sentiment_score,
            needs_human=decision.needs_human,
            reasoning=decision.reasoning,
        )

    def _build_prompt(
        self,
        *,
        system_prompt: str,
        media_library: dict[str, str],
        history: list[dict],
        incoming_message: IncomingMessage,
        media_description: str | None,
    ) -> str:
        media_keys_description = ", ".join(media_library.keys()) if media_library else "(none available)"
        history_lines = []
        for turn in history:
            content = turn["text"] or f"[{turn['message_type']}]"
            history_lines.append(f"{turn['sender']}: {content}")
        history_text = "\n".join(history_lines) or "(no prior messages)"

        media_note = f"\nThe customer's inbound image was described as: {media_description}" if media_description else ""

        return f"""{system_prompt}

You are a WhatsApp sales/support agent. Decide how to respond to the customer's latest message.

Available media assets (choose by key, only if genuinely relevant to the request): {media_keys_description}

Conversation history (most recent last):
{history_text}

Customer's latest message: "{incoming_message.text_body or f'[{incoming_message.message_type} message]'}"{media_note}

Decide:
- reply_type: "text" for a plain reply, "image" or "document" if the customer is asking for a visual/catalog/asset that matches one of the available media keys.
- text_content: your reply text (always required, even for media replies — used as the caption).
- media_asset_key: the exact key from the available media assets if reply_type is image/document, otherwise null.
- sentiment_score: 0.0 (calm) to 1.0 (highly frustrated/angry), based on the customer's tone across this conversation.
- needs_human: true only if the customer explicitly wants a human, or frustration is severe and unresolved.
- reasoning: one short sentence explaining your choice (internal only, not sent to the customer).
"""
