# feishu-bot-claude 设计文档

| 字段 | 值 |
|---|---|
| 日期 | 2026-05-26 |
| 状态 | Draft — 待用户 review |
| 项目目录 | `~/project/feishu-bot-claude/` |
| 作者 | qingyun + Claude(brainstorming session) |

## 摘要

`feishu-bot-claude` 是一个把本地 Claude Code TUI 双向镜像到飞书机器人的桥接系统。每个项目文件夹对应一个专属飞书机器人,严格 1:1 绑定。用户在项目目录里启动 Claude(包在 tmux 内),通过 `/bot-new`、`/bot-start` 等用户级斜杠命令完成绑定;此后本地 Claude 的每条事件实时渲染成飞书可更新卡片,飞书侧任何消息(文本或菜单按钮)实时注入回 Claude REPL,完整支持 Claude 原生斜杠命令。

系统由 5 个组件构成,核心实现是一个常驻 Python daemon(~1500–2000 LoC),复用官方 `lark-cli`(Go)处理所有飞书 API 调用。架构最大化复用、最小化自研代码量。

## 目标 / 非目标

### v1 In scope

- 实时双向镜像:本地 jsonl 任何更新流到飞书;飞书任何消息注入本地 Claude
- 每项目独立飞书机器人,严格 1:1 绑定,daemon 强制单例锁
- 全部 Claude 原生斜杠命令通过文本拦截或菜单按钮支持(`/clear`、`/compact`、`/agents`、`/model`、`/resume`、`/mcp` 等)
- TUI 内 6 个 `/bot-*` 用户级斜杠命令完成所有运维操作
- 首次 `/bot-start` 全量回放历史 jsonl 到飞书(默认 `replay_on_start = all`)
- 富文本 turn-card 渲染(默认 `render_style = rich`),工具调用折叠展示
- Bash/Read 长输出自动上传飞书云空间附下载链接
- Claude 内部确认弹窗(如 `/clear` 的 Y/N)渲染成飞书按钮卡片
- 飞书 11232 限流自动退避;daemon 崩溃 launchd 自启 + 状态恢复
- 凭证安全:App Secret 存 macOS Keychain,bindings.toml 仅存引用
- macOS 主支持(用户当前环境),Linux 兼容支持(systemd)

### Out of scope (v1)

- 飞书发图片/视频/文件作为 Claude 输入(v1 文字 only,后续 v2 可扩)
- 多用户共享同一机器人(用户场景明确为单人单机)
- 跨设备同步 binding 配置
- Web 管理界面
- 非 tmux 模式(即用户必须接受 tmux 包装本地 Claude)

## §1 — 架构与组件

### 拓扑

```
用户机器
├── 项目 A 目录 (~/project/foo)
│   ├── tmux session "claude-foo" 内跑 claude TUI
│   └── Claude session jsonl 位于
│       ~/.claude/projects/-Users-qingyun-project-foo/<uuid>.jsonl
│
├── feishu-bot-claude daemon (常驻 Python 进程)
│   配置: ~/.feishu-bot-claude/bindings.toml
│   状态: ~/.feishu-bot-claude/state.json
│   套接字: ~/.feishu-bot-claude/control.sock
│   per binding 3 个 asyncio 协程:
│     ① jsonl tailer    (fswatch/inotify)
│     ② lark-cli event consume subprocess 读 stdout
│     ③ menu/event_key router
│
├── feishu-bot-claude CLI (短命进程)
│   通过 control.sock 与 daemon 通信
│
└── ~/.claude/commands/bot-*.md  (6 个 markdown 文件)
                ↑↓
        飞书开放平台 (App A、App B …,经 lark-cli 长连接)
```

### 5 个组件

| 组件 | 形态 | 职责 |
|---|---|---|
| daemon | 常驻 Python 进程(launchd 自启) | 所有 binding 的镜像协程、IPC 服务端、状态持久化 |
| CLI | 短命 Python 进程 | 接收 `.claude/commands` 调用,转发到 daemon |
| `.claude/commands/bot-*.md` | 6 个 markdown 文件 | 让用户在 Claude TUI 输 `/bot-*` 触发 bash 调用 CLI |
| lark-cli | npm 装的 Go 二进制(已 clone 到 vendor/) | 所有飞书 API 通道(发送、收事件、上传文件等) |
| tmux | 系统已有 | 承载 Claude TUI;daemon `send-keys` 注入通道 |

### 关键设计决策

- daemon 单进程多 binding,共享 asyncio loop,共享限流桶
- CLI ↔ daemon 走 Unix socket(local-only、UID 隔离、零网络配置)
- 用 Claude Code 原生用户级斜杠命令机制,不写插件
- lark-cli 作为唯一飞书 API 适配层,daemon 不直接调飞书 HTTP

### 硬不变量

```
1 个 project folder ↔ 1 个 binding ↔ 1 个 tmux session
                    ↔ 1 个 Claude TUI ↔ 1 个飞书 App
```

任何一边重复,daemon 拒绝并报错。

## §2 — 绑定生命周期

### 状态机

```
       /bot-new                /bot-start
unbound ────────► bound,stopped ─────────► bound,running
                    ▲   ▲                    │    ▲
       /bot-remove  │   └───── /bot-stop ────┘    │
                    │                              │
                    └─── crash + retry (auto) ─────┘
```

### 6 个 TUI 斜杠命令

| 命令 | 作用 | 参数默认 |
|---|---|---|
| `/bot-new <name>` | 在 `$PWD` 上建新绑定 | name 缺省 = `$(basename $PWD)-bot` |
| `/bot-list` | 表格显示所有绑定 + 状态 | 无 |
| `/bot-remove <name>` | 删本地绑定(不动飞书 App) | 必填 name |
| `/bot-start` | 启动当前项目镜像 | 无,按 `$PWD` 匹配 |
| `/bot-stop` | 停镜像,保留 tmux 和 Claude TUI | 无 |
| `/bot-config <key>=<val>` | 改运行时参数 | 见下 |

`/bot-config` 支持的 key:

- `render_style` ∈ `minimal` / `full` / `rich`(默认 `rich`)
- `replay_on_start` ∈ `0` / `100` / `all`(默认 `all`)
- `mute_thinking` ∈ `true` / `false`(默认 `false`)
- `card_throttle_ms` ∈ int(默认 `300`)

### `/bot-new` 流程

1. daemon 校验:当前 `$PWD` 是否已绑定 → 是则拒绝
2. daemon 调 `lark-cli auth bot-new` 子进程
3. 抓 lark-cli stdout 拿到二维码 ASCII,通过 IPC 流式发给 CLI 渲染
4. 用户用飞书 App 扫码,lark-cli 完成 OAuth 拿到 `app_id`/`app_secret`
5. App Secret 存 macOS Keychain (`security add-generic-password -s feishu-bot-claude.<name>.app_secret`)
6. binding 写入 `bindings.toml`(secret 字段只存 keychain 引用)
7. daemon 尝试用 lark-cli 推送默认菜单 JSON;失败则把 JSON 写到 `~/.feishu-bot-claude/menus/<name>.json`,提示用户去开放平台手动粘贴
8. CLI 输出 "✅ binding <name> created. Next: /bot-start"

### `/bot-start` 流程

1. daemon 取当前 `$PWD` 对应 binding,校验非 running
2. 环境检查:tmux session `claude-<name>` 存在;`~/.claude/projects/<encoded-cwd>/` 下有 jsonl
3. 选 jsonl:目录中 mtime 最新的文件
4. 启动 backlog 回放(详见 §3.4)
5. 起 3 个协程:jsonl tailer、lark-cli event consume、menu router
6. 标记 state = running,写 state.json
7. 飞书发 "Claude bot ready" 状态卡

### `/bot-stop` 流程

1. 取消 3 个协程(优雅,SIGTERM 等待 5 秒,超时 SIGKILL)
2. 飞书发 "Claude bot offline" 状态卡
3. state = stopped,写 state.json
4. tmux 和 Claude TUI 不动,用户自行控制

### `/bot-list` 输出样式

```
NAME       PROJECT                  TMUX          SESSION       STATE
foo-bot    ~/project/foo            claude-foo    7a0ba9e4...   running
bar-bot    ~/project/bar            claude-bar    (none)        stopped
old-bot    ~/project/legacy         (gone)        —             stale
```

### bindings.toml schema

```toml
data_dir = "~/.feishu-bot-claude"

[[binding]]
name = "foo-bot"
project_dir = "/Users/qingyun/project/foo"
tmux_session = "claude-foo"
feishu_app_id = "cli_xxxxxxxxxxxxxx"
secret_ref = "feishu-bot-claude.foo-bot.app_secret"  # keychain key
render_style = "rich"
replay_on_start = "all"
mute_thinking = false
card_throttle_ms = 300
created_at = "2026-05-26T18:50:00+08:00"
```

## §3 — 双向数据流与渲染

### 3.1 出站:turn-card 合并模型

**核心原则**:一个 turn = 一张飞书可更新卡片,而不是每个事件一条新消息。

```
Claude jsonl 事件流              Feishu 卡片
─────────────────────────────────────────────────────
user "实现登录"        ━━━►   新卡片:User #1
─────────────────────────────────────────────────────
assistant text         ━━━►   新卡片:Claude turn #1
tool_use Read auth.go  ━━━┐
tool_result (50 行)    ━━━┼━► 同一张卡片 update
tool_use Edit auth.go  ━━━┤    追加 collapsible section
tool_result success    ━━━┤
assistant "完成"       ━━━┘
─────────────────────────────────────────────────────
user "再测一下"        ━━━►   新卡片:User #2
```

触发新卡片:遇到 `user` 角色事件。
更新现有卡片:同一 turn 内的 `assistant` / `tool_use` / `tool_result`。

### 3.2 单 turn assistant 卡片结构(rich 默认)

```
┌─────────────────────────────────────────┐
│ 🤖 Claude · project-foo · opus-4-7      │  header
├─────────────────────────────────────────┤
│ 我会先读 auth.go 再修改。                │  markdown body
│                                         │
│ ▼ [📖 Read] auth.go  ✓ 50 lines         │  collapsible tool #1
│   ```                                   │
│   package auth … (前 20 行预览)          │
│   ```                                   │
│                                         │
│ ▼ [✏️ Edit] auth.go  ✓ +12 -3            │  collapsible tool #2
│   diff preview                          │
│                                         │
│ 完成,改好了。                            │  final text
├─────────────────────────────────────────┤
│ 1.2K tokens · 4.3s · 2 tools            │  footer note
└─────────────────────────────────────────┘
```

工具图标映射:Read=📖、Edit=✏️、Bash=💻、Grep=🔍、Glob=📁、WebFetch=🌐、Task=🤖(子代理)、其他=🔧

### 3.3 长输出处理

- 卡片内只显示前 20 行(可配置)+ "…省略 N 行,点击下载完整结果"
- 完整结果通过 `lark-cli drive +upload` 上传到飞书云空间,卡片附下载链接
- 上传失败:卡片只显示前 20 行 + 摘要,记错误日志

### 3.4 Backlog 回放(`replay_on_start = all`)

```
[1] 读完整 jsonl,按 turn 分组
[2] 发状态卡:"⏳ Replaying 0/238 turns …"(后续 update)
[3] for turn in turns:
        渲染卡片 → lark-cli im +messages-send
        sleep 200ms                  # 5/sec,留 10× 余地
        update 状态卡 "⏳ N/238"
        idempotency_key = f"{session_id}:{turn_index}"  # 防重发
[4] 状态卡转 "✅ Replay complete, mirror live"
```

期间新进入的 jsonl 事件 daemon 同时 buffer,回放完成后追上实时。

### 3.5 入站:三路分发

```
                  lark-cli event consume
                  im.message.receive_v1 (NDJSON stdout)
                              │
                              ▼
                  ┌───────────────────────┐
                  │ daemon: event router  │
                  └───────────────────────┘
                       │       │       │
            ┌──────────┘       │       └──────────┐
            ▼                  ▼                  ▼
   普通文本消息          菜单按钮事件          /xxx 文本
   (im.message)          (application.        (im.message,
                          bot.menu_v6)         content starts /)
            │                  │                  │
            ▼                  ▼                  ▼
   tmux send-keys      event_key → / 命令   tmux send-keys
   "<text>\n"          映射表 → 同左路径    "/xxx\n"
                                            (Claude 当原生斜杠命令)
```

注入是字面键盘事件,飞书发 `/compact` 在 Claude TUI 里跟本地敲键盘完全等价。

### 3.6 Claude 内部确认弹窗(`/clear` Y/N 等)

```
Claude 弹 Y/N 提问
    ↓ jsonl 写 system 事件
    ↓ daemon 检测到等待输入状态
    ↓ 飞书发交互卡片(两个 action button:确认 / 取消)
    ↓ 用户点确认
    ↓ event_key=confirm_yes → tmux send-keys "y\n"
```

### 3.7 菜单设计(开放平台一次性配置)

悬浮菜单 5×10 满配:

```
[会话]    /clear  /compact  /resume  /cost  /status  /quit
[配置]    /model  /config  /init  /permissions  /login  /logout
[工具]    /agents  /mcp  /memory  /hooks  /skills  /add-dir
[信息]    /help  /usage  /doctor  /bug
[桥接]    pause-mirror  resume-mirror  reload-config  show-bindings
```

最后一组是桥接命令(非 Claude 原生),被 daemon 拦截不注入 tmux,直接调用 daemon 自身行为。

启动时 daemon 尝试用 lark-cli 推送菜单 JSON 到开放平台。如 lark-cli 不支持菜单 API,fallback:JSON 写入文件,CLI 输出文件路径让用户手动粘贴到开放平台 UI(一次性)。

### 3.8 限流策略

| 层 | 策略 |
|---|---|
| per-binding token bucket | 10 tokens/sec 注入,容量 20,超出排队 |
| 同卡片更新去抖 | `card_throttle_ms = 300`,300ms 内多次 update 合并为最后一次 |
| 错误 11232 退避 | 指数退避 1s → 2s → 4s → 8s → 16s,封顶 30s |
| 超大 burst | 100ms 内 ≥10 个事件触发"摘要模式",只发摘要不展开 |

### 3.9 网络与延迟容忍(China 飞书实测基线)

部署目标:`open.feishu.cn`(China 版本,默认)。实测延迟(2026-05-26 测于用户机器):

| 指标 | 实测值 | 设计阈值 |
|---|---|---|
| ICMP ping avg / max | 36ms / 124ms | — |
| HTTPS TTFB P50 / P99 估算 | 215ms / 1500ms | — |
| HTTPS 完整请求 P50 / P99 | 234ms / 2000ms | — |
| 偶发抖动 stddev | 30ms,可能撞到秒级 | — |

**超时阈值**(全部明显高于 P99 + 安全余量):

| 操作 | timeout | 理由 |
|---|---|---|
| 普通消息发送 (`im +messages-send`) | **5s** | P99 撞 2s,留 2.5× 余地 |
| 卡片更新 | **5s** | 同上 |
| 文件上传 (`drive +upload`) | **60s** | 大文件 + 抖动 |
| OAuth 扫码等待 | **300s** | 用户体验有界,但允许慢慢扫 |
| event consume 心跳间隙 | **60s** 无事件才视为可疑,**120s** 才标重连 | 长连接正常静默期可达分钟级 |
| daemon ↔ lark-cli IPC | **10s** | 子进程启动 + 第一次响应 |

**重连策略**:`event consume` 子进程退出 → daemon 1s backoff → 重启 → 失败 3 次累计后才告警飞书("⚠️ 重连飞书超时,请检查网络")。**不要在第一次失败时就报错**——80% 是临时抖动,2 秒内会恢复。

**bindings.toml 新增字段**:

```toml
[binding.network]
domain = "https://open.feishu.cn"           # 默认国内版,国际版改 larksuite.com
api_timeout_ms = 5000
upload_timeout_ms = 60000
event_silent_threshold_ms = 60000           # 静默超阈值才探活
event_dead_threshold_ms = 120000            # 真正算断线
reconnect_grace_failures = 3                # N 次连续失败才告警
```

所有时间相关常量集中在这里,方便调优,默认值即上表。

## §4 — IPC 协议与项目结构

### 4.1 `.claude/commands/bot-*.md` 内容

模板,共 6 个文件,每个 5–8 行:

```markdown
<!-- ~/.claude/commands/bot-new.md -->
---
allowed-tools: Bash(feishu-bot-claude:*)
description: Bind current project to a new Feishu bot (QR-scan to create app)
argument-hint: <bot-name>
---

!`feishu-bot-claude bind "$ARGUMENTS" --cwd "$PWD"`
```

六个命令的 bash 调用一行表:

| 文件 | 调用 |
|---|---|
| `bot-new.md` | `!feishu-bot-claude bind "$ARGUMENTS" --cwd "$PWD"` |
| `bot-list.md` | `!feishu-bot-claude list` |
| `bot-remove.md` | `!feishu-bot-claude unbind "$ARGUMENTS"` |
| `bot-start.md` | `!feishu-bot-claude start --cwd "$PWD"` |
| `bot-stop.md` | `!feishu-bot-claude stop --cwd "$PWD"` |
| `bot-config.md` | `!feishu-bot-claude config --cwd "$PWD" "$ARGUMENTS"` |

### 4.2 IPC 协议:Unix socket + NDJSON

socket 路径:`~/.feishu-bot-claude/control.sock`(权限 0600)

**请求**(CLI → daemon,一行 JSON):

```json
{"op": "bind", "args": {"name": "foo-bot", "cwd": "/Users/qingyun/project/foo"}, "request_id": "abc-123"}
```

`op` 枚举:`bind` / `unbind` / `start` / `stop` / `list` / `config` / `status` / `shell`

**响应**(daemon → CLI,多行 NDJSON 流):

```json
{"type": "log", "level": "info", "msg": "正在创建飞书 App..."}
{"type": "qrcode", "ascii": "█▀▀█...", "url": "https://..."}
{"type": "progress", "value": 0.6, "msg": "认证中"}
{"type": "result", "ok": true, "data": {"app_id": "cli_xxx", "binding": "foo-bot"}}
{"type": "done"}
```

CLI 端渲染规则:

- `log` / `progress` → 打印或刷新 spinner
- `qrcode` → 直接打印 ASCII(终端原生显示)
- `result` → 单条结果(`/bot-start`)或表格(`/bot-list`)
- `done` → 关闭连接退出

### 4.3 项目目录结构

```
~/project/feishu-bot-claude/
├── README.md
├── pyproject.toml
├── setup.sh                       # 一键安装脚本(详见 §4.5)
├── Makefile                       # 开发者粒度更细的目标
├── feishu_bot_claude/             # Python 包
│   ├── __main__.py                # python -m feishu_bot_claude 入口
│   ├── cli.py                     # CLI:socket 客户端,~150 行
│   ├── daemon/
│   │   ├── server.py              # asyncio Unix socket server
│   │   ├── binding.py             # Binding 状态机 + lock
│   │   ├── orchestrator.py        # 每 binding 启 3 协程
│   │   ├── outbound.py            # jsonl → turn card 渲染管道
│   │   ├── inbound.py             # lark-cli event consume → tmux
│   │   ├── tmux.py                # send-keys / has-session 封装
│   │   ├── feishu.py              # lark-cli 子进程封装
│   │   ├── config.py              # bindings.toml + keychain
│   │   └── ratelimit.py           # token bucket + 11232 退避
│   ├── rendering/
│   │   ├── card.py                # 飞书卡片 JSON builder
│   │   ├── turn.py                # jsonl event → 卡片
│   │   ├── tools.py               # 每种 tool_use 的渲染
│   │   └── uploads.py             # 大输出上传 lark drive
│   └── proto.py                   # 协议数据类
├── commands/                      # 模板 .claude/commands/*.md
│   ├── bot-new.md
│   ├── bot-list.md
│   ├── bot-remove.md
│   ├── bot-start.md
│   ├── bot-stop.md
│   └── bot-config.md
├── vendor/
│   └── lark-cli/                  # 已 clone (larksuite/cli)
├── scripts/
│   ├── install-commands.sh        # 复制 commands/ → ~/.claude/commands/
│   ├── launchd.plist              # macOS daemon 服务定义
│   └── systemd.service            # Linux 服务定义
├── docs/
│   └── superpowers/specs/
│       └── 2026-05-26-feishu-bot-claude-design.md  # 本文件
└── tests/
    ├── unit/
    ├── golden/
    ├── integration/
    └── smoke/
```

### 4.4 端到端调用栈追踪(`/bot-new foo-bot`)

```
[Claude TUI 用户输入]    /bot-new foo-bot
       │
       ▼
[Claude Code 解析 markdown]
       匹配 ~/.claude/commands/bot-new.md
       替换 $ARGUMENTS=foo-bot, $PWD=...
       执行 bash: feishu-bot-claude bind "foo-bot" --cwd "..."
       │
       ▼
[feishu-bot-claude CLI]
       连 ~/.feishu-bot-claude/control.sock
       发 {"op":"bind","args":{...}}
       读 socket NDJSON 流
       │
       ▼
[daemon]
       ① 校验 $PWD 未被占
       ② spawn lark-cli auth bot-new,抓 QR ASCII
          流式 {"type":"qrcode",...} 发回 CLI
       ③ 等待扫码,拿 app_id/app_secret
       ④ secret 存 keychain,binding 写 bindings.toml
       ⑤ 推送菜单 JSON(失败降级写文件)
       ⑥ 发 {"type":"result","ok":true,...} + {"type":"done"}
       │
       ▼
[CLI 终端渲染]
       打印 QR,等待,完成提示
       │
       ▼
[Claude TUI 显示 bash 输出]  用户看到结果
```

### 4.5 setup.sh 一键安装

```bash
./setup.sh             # 安装 / 升级(可重入)
./setup.sh --uninstall # 卸 daemon、删 socket、保留 bindings.toml
./setup.sh --update    # git pull + 重装包 + 重启 daemon
./setup.sh --doctor    # 诊断依赖、socket、lark-cli 认证
```

脚本职责(伪代码):

```bash
#!/usr/bin/env bash
set -euo pipefail
detect_os                                # macOS / Linux
need_cmd python3 node tmux              # 缺哪个报错并提示安装命令
ensure_lark_cli                         # npm i -g @larksuite/cli 若未装
[ -d .venv ] || uv venv .venv           # Python venv
uv pip install -e .                     # 把 feishu-bot-claude 加进 PATH
install_slash_commands                  # cp commands/*.md ~/.claude/commands/
install_daemon_service                  # 写 launchd.plist 或 systemd.service
start_daemon && wait_for_socket         # 启动并健康检查
echo "✅ Done. Next: cd <project> && feishu-bot-claude shell"
```

## §5 — 错误恢复、安全与测试

### 5.1 故障恢复矩阵

| 故障源 | 探测 | 恢复策略 |
|---|---|---|
| lark-cli 子进程死 | SIGCHLD / 退出码非 0 | backoff respawn 1s→2s→…→30s,记日志,飞书通知 |
| tmux session 不见 | 每 30s `tmux has-session` 检查 | binding 标 stale,飞书警告,`/bot-list` 高亮 |
| jsonl 轮转(`/clear` 后新会话) | fswatch 目录,mtime 跳变 | 自动切到新文件,飞书发 "新会话已绑定" |
| daemon 自身崩溃 | launchd `KeepAlive=true` | 自启;读 bindings.toml + state.json,重建协程,飞书发 "daemon 已恢复" |
| Feishu 11232 限流 | lark-cli 返回错误码 | 指数退避;15s 内宽限;超过则丢老消息保新 |
| 网络抖动(秒级) | event consume 静默 > 60s | 探活但不报错;< 120s 恢复算正常,> 120s 才告警飞书 |
| 网络断开 | event consume 子进程退出 | 1s backoff 重启;连续 3 次失败才告警飞书 |
| 磁盘满 / jsonl 损坏 | 读取异常 | binding 暂停,飞书发严重错误卡 |
| 凭证失效 | lark-cli 返回 401 | 飞书发卡提示:"运行 /bot-config refresh-creds" |

### 5.2 daemon 启动状态恢复

```
[daemon 进程启动]
    ↓
[读 ~/.feishu-bot-claude/bindings.toml]
    ↓
对每个 state=running 的 binding:
    ① tmux has-session "claude-<name>"?
       否 → 标 stale,飞书警告,跳过
    ② 找 ~/.claude/projects/<encoded>/ 下 mtime 最新 jsonl
       无 → 标 stopped,等用户 /bot-start
    ③ 读 state.json 拿 byte_offset,从该位置继续 tail
    ④ 起 3 协程,飞书发 "daemon 已重连"
```

关键:每处理完一个 jsonl 事件 daemon 把 `(binding_name, jsonl_path, byte_offset)` 写入 `state.json`,崩溃恢复时不会重发已发送事件。

### 5.3 安全边界

#### 默认开启(无脑安全)

- 文件权限:`bindings.toml` / `control.sock` / `state.json` / `logs/` 全部 0600 或 0700
- App Secret 存 macOS Keychain,bindings.toml 仅存 keychain 引用
- daemon 只监听 Unix socket,不开网络端口
- 飞书消息内容永远不进 `shell -c`,只走 `tmux send-keys` 当字面键盘事件
- lark-cli 子进程不传 `--as user`,bot identity only

#### 可选加固(opt-in,默认 off)

```toml
[binding.security]
allow_users = ["ou_xxxxxxxx"]                # 白名单 open_id,空 = 允许所有
require_confirm_patterns = [                 # 命中正则强制飞书弹按钮确认
  "rm\\s+-rf",
  "drop\\s+(table|database)",
  "DELETE\\s+FROM",
]
max_message_length = 8000                    # 防超长消息卡死 tmux
session_idle_timeout = "30m"                # 空闲超时自动 /bot-stop
```

v1 用户为单人单机,全部 opt-in 字段默认空/off。

### 5.4 测试策略

```
tests/
├── unit/                                   # 不依赖外部
│   ├── test_card_render.py                 # 卡片 JSON builder
│   ├── test_turn_grouping.py               # jsonl → turn 分组
│   ├── test_ratelimit.py                   # token bucket + 11232 退避
│   ├── test_config_keychain.py             # toml r/w + keychain mock
│   └── test_proto.py                       # 协议 dataclass roundtrip
│
├── golden/                                 # 快照比对
│   ├── fixtures/
│   │   ├── turn_simple.jsonl
│   │   ├── turn_with_read.jsonl
│   │   ├── turn_with_bash_long.jsonl       # 长输出 → 上传降级
│   │   ├── turn_with_subagent.jsonl        # Task 子代理
│   │   └── turn_confirmation.jsonl         # /clear 弹窗
│   └── expected/*.card.json
│
├── integration/                            # 真 daemon + 假外部
│   ├── fake_lark_cli/                      # 替身 lark-cli,emit NDJSON
│   ├── fake_tmux/                          # 替身 tmux,记录 send-keys
│   ├── test_bind_flow.py
│   ├── test_start_replay.py
│   ├── test_inbound_routing.py
│   ├── test_crash_recovery.py
│   └── test_rate_limit_backoff.py
│
└── smoke/                                  # 手动跑,需真飞书凭证
    └── README.md                           # 5 项手动 checklist
```

CI 跑 unit + golden + integration,smoke 本地手动。

### 5.5 边界条件清单

| 情况 | 处理 |
|---|---|
| 用户连续 `/bot-start` 两次 | 第二次拿不到 binding 锁,daemon 返回 "已在 running" |
| 飞书消息粘贴 5000 行代码 | 截断到 `max_message_length`,头尾保留,中间标记 "...长度截断..." |
| 飞书发图片/视频 | v1 不支持,daemon 回复 "暂不支持图像输入,请发文字" |
| `/bot-new` 中途断网 | lark-cli auth 超时,CLI 输出错误并提示重试,binding 不写入 |
| Claude TUI 自己崩了 | tmux 没了 → daemon 探测 stale → 飞书警告 |
| 一天累积 10000+ 事件 | jsonl 几十 MB,replay 用流式读不全量 load,内存 O(1) |
| 时区 | 内部全 UTC,显示按本地;ISO 8601 with offset |

## 关键决策记录

| # | 决策 | 替代方案 | 选定理由 |
|---|---|---|---|
| 1 | 桥接定位:实时双向镜像 | (a) 仅上下文 (b) 按需 (c) 一次性 backlog | 用户明确选择最强版本 |
| 2 | 选 lark-cli + 自研薄 daemon | (b) fork cc-connect (c) 旁路 cc-connect | lark-cli 吃掉飞书 API,剩余业务逻辑量再大也得自写;30k LoC fork 不划算 |
| 3 | 语言 Python | Go | 开发速度;jsonl/asyncio 生态;用户已确认 |
| 4 | 注入方式 tmux send-keys | (a) Claude SDK (b) jsonl 追加 | 唯一能让 Claude 原生斜杠命令工作的方式 |
| 5 | 安装 setup.sh 脚本 | 手动多步命令 | 一次性安装、跨平台、可重入 |
| 6 | 默认 `replay_on_start = all` | 100 / 0 | 用户明确选;200 turn × 200ms ≈ 40s 可接受 |
| 7 | 默认 `render_style = rich` | minimal / full | 用户明确选 |
| 8 | 长输出上传飞书云空间 | 截断 / 不传 | 用户明确选 |
| 9 | 确认弹窗用飞书按钮卡 | 自动接受 | 用户明确选 |
| 10 | daemon 启动 launchd 自启 | 手动前台 | 关机重开仍可用 |
| 11 | 菜单推送 lark-cli + JSON fallback | 纯手动 / 纯 API | 兼容 lark-cli 当前版本不确定支持菜单 API |
| 12 | 1 项目 = 1 bot 强制锁 | 多绑定灵活 | 用户明确"千万不能搞混";锁简化整套并发模型 |
| 13 | 默认 domain = `open.feishu.cn`(China) | larksuite.com 国际版 | 用户使用 China 版;实测延迟低、稳定 |
| 14 | 超时阈值放宽到 P99 × 2.5(API 5s,上传 60s) | 短超时 1-2s | 实测 P99 撞 2s,严苛超时会产生假错误 |

## 实施路线图(v1)

按依赖关系建议的实现顺序,后续 `writing-plans` 阶段细化:

1. 项目骨架 + pyproject.toml + setup.sh 框架
2. proto.py + IPC 协议 + 假 daemon/CLI 通信打通
3. config.py + bindings.toml + keychain(unit test 完整)
4. tmux.py + 假 tmux fixture(unit test)
5. feishu.py 封装 lark-cli send/event consume(integration with fake)
6. rendering/(card/turn/tools/uploads)+ golden test
7. daemon/outbound.py(jsonl tail → 卡片管道)
8. daemon/inbound.py(event consume → tmux)
9. daemon/orchestrator.py + 3 协程编排
10. daemon/server.py + 完整 IPC 处理
11. CLI 层:6 个 op 的客户端实现
12. `.claude/commands/*.md` 模板
13. scripts/install-* + launchd.plist + systemd.service
14. setup.sh 完整实现
15. 错误恢复 + 状态持久化
16. 限流退避
17. 安全加固字段
18. 文档:README + 用户指南

## v2 候选(out of v1 scope)

- 飞书图片/文件作为 Claude 输入(Vision)
- 多用户/多机器人聊同一项目
- Web 管理界面
- Linux 全功能支持(systemd 已 v1,但 GUI 集成 v2)
- 配置同步到 Drive(跨设备)
- 桥接命令深度集成(`/bot-fork` 复制 binding 等)

## 待办

无未决问题。所有设计点已在 brainstorming 闭环。
