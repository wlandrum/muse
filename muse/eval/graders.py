"""Graders: compare what happened during a run against a case's expectations."""

from __future__ import annotations

import glob
import os
import re
import sqlite3
from typing import Any

import jsonschema


def match(expected: Any, actual: Any) -> bool:
    """Match a value against an expectation.

    Expectations are literals (compared with ==, case-insensitively for
    strings) or a single-key operator dict:
      {contains: s} {startswith: s} {regex: p} {one_of: [...]} {gte: n} {lte: n}
      {min_len: n} {max_len: n}   (for lists/strings)
    Dicts without an operator key are matched as partial subsets.
    """
    if isinstance(expected, dict):
        if len(expected) == 1:
            op, arg = next(iter(expected.items()))
            if op == "contains":
                return actual is not None and str(arg).lower() in str(actual).lower()
            if op == "startswith":
                return actual is not None and str(actual).startswith(str(arg))
            if op == "regex":
                return actual is not None and re.search(arg, str(actual)) is not None
            if op == "one_of":
                return any(match(a, actual) for a in arg)
            if op == "gte":
                return actual is not None and float(actual) >= float(arg)
            if op == "lte":
                return actual is not None and float(actual) <= float(arg)
            if op == "min_len":
                return actual is not None and len(actual) >= arg
            if op == "max_len":
                return actual is not None and len(actual) <= arg
        if not isinstance(actual, dict):
            return False
        return all(k in actual and match(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.lower() == actual.lower()
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(expected) == float(actual)
    return expected == actual


def is_subsequence(expected: list[str], actual: list[str]) -> bool:
    it = iter(actual)
    return all(name in it for name in expected)


def grade(case: dict, run: dict, tool_schemas: dict[str, dict], workdir: str) -> list[str]:
    """Return a list of failure messages (empty == pass)."""
    expect = case.get("expect", {})
    failures: list[str] = []
    calls = run["calls"]
    called = [c["name"] for c in calls]

    if run["route"] != case["route"]:
        failures.append(f"route: expected {case['route']}, got {run['route']}")

    # Every tool call must be a known tool with schema-valid input.
    for c in calls:
        schema = tool_schemas.get(c["name"])
        if schema is None:
            failures.append(f"tool {c['name']!r} is not defined for this agent")
            continue
        try:
            jsonschema.validate(c["input"], schema)
        except jsonschema.ValidationError as e:
            failures.append(f"tool {c['name']!r} input invalid: {e.message}")

    if "tools_called" in expect and not is_subsequence(expect["tools_called"], called):
        failures.append(f"tools_called: expected {expect['tools_called']} in order, got {called}")

    for name in expect.get("tools_not_called", []):
        if name in called:
            failures.append(f"tools_not_called: {name!r} was called")

    for name, arg_expect in expect.get("tool_args", {}).items():
        matching = [c for c in calls if c["name"] == name]
        if not matching:
            failures.append(f"tool_args: {name!r} never called")
        elif not any(match(arg_expect, c["input"]) for c in matching):
            failures.append(f"tool_args: no {name!r} call matched {arg_expect}; got {[c['input'] for c in matching]}")

    for name, result_expect in expect.get("tool_results", {}).items():
        matching = [c for c in calls if c["name"] == name]
        if not matching:
            failures.append(f"tool_results: {name!r} never called")
        elif not any(match(result_expect, c["result"]) for c in matching):
            failures.append(f"tool_results: no {name!r} result matched {result_expect}; got {[c['result'] for c in matching]}")

    if expect.get("no_tool_errors", True):
        for c in calls:
            if c["error"] or (isinstance(c["result"], dict) and "error" in c["result"]):
                failures.append(f"tool {c['name']!r} errored: {c['error'] or c['result']['error']}")

    for check in expect.get("state", []):
        failures.extend(_check_state(check, workdir))

    response = run["response"] or ""
    for needle in expect.get("response_contains", []):
        if needle.lower() not in response.lower():
            failures.append(f"response_contains: {needle!r} not in response")

    return failures


def _check_state(check: dict, workdir: str) -> list[str]:
    if "sql" in check:
        conn = sqlite3.connect(os.path.join(workdir, "muse.db"))
        try:
            row = conn.execute(check["sql"]).fetchone()
        except sqlite3.Error as e:
            return [f"state sql failed ({check['sql']}): {e}"]
        finally:
            conn.close()
        value = row[0] if row else None
        if not match(check["equals"], value):
            return [f"state: {check['sql']} → {value!r}, expected {check['equals']!r}"]
    elif "files" in check:
        found = glob.glob(os.path.join(workdir, check["files"]))
        if not match(check["count"], len(found)):
            return [f"state: {len(found)} files match {check['files']!r}, expected {check['count']!r}"]
    return []
