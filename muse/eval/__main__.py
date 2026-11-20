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
    parser.add_argument("--router-only", action="store_true",
                        help="only check routing (with --live: a few cents' worth of classification calls)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show tool calls and responses")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    cases = load_cases(args.case, router_only=args.router_only)
    if not cases:
        print(f"No cases match {args.case!r}")
        return 1

    live_client = make_live_client() if args.live else None
    mode = "LIVE" if args.live else "mock"
    print(f"Running {len(cases)} case(s) in {mode} mode\n")

    if args.router_only:
        return run_router_only(cases, live_client)

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
    if live_client is not None:
        from muse.config import config
        print(f"\nModels: agents {config.MODEL} (effort {config.AGENT_EFFORT}), "
              f"router {config.ROUTER_MODEL} (effort {config.ROUTER_EFFORT})")
        print("Usage and estimated cost:")
        print(live_client.report())
    return 0 if passed == len(cases) else 1


def run_router_only(cases, live_client) -> int:
    from muse.config import config
    from muse.eval.scripted_client import ScriptedClient
    from muse.orchestrator import Orchestrator

    passed = 0
    for case in cases:
        client = live_client or ScriptedClient(route=case["route"], trajectory=[])
        got = Orchestrator(client=client)._classify(case["input"])
        ok = got == case["route"]
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {case['id']:<40} expected {case['route']:<9} got {got}")
    print(f"\n{passed}/{len(cases)} routed correctly")
    if live_client is not None:
        print(f"\nRouter: {config.ROUTER_MODEL} (effort {config.ROUTER_EFFORT})")
        print(live_client.report())
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
