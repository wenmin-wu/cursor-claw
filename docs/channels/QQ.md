---
summary: How to set up and configure the QQ channel for cursor-claw.
read_when:
  - user asks how to configure QQ
  - user wants to add the bot as a QQ friend
  - user asks about app_id, secret, or allow_from for QQ
---

# QQ

Requires `pip install 'cursor-claw[qq]'`.

## 1. Create a bot on QQ Open Platform

1. Log in to [QQ Open Platform](https://q.qq.com/#/apps)
2. Click **创建机器人**, fill in the required info, then enter the bot management page
3. In [Sandbox config](https://q.qq.com/qqbot/#/developer/sandbox) → **消息列表配置**, add your QQ number as an admin
4. Scan the QR code shown on the same page to add the bot as a friend

   ![Add bot as friend](./media/qq-add-bot.png)

5. Go to **管理 → 开发管理** to find your **AppID** and **AppSecret**

## 2. Configure

Add to `~/.cursorclaw/config.json`:

```json
{
  "channels": {
    "qq": {
      "enabled": true,
      "app_id": "YOUR_APP_ID",
      "secret": "YOUR_APP_SECRET",
      "allow_from": []
    }
  }
}
```

| Key | Default | Description |
|---|---|---|
| `app_id` | `""` | QQ bot AppID |
| `secret` | `""` | QQ bot AppSecret |
| `allow_from` | `[]` | User openids allowed to use the bot (empty = anyone). The openid appears in logs the first time a user messages the bot. |

## 3. Commands

Send `/new` (or `/新建` / `新建对话`) to start a fresh conversation session.
