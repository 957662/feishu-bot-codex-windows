# Phase 5 Summary

**Date completed:** 2026-05-27

## What's in place

- `daemon/ratelimit.py` — `TokenBucket` (async wait + try_acquire), `BackoffPolicy`
- `daemon/state.py` — `BindingRuntimeState` with persist/restore
- `daemon/outbound.py` — `OutboundPipeline` reads new jsonl bytes past stored offset, groups into turns, calls LarkCli.send_card/update_card (rate-limited)
- `daemon/inbound.py` — `InboundPipeline` consumes lark-cli event NDJSON, routes text/slash/menu to Tmux.send_keys, supports user whitelist, truncates long messages
- All tested with FakeTmux + FakeLarkCli

## What's intentionally missing

- No watchfiles-based continuous tailing (Phase 6 orchestrator wires it up)
- No confirmation-button card rendering (Phase 6 handles the round-trip)
- No 11232 backoff invocation (the policy exists; orchestrator uses it in Phase 6)
- No backlog progress card (Phase 6)

## Next phase preview

Phase 6 — Orchestrator + Lifecycle:
- daemon/orchestrator.py — per-binding coroutine group (jsonl watcher + inbound + health)
- Wire OutboundPipeline.process_backlog + watchfiles for live tailing
- Implement real bind/start/stop/unbind handlers using the pipelines
- Backlog replay progress card with `--replay-on-start = all`
- Daemon-side state recovery on restart
