# Phase 7 Summary

**Date completed:** 2026-05-27

## What's in place

- `menu_template.py` — 26-button default menu (within 50-button floating-menu cap) + event_key → /command map
- `daemon/auth.py` — `bot_new` stream parser (QR + URL + creds with deferred-emit pattern)
- `daemon/menu.py` — `push_menu_with_fallback` (file-write on API failure)
- `daemon/feishu.py` — `RealLarkCli.auth_bot_new_stream` + `push_menu`; FakeLarkCli matching test helpers
- Real `bind`/`unbind` handlers replacing stubs (with full event streaming)
- Daemon wires MacOSKeychainStore, lark-cli auth runner, menu pusher at startup

## Verification

- Unit tests: `pytest tests/unit/test_menu_template.py tests/unit/test_auth.py tests/unit/test_menu_push.py tests/unit/test_handlers.py -v`
- Manual smoke: see `phase-7-smoke.md`

## Known gaps (deferred to Phase 9 hardening)

- bind atomicity: keychain.put happens before store.add; if store.add fails, secret is orphaned
- chat_id is hardcoded/empty in orchestrator wiring; first inbound message could populate it
- `lark-cli apps menu update` subcommand may not exist; file fallback handles this case

## Next phase preview

Phase 8 — Distribution:
- `.claude/commands/bot-*.md` (6 markdown files)
- `scripts/install-commands.sh`
- `scripts/launchd.plist` + `scripts/systemd.service`
- `setup.sh` (full)
