"""Settings for a single-artist (Phase 0) deployment."""

import json
import os

from muse.config import config


def test_no_demo_data_when_seeding_is_off(workdir, monkeypatch):
    monkeypatch.setattr(config, "SEED_DEMO_DATA", False)
    from muse.tools.crm_tools import CRMTools
    from muse.tools.email_tools import EmailTools
    from muse.tools.invoice_tools import InvoiceTools
    from muse.tools.social_tools import SocialTools

    assert InvoiceTools().list_invoices() == []
    assert CRMTools().search_contacts() == []
    assert EmailTools().list_emails() == []
    social = SocialTools()
    assert social.list_posts()["posts"] == []
    assert social.list_voice_samples()["total_samples"] == 0


def test_email_agent_cannot_send(workdir):
    from muse.agents.email_agent import EmailAgent
    agent = EmailAgent(client=object())
    names = {t["name"] for t in agent.tool_definitions()}
    assert "send_draft" not in names
    assert {"draft_reply", "create_draft"} <= names
    assert "error" in agent.execute_tool("send_draft", {"draft_id": "d"})


class FakeCreds:
    def to_json(self):
        return json.dumps({"token": "t", "refresh_token": "r"})


def test_single_user_cloud_deploy_keeps_token_on_disk(workdir, monkeypatch):
    from muse.utils import google_oauth
    monkeypatch.setenv("STREAMLIT_URL", "https://muse.example.com")
    path = os.path.join(workdir, "token.json")

    monkeypatch.setattr(config, "SINGLE_USER", False)
    google_oauth._save_token(FakeCreds(), path, config.GOOGLE_SCOPES)
    assert not os.path.exists(path)  # multi-user cloud: never on shared disk

    monkeypatch.setattr(config, "SINGLE_USER", True)
    google_oauth._save_token(FakeCreds(), path, config.GOOGLE_SCOPES)
    assert json.load(open(path))["refresh_token"] == "r"
