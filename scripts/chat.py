"""Chat with Muse in the terminal — no Streamlit needed.

Usage:
    python -m scripts.chat                    # full Muse (router picks the agent)
    python -m scripts.chat --agent calendar   # talk to one agent directly

Uses local SQLite/ChromaDB unless Google is connected. Needs ANTHROPIC_API_KEY.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse.orchestrator import Orchestrator

EXAMPLES = {
    None: [
        "Book a session at West End Sound next Thursday, noon to 5pm, $500",
        "Check my inbox",
        "How much have I made this year?",
    ],
    "calendar": [
        "I have a gig at The Earl on March 15, load-in at 5, set at 9, pays $300",
        "What's on my schedule this week?",
        "Am I free next Saturday afternoon?",
    ],
    "email": [
        "Check my inbox",
        "Extract the gig details from the booking inquiry",
        "Draft a reply to Sarah saying I'm in",
    ],
    "invoice": [
        "Show me my invoices",
        "Create an invoice for The Earl, $400 gig on March 22",
        "How much have I made this year?",
    ],
    "social": [
        "Draft a post about my gig at The Earl this Saturday",
        "Show my voice samples",
        "What drafts do I have?",
    ],
    "crm": [
        "Who do I work with at West End Sound?",
        "Log a meeting with Dave Promotions about the summer festival",
        "Add Patchwerk Recording as a studio contact",
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent", choices=["calendar", "email", "invoice", "social", "crm"],
                        help="bypass the router and talk to one agent")
    parser.add_argument("-v", "--verbose", action="store_true", help="show tool-call logs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s [%(name)s] %(message)s")

    orch = Orchestrator()
    agent = orch._get_agent(args.agent.upper()) if args.agent else None

    print(f"\n🎵 Muse — {args.agent or 'all agents'} (type 'quit' to exit)\n")
    print("Try:")
    for example in EXAMPLES[args.agent]:
        print(f'  "{example}"')
    print()

    while True:
        try:
            user_input = input("🎤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break

        try:
            if agent:
                reply = agent.run(user_input)
            else:
                category, reply = orch.route(user_input)
                print(f"   [{category}]")
            print(f"\n🎵 Muse: {reply}\n")
        except Exception as e:
            logging.exception("Request failed")
            print(f"\n❌ Error: {e}\n")

    print("\nSee you! 🎵")


if __name__ == "__main__":
    main()
