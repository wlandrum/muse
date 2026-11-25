"""Muse configuration — loads environment variables and app settings."""

import json
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Project root: two levels up from this file (muse/muse/config.py → project root)
# config.py is at muse/muse/config.py, one up = muse/, two up = project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve(path: str) -> str:
    """Resolve a path relative to the project root if not already absolute."""
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


class Config:
    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    # Before changing a model or effort level, run the evals (muse/eval).
    MODEL: str = os.getenv("MUSE_AGENT_MODEL", "claude-sonnet-5-5")
    AGENT_EFFORT: str = os.getenv("MUSE_AGENT_EFFORT", "medium")
    # Thinking counts toward max_tokens, so leave room beyond the reply itself.
    AGENT_MAX_TOKENS: int = 16000
    # Routing is a one-word classification: a small, fast model is enough.
    ROUTER_MODEL: str = os.getenv("MUSE_ROUTER_MODEL", "claude-haiku-5-5")
    ROUTER_EFFORT: str = os.getenv("MUSE_ROUTER_EFFORT", "low")
    ROUTER_MAX_TOKENS: int = 1024
    # Retry safety-classifier declines on a fallback model (Claude API only).
    REFUSAL_FALLBACK: bool = os.getenv("MUSE_REFUSAL_FALLBACK", "1") == "1"

    # Google OAuth — single token with both Calendar + Gmail scopes
    GOOGLE_CREDENTIALS_PATH: str = _resolve(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
    GOOGLE_TOKEN_PATH: str = _resolve(os.getenv("GOOGLE_TOKEN_PATH", "token.json"))
    GOOGLE_SCOPES: list[str] = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/gmail.modify",
    ]

    # App
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "America/New_York")
    ARTIST_NAME: str = os.getenv("ARTIST_NAME", "Artist")
    ARTIST_EMAIL: str = os.getenv("ARTIST_EMAIL", "")

    # Invoicing
    INVOICE_OUTPUT_DIR: str = _resolve(os.getenv("INVOICE_OUTPUT_DIR", "invoices"))
    INVOICE_PAYMENT_TERMS: str = os.getenv("INVOICE_PAYMENT_TERMS", "Due upon receipt")

    # Social Media
    CHROMADB_PATH: str = _resolve(os.getenv("CHROMADB_PATH", "chroma_db"))
    SOCIAL_PLATFORM: str = os.getenv("SOCIAL_PLATFORM", "instagram")

    # Database
    DB_PATH: str = _resolve(os.getenv("DB_PATH", "muse.db"))
    # Sample gigs, invoices, contacts, emails and voice samples for demos and
    # evals. Turn off for a real artist's data.
    SEED_DEMO_DATA: bool = os.getenv("MUSE_SEED_DEMO_DATA", "1") == "1"

    # Deployment
    # One artist per deployment (Phase 0): keep the Google token in a file on
    # the server's disk even in cloud mode, so it survives browser sessions.
    SINGLE_USER: bool = os.getenv("MUSE_SINGLE_USER", "0") == "1"
    # If set, the web UI asks for this password before showing anything.
    APP_PASSWORD: str = os.getenv("MUSE_APP_PASSWORD", "")
    # Tester round: several invited people share one deployment. Each browser
    # session gets its own copy of the sample data, which clears on refresh.
    # Google sign-in and the Settings panel are off, so nobody can reach a
    # real account or change settings for everyone.
    TESTER_MODE: bool = os.getenv("MUSE_TESTER_MODE", "0") == "1"


config = Config()


def get_google_client_config() -> Optional[dict]:
    """Load Google OAuth client config from st.secrets or credentials.json.

    Tries two sources in order:
    1. Streamlit secrets (cloud): st.secrets["google_oauth"] → builds a dict
    2. Local file: reads credentials.json from disk

    Returns:
        Dict in the format expected by Flow.from_client_config(), or None.
    """
    # 1. Try st.secrets (Streamlit Cloud)
    try:
        import streamlit as st

        if hasattr(st, "secrets") and "google_oauth" in st.secrets:
            from muse.utils.env import get_app_url

            secrets = dict(st.secrets["google_oauth"])
            app_url = get_app_url()
            return {
                "web": {
                    "client_id": secrets["client_id"],
                    "client_secret": secrets["client_secret"],
                    "project_id": secrets.get("project_id", ""),
                    "auth_uri": secrets.get(
                        "auth_uri", "https://accounts.google.com/o/oauth2/auth"
                    ),
                    "token_uri": secrets.get(
                        "token_uri", "https://oauth2.googleapis.com/token"
                    ),
                    "auth_provider_x509_cert_url": secrets.get(
                        "auth_provider_x509_cert_url",
                        "https://www.googleapis.com/oauth2/v1/certs",
                    ),
                    "redirect_uris": [app_url],
                }
            }
    except Exception:
        pass

    # 2. Fall back to credentials.json file (local dev)
    creds_path = config.GOOGLE_CREDENTIALS_PATH
    if os.path.exists(creds_path):
        with open(creds_path) as f:
            return json.load(f)

    return None
