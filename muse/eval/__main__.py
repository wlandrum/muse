"""CLI: python -m muse.eval [--case PATTERN] [--live] [--verbose]"""

from __future__ import annotations

import argparse
import logging
import sys

from muse.eval.runner import load_cases, make_live_client, run_case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Muse agent evals.")
    parser.add_argument("--case", default="*", help="glob over case ids, e.g. 'invoice-*'")
    parser.add_argument("--live", action="store_true",
                        help="use the real Anthropic API (requires MUSE_EVAL_ALLOW_LIVE=1)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show tool calls and responses")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    cases = load_cases(args.case)
    if not cases:
        print(f"No cases match {args.case!r}")
        return 1

    live_client = make_live_client() if args.live else None
    mode = "LIVE" if args.live else "mock"
    print(f"Running {len(cases)} case(s) in {mode} mode\n")

    passed = 0
    for case in cases:
        result = run_case(case, live_client=live_client)
        passed += result.passed
        mark = "PASS" if result.passed else "FAIL"
        print(f"  {mark}  {result.id:<40} {result.route or '-':<9} {result.seconds:5.2f}s")
        for failure in result.failures:
            print(f"        - {failure}")
        if args.verbose:
            for c in result.calls:
                print(f"        > {c['name']}({c['input']})")
            print(f"        < {(result.response or '')[:200]!r}")

    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
