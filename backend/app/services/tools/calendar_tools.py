"""
Google Calendar Tools.
Exposes structured functions for the agent to interact with Google Calendar.
Authentication and token refresh are handled securely on the backend.
"""
from typing import Any, Dict, List
import httpx
from datetime import datetime

from app.database.connection import mongo_connection
from app.database.repositories.integration_repository import IntegrationRepository
from app.services.google_oauth import GoogleOAuthService

oauth_service = GoogleOAuthService()

class CalendarToolError(Exception):
    pass

async def _get_calendar_client(tenant_id: str, user_id: str) -> httpx.AsyncClient:
    """Helper to get an authenticated HTTP client for a user's Google Calendar."""
    repo = IntegrationRepository(mongo_connection.db)
    integration = await repo.get_by_user(tenant_id, user_id)
    
    if not integration:
        raise CalendarToolError("Google account is not connected. Please connect your account first.")
        
    access_token = await oauth_service.ensure_valid_token(integration, repo)
    
    return httpx.AsyncClient(
        base_url="https://www.googleapis.com/calendar/v3",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0
    )


async def calendar_check_availability(
    tenant_id: str, 
    user_id: str, 
    time_min: str, 
    time_max: str, 
    timezone: str = "UTC"
) -> Dict[str, Any]:
    """
    Check the user's primary calendar for events between time_min and time_max.
    time_min and time_max should be ISO 8601 strings (e.g., '2026-09-20T10:00:00Z').
    """
    async with await _get_calendar_client(tenant_id, user_id) as client:
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": timezone,
            "singleEvents": "true",
            "orderBy": "startTime"
        }
        
        response = await client.get("/calendars/primary/events", params=params)
        
        if response.status_code != 200:
            raise CalendarToolError(f"Failed to check calendar availability: {response.text}")
            
        events = response.json().get("items", [])
        
        # Summarize to save tokens and avoid leaking sensitive details unnecessarily
        busy_slots = []
        for event in events:
            start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
            end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
            if start and end:
                busy_slots.append({"start": start, "end": end, "status": event.get("status", "confirmed")})
                
        return {
            "time_checked": {"start": time_min, "end": time_max, "timezone": timezone},
            "busy_slots": busy_slots,
            "is_available": len(busy_slots) == 0
        }


async def calendar_create_event(
    tenant_id: str,
    user_id: str,
    title: str,
    start_time: str,
    end_time: str,
    timezone: str = "UTC",
    description: str = "",
    attendees: List[str] | None = None
) -> Dict[str, Any]:
    """
    Create a new event on the primary calendar.
    """
    payload = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_time, "timeZone": timezone},
        "end": {"dateTime": end_time, "timeZone": timezone}
    }
    
    if attendees:
        payload["attendees"] = [{"email": email} for email in attendees]

    async with await _get_calendar_client(tenant_id, user_id) as client:
        response = await client.post("/calendars/primary/events", json=payload, params={"sendUpdates": "all"})
        
        if response.status_code != 200:
            raise CalendarToolError(f"Failed to create event: {response.text}")
            
        data = response.json()
        return {
            "event_id": data.get("id"),
            "title": data.get("summary"),
            "start": data.get("start"),
            "end": data.get("end"),
            "status": "created",
            "link": data.get("htmlLink")
        }


async def calendar_update_event(
    tenant_id: str,
    user_id: str,
    event_id: str,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    timezone: str = "UTC",
    description: str | None = None
) -> Dict[str, Any]:
    """
    Update an existing calendar event.
    """
    async with await _get_calendar_client(tenant_id, user_id) as client:
        # First, fetch the existing event
        get_resp = await client.get(f"/calendars/primary/events/{event_id}")
        if get_resp.status_code != 200:
            raise CalendarToolError(f"Event not found or cannot be retrieved: {get_resp.text}")
            
        event = get_resp.json()
        
        # Apply updates
        if title is not None:
            event["summary"] = title
        if description is not None:
            event["description"] = description
        if start_time is not None:
            event["start"] = {"dateTime": start_time, "timeZone": timezone}
        if end_time is not None:
            event["end"] = {"dateTime": end_time, "timeZone": timezone}
            
        update_resp = await client.put(f"/calendars/primary/events/{event_id}", json=event, params={"sendUpdates": "all"})
        if update_resp.status_code != 200:
            raise CalendarToolError(f"Failed to update event: {update_resp.text}")
            
        data = update_resp.json()
        return {
            "event_id": data.get("id"),
            "status": "updated",
            "title": data.get("summary")
        }


async def calendar_cancel_event(
    tenant_id: str,
    user_id: str,
    event_id: str
) -> Dict[str, Any]:
    """
    Cancel/delete an event.
    """
    async with await _get_calendar_client(tenant_id, user_id) as client:
        response = await client.delete(f"/calendars/primary/events/{event_id}", params={"sendUpdates": "all"})
        
        if response.status_code not in (200, 204):
            raise CalendarToolError(f"Failed to cancel event: {response.text}")
            
        return {
            "event_id": event_id,
            "status": "cancelled"
        }
