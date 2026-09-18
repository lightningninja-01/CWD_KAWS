import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx

from app.config.settings import get_settings
from app.exceptions.custom_exceptions import MetaAPIError # reusing custom error pattern, but let's make a specific one or generic
from app.utils.logger import get_logger
from app.models.integration import GoogleIntegration

log = get_logger(__name__)

class GoogleOAuthError(Exception):
    """Raised for errors related to Google OAuth."""
    pass

class GoogleOAuthService:
    """
    Handles Google OAuth authorization code flow and token refresh.
    Operates at the User level.
    """

    def __init__(self):
        self.settings = get_settings()
        self._auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self._token_url = "https://oauth2.googleapis.com/token"

    def get_authorization_url(self, tenant_id: str, user_id: str) -> str:
        """
        Generate the OAuth 2.0 authorization URL.
        State encodes the tenant and user ID to link the callback securely.
        """
        if not self.settings.google_client_id:
            raise GoogleOAuthError("GOOGLE_CLIENT_ID is not configured.")

        # Encode state to pass through the OAuth flow
        state_data = json.dumps({"t": tenant_id, "u": user_id})
        state_b64 = base64.urlsafe_b64encode(state_data.encode()).decode().rstrip("=")

        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": self.settings.google_oauth_scopes,
            "access_type": "offline",
            "prompt": "consent",  # Force consent to ensure we get a refresh token
            "state": state_b64,
        }
        
        # Build query string manually to ensure correct encoding
        import urllib.parse
        query = urllib.parse.urlencode(params)
        return f"{self._auth_url}?{query}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange the authorization code for an access token and refresh token."""
        if not self.settings.google_client_id or not self.settings.google_client_secret:
            raise GoogleOAuthError("Google OAuth credentials are not configured.")

        payload = {
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.settings.google_redirect_uri,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._token_url, data=payload)
            if resp.status_code != 200:
                log.error(f"Failed to exchange Google OAuth code: {resp.text}")
                raise GoogleOAuthError(f"Token exchange failed: {resp.status_code}")
            return resp.json()

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Get a new access token using a refresh token."""
        payload = {
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._token_url, data=payload)
            if resp.status_code != 200:
                log.error(f"Failed to refresh Google OAuth token: {resp.text}")
                raise GoogleOAuthError(f"Token refresh failed: {resp.status_code}")
            return resp.json()
            
    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch the authenticated user's profile info (mainly email)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if resp.status_code != 200:
                log.error(f"Failed to fetch Google user info: {resp.text}")
                raise GoogleOAuthError("User info fetch failed")
            return resp.json()

    def parse_state(self, state_b64: str) -> tuple[str, str]:
        """Decode the state parameter back to tenant_id and user_id."""
        try:
            # Pad the b64 string if necessary
            padding = 4 - (len(state_b64) % 4)
            if padding != 4:
                state_b64 += "=" * padding
            
            state_json = base64.urlsafe_b64decode(state_b64).decode()
            data = json.loads(state_json)
            return data["t"], data["u"]
        except Exception as e:
            raise GoogleOAuthError(f"Invalid state parameter: {e}")

    async def ensure_valid_token(self, integration: GoogleIntegration, repo: Any) -> str:
        """
        Check if the token is expired. If so, refresh it and save to DB.
        Returns the valid access token.
        """
        if not integration.is_connected:
            raise GoogleOAuthError("Google account is not connected.")

        # Give a 1-minute buffer for expiry
        if integration.token_expiry:
            expiry = integration.token_expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            
            if datetime.now(timezone.utc) > (expiry - timedelta(minutes=1)):
                if not integration.refresh_token:
                    raise GoogleOAuthError("Token expired and no refresh token available.")
            
            log.info(f"Refreshing Google token for user {integration.user_id}")
            token_data = await self.refresh_token(integration.refresh_token)
            
            integration.access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                integration.refresh_token = token_data["refresh_token"]
            expires_in = token_data.get("expires_in", 3600)
            integration.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            await repo.upsert(integration)
            
        return integration.access_token
