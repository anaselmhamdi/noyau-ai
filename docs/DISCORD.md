# Discord Bot Integration Guide

## Overview

NoyauNews Discord bot allows users to subscribe to daily digest DMs via slash commands. This guide covers setup, configuration, and troubleshooting.

## Architecture

- **discord.py** library with slash commands
- **Global bot token** (not per-server OAuth)
- **REST API** for DM delivery (no persistent WebSocket needed for sending)
- Connections stored in `messaging_connections` table

```
User runs /subscribe in Discord server
  → Bot validates email format
  → Creates User if email not found
  → Creates MessagingConnection
  → Daily job sends DMs via REST API
```

## Bot Commands

### `/subscribe <email>`

Subscribe to receive daily digest DMs.

**Usage**: `/subscribe your@email.com`

**Behavior**:
- Validates email format
- Creates `User` record if email doesn't exist
- Creates `MessagingConnection` with platform="discord"
- Sends ephemeral confirmation message

**Response**: "You're subscribed! You'll receive daily digests as DMs."

### `/unsubscribe`

Stop receiving daily digest DMs.

**Usage**: `/unsubscribe`

**Behavior**:
- Sets `is_active=false` on connection
- Preserves data for potential resubscription

**Response**: "You've been unsubscribed. Run /subscribe to resubscribe."

### `/status`

Check current subscription status.

**Usage**: `/status`

**Response**: Shows active/inactive status, linked email, and last delivery time.

## Setup Steps

### 1. Create Discord Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application**
3. Name: `NoyauNews`
4. Click **Create**

### 2. Add Bot

1. In your application, go to **Bot** in the sidebar
2. Click **Add Bot** > **Yes, do it!**
3. Under **Privileged Gateway Intents**:
   - Enable **Message Content Intent** (optional, for future features)

### 3. Get Credentials

Copy these values to your `.env` file:

| Credential | Location | Environment Variable |
|------------|----------|---------------------|
| Bot Token | Bot > Token > Copy | `DISCORD_BOT_TOKEN` |
| Application ID | General Information | `DISCORD_APPLICATION_ID` |

```bash
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_APPLICATION_ID=your_application_id
```

### 4. Generate Invite URL

1. Go to **OAuth2** > **URL Generator**
2. Select scopes:
   - `bot`
   - `applications.commands`
3. Select bot permissions:
   - `Send Messages`
4. Copy the generated URL

Example URL structure:
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_APP_ID&permissions=2048&scope=bot%20applications.commands
```

### 5. Enable in Config

In `config.yml`:

```yaml
discord_bot:
  enabled: true
```

## Deployment

### With API (Recommended)

The Discord bot runs automatically when the API starts if `DISCORD_BOT_TOKEN` is set.

```bash
# Bot starts with API
docker compose up -d api
```

### Standalone

Run the bot separately:

```bash
python -m app.jobs.discord_bot
```

## DM Message Format

Discord DMs use embeds for clean formatting:

### Structure

```python
embeds = [
    {
        "title": "Noyau Daily - 2026-01-10",
        "description": "Your daily tech digest",
        "color": 0x5865F2,  # Discord blurple
        "fields": [
            {
                "name": "1. Python 3.13 Released",
                "value": "Major performance improvements with new JIT...",
                "inline": False
            },
            # ... more items
        ],
        "footer": {
            "text": "Reply /unsubscribe to stop | noyau.news"
        }
    }
]
```

### Message Limits

- Embed title: 256 characters
- Embed description: 4096 characters
- Field name: 256 characters
- Field value: 1024 characters
- Total embeds per message: 10

Items are split across multiple embeds if needed.

## Database Schema

### messaging_connections (Discord rows)

| Column | Type | Description |
|--------|------|-------------|
| `platform` | string | Always "discord" |
| `platform_user_id` | string | Discord user ID (snowflake) |
| `platform_team_id` | string | Guild ID where subscribed |
| `platform_team_name` | string | Guild name |
| `access_token` | null | Not used (global bot token) |
| `is_active` | bool | Whether to send DMs |
| `last_sent_at` | datetime | Last successful DM timestamp |

## Troubleshooting

### Bot Not Responding to Commands

1. **Verify bot is online**:
   ```bash
   docker compose logs api | grep discord_bot_ready
   ```

2. **Check bot is invited correctly**:
   - Ensure `applications.commands` scope was included in invite URL
   - Re-invite if needed

3. **Commands not registered**:
   - Slash commands sync on bot startup
   - May take up to 1 hour to propagate globally
   - Use guild-specific commands for instant testing

### DMs Not Delivered

#### Error: Cannot send messages to this user (50007)

User has DMs disabled from server members.

**Solution**: User needs to enable DMs in their privacy settings.

#### Error: Unknown User (10013)

User ID is invalid or user no longer exists.

**Solution**: Deactivate the connection.

### Logs

Check Discord-related logs:

```bash
# All Discord logs
docker compose logs api | grep -i discord

# Bot ready event
docker compose logs api | grep discord_bot_ready

# Command handling
docker compose logs api | grep discord_command

# DM sending
docker compose logs api | grep discord_dm
```

### Verify Connection

```sql
SELECT * FROM messaging_connections
WHERE platform = 'discord'
ORDER BY created_at DESC
LIMIT 10;
```

### Test DM Manually

```python
from app.services.discord_dm_service import DiscordDMService

service = DiscordDMService()
await service.send_dm(
    user_id="123456789012345678",
    content="Test message"
)
```

## Permissions

### Required Bot Permissions

| Permission | Value | Purpose |
|------------|-------|---------|
| Send Messages | 2048 | Send DMs and command responses |

### Required Scopes

| Scope | Purpose |
|-------|---------|
| `bot` | Add bot to servers |
| `applications.commands` | Register slash commands |

## Rate Limits

Discord has strict rate limits:

| Resource | Limit |
|----------|-------|
| Global | 50 requests/second |
| Per DM channel | 5 messages/5 seconds |
| Create DM | 1/second per user |

The bot handles rate limits automatically with exponential backoff.

## Security Considerations

- **Bot token is sensitive**: Never commit to version control
- **Ephemeral responses**: Command responses only visible to invoking user
- **No message content access needed**: Bot only sends, doesn't read
- **User data**: Only stores Discord user ID and guild context

## Development Tips

### Local Testing

1. Create a test Discord server
2. Use guild-specific commands for instant sync:
   ```python
   @bot.tree.command(guild=discord.Object(id=TEST_GUILD_ID))
   ```

### Command Sync

Force command sync:
```python
await bot.tree.sync()  # Global (takes time)
await bot.tree.sync(guild=discord.Object(id=GUILD_ID))  # Instant
```

## Related Files

| File | Purpose |
|------|---------|
| `app/services/discord_bot.py` | Bot client, slash commands |
| `app/services/discord_dm_service.py` | REST API DM dispatch |
| `app/jobs/discord_bot.py` | Entry point to run bot |
| `app/models/messaging.py` | MessagingConnection model |
