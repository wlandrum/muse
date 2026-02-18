"""Quick CLI test for the Calendar Agent — no Streamlit needed.

Usage:
    python -m tests.test_calendar_cli

Runs in local calendar mode (SQLite) so no Google credentials required.
"""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from muse.agents.calendar_agent import CalendarAgent


def main():
    print("\n🎵 Muse Calendar Agent — CLI Test Mode")
    print("=" * 50)
    print("Type your requests naturally. Type 'quit' to exit.\n")
    print("Try things like:")
    print('  "Book a session at West End Sound next Thursday, noon to 5pm, $500"')
    print('  "I have a gig at The Earl on March 15, load-in at 5, set at 9, pays $300"')
    print('  "What\'s on my schedule this week?"')
    print('  "Am I free next Saturday afternoon?"')
    print()

    agent = CalendarAgent()

    while True:
        try:
            user_input = input("🎤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSee you! 🎵")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("\nSee you! 🎵")
            break

        print("\n🎵 Muse: ", end="", flush=True)
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
