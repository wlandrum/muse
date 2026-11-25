# 🎵 Muse — AI Manager for Independent Artists

Muse is a multi-agent AI system that handles the operational overhead independent musicians deal with every day — scheduling, social media, invoicing, and email management — so they can focus on making music.

Built with **Claude** (Anthropic SDK), native tool calling, and zero framework dependencies (no LangChain).

## The Problem

Independent musicians spend 10-20 hours per week on logistics: scheduling gigs, chasing invoices, posting on social media, responding to booking emails. Most can't afford a manager. Muse acts as an always-on AI manager that handles the admin.

## Architecture

```
User ──▶ Orchestrator ──▶ Calendar Agent  ──▶ Google Calendar API
                    ├──▶ Email Agent      ──▶ Gmail API
                    ├──▶ Invoice Agent    ──▶ PDF Generation (ReportLab)
                    └──▶ Social Agent     ──▶ ChromaDB (voice matching) + Local Drafts
```

**Key Design Decisions:**
- **Raw Anthropic SDK** — no LangChain, no LlamaIndex. Every tool call, agent loop, and state management pattern is built from primitives.
- **Human-in-the-loop by design** — email, invoice, and social agents never auto-send/post. They draft, the artist approves.
- **RAG-based voice matching** — ChromaDB stores the artist's writing style samples. Before generating any caption, the Social Agent retrieves relevant voice samples to match the artist's tone.
- **Local-first** — runs with SQLite for development/demos, Google Calendar API and Gmail API for production.
- **MCP-ready** — tool interfaces designed for future Model Context Protocol server exposure.

## Current Status

| Agent | Status | Features |
|-------|--------|----------|
| 📅 Calendar | ✅ Active | Create events, conflict detection, availability search, natural language scheduling |
| 📧 Email | ✅ Active | Inbox triage, reply drafting, gig detail extraction, search, archive/star/label |
| 💰 Invoice | ✅ Active | Create invoices, PDF generation, payment tracking, income summaries |
| 📱 Social | ✅ Active | RAG voice matching, caption generation, hashtag suggestions, post draft management |
| 👥 CRM | ✅ Active | Contacts, meeting notes, follow-ups, relationship summaries across invoices and gigs |

## Quick Start

### 1. Clone and install
```bash
git clone https://github.com/wlandrum/muse.git
cd muse
pip install -r requirements.txt
```

### 2. Set up environment
```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Chat with Muse in the terminal
```bash
python -m scripts.chat                    # full Muse — the router picks the agent
python -m scripts.chat --agent invoice    # or talk to one agent directly
```
No Google credentials needed — runs on local SQLite (with sample emails, invoices, and contacts) and ChromaDB. Invoice PDFs are saved to `invoices/`.

### 4. Run the Streamlit UI
```bash
streamlit run ui/app.py
```

### 5. Run the tests and evals
```bash
pip install -r requirements-dev.txt
pytest                     # unit tests + scenario evals — offline, no API key needed
python -m muse.eval        # eval report on its own
```
CI runs both on every pull request (Python 3.11 and 3.12).
See [muse/eval/README.md](muse/eval/README.md) for the case format and live mode.

### 6. (Optional) Connect Google Calendar
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the Google Calendar API
3. Create OAuth 2.0 credentials (Desktop application)
4. Download `credentials.json` to the project root
5. Add your Google account as a test user in the OAuth consent screen
6. On first run, Muse will open a browser for OAuth consent

### 7. (Optional) Connect Gmail
1. In the same Google Cloud Console project, enable the **Gmail API**
2. The same `credentials.json` file works for both Calendar and Gmail
3. Add the `gmail.modify` scope to your OAuth consent screen
4. On first run of the Email Agent, Muse will open a browser for Gmail OAuth consent
5. A separate token (`token_gmail.json`) is created for Gmail to avoid scope conflicts with Calendar

## Hosting a Tester Round

To let a few invited artists try Muse on one shared deployment, turn on tester mode:

| Setting | Value | Why |
|---|---|---|
| `MUSE_TESTER_MODE` | `1` | Each browser session gets its own copy of the sample data, which clears on refresh. Google sign-in and the Settings panel are off. |
| `MUSE_APP_PASSWORD` | set | Only people with the password can chat. Every message uses your API key. |
| `MUSE_SEED_DEMO_DATA` | `1` (default) | Testers start with sample gigs, invoices, contacts and emails. |
| `MUSE_SINGLE_USER` | unset | Not for tester rounds: it shares one Google connection with everyone. |

On the Phase 0 VM ([deploy/README.md](deploy/README.md)), layer `deploy/docker-compose.tester.yml` over the usual compose file; the steps are under *Tester round* there. On Streamlit Community Cloud, put `ANTHROPIC_API_KEY`, `STREAMLIT_URL`, `MUSE_TESTER_MODE` and `MUSE_APP_PASSWORD` in the app's secrets and leave out the `[google_oauth]` section.

## Example Interactions

### Calendar Agent
```
🎤 You: I just got offered a session at West End Sound next Thursday,
         noon to 5pm, $500. Engineer is Miles.

🎵 Muse: I checked your calendar — you're free next Thursday. Created:

         🎙️ Session at West End Sound
         📍 West End Sound, Atlanta
         🕐 Thursday, Feb 20 · 12:00 PM - 5:00 PM
         💰 $500
         👤 Contact: Miles

         Want me to add any gear notes or send a confirmation?
```

### Email Agent
```
🎤 You: Check my inbox

📧 Muse: You have 3 emails in your inbox. 2 are unread:

         📩 [NEW] Booking Inquiry - March 22 at The Earl
           From: Sarah Chen <sarah@theearlatlanta.com>
           Mar 1 — "We'd love to have you play The Earl..."

         📩 [NEW] Session Rates - West End Sound
           From: Miles Davis Jr <miles@westendsound.com>
           Feb 28 — "Following up on our conversation..."

         📩 Re: Summer Festival Lineup
           From: Dave Promotions <bookings@davepromotes.com>
           Feb 25 — "Great news! You're confirmed..."

         Want me to read any of these or extract gig details?
```

### Invoice Agent
```
🎤 You: Create an invoice for The Earl for that $400 gig on March 22

💰 Muse: Here's the invoice preview:

         📝 Invoice INV-2026-003
           Status: DRAFT
           To: The Earl
           Date: 2026-02-18
           Due: Due upon receipt

           Line Items:
             - Live performance @ The Earl (2026-03-22) — $400.00

           Total: $400.00

         Want me to generate the PDF or make any changes?
```

```
🎤 You: How much have I made this year?

💰 Muse: Here's your income summary for 2026:

         💵 Total Invoiced: $925.00
         ✅ Paid: $400.00 (1 invoice)
         ⏳ Outstanding: $525.00 (1 invoice)
         ⚠️ Overdue: $0.00

         Want to see the details or create a new invoice?
```

### Social Media Agent
```
🎤 You: Draft a post about my gig at The Earl this Saturday

📱 Muse: Here's your post draft:

         --- 📸 INSTAGRAM POST DRAFT ---
           Status: 📝 DRAFT
           Type: Feed

           Caption:
           ATLANTA. Saturday night. The Earl. This is the one you
           don't want to miss. Full band, new songs, and some energy
           that's been building all week. Doors at 8. Link in bio.

           Hashtags: #livemusic #atlantamusic #theearlatlanta
           #indierock #liveshow #newmusic #supportlocalmusic
           --- END DRAFT ---

         Tell me to edit it, or copy the caption to post on Instagram.
```

```
🎤 You: Show my voice samples

📱 Muse: You have 5 voice samples in your library:

         1. [gig_promo] "ATLANTA. This Saturday. The Earl. Doors at 8..."
         2. [behind_the_scenes] "3am in the studio and this track just..."
         3. [fan_engagement] "Last night was unreal. Sold out room..."
         4. [new_release] "It's here. New single drops this Friday..."
         5. [collaboration] "Huge shoutout to @miles_westendsound..."

         Want to add a new voice sample or generate a post?
```

## Project Structure

```
muse/
├── muse/
│   ├── config.py              # App configuration
│   ├── orchestrator.py        # Routes requests to agents
│   ├── agents/
│   │   ├── base.py            # Base agent with tool calling loop
│   │   ├── calendar_agent.py  # Calendar management agent
│   │   ├── email_agent.py     # Email management agent
│   │   ├── invoice_agent.py   # Invoice management agent
│   │   └── social_agent.py    # Social media agent (Instagram)
│   ├── tools/
│   │   ├── calendar_tools.py  # Google Calendar + local SQLite
│   │   ├── email_tools.py     # Gmail API + local SQLite
│   │   ├── invoice_tools.py   # Invoice CRUD + PDF generation
│   │   └── social_tools.py    # Post CRUD + voice engine bridge
│   ├── models/
│   │   ├── events.py          # Calendar event models
│   │   ├── emails.py          # Email message models
│   │   ├── invoices.py        # Invoice data models
│   │   └── social.py          # Social post & voice sample models
│   └── rag/
│       └── voice_engine.py    # ChromaDB RAG for voice matching
├── ui/
│   └── app.py                 # Streamlit interface
├── tests/                     # pytest: tool backends, agent loop, router, evals
├── scripts/
│   └── chat.py                # terminal chat (all agents or one)
├── invoices/                  # Generated PDF output directory
├── chroma_db/                 # ChromaDB persistent storage (auto-created)
└── requirements.txt
```

## Tech Stack

- **LLM:** Claude Sonnet 5.5 for agents, Claude Haiku 5.5 for routing (Anthropic Python SDK 2.x; override with `MUSE_AGENT_MODEL` / `MUSE_ROUTER_MODEL`)
- **Agent Framework:** Custom (raw tool calling, no LangChain)
- **Calendar:** Google Calendar API + SQLite fallback
- **Email:** Gmail API + SQLite fallback
- **Invoicing:** ReportLab PDF generation + SQLite
- **Social Media:** ChromaDB RAG + SQLite (local drafts)
- **UI:** Streamlit
- **Data Models:** Pydantic v2
- **Storage:** SQLite (local-first) + ChromaDB (vector store)

## Why No LangChain?

This project is built on the raw Anthropic SDK intentionally. For a Forward Deployed Engineer role, understanding what happens under the hood matters — how tool calling works, how the agent loop operates, how to manage conversation state. When deploying in enterprise customer environments, framework abstractions may not be available or appropriate.

## Background

Built by [William Landrum](https://linkedin.com/in/william-landrum) — AI Engineer with 4 years of enterprise AI deployment experience (100+ engagements, Fortune 500 clients). Inspired by watching my brother, a professional session musician and recording engineer, lose hours every week to logistics that should be automated.

## License

MIT
