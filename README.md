# cursor-claw

Turn your [Cursor](https://www.cursor.com/) editor into a multi-channel AI coding agent. cursor-claw bridges Mattermost, Telegram, and QQ to the Cursor Agent CLI — each chat thread gets its own persistent session so the agent remembers context across messages.

## Requirements

- Python 3.10+
- Cursor `agent` CLI (see below)
- At least one supported chat channel

### Install the Cursor Agent CLI

```bash
curl https://cursor.com/install -fsS | bash
```

This installs the `agent` binary and makes it available in your `PATH`.

## Installation

```bash
pip install cursor-claw
```

With optional channel dependencies:

```bash
pip install 'cursor-claw[telegram]'   # Telegram support
pip install 'cursor-claw[qq]'         # QQ support
pip install 'cursor-claw[all]'        # All channels
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv tool install 'cursor-claw[all]'
```

## Setup

### 1. Initialize cursor-claw

```bash
cursorclaw init
```

This creates `~/.cursorclaw/config.json` with defaults and scaffolds three context files in `~/.cursorclaw/workspace/`:

| File | Purpose |
|---|---|
| `AGENT.md` | System instructions for the Cursor agent |
| `SOUL.md` | Persona / values of the bot |
| `MEMORY.md` | Persistent notes the agent can read and update |

Edit these files to customise how your agent behaves.

### 2. Configure a channel

Edit `~/.cursorclaw/config.json` and enable at least one channel (see [Channel Configuration](#channel-configuration) below).

### 3. Start

```bash
cursorclaw start
```

All enabled channels start concurrently. The agent remembers conversation context per thread.

---

## Channel Configuration

Config file: `~/.cursorclaw/config.json`

### Mattermost

**1. Create a bot account**
- System Console → Integrations → Bot Accounts → Add Bot Account
- Copy the token and add the bot to the channels you want it to monitor

**2. Configure**

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

| Key | Default | Description |
|---|---|---|
| `base_url` | `""` | Mattermost server URL |
| `bot_token` | `""` | Bot account token |
| `verify` | `true` | Verify TLS certificates |
| `chatmode` | `"oncall"` | `oncall` (@mention only), `onmessage` (every message), `onchar` (prefix trigger) |
| `onchar_prefixes` | `[">"]` | Trigger prefixes when `chatmode` is `"onchar"` |
| `dm_enabled` | `true` | Allow direct messages |
| `dm_allow_from` | `[]` | Mattermost user IDs allowed to DM (empty = anyone) |
| `group_policy` | `"open"` | `"open"` (all channels) or `"allowlist"` |
| `group_allow_from` | `[]` | Channel IDs allowed when `group_policy` is `"allowlist"` |
| `react_emoji` | `"eyes"` | Emoji reacted to the trigger post while the agent is running |
| `reply_in_thread` | `true` | Post replies in the same thread |
| `max_post_chars` | `15000` | Max characters per post; long replies are split automatically |

### Telegram

Requires `pip install 'cursor-claw[telegram]'`.

**1. Create a bot**
- Open Telegram, search `@BotFather`
- Send `/newbot`, follow the prompts, copy the token

**2. Configure**

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

| Key | Default | Description |
|---|---|---|
| `token` | `""` | Bot token from @BotFather |
| `allow_from` | `[]` | Telegram user IDs allowed to use the bot (empty = anyone) |
| `proxy` | `null` | Optional HTTP/SOCKS5 proxy URL |
| `max_message_chars` | `4000` | Max characters per Telegram message |

> You can find your Telegram user ID by messaging `@userinfobot`.

Available bot commands: `/new` to start a fresh conversation, `/help` for the command list.

### QQ

Requires `pip install 'cursor-claw[qq]'`.

**1. Register a bot**
- Visit [QQ Open Platform](https://q.qq.com) → create a bot application
- Copy the **AppID** and **AppSecret** from Developer Settings

**2. Configure**

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

| Key | Default | Description |
|---|---|---|
| `app_id` | `""` | QQ bot AppID |
| `secret` | `""` | QQ bot AppSecret |
| `allow_from` | `[]` | QQ user openids allowed to use the bot (empty = anyone). Find openids in logs when a user messages the bot. |

---

## Global Configuration

These settings apply to all channels.

### Agent

```json
{
  "workspace": "/path/to/your/repo",
  "agent_command": "agent"
}
```

| Key | Default | Description |
|---|---|---|
| `workspace` | `"."` | Code repo directory passed to `agent --workspace` |
| `agent_command` | `"agent"` | Cursor agent executable name or path |

### Timeouts

```json
{
  "chunk_timeout_sec": 300,
  "turn_timeout_sec": 1800,
  "outer_timeout_sec": 1800
}
```

| Key | Default | Description |
|---|---|---|
| `chunk_timeout_sec` | `300` | Seconds without agent output before killing the subprocess |
| `turn_timeout_sec` | `1800` | Maximum seconds for a single agent turn |
| `outer_timeout_sec` | `1800` | Hard outer timeout for the whole async task |

---

## How It Works

1. cursor-claw connects to all enabled channels concurrently
2. When a message arrives (mention, DM, or trigger prefix), it is forwarded to the Cursor `agent` CLI with `--workspace` pointed at your repo
3. Agent output streams back in chunks (split at tool-call boundaries for readable posts)
4. Each chat thread maintains a `session_id` for conversation continuity — the agent remembers context across follow-up messages in the same thread

## CLI Reference

```
cursorclaw init [--force]   # Create config and scaffold workspace files
cursorclaw start            # Start all enabled channels
cursorclaw run              # Alias for start
```

## License

MIT
