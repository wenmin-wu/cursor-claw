---
summary: How to set up and configure the Telegram channel for cursor-claw.
read_when:
  - user asks how to configure Telegram
  - user asks about bot token, allow_from, or proxy for Telegram
  - user asks about /new command or streaming responses in Telegram
---

# Telegram

Requires `pip install 'cursor-claw[telegram]'`.

## 1. Create a bot via BotFather

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`, follow the prompts, and copy the token

## 2. Configure

Add to `~/.cursorclaw/config.json`:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allow_from": [],
      "proxy": null,
      "max_message_chars": 4000
    }
  }
}
```

| Key | Default | Description |
|---|---|---|
| `token` | `""` | Bot token from @BotFather |
| `allow_from` | `[]` | Telegram user IDs allowed to use the bot (empty = anyone). Message `@userinfobot` to find your ID. |
| `proxy` | `null` | Optional HTTP/SOCKS5 proxy URL, e.g. `"socks5://127.0.0.1:1080"` |
| `max_message_chars` | `4000` | Max characters per Telegram message |

## 3. Commands

| Command | Description |
|---|---|
| `/new` | Start a fresh conversation session |
| `/help` | Show available commands |
| `/start` | Welcome message |

## 4. Behaviour

- The bot reacts with 👀 when processing a message and ✅ when done
- Responses stream progressively using Telegram's draft-message animation
- Long replies are split automatically at `max_message_chars`
- Markdown is converted to Telegram HTML before sending
