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
    MODEL: str = "claude-sonnet-4-20250514"

    # Google OAuth
    GOOGLE_CREDENTIALS_PATH: str = _resolve(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
    GOOGLE_TOKEN_PATH: str = _resolve(os.getenv("GOOGLE_TOKEN_PATH", "token.json"))
    GOOGLE_SCOPES: list[str] = [
        "https://www.googleapis.com/auth/calendar",
    ]

    # Gmail OAuth (separate token to avoid scope conflict with Calendar)
    GOOGLE_GMAIL_TOKEN_PATH: str = _resolve(os.getenv("GOOGLE_GMAIL_TOKEN_PATH", "token_gmail.json"))
    GMAIL_SCOPES: list[str] = [
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
            secrets = dict(st.secrets["google_oauth"])
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
