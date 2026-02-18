"""Shared Google OAuth helper for Streamlit-based authentication.

Centralizes OAuth logic so both CalendarTools and EmailTools can use it,
and the Streamlit UI can drive the consent flow via browser redirect.

Supports two modes:
- **Local dev**: credentials from file, tokens saved to file, HTTP redirect
- **Cloud (Streamlit Cloud)**: credentials from st.secrets, tokens in
  st.session_state, HTTPS redirect

Uses google_auth_oauthlib.flow.Flow (NOT InstalledAppFlow) so we can
specify a custom redirect_uri pointing back to the Streamlit app.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from muse.utils.env import is_cloud, get_app_url

logger = logging.getLogger(__name__)

# Allow HTTP redirect for local development only (Cloud uses HTTPS)
if not is_cloud():
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Allow token response to include more scopes than originally requested.
# Google merges previously-granted scopes for the same user/app, so the
# token response often contains scopes from earlier grants (e.g. granting
# Gmail after Calendar returns both). Without this, oauthlib raises
# "Scope has changed" and the exchange fails.
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

# Try to import Google libraries — graceful fallback
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow

    GOOGLE_OAUTH_AVAILABLE = True
except ImportError:
    GOOGLE_OAUTH_AVAILABLE = False
    logger.info("Google OAuth libraries not installed — OAuth features disabled")

# Dynamic default: HTTPS on cloud, HTTP locally
DEFAULT_REDIRECT_URI = get_app_url()


# ── Helpers ──────────────────────────────────────────────────────────


def _token_key(scopes: list[str]) -> str:
    """Determine session-state key based on scopes."""
    scope_str = " ".join(scopes)
    if "gmail" in scope_str:
        return "oauth_token_gmail"
    return "oauth_token_calendar"


def _create_flow(
    scopes: list[str],
    redirect_uri: str,
    client_config: dict | None = None,
    credentials_path: str | None = None,
) -> "Flow":
    """Create a Flow from either a client config dict or a file."""
    if client_config:
        return Flow.from_client_config(
            client_config,
            scopes=scopes,
            redirect_uri=redirect_uri,
        )
    elif credentials_path:
        return Flow.from_client_secrets_file(
            credentials_path,
            scopes=scopes,
            redirect_uri=redirect_uri,
        )
    else:
        raise ValueError("Either client_config or credentials_path must be provided")


# ── Public API ───────────────────────────────────────────────────────


def is_connected(token_path: str | None, scopes: list[str]) -> bool:
    """Check if a valid (or refreshable) Google token exists."""
    creds = load_credentials(token_path, scopes)
    return creds is not None


def load_credentials(
    token_path: str | None, scopes: list[str]
) -> Optional["Credentials"]:
    """Load and refresh cached Google credentials.

    Checks two sources in order:
    1. st.session_state (cloud / current session)
    2. Token file on disk (local dev)

    Returns valid Credentials or None if no token / refresh fails.
    """
    if not GOOGLE_OAUTH_AVAILABLE:
        return None

    creds = None

    # 1. Try session state (cloud mode, or tokens saved during this session)
    try:
        import streamlit as st

        key = _token_key(scopes)
        if key in st.session_state:
            token_data = st.session_state[key]
            creds = Credentials.from_authorized_user_info(
                json.loads(token_data), scopes
            )
    except Exception:
        pass

    # 2. Fall back to token file (local dev)
    if creds is None and token_path and os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, scopes)
        except Exception as e:
            logger.warning(f"Failed to load token from {token_path}: {e}")
            return None

    if creds is None:
        return None

    if creds.valid:
        return creds

    # Try to refresh expired credentials
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed token back to the right place
            _save_token(creds, token_path, scopes)
            return creds
        except Exception as e:
            logger.warning(f"Failed to refresh token: {e}")
            return None

    return None


def _save_token(
    creds: "Credentials", token_path: str | None, scopes: list[str]
) -> None:
    """Save token to file (local) or session state (cloud)."""
    token_json = creds.to_json()

    # Always try session state (works in both modes when Streamlit is running)
    try:
        import streamlit as st

        st.session_state[_token_key(scopes)] = token_json
    except Exception:
        pass

    # Also save to file if we have a path and we're in local mode
    if token_path and not is_cloud():
        try:
            with open(token_path, "w") as f:
                f.write(token_json)
        except Exception as e:
            logger.warning(f"Failed to save token to {token_path}: {e}")


def get_auth_url(
    scopes: list[str],
    client_config: dict | None = None,
    credentials_path: str | None = None,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    state: str = "calendar",
) -> str:
    """Generate the Google OAuth authorization URL.

    Args:
        scopes: OAuth scopes to request.
        client_config: Client config dict (from st.secrets or loaded JSON).
        credentials_path: Path to client credentials.json (local fallback).
        redirect_uri: Where Google redirects after consent.
        state: Encodes which service ("calendar" or "gmail") for the callback.

    Returns:
        The authorization URL to redirect the user to.
    """
    if not GOOGLE_OAUTH_AVAILABLE:
        raise RuntimeError("Google OAuth libraries not installed")

    flow = _create_flow(scopes, redirect_uri, client_config, credentials_path)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    return auth_url


def exchange_code(
    code: str,
    scopes: list[str],
    client_config: dict | None = None,
    credentials_path: str | None = None,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    token_path: str | None = None,
) -> bool:
    """Exchange an OAuth authorization code for credentials and save them.

    Args:
        code: The authorization code from the Google redirect.
        scopes: OAuth scopes (must match the original auth request).
        client_config: Client config dict (cloud).
        credentials_path: Path to credentials.json (local fallback).
        redirect_uri: Must match the redirect_uri used in get_auth_url.
        token_path: Where to save the token file. If None, saves to
            st.session_state only (cloud mode).

    Returns:
        True if successful, False otherwise.
    """
    if not GOOGLE_OAUTH_AVAILABLE:
        return False

    try:
        # Ensure relaxed scope checking is active right before exchange.
        # Google merges previously-granted scopes, so connecting Gmail after
        # Calendar (or vice versa) returns both scopes in the token response.
        # Without this, oauthlib raises "Scope has changed".
        os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

        flow = _create_flow(scopes, redirect_uri, client_config, credentials_path)

        # Belt-and-suspenders: manually exchange the code via Google's token
        # endpoint using requests, then build Credentials from the response.
        # This completely sidesteps oauthlib's scope-change validation, which
        # can break when Google merges scopes from multiple grants.
        import requests as _requests

        client_info = (client_config or {}).get("web") or (client_config or {}).get("installed") or {}
        token_resp = _requests.post(
            client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            data={
                "code": code,
                "client_id": client_info["client_id"],
                "client_secret": client_info["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_data = token_resp.json()

        if "error" in token_data:
            logger.error(f"Token exchange error: {token_data}")
            return False

        creds = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri=client_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=client_info["client_id"],
            client_secret=client_info["client_secret"],
            scopes=scopes,
        )

        _save_token(creds, token_path, scopes)
        logger.info(f"OAuth token saved (scopes={scopes}, token_path={token_path})")
        return True

    except Exception as e:
        logger.error(f"Failed to exchange OAuth code: {e}", exc_info=True)
        return False


def disconnect(token_path: str | None, scopes: list[str] | None = None) -> bool:
    """Remove a saved token (disconnect a Google service).

    Clears both file token and session-state token.
    Returns True if any token was removed.
    """
    removed = False

    # Remove file token
    if token_path and os.path.exists(token_path):
        os.remove(token_path)
        logger.info(f"Disconnected: removed {token_path}")
        removed = True

    # Remove session-state token
    if scopes:
        try:
            import streamlit as st

            key = _token_key(scopes)
            if key in st.session_state:
                del st.session_state[key]
                logger.info(f"Disconnected: removed session_state[{key}]")
                removed = True
        except Exception:
            pass

    return removed
