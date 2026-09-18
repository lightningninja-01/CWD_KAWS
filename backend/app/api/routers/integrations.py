"""
Google Integrations router.
Handles the OAuth 2.0 flow for Google Workspace (Calendar/Gmail).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.database.connection import mongo_connection
from app.database.repositories.integration_repository import IntegrationRepository
from app.models.integration import GoogleIntegration
from app.services.google_oauth import GoogleOAuthService, GoogleOAuthError
from app.config.settings import get_settings

router = APIRouter()
oauth_service = GoogleOAuthService()


def get_integration_repo() -> IntegrationRepository:
    return IntegrationRepository(mongo_connection.db)


@router.get("/google/auth")
async def initiate_google_auth(
    tenant_id: str = Query(...),
    user_id: str = Query(...),
):
    """
    Start the OAuth flow. Redirects the user to Google's consent screen.
    """
    try:
        auth_url = oauth_service.get_authorization_url(tenant_id, user_id)
        return RedirectResponse(url=auth_url)
    except GoogleOAuthError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/google/callback")
async def google_auth_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
):
    """
    Handle the callback from Google.
    Exchanges the code for tokens and stores them in the database.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    try:
        tenant_id, user_id = oauth_service.parse_state(state)
        
        # Exchange code for tokens
        token_data = await oauth_service.exchange_code(code)
        
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        granted_scopes = token_data.get("scope", "").split(" ")
        
        # Fetch user info to get the email address
        user_info = await oauth_service.get_user_info(access_token)
        google_email = user_info.get("email")

        # Save to DB
        repo = get_integration_repo()
        
        # Check if an integration already exists to preserve the refresh token if Google didn't send a new one
        existing = await repo.get_by_user(tenant_id, user_id)
        if not refresh_token and existing and existing.refresh_token:
            refresh_token = existing.refresh_token

        integration = GoogleIntegration(
            tenant_id=tenant_id,
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            granted_scopes=granted_scopes,
            google_email=google_email,
            is_connected=True,
        )
        
        await repo.upsert(integration)
        
        settings = get_settings()
        # Redirect back to the frontend dashboard or demo page
        # In a real app, you might want to redirect to a specific success page
        frontend_url = settings.cors_origins_list[0] if settings.cors_origins_list else "http://localhost:5173"
        return RedirectResponse(url=f"{frontend_url}/demo?integration=success")

    except GoogleOAuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error during callback")


@router.get("/google/status")
async def get_google_integration_status(
    tenant_id: str = Query(...),
    user_id: str = Query(...),
):
    """Check if the user has a connected Google account."""
    repo = get_integration_repo()
    integration = await repo.get_by_user(tenant_id, user_id)
    
    if not integration or not integration.is_connected:
        return {"is_connected": False}
        
    return {
        "is_connected": True,
        "google_email": integration.google_email,
        "scopes": integration.granted_scopes,
        "updated_at": integration.updated_at
    }

@router.post("/google/disconnect")
async def disconnect_google_integration(
    tenant_id: str = Query(...),
    user_id: str = Query(...),
):
    """Disconnect the Google account."""
    repo = get_integration_repo()
    await repo.disconnect(tenant_id, user_id)
    return {"status": "disconnected"}
