# cursor-claw

Turn your [Cursor](https://www.cursor.com/) editor into an [openclaw](https://github.com/tsuji-tomonori/openclaw)-like Mattermost agent. cursor-claw bridges Mattermost to the Cursor Agent CLI per thread — mention the bot in any channel or send it a DM, and it runs the Cursor agent against your codebase and replies in-thread.

## Requirements

- Python 3.11+
- [Cursor](https://www.cursor.com/) with the `agent` CLI available in your `PATH`
- A Mattermost server with a bot account and token

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

Edit `~/.cursorclaw/config.json`:

```json
{
  "mattermost_base_url": "https://your-mattermost.example.com",
  "mattermost_bot_token": "your-bot-token-here",
  "workspace": "/path/to/your/code/repo"
}
```

All settings can also be overridden via environment variables prefixed with `CURSOR_CLAW_`:

```bash
export CURSOR_CLAW_MATTERMOST_BASE_URL=https://your-mattermost.example.com
export CURSOR_CLAW_MATTERMOST_BOT_TOKEN=your-bot-token-here
export CURSOR_CLAW_WORKSPACE=/path/to/your/code/repo
```

### 4. Start the Bot

```bash
cursorclaw start
```

The bot connects to Mattermost via WebSocket and is ready to receive messages.

## Configuration Reference

| Key | Default | Description |
|---|---|---|
| `mattermost_base_url` | `""` | Mattermost server URL, e.g. `https://mattermost.example.com` |
| `mattermost_bot_token` | `""` | Bot account token |
| `mattermost_verify` | `true` | Verify TLS certificates |
| `workspace` | `"."` | Path to the code repo passed to `agent --workspace` |
| `agent_command` | `"agent"` | Cursor agent executable name or path |
| `state_db` | `~/.cursorclaw/state.db` | SQLite file for session continuity |
| `chatmode` | `"oncall"` | When to respond: `oncall` (on @mention), `onmessage` (every message), `onchar` (on prefix) |
| `onchar_prefixes` | `[">"]` | Trigger prefixes when `chatmode` is `onchar` |
| `dm_enabled` | `true` | Allow direct messages |
| `dm_allow_from` | `[]` | Mattermost user IDs allowed to DM (empty = anyone) |
| `group_policy` | `"open"` | Channel policy: `open` (all channels) or `allowlist` |
| `group_allow_from` | `[]` | Channel IDs allowed when `group_policy` is `allowlist` |
| `react_emoji` | `"eyes"` | Emoji reacted to the trigger post while the agent is running |
| `reply_in_thread` | `true` | Post replies in the same thread as the trigger |
| `max_post_chars` | `15000` | Maximum characters per Mattermost post (long replies are split) |
| `chunk_timeout_sec` | `300` | Seconds to wait for the next agent output chunk before killing |
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
