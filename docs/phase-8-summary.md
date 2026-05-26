# Phase 8 Summary

**Date completed:** 2026-05-27

## What's in place

- `commands/bot-*.md` (6 files) — Claude Code user-level slash commands
- `scripts/install-commands.sh` — idempotent installer for slash commands
- `scripts/launchd.plist` — macOS service template (with __PYTHON__ / __HOME__ placeholders)
- `scripts/systemd.service` — Linux service template
- `scripts/feishu-bot-claude-shell` — tmux + claude wrapper
- `setup.sh` — full install/uninstall/update/doctor entry
- `docs/install.md` — user-facing install guide
- `cli.py shell` op — execs tmux helper directly (no daemon round-trip)

After Phase 8, a user can:

```bash
git clone <repo> && cd <repo>
./setup.sh
cd ~/some-project
feishu-bot-claude shell
# inside Claude:
/bot-new myproject
/bot-start
```

…and be fully mirrored to Feishu.

## What's intentionally missing (Phase 9)

- Persistent state recovery (daemon restart picks up running bindings)
- Rate-limit hardening (TokenBucket already exists, but isn't always applied)
- Security opt-in fields (allow_users whitelist, dangerous-command confirm)
- Stale binding detection + Feishu warning card
- bind atomicity (keychain.put then store.add — orphan secret on store failure)
