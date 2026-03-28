---
summary: How to set up and configure the Mattermost channel for cursor-claw.
read_when:
  - user asks how to configure Mattermost
  - user asks about bot_token, chatmode, or dm_allow_from for Mattermost
  - user wants the bot to respond only on @mention, every message, or a trigger prefix
  - user asks about group_policy or allowlist for Mattermost channels
---

# Mattermost

Included in the base install — no extra dependencies needed.

## 1. Create a bot account

1. Go to **System Console → Integrations → Bot Accounts → Add Bot Account**
2. Copy the token
3. Add the bot to the channels you want it to monitor (the bot only sees channels it is a member of)

## 2. Configure

Add to `~/.cursorclaw/config.json`:

```json
{
  "channels": {
    "mattermost": {
      "enabled": true,
      "base_url": "https://mattermost.example.com",
      "bot_token": "YOUR_BOT_TOKEN",
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
| `chatmode` | `"oncall"` | `oncall` — @mention only; `onmessage` — every message; `onchar` — prefix trigger |
| `onchar_prefixes` | `[">"]` | Trigger prefixes when `chatmode` is `"onchar"` |
| `dm_enabled` | `true` | Allow direct messages |
| `dm_allow_from` | `[]` | Mattermost user IDs allowed to DM (empty = anyone) |
| `group_policy` | `"open"` | `"open"` — all channels; `"allowlist"` — only listed channels |
| `group_allow_from` | `[]` | Channel IDs allowed when `group_policy` is `"allowlist"` |
| `react_emoji` | `"eyes"` | Emoji added to the trigger post while the agent is running |
| `reply_in_thread` | `true` | Post replies in the same thread as the trigger message |
| `max_post_chars` | `15000` | Max characters per post; long replies are split automatically |

## 3. Chat modes

| Mode | Trigger |
|---|---|
| `oncall` | Bot responds only when @mentioned by name |
| `onmessage` | Bot responds to every message in the channel |
| `onchar` | Bot responds when message starts with one of `onchar_prefixes` |

## 4. Access control

- **DMs**: controlled by `dm_allow_from` — list specific user IDs, or leave empty for anyone
- **Group channels**: set `group_policy` to `"allowlist"` and list channel IDs in `group_allow_from` to restrict which channels the bot responds in

## 5. Behaviour

- The bot adds `react_emoji` (default 👀) to the trigger post while processing
- Responses are posted in-thread when `reply_in_thread` is `true`
- Long responses are split at `max_post_chars` boundaries
