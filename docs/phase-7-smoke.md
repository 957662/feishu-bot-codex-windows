# Phase 7 Smoke Test Recipe

Requires:
- `lark-cli` installed and globally authenticated (`lark-cli auth login` once)
- macOS for Keychain
- A real Feishu (China) account

## Steps

1. Start daemon:
   ```bash
   python -m feishu_bot_claude daemon &
   ```

2. Create a sandbox project dir:
   ```bash
   mkdir -p ~/tmp/smoketest && cd ~/tmp/smoketest
   ```

3. Trigger `bind`:
   ```bash
   feishu-bot-claude bind smoketest-bot --cwd "$PWD"
   ```
   Expected: terminal shows ASCII QR + URL. Scan with Feishu mobile.

4. After scan, daemon prints `App created: cli_xxx` and writes `~/.feishu-bot-claude/bindings.toml` containing the new binding.

5. Verify Keychain:
   ```bash
   security find-generic-password -s feishu-bot-claude -a "smoketest-bot.app_secret" -w
   ```
   Should print the secret.

6. Verify list:
   ```bash
   feishu-bot-claude list
   ```
   Should show smoketest-bot with the cwd.

7. Clean up:
   ```bash
   feishu-bot-claude unbind smoketest-bot
   ```
   The Feishu app remains on the open platform (delete manually).
