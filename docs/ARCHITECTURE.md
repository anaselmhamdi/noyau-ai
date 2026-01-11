# NoyauAI Architecture

## Overview

NoyauAI is a daily tech digest application that aggregates content from multiple sources, clusters related items, scores them by relevance, and distills top stories using LLMs.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           NOYAU.NEWS                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐              │
│  │   RSS   │    │ Nitter  │    │ Reddit  │    │ YouTube │    ...       │
│  │ Feeds   │    │   RSS   │    │  JSON   │    │ + Trans │              │
│  └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘              │
│       │              │              │              │                    │
│       └──────────────┴──────────────┴──────────────┘                    │
│                              │                                          │
│                      ┌───────▼───────┐                                  │
│                      │    Ingest     │  ← Hourly Job                    │
│                      │  Orchestrator │                                  │
│                      └───────┬───────┘                                  │
│                              │                                          │
│                      ┌───────▼───────┐                                  │
│                      │   PostgreSQL  │                                  │
│                      │  content_items│                                  │
│                      │  metrics_snap │                                  │
│                      └───────┬───────┘                                  │
│                              │                                          │
│       ┌──────────────────────┼──────────────────────┐                   │
│       │                      │                      │                   │
│       ▼                      ▼                      ▼                   │
│  ┌─────────┐          ┌─────────┐          ┌─────────┐                 │
│  │Clustering│    →    │ Scoring │    →    │ Select  │  ← Daily Job     │
│  │canonical │          │ ranking │          │ Top 10  │                 │
│  └────┬────┘          └────┬────┘          └────┬────┘                 │
│       │                    │                    │                       │
│       └────────────────────┴────────────────────┘                       │
│                              │                                          │
│                      ┌───────▼───────┐                                  │
│                      │  LLM Distill  │  → GPT-4o-mini                   │
│                      │  Structured   │                                  │
│                      └───────┬───────┘                                  │
│                              │                                          │
│              ┌───────────────┼───────────────┐                          │
│              │               │               │                          │
│              ▼               ▼               ▼                          │
│       ┌─────────┐     ┌─────────┐     ┌─────────┐                      │
│       │  Store  │     │  JSON   │     │  Email  │                      │
│       │   DB    │     │  File   │     │  Send   │                      │
│       └─────────┘     └─────────┘     └─────────┘                      │
│                              │                                          │
│                      ┌───────▼───────┐                                  │
│                      │   FastAPI     │                                  │
│                      │   /api/*      │                                  │
│                      └───────┬───────┘                                  │
│                              │                                          │
│                      ┌───────▼───────┐                                  │
│                      │    Caddy      │  ← Auto TLS                      │
│                      │   Reverse     │                                  │
│                      │    Proxy      │                                  │
│                      └───────┬───────┘                                  │
│                              │                                          │
│                      ┌───────▼───────┐                                  │
│                      │    Astro      │  (Frontend - separate repo)      │
│                      │   Static      │                                  │
│                      └───────────────┘                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Data Layer

#### PostgreSQL Database

The database stores all application state:

| Table | Purpose |
|-------|---------|
| `users` | Subscriber accounts |
| `magic_links` | Passwordless auth tokens |
| `sessions` | User sessions |
| `content_items` | Ingested content from all sources |
| `metrics_snapshots` | Point-in-time engagement metrics |
| `clusters` | Grouped related content |
| `cluster_items` | M2M: clusters ↔ content |
| `cluster_summaries` | LLM-generated summaries |
| `issues` | Daily digest metadata |
| `events` | Analytics events |

#### Key Relationships

```
content_items 1→N metrics_snapshots
clusters 1→N cluster_items N→1 content_items
clusters 1→1 cluster_summaries
users 1→N sessions
issues 1→N clusters (via issue_date)
```

### 2. Ingest Layer (`app/ingest/`)

The ingest layer fetches content from multiple sources:

| Source | Module | Method |
|--------|--------|--------|
| RSS/Atom | `rss.py` | Standard feed parsing |
| GitHub | `rss.py` | releases.atom feeds |
| X/Twitter | `nitter.py` | Nitter RSS (rotating instances) |
| Reddit | `reddit.py` | JSON API (no auth) |
| dev.to | `devto.py` | Public API |
| YouTube | `youtube.py` | RSS + youtube-transcript-api |

#### Normalizer (`normalizer.py`)

URL normalization is critical for clustering:

```python
# Input: "https://github.com/owner/repo/releases/tag/v1.0?utm_source=twitter"
# Output: "github:owner/repo"

# Input: "Blog post about CVE-2024-1234"
# Output: "cve:CVE-2024-1234"

# Input: "https://example.com/article?utm_campaign=social"
# Output: "https://example.com/article"
```

### 3. Pipeline Layer (`app/pipeline/`)

The daily pipeline processes ingested content:

#### Clustering (`clustering.py`)

Groups content by **canonical identity**:
1. GitHub URLs → `github:owner/repo`
2. CVE mentions → `cve:CVE-YYYY-XXXXX`
3. Other URLs → Canonicalized URL

#### Scoring (`scoring.py`)

Each cluster receives a composite score:

```
score = (
    0.30 × recency +           # exp(-age_hours / 18)
    0.20 × engagement_pctl +   # percentile within source
    0.25 × velocity_pctl +     # engagement change rate
    0.25 × echo_scaled +       # log1p(distinct X accounts)
    practical_boost -          # +0.15 for keywords
    already_seen_penalty       # -0.30 if in yesterday's top 10
)

if viral: score × 1.35
```

#### Viral Detection

A cluster is viral if ANY condition is true:
- `engagement_pctl >= 90`
- `velocity_pctl >= 90`
- `echo_count >= 3`

#### Filters (`filters.py`)

Two-stage politics filter:
1. **Keyword match**: Fast regex check
2. **LLM validation**: For keyword matches, GPT-4o-mini confirms context

This prevents false positives like "leader election" in distributed systems.

#### Distiller (`distiller.py`)

Uses OpenAI structured output for guaranteed schema compliance:

```python
response = await client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    response_format=ClusterDistillOutput,  # Pydantic model
)
```

Output schema:
```json
{
  "headline": "string (max 90 chars)",
  "teaser": "string (1 line)",
  "takeaway": "string (1-2 lines)",
  "why_care": "string | null",
  "bullets": ["string", "string"],
  "citations": [{"url": "string", "label": "string"}],
  "confidence": "low | medium | high"
}
```

### 4. API Layer (`app/api/`)

FastAPI endpoints:

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/auth/request-link` | POST | - | Request magic link |
| `/auth/magic` | GET | - | Verify token, create session |
| `/api/me` | GET | Optional | Get user info |
| `/api/issues/{date}` | GET | Optional | Get daily issue |
| `/api/events` | POST | Optional | Record event |
| `/health` | GET | - | Health check |

#### Soft Gate Logic

```
GET /api/issues/2026-01-10?view=public

Items 1-5: Full content (headline, teaser, takeaway, bullets, citations)
Items 6-10: Locked (headline, teaser only)

GET /api/issues/2026-01-10?view=full + session cookie

Items 1-10: Full content
```

### 5. Infrastructure Layer

#### Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `db` | postgres:16-alpine | 5432 | Database |
| `api` | Custom | 8000 | FastAPI backend |
| `caddy` | caddy:2-alpine | 80, 443 | Reverse proxy + TLS |

#### Caddy Configuration

- Automatic TLS via Let's Encrypt
- Static file serving for Astro frontend
- Reverse proxy `/api/*` and `/auth/*` to FastAPI
- Security headers (X-Content-Type-Options, X-Frame-Options)

#### Terraform Resources

| Resource | Type | Purpose |
|----------|------|---------|
| `hcloud_ssh_key` | SSH Key | Server access |
| `hcloud_firewall` | Firewall | Port 22/80/443 |
| `hcloud_server` | Server | cx22 (2 vCPU, 4GB) |

#### systemd Timers

| Timer | Schedule | Job |
|-------|----------|-----|
| `noyau-hourly.timer` | Hourly | Ingest content |
| `noyau-daily.timer` | 06:00 UTC | Build issue |
| `noyau-backup.timer` | 02:00 UTC | pg_dump backup |

## Data Flow

### Hourly Ingest

```
1. Timer triggers hourly.py
2. For each configured source:
   a. Fetch content (RSS, API, scraping)
   b. Normalize URLs and extract metadata
   c. Upsert content_items by URL
   d. Create metrics_snapshot with current engagement
3. Commit transaction
```

### Daily Issue Build

```
1. Timer triggers daily.py at 06:00 UTC
2. Load content_items from last 36 hours
3. Filter political content (keyword + LLM)
4. Build clusters by canonical identity
5. Score and rank clusters
6. Select top 10
7. Distill each with GPT-4o-mini
8. Store clusters + summaries in DB
9. Write public JSON for Astro
10. Send daily digest emails
```

### Request Flow

```
User → Caddy (TLS) → FastAPI → PostgreSQL
                  ↘ Static files (Astro)
```

## Security

### Authentication

- **Magic Links**: One-time tokens, 15-minute expiry
- **Sessions**: UUID cookies, 30-day expiry, HttpOnly + Secure + SameSite=Lax
- **Token Storage**: SHA-256 hashed in DB

### API Security

- CORS configured for specific origins
- No sensitive data in query params
- Rate limiting (to be added)

### Infrastructure Security

- SSH restricted to specific IP
- Secrets in `.env`, not in Terraform
- Postgres not exposed externally

## Scalability Considerations

Current architecture is designed for side-project scale (~1000 users):

| Component | Current | Scale Path |
|-----------|---------|------------|
| Database | Single Postgres | Read replicas, Citus |
| API | Single container | Multiple replicas, load balancer |
| Jobs | systemd timers | Celery + Redis |
| Storage | Local disk | S3 for raw JSON |
| Caching | None | Redis for sessions, hot data |

## Analytics

Product analytics via PostHog (see [TRACKING.md](./TRACKING.md) for full event taxonomy):

| Layer | Library | Events |
|-------|---------|--------|
| Frontend | `posthog-js` | Page views, soft gate hits, shares |
| Backend | `posthog-python` | Signup completed, session started, email events |

Key funnels tracked:
- Visitor → Subscriber (5-10% target)
- Subscriber → Daily Active (40%+ email open rate)
- Reader → Sharer (viral loop)

## Monitoring

Current: Basic logs via structlog (JSON in prod, console in dev)

Future additions:
- Prometheus metrics endpoint
- Error tracking (Sentry)
- Uptime monitoring (external)
