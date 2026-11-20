# Muse evals

Scenario evals for the orchestrator and all five agents. Each case is a realistic
artist request plus what a correct Muse does about it: which agent it routes to,
which tools it calls with what arguments, what it must *not* do, and what the
database looks like afterwards.

```bash
python -m muse.eval                     # all cases, mock mode (free, offline)
python -m muse.eval --case 'invoice-*'  # filter by id glob
python -m muse.eval -v                  # show tool calls + responses
pytest tests/test_eval_harness.py       # same cases under pytest (what CI runs)

MUSE_EVAL_ALLOW_LIVE=1 python -m muse.eval --live   # real API — costs money
```

## Modes

| | Model | What it tells you |
|---|---|---|
| **mock** (default) | `ScriptedClient` replays each case's gold `trajectory` | The plumbing is right: routing wiring, agent loop, tool schemas, tool execution, resulting state, safety rules encoded as expectations. Catches tool/schema drift and backend bugs. |
| **live** | Real Anthropic API; `trajectory` ignored | Whether the *model* actually behaves: routes correctly, calls the right tools, respects "draft, don't send". Use when changing prompts or models. |

Both modes run every case in a throwaway sandbox (temp SQLite DB, temp ChromaDB with
an offline hashing embedder, temp invoice dir, Google auth forced to local fallback),
so nothing touches your real data.

## Case format

Cases live in `cases/*.yaml`, one list per file:

```yaml
- id: calendar-conflict-blocks-create      # unique
  description: Why this case exists.
  input: "Book a rehearsal at Rock Box on December 5, 2026 from 8pm to 10pm."
  route: CALENDAR                          # CALENDAR | EMAIL | INVOICE | SOCIAL | CRM | GENERAL
  setup:                                   # optional: tool calls run directly before the case
    - agent: CALENDAR
      tool: create_event
      input: {...}
      save_as: gig                         # result available as ${gig.event.id}
  trajectory:                              # mock mode: the model's turns, in order
    - tools:
        - name: check_conflicts
          input: {...}                     # may use ${name.path} references
          save_as: conflicts               # optional
    - text: "Final reply to the user."
  expect:                                  # graded in both modes
    tools_called: [check_conflicts]        # ordered subsequence
    tools_not_called: [create_event]
    tool_args:                             # some call of this tool must match
      check_conflicts: {start_time: {startswith: "2026-12-05T20"}}
    tool_results:                          # some result of this tool must match
      get_contact_summary: {event_count: 0}
    no_tool_errors: true                   # default
    state:
      - sql: "SELECT count(*) FROM events"
        equals: 1
      - files: "invoices/*.pdf"
        count: 1
    response_contains: [The Earl]          # case-insensitive
```

Matchers: literals (strings compare case-insensitively, numbers by value), or
`{contains}`, `{startswith}`, `{regex}`, `{one_of: [...]}`, `{gte}`, `{lte}`,
`{min_len}`, `{max_len}`.
A plain dict matches as a subset.

Every tool call is also validated against the agent's `input_schema`.

Use explicit dates in inputs ("December 5, 2026", not "next Friday") so
`tool_args` stay stable in live mode.
