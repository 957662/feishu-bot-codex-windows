# Phase 3 Summary

**Date completed:** 2026-05-27

## What's in place

- `daemon/tmux.py` — `Tmux` ABC, `FakeTmux` (records calls + configurable session state), `RealTmux` (subprocess wrapper around `tmux has-session/new-session/send-keys/kill-session`)
- `daemon/feishu.py` — `LarkCli` ABC, `FakeLarkCli` (records send + queued consume events), `RealLarkCli` (subprocess wrapper around `lark-cli` for send_text/send_card/update_card/consume_events)
- Real-binary smoke tests (skip when binaries absent)
- Fake-only unit tests for behavior

## Verification

```bash
pytest tests/unit/test_tmux_fake.py tests/unit/test_feishu_fake.py -v
pytest tests/integration/test_tmux_real.py tests/integration/test_feishu_real.py -v
```

## What's intentionally missing

- No `auth bot-new` wrapper yet (Phase 7 covers OAuth flow)
- No menu push API (Phase 7)
- No file upload (Phase 4 / uploads.py will use lark-cli drive +upload)
- No retry/backoff logic in adapters (Phase 9 hardening adds this around call sites)

## Next phase preview

Phase 4 — Card rendering: card.py, turn.py, tools.py, uploads.py with
golden fixtures for every Claude jsonl event type.
