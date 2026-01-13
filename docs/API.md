# NoyauAI API Documentation

## Base URL

- Production: `https://noyau.news`
- Development: `http://localhost:8000`

## Authentication

NoyauAI uses **magic link authentication** (passwordless):

1. Request a magic link via email
2. Click the link to authenticate
3. Session cookie is set for subsequent requests

---

## Endpoints

### Authentication

#### Request Magic Link

```http
POST /auth/request-link
Content-Type: application/json

{
  "email": "user@example.com",
  "redirect": "/daily/2026-01-10"
}
```

**Response (200 OK):**
```json
{
  "ok": true,
  "message": "Magic link sent to your email"
}
```

**Errors:**
- `422`: Invalid email format

---

#### Verify Magic Link

```http
GET /auth/magic?token={token}&redirect={path}
```

**Success:** Redirects to `{redirect}` with `session_id` cookie set

**Errors:**
- `400`: Invalid or expired link
- `400`: Link already used

---

### User

#### Get Current User

```http
GET /api/me
Cookie: session_id={session_id}
```

**Response (authenticated):**
```json
{
  "authed": true,
  "email": "user@example.com",
  "timezone": "Europe/Paris",
  "ref_code": "abc123xy"
}
```

**Response (unauthenticated):**
```json
{
  "authed": false,
  "email": null,
  "timezone": null,
  "ref_code": null
}
```

---

### User Preferences

#### Get Available Timezones

```http
GET /api/users/timezones
```

**Response (200 OK):**
```json
{
  "timezones": [
    "UTC",
    "America/New_York",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Asia/Tokyo"
  ]
}
```

---

#### Update User Preferences

```http
PATCH /api/users/me/preferences
Cookie: session_id={session_id}
Content-Type: application/json

{
  "timezone": "America/New_York",
  "delivery_time_local": "09:00"
}
```

**Response (200 OK):**
```json
{
  "authed": true,
  "email": "user@example.com",
  "timezone": "America/New_York",
  "delivery_time_local": "09:00",
  "ref_code": "abc123xy",
  "is_subscribed": true
}
```

**Errors:**
- `401`: Unauthorized (session required)
- `422`: Invalid timezone or time format (HH:MM required)

---

#### Unsubscribe from Email Digests

```http
POST /api/users/me/unsubscribe
Cookie: session_id={session_id}
```

**Response (200 OK):**
```json
{
  "ok": true,
  "message": "You have been unsubscribed from email digests."
}
```

---

#### Resubscribe to Email Digests

```http
POST /api/users/me/resubscribe
Cookie: session_id={session_id}
```

**Response (200 OK):**
```json
{
  "ok": true,
  "message": "You have been resubscribed to email digests."
}
```

---

### Slack OAuth

#### Initiate Slack Connection

```http
GET /auth/slack/connect
```

Initiates OAuth flow to connect user's Slack workspace.

**Response:** Redirects to Slack OAuth authorization page

**Errors:**
- `400`: Slack integration not enabled
- `500`: Slack client ID not configured

---

#### Slack OAuth Callback

```http
GET /auth/slack/callback?code={code}&state={state}
```

Handles OAuth callback from Slack after user authorization.

**Success:** Redirects to `https://noyau.news/?slack=success`

**Errors:**
- Redirects to `/?slack=error&message={error}` on failure

---

#### Unsubscribe from Slack DMs

```http
GET /auth/slack/unsubscribe?user_id={slack_user_id}
```

Deactivates Slack DM subscription.

**Success:** Redirects to `/?slack=unsubscribed`

---

### Issues

#### Get Daily Issue

```http
GET /api/issues/{date}?view={public|full}
Cookie: session_id={session_id}  # Optional
```

**Parameters:**
- `date`: ISO date format (YYYY-MM-DD)
- `view`: `public` (default) or `full` (requires auth)

**Response (200 OK):**
```json
{
  "date": "2026-01-10",
  "items": [
    {
      "rank": 1,
      "headline": "Python 3.13 Released with 15% Performance Boost",
      "teaser": "The latest Python version brings significant improvements.",
      "takeaway": "Upgrade your projects to benefit from faster execution.",
      "why_care": "Directly impacts your development workflow.",
      "bullets": [
        "New JIT compiler for numeric workloads",
        "Improved error messages for debugging"
      ],
      "citations": [
        {"url": "https://python.org", "label": "Python.org"}
      ],
      "confidence": "high",
      "locked": false
    },
    // ... items 2-5 (full content)
    {
      "rank": 6,
      "headline": "Kubernetes 1.30 Introduces New Features",
      "teaser": "Major release with improved networking.",
      "locked": true  // Items 6-10 locked for unauthenticated users
    }
    // ... items 7-10 (locked)
  ]
}
```

**Soft Gate Logic:**
- `view=public`: Items 1-5 full, items 6-10 locked (headline + teaser only)
- `view=full` + authenticated: All items full
- `view=full` + unauthenticated: Same as `view=public`

**Errors:**
- `404`: No issue found for date
- `422`: Invalid date format or view parameter

---

### Events

#### Record Event

```http
POST /api/events
Content-Type: application/json
Cookie: session_id={session_id}  # Optional

{
  "event_name": "issue_view",
  "properties": {
    "issue_date": "2026-01-10",
    "source": "email_link"
  }
}
```

**Response (200 OK):**
```json
{
  "ok": true,
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "ts": "2026-01-10T10:30:00Z"
}
```

**Common Event Names:**
- `issue_view`: User viewed an issue
- `subscribe_click`: User clicked subscribe button
- `unlock_click`: User clicked unlock button
- `share_click`: User clicked share button
- `email_open`: User opened email (via tracking pixel)

**Errors:**
- `422`: Missing `event_name` or name exceeds 100 chars

---

### Health

#### Health Check

```http
GET /health
```

**Response (200 OK):**
```json
{
  "status": "healthy"
}
```

---

## Response Schemas

### MeResponse

User status and preferences:

```typescript
interface MeResponse {
  authed: boolean;
  email: string | null;
  timezone: string | null;
  delivery_time_local: string | null;  // HH:MM format
  ref_code: string | null;
  is_subscribed: boolean | null;
}
```

### IssueItemFull

Full item visible to authenticated users:

```typescript
interface IssueItemFull {
  rank: number;           // 1-10
  headline: string;       // Max 200 chars
  teaser: string;         // Max 500 chars
  takeaway: string;       // 1-2 sentences
  why_care: string | null;
  bullets: string[];      // Exactly 2 items
  citations: Citation[];  // 1-3 items
  confidence: "low" | "medium" | "high";
  locked: false;
}
```

### IssueItemPublic

Locked item for soft gate:

```typescript
interface IssueItemPublic {
  rank: number;
  headline: string;
  teaser: string;
  locked: true;
}
```

### Citation

```typescript
interface Citation {
  url: string;
  label: string;
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message describing the problem"
}
```

**HTTP Status Codes:**
- `400`: Bad request (invalid token, etc.)
- `401`: Unauthorized (session required)
- `404`: Resource not found
- `422`: Validation error
- `500`: Internal server error

---

## Rate Limits

Currently no rate limiting is implemented. Future plans:

| Endpoint | Limit |
|----------|-------|
| `/auth/request-link` | 5 per email per hour |
| `/api/events` | 100 per IP per minute |
| Other endpoints | 1000 per IP per minute |

---

## CORS

Allowed origins:
- `https://noyau.news`
- `http://localhost:4321` (Astro dev server)

---

## Examples

### cURL: Request Magic Link

```bash
curl -X POST https://noyau.news/auth/request-link \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "redirect": "/daily/2026-01-10"}'
```

### cURL: Get Issue (Public)

```bash
curl https://noyau.news/api/issues/2026-01-10
```

### cURL: Get Issue (Authenticated)

```bash
curl https://noyau.news/api/issues/2026-01-10?view=full \
  -H "Cookie: session_id=your-session-id"
```

### JavaScript: Fetch Issue

```javascript
// Check auth status
const meResponse = await fetch('/api/me', { credentials: 'include' });
const { authed } = await meResponse.json();

// Fetch issue with appropriate view
const view = authed ? 'full' : 'public';
const issueResponse = await fetch(`/api/issues/2026-01-10?view=${view}`, {
  credentials: 'include'
});
const issue = await issueResponse.json();
```

### JavaScript: Record Event

```javascript
await fetch('/api/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({
    event_name: 'issue_view',
    properties: { issue_date: '2026-01-10' }
  })
});
```
