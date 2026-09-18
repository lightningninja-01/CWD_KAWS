"""
Gmail Agent Tools.
Exposes structured functions for the agent to interact with Gmail.
Authentication and token refresh are handled securely on the backend.
"""
from typing import Any, Dict, List
import httpx
import base64
from email.message import EmailMessage

from app.database.connection import mongo_connection
from app.database.repositories.integration_repository import IntegrationRepository
from app.services.google_oauth import GoogleOAuthService

oauth_service = GoogleOAuthService()

class GmailToolError(Exception):
    pass


async def _get_gmail_client(tenant_id: str, user_id: str) -> httpx.AsyncClient:
    """Helper to get an authenticated HTTP client for a user's Gmail."""
    repo = IntegrationRepository(mongo_connection.db)
    integration = await repo.get_by_user(tenant_id, user_id)
    
    if not integration:
        raise GmailToolError("Google account is not connected. Please connect your account first.")
        
    access_token = await oauth_service.ensure_valid_token(integration, repo)
    
    return httpx.AsyncClient(
        base_url="https://gmail.googleapis.com/gmail/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15.0
    )


async def gmail_search_messages(
    tenant_id: str,
    user_id: str,
    query: str,
    max_results: int = 5
) -> Dict[str, Any]:
    """
    Search for emails using standard Gmail query syntax.
    Returns message IDs and snippets.
    """
    async with await _get_gmail_client(tenant_id, user_id) as client:
        response = await client.get("/messages", params={"q": query, "maxResults": max_results})
        
        if response.status_code != 200:
            raise GmailToolError(f"Failed to search Gmail: {response.text}")
            
        messages = response.json().get("messages", [])
        if not messages:
            return {"results": [], "query": query, "message": "No messages found."}
            
        # Fetch snippets for the found messages
        results = []
        for msg in messages:
            msg_id = msg["id"]
            msg_resp = await client.get(f"/messages/{msg_id}", params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]})
            if msg_resp.status_code == 200:
                data = msg_resp.json()
                headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
                results.append({
                    "id": msg_id,
                    "threadId": data.get("threadId"),
                    "snippet": data.get("snippet"),
                    "subject": headers.get("Subject", "(No Subject)"),
                    "from": headers.get("From", "Unknown Sender"),
                    "date": headers.get("Date", "")
                })
                
        return {"query": query, "results": results}


async def gmail_get_message(
    tenant_id: str,
    user_id: str,
    message_id: str
) -> Dict[str, Any]:
    """
    Get the full content of a specific email message.
    """
    async with await _get_gmail_client(tenant_id, user_id) as client:
        # Request full format to extract body
        response = await client.get(f"/messages/{message_id}", params={"format": "full"})
        
        if response.status_code != 200:
            raise GmailToolError(f"Failed to get message: {response.text}")
            
        data = response.json()
        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        
        # Extract body (simplistic approach for plain text)
        body = ""
        payload = data.get("payload", {})
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
        elif "body" in payload and "data" in payload["body"]:
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
            
        return {
            "id": data.get("id"),
            "threadId": data.get("threadId"),
            "subject": headers.get("Subject", "(No Subject)"),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body
        }


async def gmail_send_email(
    tenant_id: str,
    user_id: str,
    to: str,
    subject: str,
    body: str
) -> Dict[str, Any]:
    """
    Send a new email.
    """
    message = EmailMessage()
    message.set_content(body)
    message["To"] = to
    message["Subject"] = subject
    # 'From' will automatically be resolved by Google to the authenticated user's email

    raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    
    async with await _get_gmail_client(tenant_id, user_id) as client:
        response = await client.post("/messages/send", json={"raw": raw_msg})
        
        if response.status_code != 200:
            raise GmailToolError(f"Failed to send email: {response.text}")
            
        return {
            "status": "sent",
            "message_id": response.json().get("id"),
            "thread_id": response.json().get("threadId"),
            "recipient": to,
            "subject": subject
        }


async def gmail_reply_to_email(
    tenant_id: str,
    user_id: str,
    message_id: str,
    body: str
) -> Dict[str, Any]:
    """
    Reply to an existing email, preserving the thread.
    """
    async with await _get_gmail_client(tenant_id, user_id) as client:
        # Need to fetch the original message to get Message-ID, Subject, and References headers
        orig_resp = await client.get(f"/messages/{message_id}", params={"format": "metadata", "metadataHeaders": ["Message-ID", "References", "Subject", "From", "To"]})
        
        if orig_resp.status_code != 200:
            raise GmailToolError(f"Failed to fetch original message for reply: {orig_resp.text}")
            
        orig_data = orig_resp.json()
        headers = {h["name"].lower(): h["value"] for h in orig_data.get("payload", {}).get("headers", [])}
        
        thread_id = orig_data.get("threadId")
        orig_message_id = headers.get("message-id", "")
        references = headers.get("references", "")
        orig_subject = headers.get("subject", "")
        reply_to = headers.get("from", "")
        
        new_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"
        new_references = f"{references} {orig_message_id}".strip() if references else orig_message_id
        
        message = EmailMessage()
        message.set_content(body)
        message["To"] = reply_to
        message["Subject"] = new_subject
        message["In-Reply-To"] = orig_message_id
        message["References"] = new_references
        
        raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        payload = {"raw": raw_msg, "threadId": thread_id}
        
        response = await client.post("/messages/send", json=payload)
        
        if response.status_code != 200:
            raise GmailToolError(f"Failed to send reply: {response.text}")
            
        return {
            "status": "replied",
            "message_id": response.json().get("id"),
            "thread_id": thread_id,
            "recipient": reply_to
        }
