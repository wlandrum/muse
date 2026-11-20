"""Orchestrator — routes user messages to the appropriate agent."""

from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from muse.config import config

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """You are a router for Muse, an AI manager for independent musicians.
Classify the user's message into exactly ONE category:

- CALENDAR: the artist's own schedule: adding, moving or cancelling gigs, sessions, rehearsals, lessons; availability, conflicts, "what's on my schedule", "am I free"
- SOCIAL: social media posts, captions, content creation, Instagram, TikTok, hashtags, promo; the artist's voice samples (example captions saved so drafts match their writing style)
- INVOICE: billing, payments, invoices, money owed, rates, income
- EMAIL: the inbox and anything someone sent by email: reading, searching, summarizing or archiving messages, booking inquiries and offers received, pulling gig details out of an email, drafting replies
- CRM: contacts, clients, venues, studios, promoters, relationships, meeting notes, follow-ups, "who do I work with", "tell me about [person/venue]", contact info, networking
- GENERAL: greetings, general questions, anything that doesn't fit the above

You may be told which category handled the previous message. Short follow-ups
("yes", "send it", "make it $450", "what about Friday?") continue that category
unless the new message clearly changes topic."""

CATEGORIES = ["CALENDAR", "SOCIAL", "INVOICE", "EMAIL", "CRM", "GENERAL"]

ROUTER_FORMAT = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {"category": {"type": "string", "enum": CATEGORIES}},
        "required": ["category"],
        "additionalProperties": False,
    },
}


class Orchestrator:
    """Routes user messages to the appropriate Muse agent.

    Agents are lazy-loaded on first use so that heavy dependencies
    (ChromaDB, Google OAuth) are only initialized when needed.
    """

    def __init__(self, client: Anthropic | None = None):
        self.client = client or Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.last_category: str | None = None

        # Lazy-loaded agent instances
        self._calendar_agent = None
        self._email_agent = None
        self._invoice_agent = None
        self._social_agent = None
        self._crm_agent = None

    # ── Lazy Agent Properties ────────────────────────────────────────

    @property
    def calendar_agent(self):
        if self._calendar_agent is None:
            from muse.agents.calendar_agent import CalendarAgent
            self._calendar_agent = CalendarAgent(client=self.client)
            logger.info("[Orchestrator] Calendar agent initialized")
        return self._calendar_agent

    @property
    def email_agent(self):
        if self._email_agent is None:
            from muse.agents.email_agent import EmailAgent
            self._email_agent = EmailAgent(client=self.client)
            logger.info("[Orchestrator] Email agent initialized")
        return self._email_agent

    @property
    def invoice_agent(self):
        if self._invoice_agent is None:
            from muse.agents.invoice_agent import InvoiceAgent
            self._invoice_agent = InvoiceAgent(client=self.client)
            logger.info("[Orchestrator] Invoice agent initialized")
        return self._invoice_agent

    @property
    def social_agent(self):
        if self._social_agent is None:
            from muse.agents.social_agent import SocialAgent
            self._social_agent = SocialAgent(client=self.client)
            logger.info("[Orchestrator] Social agent initialized")
        return self._social_agent

    @property
    def crm_agent(self):
        if self._crm_agent is None:
            from muse.agents.crm_agent import CRMAgent
            self._crm_agent = CRMAgent(client=self.client)
            logger.info("[Orchestrator] CRM agent initialized")
        return self._crm_agent

    # ── Agent Map (resolves lazily) ──────────────────────────────────

    def _get_agent(self, category: str):
        """Get the agent for a category, initializing lazily."""
        agent_map = {
            "CALENDAR": lambda: self.calendar_agent,
            "EMAIL": lambda: self.email_agent,
            "INVOICE": lambda: self.invoice_agent,
            "SOCIAL": lambda: self.social_agent,
            "CRM": lambda: self.crm_agent,
        }
        getter = agent_map.get(category)
        return getter() if getter else None

    # ── Routing ──────────────────────────────────────────────────────

    def route(self, user_message: str) -> tuple[str, str]:
        """Classify the message and route to the right agent.

        Returns (agent_name, response_text).
        """
        category = self._classify(user_message, previous=self.last_category)
        logger.info(f"[Orchestrator] Classified as: {category}")
        self.last_category = category

        agent = self._get_agent(category)
        if agent:
            response = agent.run(user_message)
            return category, response

        # General / fallback
        return "GENERAL", (
            "Hey! I'm Muse, your AI manager. I can help you with:\n\n"
            "📅 **Calendar** — schedule gigs, sessions, rehearsals, check availability\n"
            "📧 **Email** — inbox triage, draft replies, extract gig details\n"
            "💰 **Invoicing** — create invoices, generate PDFs, track payments\n"
            "📱 **Social Media** — draft Instagram posts, voice-matched captions, hashtags\n"
            "👥 **CRM** — manage contacts, log meeting notes, track relationships\n\n"
            "What can I help you with?"
        )

    def _classify(self, message: str, previous: str | None = None) -> str:
        """Use Claude to classify the message intent."""
        content = message
        if previous:
            content = f"Previous message was handled by: {previous}\n\nNew message: {message}"
        response = self.client.messages.create(
            model=config.ROUTER_MODEL,
            max_tokens=config.ROUTER_MAX_TOKENS,
            system=ROUTER_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": config.ROUTER_EFFORT, "format": ROUTER_FORMAT},
        )
        if response.stop_reason != "end_turn":
            logger.warning(f"[Orchestrator] Router stopped with {response.stop_reason}, defaulting to GENERAL")
            return "GENERAL"

        # Responses can start with thinking blocks — read the text block.
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            category = str(json.loads(text)["category"]).strip().upper()
        except (ValueError, KeyError, TypeError):
            logger.warning(f"[Orchestrator] Unparseable router output {text!r}, defaulting to GENERAL")
            return "GENERAL"

        if category not in CATEGORIES:
            logger.warning(f"[Orchestrator] Unexpected category '{category}', defaulting to GENERAL")
            return "GENERAL"
        return category

    def reset(self) -> None:
        """Reset all agent conversation histories."""
        self.last_category = None
        for agent_attr in [self._calendar_agent, self._email_agent,
                           self._invoice_agent, self._social_agent,
                           self._crm_agent]:
            if agent_attr is not None:
                agent_attr.reset()
