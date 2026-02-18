"""Quick CLI test for the Invoice Agent — no Streamlit needed.

Usage:
    python -m tests.test_invoice_cli

Runs with local SQLite database. Sample invoices are pre-loaded for testing.
"""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from muse.agents.invoice_agent import InvoiceAgent


def main():
    print("\n💰 Muse Invoice Agent — CLI Test Mode")
    print("=" * 50)
    print("Type your requests naturally. Type 'quit' to exit.\n")
    print("Try things like:")
    print('  "Show me my invoices"')
    print('  "Create an invoice for The Earl, $400 gig on March 22"')
    print('  "Generate a PDF for invoice INV-2026-002"')
    print('  "How much have I made this year?"')
    print('  "Mark the first invoice as paid via Venmo"')
    print('  "Show me outstanding invoices"')
    print()

    agent = InvoiceAgent()

    while True:
        try:
            user_input = input("🎤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSee you! 💰")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("\nSee you! 💰")
            break

        print("\n💰 Muse: ", end="", flush=True)
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
