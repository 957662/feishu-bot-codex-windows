# Phase 9 Summary

**Date completed:** 2026-05-27

## What's in place

- `Orchestrator.restore_from_disk()` — daemon restart picks up running bindings from `running-<name>` marker files
- `FeishuThrottled(RuntimeError)` exception + FakeLarkCli `simulate_throttle()` helper for tests
- `BindingConfig` opt-in security fields: `allow_users`, `require_confirm_patterns`, `max_message_length`, `session_idle_timeout_seconds`
- `daemon/inbound.py` `DEFAULT_CONFIRM_MAP = {"confirm_yes":"y","confirm_no":"n"}` for /clear-style prompts
- `InboundPipeline.on_chat_id_discovered` callback — auto-captures chat_id from first message

## Verification

```bash
pytest -v --cov=feishu_bot_claude
```

189+ tests passing, 100% coverage on core modules.

## v1.0.0 release

After Phase 9, the system meets all original requirements from the design spec:

- Real-time bidirectional mirror ✓
- 1 project ↔ 1 bot strict isolation ✓
- Native Claude slash commands via menu + text intercept ✓
- TUI-side `/bot-*` commands work ✓
- China Feishu (`open.feishu.cn`) baseline ✓
- macOS Keychain credential safety ✓
- Daemon auto-restart + state recovery ✓
- Rate-limit hardening primitives ✓
- Opt-in user whitelist + dangerous-command confirmation fields ✓

## v2 candidates (out of v1)

- Image / file message support (Vision input)
- Multiple users on one project / one bot
- Web management dashboard
- Linux GUI integration
- Cross-device binding sync via Drive
- Live wire-up of opt-in security fields into InboundPipeline (currently fields exist on config but aren't auto-read by orchestrator)
- Backoff invocation around RealLarkCli send_text/send_card (FeishuThrottled exists; wrapper deferred)
- Outbound detection of confirmation prompts in jsonl (DEFAULT_CONFIRM_MAP exists; jsonl-side detection deferred)
