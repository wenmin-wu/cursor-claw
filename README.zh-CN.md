**[English](README.md)**

将你的 [Cursor](https://www.cursor.com/) 编辑器变成多频道 AI 编程助手。cursor-claw 将 Mattermost、Telegram 和 QQ 接入 Cursor Agent CLI——每个对话线程拥有独立的持久化会话，让助手在跨消息交互中保留上下文记忆。

## 环境要求

- Python 3.10+
- Cursor `agent` CLI（见下方）
- 至少一个受支持的聊天频道

### 安装 Cursor Agent CLI

```bash
curl https://cursor.com/install -fsS | bash
```

该命令会安装 `agent` 二进制文件并将其加入 `PATH`。

## 安装

```bash
pip install cursor-claw
```

安装可选频道依赖：

```bash
pip install 'cursor-claw[telegram]'   # Telegram 支持
pip install 'cursor-claw[qq]'         # QQ 支持
pip install 'cursor-claw[all]'        # 所有频道
```

或使用 [uv](https://github.com/astral-sh/uv)：

```bash
uv tool install 'cursor-claw[all]'
```

## 初始化

### 1. 初始化 cursor-claw

```bash
cursorclaw init
```

此命令会在 `~/.cursorclaw/config.json` 生成默认配置，并在 `~/.cursorclaw/workspace/` 创建三个上下文文件：

| 文件 | 用途 |
|---|---|
| `AGENT.md` | Cursor 助手的系统指令 |
| `SOUL.md` | 机器人的人格与价值观 |
| `MEMORY.md` | 助手可读写的持久化笔记 |

编辑这些文件可自定义助手的行为。

### 2. 配置频道

编辑 `~/.cursorclaw/config.json`，启用至少一个频道（参见下方[频道配置](#频道配置)）。

### 3. 启动

```bash
cursorclaw start
```

所有已启用的频道将并发启动。助手会在同一线程内跨消息保留对话上下文。

---

## 频道配置

配置文件：`~/.cursorclaw/config.json`

### Mattermost

**1. 创建机器人账号**
- 进入系统控制台 → 集成 → 机器人账号 → 添加机器人账号
- 复制 Token，并将机器人添加到需要监听的频道

**2. 配置**

```json
{
  "channels": {
    "mattermost": {
      "enabled": true,
      "base_url": "https://mattermost.example.com",
      "bot_token": "your-bot-token",
      "verify": true,
      "chatmode": "oncall",
      "dm_enabled": true,
      "dm_allow_from": [],
      "group_policy": "open",
      "group_allow_from": [],
      "react_emoji": "eyes",
      "reply_in_thread": true,
      "max_post_chars": 15000
    }
  }
}
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `base_url` | `""` | Mattermost 服务器地址 |
| `bot_token` | `""` | 机器人账号 Token |
| `verify` | `true` | 是否验证 TLS 证书 |
| `chatmode` | `"oncall"` | `oncall`（仅@提及）、`onmessage`（所有消息）、`onchar`（前缀触发） |
| `onchar_prefixes` | `[">"]` | `chatmode` 为 `"onchar"` 时的触发前缀 |
| `dm_enabled` | `true` | 是否允许私信 |
| `dm_allow_from` | `[]` | 允许私信的 Mattermost 用户 ID（为空表示所有人） |
| `group_policy` | `"open"` | `"open"`（所有频道）或 `"allowlist"` |
| `group_allow_from` | `[]` | `group_policy` 为 `"allowlist"` 时的允许频道 ID |
| `react_emoji` | `"eyes"` | 助手运行期间对触发消息添加的 Emoji |
| `reply_in_thread` | `true` | 是否在同一线程内回复 |
| `max_post_chars` | `15000` | 单条消息最大字符数，超长回复会自动拆分 |

### Telegram

需要先安装：`pip install 'cursor-claw[telegram]'`

**1. 创建机器人**
- 打开 Telegram，搜索 `@BotFather`
- 发送 `/newbot`，按提示操作，复制 Token

**2. 配置**

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allow_from": ["YOUR_TELEGRAM_USER_ID"],
      "proxy": null,
      "max_message_chars": 4000
    }
  }
}
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `token` | `""` | 来自 @BotFather 的机器人 Token |
| `allow_from` | `[]` | 允许使用机器人的 Telegram 用户 ID（为空表示所有人） |
| `proxy` | `null` | 可选的 HTTP/SOCKS5 代理地址 |
| `max_message_chars` | `4000` | 单条 Telegram 消息最大字符数 |

> 通过向 `@userinfobot` 发消息可获取你的 Telegram 用户 ID。

可用机器人指令：`/new` 开启新对话，`/help` 查看指令列表。

### QQ

需要先安装：`pip install 'cursor-claw[qq]'`

**1. 注册机器人**
- 访问 [QQ 开放平台](https://q.qq.com) → 创建机器人应用
- 在开发者设置中复制 **AppID** 和 **AppSecret**

**2. 配置**

```json
{
  "channels": {
    "qq": {
      "enabled": true,
      "app_id": "YOUR_APP_ID",
      "secret": "YOUR_APP_SECRET",
      "allow_from": ["YOUR_USER_OPENID"]
    }
  }
}
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `app_id` | `""` | QQ 机器人 AppID |
| `secret` | `""` | QQ 机器人 AppSecret |
| `allow_from` | `[]` | 允许使用机器人的 QQ 用户 openid（为空表示所有人）。用户首次发消息时，openid 会打印在日志中 |

---

## 全局配置

以下配置对所有频道生效。

### 助手

```json
{
  "workspace": "/path/to/your/repo",
  "agent_command": "agent"
}
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `workspace` | `"."` | 传给 `agent --workspace` 的代码仓库目录 |
| `agent_command` | `"agent"` | Cursor agent 可执行文件名或路径 |

### 超时

```json
{
  "chunk_timeout_sec": 300,
  "turn_timeout_sec": 1800,
  "outer_timeout_sec": 1800
}
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `chunk_timeout_sec` | `300` | 助手无输出超过该秒数后终止子进程 |
| `turn_timeout_sec` | `1800` | 单次对话轮次最大秒数 |
| `outer_timeout_sec` | `1800` | 整个异步任务的最终超时时间 |

---

## 工作原理

1. cursor-claw 并发连接所有已启用的频道
2. 当消息到达时（@提及、私信或触发前缀），转发给 Cursor `agent` CLI，并以 `--workspace` 指向你的代码仓库
3. 助手输出以分块方式流式返回（在工具调用边界处拆分，保证可读性）
4. 每个对话线程维护独立的 `session_id` 以保证连续性——助手在同一线程的后续消息中保留上下文

## CLI 命令

```
cursorclaw init [--force]   # 创建配置文件并初始化工作区文件
cursorclaw start            # 启动所有已启用的频道
cursorclaw run              # start 的别名
```

## Skills

[`docs/skills/`](docs/skills/) 目录包含 Cursor Agent Skill 的构建指南，说明如何将对应的 `SKILL.md` 放入 `~/.cursor/skills/`，从而在所有工作区永久生效。

| 指南 | 说明 |
|---|---|
| [`rednote-cli`](docs/skills/rednote-cli.md) | 通过 `rednote-cli` 抓取、搜索和发布小红书笔记 |

## 开源协议

MIT

---

<div align="center">
  <a href="https://star-history.com/#wenmin-wu/cursor-claw&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=wenmin-wu/cursor-claw&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=wenmin-wu/cursor-claw&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=wenmin-wu/cursor-claw&type=Date" />
    </picture>
  </a>
</div>
