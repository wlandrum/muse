"""Quick CLI test for the Email Agent — no Streamlit needed.

Usage:
    python -m tests.test_email_cli

Runs in local email mode (SQLite) so no Google credentials required.
Sample booking emails are pre-loaded for testing.
"""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from muse.agents.email_agent import EmailAgent


def main():
    print("\n📧 Muse Email Agent — CLI Test Mode")
    print("=" * 50)
    print("Type your requests naturally. Type 'quit' to exit.\n")
    print("Try things like:")
    print('  "Check my inbox"')
    print('  "Show me unread emails"')
    print('  "Read the email from Sarah about The Earl"')
    print('  "Extract the gig details from that booking email"')
    print('  "Draft a reply saying I\'m interested but need to check my schedule"')
    print('  "Search for emails about festival"')
    print()

    agent = EmailAgent()

    while True:
        try:
            user_input = input("🎤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSee you! 📧")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("\nSee you! 📧")
            break

        print("\n📧 Muse: ", end="", flush=True)
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
