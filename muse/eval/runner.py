"""Load eval cases and run them through the real orchestrator + agents.

Two modes share the same case files:

- mock (default): the model is a ScriptedClient replaying each case's gold
  `trajectory`. No API calls. Checks that routing, the agent loop, tool
  schemas, tool execution and resulting state all behave as the case expects.
- live: the model is the real Anthropic API and `trajectory` is ignored; the
  same `expect` block grades what the model actually did. Costs money, so it
  refuses to run unless MUSE_EVAL_ALLOW_LIVE=1 is set.
"""

from __future__ import annotations

import fnmatch
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from muse.eval.graders import grade
from muse.eval.sandbox import sandbox
from muse.eval.scripted_client import ScriptedClient
from muse.orchestrator import Orchestrator

CASES_DIR = Path(__file__).parent / "cases"
_REF = re.compile(r"\$\{([^}]+)\}")


@dataclass
class CaseResult:
    id: str
    passed: bool
    failures: list[str]
    route: str | None = None
    response: str | None = None
    calls: list[dict] = field(default_factory=list)
    seconds: float = 0.0


def load_cases(pattern: str = "*", cases_dir: Path = CASES_DIR, router_only: bool = False) -> list[dict]:
    """Load cases matching `pattern`. Cases marked `router_only` (no agent
    trajectory) are included only when `router_only` is set."""
    cases = []
    for path in sorted(cases_dir.glob("*.yaml")):
        for case in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            case["_file"] = path.name
            if case.get("router_only") and not router_only:
                continue
            if fnmatch.fnmatch(case["id"], pattern):
                cases.append(case)
    ids = [c["id"] for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate case ids: {sorted(dupes)}")
    return cases


def _lookup(context: dict, path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _resolve(obj: Any, context: dict) -> Any:
    """Substitute ${name.path} references with saved tool results."""
    if isinstance(obj, str):
        whole = _REF.fullmatch(obj)
        if whole:
            return _lookup(context, whole.group(1))
        return _REF.sub(lambda m: str(_lookup(context, m.group(1))), obj)
    if isinstance(obj, list):
        return [_resolve(v, context) for v in obj]
    if isinstance(obj, dict):
        return {k: _resolve(v, context) for k, v in obj.items()}
    return obj


def make_live_client():
    if os.environ.get("MUSE_EVAL_ALLOW_LIVE") != "1":
        raise RuntimeError(
            "Live evals call the Anthropic API and cost money. "
            "Set MUSE_EVAL_ALLOW_LIVE=1 to confirm."
        )
    from anthropic import Anthropic
    from muse.config import config
    from muse.eval.usage import UsageTrackingClient
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (looked in the environment and .env).")
    return UsageTrackingClient(Anthropic(api_key=config.ANTHROPIC_API_KEY))


def run_case(case: dict, live_client=None) -> CaseResult:
    started = time.perf_counter()
    context: dict = {}
    calls: list[dict] = []
    pending_names: list[str | None] = []

    with sandbox() as workdir:
        if live_client is None:
            client = ScriptedClient(
                route=case["route"],
                trajectory=case.get("trajectory", []),
                resolve=lambda obj: _resolve(obj, context),
                on_emit=pending_names.extend,
            )
        else:
            client = live_client
        orch = Orchestrator(client=client)

        try:
            for step in case.get("setup", []):
                agent = orch._get_agent(step["agent"])
                result = agent.execute_tool(step["tool"], _resolve(step.get("input", {}), context))
                if step.get("save_as"):
                    context[step["save_as"]] = result
        except Exception as e:
            return CaseResult(case["id"], False, [f"setup failed: {e!r}"])

        # Record every tool call the routed agent makes.
        wrapped: set[int] = set()
        get_agent = orch._get_agent

        def recording_get_agent(category):
            agent = get_agent(category)
            if agent is not None and id(agent) not in wrapped:
                wrapped.add(id(agent))
                execute = agent.execute_tool

                def recording_execute(name, tool_input):
                    save_as = pending_names.pop(0) if pending_names else None
                    record = {"name": name, "input": tool_input, "result": None, "error": None}
                    calls.append(record)
                    try:
                        record["result"] = execute(name, tool_input)
                    except Exception as e:
                        record["error"] = repr(e)
                        raise
                    if save_as:
                        context[save_as] = record["result"]
                    return record["result"]

                agent.execute_tool = recording_execute
            return agent

        orch._get_agent = recording_get_agent

        try:
            route, response = orch.route(case["input"])
        except Exception as e:
            return CaseResult(case["id"], False, [f"run raised {e!r}"], calls=calls,
                              seconds=time.perf_counter() - started)

        expected_agent = get_agent(case["route"])
        schemas = (
            {t["name"]: t["input_schema"] for t in expected_agent.tool_definitions()}
            if expected_agent else {}
        )
        run = {"route": route, "response": response, "calls": calls}
        failures = grade(case, run, schemas, workdir)
        if isinstance(client, ScriptedClient) and client.unused_steps:
            failures.append(f"agent stopped with {client.unused_steps} scripted step(s) unused")

    return CaseResult(case["id"], not failures, failures, route, response, calls,
                      time.perf_counter() - started)
