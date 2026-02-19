"""Quick CLI test for the CRM Agent — no Streamlit needed.

Usage:
    python -m tests.test_crm_cli

Runs with local SQLite database. Sample contacts are pre-loaded for testing.
"""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from muse.agents.crm_agent import CRMAgent


def main():
    print("\n👥 Muse CRM Agent — CLI Test Mode")
    print("=" * 50)
    print("Type your requests naturally. Type 'quit' to exit.\n")
    print("Try things like:")
    print('  "Show me all my contacts"')
    print('  "Tell me about The Earl"')
    print('  "Add a new contact: Vinyl Lounge, venue, contact Jamie Lee, jamie@vinyllounge.com"')
    print('  "Log a meeting note for West End Sound — discussed rates for March session"')
    print('  "Who do I need to follow up with?"')
    print('  "What\'s my history with Dave Promotions?"')
    print()

    agent = CRMAgent()

    while True:
        try:
            user_input = input("🎤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSee you! 👥")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("\nSee you! 👥")
            break

        print("\n👥 Muse: ", end="", flush=True)
        try:
            response = agent.run(user_input)
            print(response)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        print()


if __name__ == "__main__":
    main()
