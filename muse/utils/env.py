"""Environment detection utilities for local vs. Streamlit Cloud."""

import os


def is_cloud() -> bool:
    """Return True if running on Streamlit Cloud (or any non-local deployment).

    Detection: the STREAMLIT_URL env var is set in Streamlit Cloud secrets.
    Its presence signals cloud mode; its value provides the app's public URL.
    """
    return bool(os.environ.get("STREAMLIT_URL"))


def get_app_url() -> str:
    """Return the app's public base URL.

    On Streamlit Cloud: reads STREAMLIT_URL env var (e.g. "https://muse-app.streamlit.app")
    Locally: falls back to "http://localhost:8501"
    """
    return os.environ.get("STREAMLIT_URL", "http://localhost:8501").rstrip("/")
