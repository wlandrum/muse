"""Muse — AI Manager for Independent Artists
Streamlit UI with chat interface and calendar dashboard.
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta

import anthropic
import streamlit as st
from anthropic import Anthropic

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse.config import config, get_google_client_config
from muse.orchestrator import Orchestrator
from muse.utils.env import get_app_url, is_cloud
from muse.utils.google_oauth import (
    is_connected,
    get_auth_url,
    exchange_code,
    disconnect,
    GOOGLE_OAUTH_AVAILABLE,
)

# ── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Page Config ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Muse — AI Manager",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark theme overrides */
    .stApp {
        background-color: #0e1117;
    }

    /* Chat message styling */
    .user-message {
        background-color: #1a1f2e;
        border-radius: 12px;
        padding: 12px 16px;
        margin: 8px 0;
        border-left: 3px solid #6c63ff;
    }
    .assistant-message {
        background-color: #141820;
        border-radius: 12px;
        padding: 12px 16px;
        margin: 8px 0;
        border-left: 3px solid #22c55e;
    }

    /* Event card styling */
    .event-card {
        background-color: #1a1f2e;
        border-radius: 8px;
        padding: 12px;
        margin: 6px 0;
        border-left: 4px solid #6c63ff;
    }

    /* Sidebar styling */
    .sidebar-header {
        font-size: 1.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ── Password Gate ───────────────────────────────────────────────────
# Runs before anything else, including the OAuth callback, so nobody can
# connect their own Google account to a single-artist deployment.
#
# Google's redirect back lands in a new Streamlit session, so the OAuth
# state carries proof that the password was entered: a timestamp signed with
# the password, valid for OAUTH_STATE_TTL seconds.
OAUTH_STATE_TTL = 15 * 60


def _sign(value: str) -> str:
    return hmac.new(config.APP_PASSWORD.encode(), value.encode(), hashlib.sha256).hexdigest()


def _signed_oauth_state(service: str) -> str:
    payload = f"{service}.{int(time.time())}"
    return f"{payload}.{_sign(payload)}"


def _oauth_state_is_valid(state: str) -> bool:
    payload, _, signature = state.rpartition(".")
    _, _, issued = payload.partition(".")
    if not issued.isdigit() or not hmac.compare_digest(signature, _sign(payload)):
        return False
    return 0 <= time.time() - int(issued) <= OAUTH_STATE_TTL


if (
    config.APP_PASSWORD
    and not st.session_state.get("_authed")
    and st.query_params.get("code")
    and _oauth_state_is_valid(st.query_params.get("state", ""))
):
    st.session_state["_authed"] = True

if config.APP_PASSWORD and not st.session_state.get("_authed"):
    st.title("🎵 Muse")
    with st.form("login"):
        _password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            if hmac.compare_digest(_password.encode(), config.APP_PASSWORD.encode()):
                st.session_state["_authed"] = True
                st.rerun()
            st.error("That password isn't right.")
    st.stop()

# ── OAuth Callback Handler ──────────────────────────────────────────
# When Google redirects back with ?code=...&state=..., exchange the code
# for a token and save it. This runs BEFORE the rest of the UI renders.

_query_params = st.query_params
_oauth_code = _query_params.get("code")
_oauth_state = _query_params.get("state")

if _oauth_code and _oauth_state and not config.TESTER_MODE:
    _client_cfg = get_google_client_config()
    _redirect_uri = get_app_url()
    _cloud = is_cloud()

    success = exchange_code(
        code=_oauth_code,
        scopes=config.GOOGLE_SCOPES,
        client_config=_client_cfg,
        redirect_uri=_redirect_uri,
        token_path=config.GOOGLE_TOKEN_PATH if (not _cloud or config.SINGLE_USER) else None,
    )
    if success:
        st.session_state["_oauth_toast"] = ("Google connected! Calendar & Gmail ready.", "✅")
    else:
        st.session_state["_oauth_toast"] = ("Failed to connect Google. Check logs.", "❌")

    # Clear the OAuth query params and reload the page cleanly
    st.query_params.clear()
    st.rerun()

# Show toast from previous OAuth redirect (survives rerun via session_state)
if "_oauth_toast" in st.session_state:
    _msg, _icon = st.session_state.pop("_oauth_toast")
    st.toast(_msg, icon=_icon)

# ── Session State Init ──────────────────────────────────────────────


def _session_db_path() -> str | None:
    """In tester mode, a fresh database for this browser session.

    Testers never see each other's gigs, invoices or contacts, and each one
    starts from the same sample data. Otherwise the shared DB_PATH is used.
    """
    if not config.TESTER_MODE:
        return None
    folder = os.path.join(tempfile.gettempdir(), "muse_sessions")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"s_{uuid.uuid4().hex[:12]}.db")


def init_session_state():
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = Orchestrator(db_path=_session_db_path())
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_log" not in st.session_state:
        st.session_state.agent_log = []


init_session_state()

# ── Google Connection Status ────────────────────────────────────────
_client_config = None if config.TESTER_MODE else get_google_client_config()
_has_credentials = _client_config is not None
_google_connected = _has_credentials and is_connected(config.GOOGLE_TOKEN_PATH, config.GOOGLE_SCOPES)

# ── Sidebar ─────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("# 🎵 Muse")
    st.markdown("**AI Manager for Independent Artists**")
    st.divider()

    # Agent status indicators (dynamic based on connection)
    st.markdown("### Agents")
    _g_label = "Google" if _google_connected else "Local"
    st.markdown(f"✅ **Calendar** — {_g_label}")
    st.markdown(f"✅ **Email** — {_g_label}")
    st.markdown("✅ **Invoicing** — Active")
    st.markdown("✅ **Social Media** — Active")
    st.markdown("✅ **CRM** — Active")
    st.divider()

    # ── Google Connection ────────────────────────────────────────
    st.markdown("### Google Connection")

    if config.TESTER_MODE:
        st.caption("Google sign-in is off for this test. Muse uses sample data.")
    elif not GOOGLE_OAUTH_AVAILABLE:
        st.warning("Google API libraries not installed. Running in local-only mode.")
    elif not _has_credentials:
        st.warning(
            "**Google credentials not configured.**\n\n"
            "To connect Google Calendar & Gmail:\n"
            "1. Go to [Google Cloud Console](https://console.cloud.google.com/)\n"
            "2. Create OAuth 2.0 credentials (Web application type)\n"
            f"3. Add `{get_app_url()}` as an authorized redirect URI\n"
            "4. Add credentials to Streamlit secrets or download `credentials.json`"
        )
    elif _google_connected:
        col_status, col_btn = st.columns([3, 1])
        with col_status:
            st.markdown("✅ **Google** connected")
            st.caption("Calendar & Gmail active")
        with col_btn:
            if st.button("✕", key="disconnect_google", help="Disconnect Google"):
                disconnect(config.GOOGLE_TOKEN_PATH, config.GOOGLE_SCOPES)
                st.rerun()
    else:
        try:
            _auth_url = get_auth_url(
                scopes=config.GOOGLE_SCOPES,
                client_config=_client_config,
                redirect_uri=get_app_url(),
                state=_signed_oauth_state("google") if config.APP_PASSWORD else "google",
            )
            st.link_button(
                "🔗 Connect Google",
                _auth_url,
                use_container_width=True,
            )
            st.caption("Grants Calendar & Gmail access")
        except Exception as e:
            st.error(f"Auth error: {e}")

    st.divider()

    # Quick actions
    st.markdown("### Quick Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📅 This Week", use_container_width=True):
            st.session_state.quick_action = "What's on my schedule this week?"
    with col2:
        if st.button("🔍 Next Open", use_container_width=True):
            st.session_state.quick_action = "When am I free this week?"

    col3, col4 = st.columns(2)
    with col3:
        if st.button("🎸 Add Gig", use_container_width=True):
            st.session_state.quick_action = "I need to add a gig to my calendar"
    with col4:
        if st.button("🎙️ Add Session", use_container_width=True):
            st.session_state.quick_action = "I need to add a recording session"

    col5, col6 = st.columns(2)
    with col5:
        if st.button("📧 Check Inbox", use_container_width=True):
            st.session_state.quick_action = "Check my email inbox"
    with col6:
        if st.button("📨 Unread", use_container_width=True):
            st.session_state.quick_action = "Show me my unread emails"

    col7, col8 = st.columns(2)
    with col7:
        if st.button("💰 Invoices", use_container_width=True):
            st.session_state.quick_action = "Show me my invoices"
    with col8:
        if st.button("📊 Income", use_container_width=True):
            st.session_state.quick_action = "How much have I made this year?"

    col9, col10 = st.columns(2)
    with col9:
        if st.button("📱 Draft Post", use_container_width=True):
            st.session_state.quick_action = "Help me draft an Instagram post"
    with col10:
        if st.button("📝 My Posts", use_container_width=True):
            st.session_state.quick_action = "Show my post drafts"

    col11, col12 = st.columns(2)
    with col11:
        if st.button("👥 Contacts", use_container_width=True):
            st.session_state.quick_action = "Show me my contacts"
    with col12:
        if st.button("📋 Follow-ups", use_container_width=True):
            st.session_state.quick_action = "Who do I need to follow up with?"

    st.divider()

    # Settings change the whole server's config, so testers don't get them.
    if not config.TESTER_MODE:
        with st.expander("⚙️ Settings"):
            artist_name = st.text_input("Artist Name", value=config.ARTIST_NAME)
            timezone = st.text_input("Timezone", value=config.DEFAULT_TIMEZONE)
            if st.button("Save Settings"):
                config.ARTIST_NAME = artist_name
                config.DEFAULT_TIMEZONE = timezone
                st.success("Settings saved!")

    # Reset conversation
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.agent_log = []
        st.session_state.orchestrator.reset()
        st.rerun()

# ── Main Chat Interface ─────────────────────────────────────────────

# Header
st.markdown("## 💬 Chat with Muse")
st.markdown(
    "*Tell me about gigs, sessions, email, invoicing, contacts, or social media — I'll handle it.*"
)

if config.SEED_DEMO_DATA and not _google_connected:
    _keep_note = (
        "Anything you add stays in this browser tab and clears when you refresh the page."
        if config.TESTER_MODE
        else "Anything you add is saved."
    )
    if not st.session_state.messages:
        st.info(
            "**You're trying Muse with sample data.** The inbox, invoices, contacts "
            "and post drafts start with made up examples so there's something to work "
            f"with. {_keep_note}\n\n"
            "**Things to try:** add a gig you have coming up, ask what your week looks "
            "like, draft a post for a show, or make an invoice for a gig."
        )
    else:
        st.caption(f"Sample data mode. {_keep_note}")


def _friendly_error(err: Exception) -> str:
    """A message the artist can act on, instead of a stack trace."""
    if isinstance(err, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return (
            "Muse can't reach its AI service right now because its API key isn't "
            "working. Let the person who set up Muse know."
        )
    if isinstance(err, anthropic.NotFoundError):
        return "Muse's AI model isn't available right now. Let the person who set up Muse know."
    if isinstance(err, (anthropic.RateLimitError, anthropic.APIConnectionError)):
        return "Muse is busy right now. Give it a moment and try again."
    if isinstance(err, anthropic.APIStatusError) and err.status_code >= 500:
        return "Muse is busy right now. Give it a moment and try again."
    return "Something went wrong on Muse's side. Try again, or ask another way."


def _render_reply(msg: dict, index: int) -> None:
    st.markdown(msg["content"])
    if msg.get("pdf"):
        filename, data = msg["pdf"]
        st.download_button(
            f"⬇️ Download {filename}",
            data=data,
            file_name=filename,
            mime="application/pdf",
            key=f"pdf_{index}",
        )
    if msg.get("agent"):
        st.caption(f"Handled by: {msg['agent']} agent")


def _ask_muse(prompt: str) -> None:
    """Send one message to Muse, show the reply, and keep both in the history."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🎤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🎵"):
        orchestrator = st.session_state.orchestrator
        try:
            with st.spinner("Working on it..."):
                agent_name, response = orchestrator.route(prompt)
            reply = {"role": "assistant", "content": response, "agent": agent_name}
            pdf = orchestrator.take_pending_pdf()
            if pdf:
                reply["pdf"] = pdf
        except Exception as err:  # keep the chat usable whatever failed
            logger.exception("Muse failed to answer")
            reply = {"role": "assistant", "content": _friendly_error(err)}
        _render_reply(reply, len(st.session_state.messages))

    st.session_state.messages.append(reply)


# Display chat history
for _i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="🎵" if msg["role"] == "assistant" else "🎤"):
        if msg["role"] == "assistant":
            _render_reply(msg, _i)
        else:
            st.markdown(msg["content"])

# Handle quick actions
if "quick_action" in st.session_state:
    _ask_muse(st.session_state.pop("quick_action"))
    st.rerun()

# Chat input
if prompt := st.chat_input("e.g. 'Book a session at West End Sound next Thursday, noon to 5pm, $500'"):
    _ask_muse(prompt)

# ── Footer ──────────────────────────────────────────────────────────
st.divider()

st.caption(
    "Muse v0.1 — Built with Claude (Anthropic) · "
    "Calendar + Email + Invoice + Social + CRM Agents available · "
    f"Google: {'Connected' if _google_connected else 'Local mode'} · "
    "Invoices: Active · Social: Active · CRM: Active"
)
