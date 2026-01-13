# Slack App Integration Guide

## Overview

NoyauNews integrates with Slack to deliver daily digest DMs directly to users in their workspace. This guide covers setup, configuration, and troubleshooting.

## Architecture

- **OAuth 2.0 flow** for workspace installation
- **Bot token per workspace** stored in `messaging_connections.access_token`
- **Block Kit formatting** for rich message display
- **Multi-tenant**: Supports multiple workspaces

```
User clicks "Add to Slack" → /auth/slack/connect
  → Redirects to Slack OAuth
  → User authorizes app in workspace
  → /auth/slack/callback receives code
  → Exchange code for access_token
  → Create/update MessagingConnection
  → Daily job sends DMs via Block Kit
```

## Setup Steps

### 1. Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** > **From scratch**
3. Name: `NoyauNews`
4. Select your development workspace
5. Click **Create App**

### 2. Configure OAuth Scopes

Navigate to **OAuth & Permissions** in the sidebar.

#### Bot Token Scopes (Required)

Add these scopes under "Scopes" > "Bot Token Scopes":

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send DM messages to users |
| `users:read` | Access basic user information |
| `users:read.email` | Get user email for account linking |

#### User Token Scopes (Optional)

These are only needed if you want OpenID Connect:

| Scope | Purpose |
|-------|---------|
| `openid` | OpenID Connect identity |
| `email` | Access user's email via OIDC |

### 3. Add Redirect URL

Under **OAuth & Permissions** > **Redirect URLs**, add:

- **Production**: `https://noyau.news/auth/slack/callback`
- **Development**: `http://localhost:8000/auth/slack/callback`

### 4. Get Credentials

Navigate to **Basic Information** and copy:

| Credential | Environment Variable |
|------------|---------------------|
| Client ID | `SLACK_CLIENT_ID` |
| Client Secret | `SLACK_CLIENT_SECRET` |
| Signing Secret | `SLACK_SIGNING_SECRET` |

Add these to your `.env` file:

```bash
SLACK_CLIENT_ID=your_client_id
SLACK_CLIENT_SECRET=your_client_secret
SLACK_SIGNING_SECRET=your_signing_secret
```

### 5. Enable in Config

In `config.yml`:

```yaml
slack:
  enabled: true
```

## User Flow

1. User visits website and clicks "Add to Slack" button
2. Redirected to Slack OAuth authorization page
3. User selects workspace and authorizes app
4. Callback creates:
   - New `User` record (if email not found)
   - New `MessagingConnection` with platform="slack"
5. User redirected to `/?slack=success`
6. Daily digests sent as DMs

## Message Format

Messages use Slack's Block Kit for rich formatting:

### Structure

```json
[
  {
    "type": "header",
    "text": {"type": "plain_text", "text": "Noyau Daily - 2026-01-10"}
  },
  {"type": "divider"},
  {
    "type": "section",
    "text": {
      "type": "mrkdwn",
      "text": ":rocket: *1. Python 3.13 Released*\nMajor performance improvements..."
    }
  },
  // ... more items
  {
    "type": "actions",
    "elements": [{
      "type": "button",
      "text": {"type": "plain_text", "text": "Read on Web"},
      "url": "https://noyau.news/daily/2026-01-10"
    }]
  }
]
```

### Topic Emoji

Items are prefixed with topic-specific emoji:

| Topic | Emoji |
|-------|-------|
| Releases | :rocket: |
| Security | :warning: |
| Performance | :chart_with_upwards_trend: |
| Deep Dive | :mag: |
| News | :newspaper: |
| Default | :bulb: |

## API Endpoints

### Initiate Connection

```http
GET /auth/slack/connect
```

Redirects user to Slack OAuth authorization.

### OAuth Callback

```http
GET /auth/slack/callback?code={code}&state={state}
```

Handles OAuth callback, creates user/connection.

### Unsubscribe

```http
GET /auth/slack/unsubscribe?user_id={slack_user_id}
```

Deactivates Slack DM subscription (included in message footer).

## Database Schema

### messaging_connections (Slack rows)

| Column | Type | Description |
|--------|------|-------------|
| `platform` | string | Always "slack" |
| `platform_user_id` | string | Slack user ID (e.g., "U01234567") |
| `platform_team_id` | string | Workspace ID (e.g., "T01234567") |
| `platform_team_name` | string | Workspace name |
| `access_token` | text | Bot token for this workspace |
| `is_active` | bool | Whether to send DMs |
| `last_sent_at` | datetime | Last successful DM timestamp |

## Troubleshooting

### Common Errors

#### `token_revoked`

User removed the app from their workspace. The connection is automatically deactivated.

**Solution**: User needs to re-authorize via "Add to Slack".

#### `invalid_auth`

Token is invalid or expired.

**Solution**: Check if `access_token` is correctly stored. User may need to re-authorize.

#### `no_email`

User's email is not accessible.

**Solution**: Ensure `users:read.email` scope is included. User may have email privacy settings.

#### `channel_not_found`

Cannot create DM channel with user.

**Solution**: User may have left the workspace or blocked DMs.

### Logs

Check Slack-related logs:

```bash
# All Slack logs
docker compose logs api | grep -i slack

# OAuth flow
docker compose logs api | grep slack_oauth

# DM sending
docker compose logs api | grep slack_dm
```

### Verify Connection

```sql
SELECT * FROM messaging_connections
WHERE platform = 'slack'
ORDER BY created_at DESC
LIMIT 10;
```

### Test DM Manually

```python
from app.services.slack_service import SlackService

service = SlackService()
await service.send_dm(
    access_token="xoxb-...",
    user_id="U01234567",
    text="Test message"
)
```

## Distribution (Optional)

To distribute your app publicly:

1. Go to **Manage Distribution** in Slack App settings
2. Complete the checklist:
   - Add app icon (512x512 PNG)
   - Add short description
   - Add long description
   - Set up landing page
3. Submit for Slack App Directory review

## Security Considerations

- **Tokens are stored encrypted** in the database
- **State parameter** used for CSRF protection during OAuth
- **Signing secret** validates incoming requests from Slack
- **Token revocation** handled gracefully (connection deactivated)

## Related Files

| File | Purpose |
|------|---------|
| `app/services/slack_service.py` | OAuth flow, token exchange, DM sending |
| `app/services/slack_dm_service.py` | Batch DM dispatch |
| `app/api/slack.py` | OAuth endpoints |
| `app/models/messaging.py` | MessagingConnection model |
