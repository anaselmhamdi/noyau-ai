# PostHog Tracking Plan

## Overview

NoyauAI uses PostHog for product analytics, following the AARRR (Pirate Metrics) framework to measure the full user journey from acquisition to referral.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TRACKING ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐       │
│   │   Browser   │         │   FastAPI   │         │   PostHog   │       │
│   │  (Astro)    │         │   Backend   │         │    Cloud    │       │
│   └──────┬──────┘         └──────┬──────┘         └──────┬──────┘       │
│          │                       │                       │               │
│          │  posthog-js           │  posthog-python       │               │
│          │  ──────────────────────────────────────────►  │               │
│          │                       │                       │               │
│          │  page_viewed          │                       │               │
│          │  issue_page_viewed    │                       │               │
│          │  soft_gate_hit        │                       │               │
│          │  signup_form_shown    │                       │               │
│          │  signup_started       │  signup_completed     │               │
│          │  share_snippet_copied │  session_started      │               │
│          │  referral_landing     │  email_delivered      │               │
│          │                       │                       │               │
└─────────────────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

```bash
# Backend (FastAPI)
POSTHOG_API_KEY=phc_your_project_api_key
POSTHOG_HOST=https://us.i.posthog.com

# Frontend (Astro) - must start with PUBLIC_
PUBLIC_POSTHOG_KEY=phc_your_project_api_key
```

### Files

| File | Purpose |
|------|---------|
| `ui/src/lib/posthog.ts` | Typed PostHog wrapper for frontend |
| `app/services/posthog_client.py` | Server-side PostHog client |

## Event Taxonomy

### 1. Acquisition Events

Track how users discover and land on the site.

| Event | Trigger | Properties |
|-------|---------|------------|
| `page_viewed` | Any page load | `path`, `referrer`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `device_type`, `is_mobile` |
| `landing_page_viewed` | Homepage load | `referrer`, `utm_*`, `entry_point` |
| `issue_page_viewed` | `/daily/YYYY-MM-DD` load | `issue_date`, `referrer`, `is_latest`, `items_visible` (5 or 10) |
| `referral_landing` | Visit with `?ref=CODE` | `ref_code`, `referrer_user_id`, `issue_date` |

### 2. Activation Events

Track the path to first value (subscription).

| Event | Trigger | Properties |
|-------|---------|------------|
| `soft_gate_hit` | User scrolls to locked items 6-10 | `item_rank`, `issue_date`, `time_on_page_seconds` |
| `signup_form_shown` | Subscribe form enters viewport | `trigger` (scroll, gate_hit, cta_click, page_load), `issue_date` |
| `signup_started` | User submits email | `email_domain`, `issue_date`, `form_location` (hero, footer) |
| `signup_completed` | Magic link sent successfully | `email_domain`, `issue_date`, `validation_status` |
| `magic_link_clicked` | User clicks email link | `token_age_seconds`, `email_client` |
| `session_started` | Auth successful | `is_new_user`, `signup_source`, `ref_code` |

### 3. Retention Events

Track ongoing engagement.

| Event | Trigger | Properties |
|-------|---------|------------|
| `email_delivered` | Resend webhook: delivered | `issue_date`, `user_id`, `email_domain` |
| `email_opened` | Tracking pixel loaded | `issue_date`, `user_id`, `time_since_send_hours` |
| `email_clicked` | Link clicked from email | `issue_date`, `link_type` (read_full, item_link, forward) |
| `return_visit` | Authenticated user returns | `days_since_last_visit`, `entry_point` |
| `full_issue_consumed` | User scrolls past item 10 | `issue_date`, `time_on_page_seconds`, `items_clicked` |

### 4. Referral Events

Track viral sharing behavior.

| Event | Trigger | Properties |
|-------|---------|------------|
| `share_snippet_copied` | "Share" button clicked | `issue_date`, `platform_hint`, `items_in_snippet` |
| `share_link_clicked` | Share button clicked | `issue_date`, `share_platform` (whatsapp, slack, twitter, linkedin, copy) |
| `forward_email_clicked` | "Forward to friend" in email | `issue_date`, `user_id` |
| `referral_signup` | Referred user signs up | `ref_code`, `referrer_user_id` |

## User Properties

Set on user identification:

| Property | Value | When Set |
|----------|-------|----------|
| `$email` | User's email | On signup |
| `email_domain` | Domain from email | On signup |
| `signup_date` | ISO date | On first signup |
| `signup_source` | Referrer/UTM | On signup |
| `ref_code` | User's personal code | On signup |
| `referred_by` | Referrer's user_id | If from ref link |
| `referral_count` | Count of referrals | Incremented on referral_signup |

## Funnels

### Funnel 1: Visitor → Subscriber

```
page_viewed (landing OR issue)
  → signup_form_shown
    → signup_started
      → signup_completed
        → magic_link_clicked
          → session_started (is_new_user=true)
```

**Target**: 5-10% conversion rate

### Funnel 2: Subscriber → Daily Active

```
email_delivered
  → email_opened
    → email_clicked OR issue_page_viewed
      → full_issue_consumed
```

**Target**: 40%+ open rate, 20%+ click rate

### Funnel 3: Reader → Sharer (Viral Loop)

```
full_issue_consumed
  → share_snippet_copied
    → referral_landing (from that share)
      → referral_signup
```

**Target**: 10% share rate, 5% referral conversion

## Cohorts

| Cohort | Definition | Purpose |
|--------|------------|---------|
| **Power Users** | email_opened 4+ times in 7 days | Champions for feedback |
| **At Risk** | No email_opened or page_viewed in 14 days | Win-back campaigns |
| **Viral Amplifiers** | share_* events 2+ in 30 days | Exclusive perks |
| **Gate Abandoners** | soft_gate_hit but no signup in 7 days | Retarget |
| **Email-Only** | email_opened but no page_viewed in 30 days | Test web content |
| **Referred Users** | referred_by is set | Compare retention |

## Feature Flags

| Flag | Purpose | Metric |
|------|---------|--------|
| `soft_gate_item_count` | Test gate at item 4 vs 5 vs 6 | signup_completed rate |
| `email_send_time` | Test 07:00 vs 08:00 vs 09:00 | email_opened rate |
| `share_snippet_format` | Test bullet vs paragraph | share → referral_landing |
| `cta_copy` | Test "Get all 10" vs "Unlock full issue" | signup_started rate |

## Implementation Details

### Frontend Tracking (`ui/src/lib/posthog.ts`)

```typescript
import { initPostHog, trackPageView, track } from '../lib/posthog';

// Initialize (in BaseLayout.astro)
initPostHog(apiKey, { debug: isDev });

// Track page view with UTM capture
trackPageView(window.location.pathname);

// Track custom event
track('soft_gate_hit', {
  item_rank: 6,
  issue_date: '2026-01-10',
  time_on_page_seconds: 45
});
```

### Backend Tracking (`app/services/posthog_client.py`)

```python
from app.services.posthog_client import (
    capture,
    identify,
    track_session_started,
    track_signup_completed,
)

# Track event
capture(
    distinct_id=str(user.id),
    event="email_delivered",
    properties={"issue_date": "2026-01-10"}
)

# Identify user
identify(
    distinct_id=str(user.id),
    properties={"$email": user.email}
)
```

## Session Recording

Record sessions for:
- Users who hit `soft_gate_hit` (understand drop-off)
- Users in signup flow
- Users with `engagement_tier = low`
- Random 5% sample

Exclude:
- Power users (already engaged)
- API-only interactions

## Dashboards

### Growth Dashboard
- Daily/Weekly/Monthly active users
- Signup funnel conversion rates
- Referral metrics (K-factor)

### Engagement Dashboard
- Email open/click rates by day
- Issue consumption depth
- Time on page distribution

### Acquisition Dashboard
- Traffic by source (UTM)
- Referrer breakdown
- Device type distribution

## Privacy Considerations

- No PII in event properties (only email domain, not full email)
- IP anonymization enabled
- Cookie consent required in EU (implement banner)
- Data retention: 12 months default
