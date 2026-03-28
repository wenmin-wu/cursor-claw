# cursor-claw

Turn your [Cursor](https://www.cursor.com/) editor into an [openclaw](https://github.com/tsuji-tomonori/openclaw)-like Mattermost agent. cursor-claw bridges Mattermost to the Cursor Agent CLI per thread — mention the bot in any channel or send it a DM, and it runs the Cursor agent against your codebase and replies in-thread.

## Requirements

- Python 3.10+
- Cursor `agent` CLI (see below)
- A Mattermost server with a bot account and token

### Install the Cursor Agent CLI

```bash
curl https://cursor.com/install -fsS | bash
```

This installs the `agent` binary and makes it available in your `PATH`.

## Installation

```bash
pip install cursor-claw
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv tool install cursor-claw
```

## Setup

### 1. Create a Mattermost Bot Account

1. In Mattermost, go to **System Console → Integrations → Bot Accounts**
2. Create a new bot and copy the **bot token**
3. Add the bot to the channels you want it to monitor

### 2. Initialize cursor-claw

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

### 3. Configure the Bot

Edit `~/.cursorclaw/config.json`. The minimum required fields are:

```json
{
  "mattermost_base_url": "https://your-mattermost.example.com",
  "mattermost_bot_token": "your-bot-token-here",
  "workspace": "/path/to/your/code/repo"
}
```

### 4. Start the Bot

```bash
cursorclaw start
```

The bot connects to Mattermost via WebSocket and is ready to receive messages.

## Configuration Reference

Config file: `~/.cursorclaw/config.json`

### Connection

```json
{
  "mattermost_base_url": "https://mattermost.example.com",
  "mattermost_bot_token": "your-bot-token",
  "mattermost_verify": true
}
```

| Key | Default | Description |
|---|---|---|
| `mattermost_base_url` | `""` | Mattermost server URL |
| `mattermost_bot_token` | `""` | Bot account token |
| `mattermost_verify` | `true` | Verify TLS certificates |

### Agent

```json
{
  "workspace": "/path/to/your/repo",
  "agent_command": "agent"
}
```

| Key | Default | Description |
|---|---|---|
| `workspace` | `"."` | Path to the code repo passed to `agent --workspace` |
| `agent_command` | `"agent"` | Cursor agent executable name or path |

### Chat Behaviour

```json
{
  "chatmode": "oncall",
  "onchar_prefixes": [">"],
  "reply_in_thread": true,
  "react_emoji": "eyes",
  "max_post_chars": 15000
}
```

| Key | Default | Description |
|---|---|---|
| `chatmode` | `"oncall"` | When to respond: `oncall` (@mention only), `onmessage` (every message), `onchar` (prefix trigger) |
| `onchar_prefixes` | `[">"]` | Trigger prefixes when `chatmode` is `"onchar"` |
| `reply_in_thread` | `true` | Post replies in the same Mattermost thread |
| `react_emoji` | `"eyes"` | Emoji added to the trigger post while the agent is running |
| `max_post_chars` | `15000` | Max characters per post; long replies are split automatically |

### Access Control

```json
{
  "dm_enabled": true,
  "dm_allow_from": ["user_id_1", "user_id_2"],
  "group_policy": "open",
  "group_allow_from": []
}
```

| Key | Default | Description |
|---|---|---|
| `dm_enabled` | `true` | Allow direct messages |
| `dm_allow_from` | `[]` | Mattermost user IDs allowed to DM (empty = anyone) |
| `group_policy` | `"open"` | Channel policy: `"open"` (all channels) or `"allowlist"` |
| `group_allow_from` | `[]` | Channel IDs allowed when `group_policy` is `"allowlist"` |

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

## How It Works

1. cursor-claw listens to Mattermost over a persistent WebSocket connection
2. When a message triggers the bot (mention, DM, or prefix), it reacts with the configured emoji to acknowledge
3. The message is forwarded to the Cursor `agent` CLI with `--workspace` pointed at your repo
4. Agent output is streamed back and posted to Mattermost in chunks (split at tool-call boundaries so each post is readable)
5. Each thread maintains a `session_id` for conversation continuity — the agent remembers context across follow-up messages in the same thread
6. The acknowledgement reaction is removed when the turn completes

## CLI Reference

```
cursorclaw init [--force]   # Create config and scaffold workspace files
cursorclaw start            # Connect to Mattermost and start the bot
cursorclaw run              # Alias for start
```

## License

MIT
