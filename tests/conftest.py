"""Shared fixtures: every test runs against a throwaway, offline sandbox."""

import pytest

from muse.eval.sandbox import sandbox


@pytest.fixture
def workdir():
    """Temp dir that all Muse storage (SQLite, Chroma, invoices) points at."""
    with sandbox() as tmp:
        yield tmp


@pytest.fixture
def calendar(workdir):
    from muse.tools.calendar_tools import CalendarTools
    tools = CalendarTools()
    assert tools.use_local
    return tools


@pytest.fixture
def email(workdir):
    from muse.tools.email_tools import EmailTools
    tools = EmailTools()
    assert tools.use_local
    return tools


@pytest.fixture
def invoices(workdir):
    from muse.tools.invoice_tools import InvoiceTools
    return InvoiceTools()


@pytest.fixture
def crm(workdir):
    from muse.tools.crm_tools import CRMTools
    return CRMTools()


@pytest.fixture
def social(workdir):
    from muse.tools.social_tools import SocialTools
    return SocialTools()
