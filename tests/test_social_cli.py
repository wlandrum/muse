"""Quick CLI test for the Social Media Agent — no Streamlit needed.

Usage:
    python -m tests.test_social_cli

Runs with local SQLite database and ChromaDB for voice matching.
No Instagram credentials needed — drafts are stored locally.
"""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from muse.agents.social_agent import SocialAgent


def main():
    print("\n📱 Muse Social Media Agent — CLI Test Mode")
    print("=" * 50)
    print("Type your requests naturally. Type 'quit' to exit.\n")
    print("Try things like:")
    print('  "Draft a post about my gig at The Earl this Saturday"')
    print('  "Show my drafts"')
    print('  "Add a voice sample"')
    print('  "Generate hashtags for indie rock"')
    print('  "Show my voice samples"')
    print('  "Write a behind-the-scenes post about my studio session"')
    print()

    agent = SocialAgent()

    while True:
        try:
            user_input = input("🎤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSee you! 📱")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("\nSee you! 📱")
            break

        print("\n📱 Muse: ", end="", flush=True)
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
