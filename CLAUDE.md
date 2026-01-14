# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NoyauAI is a daily tech digest application for noyau.news. It ingests content from multiple sources (RSS, GitHub releases, Reddit, dev.to, YouTube, Bluesky), clusters related items into stories, scores them algorithmically, distills them with LLM (OpenAI), and delivers a curated 10-item daily digest via email.

## Commands

### Development
```bash
# Install dependencies (prefer uv)
uv pip install -e ".[dev]"

# Start PostgreSQL
docker compose up -d db

# Run migrations
alembic upgrade head

# Start API with hot reload
uvicorn app.main:app --reload

# Run all tests
pytest

# Run single test file
pytest tests/test_api/test_auth.py

# Run tests with coverage
pytest --cov

# Lint and format
ruff check . --fix
ruff format .

# Type check
mypy app/

# Pre-commit hooks
pre-commit run --all-files
```

### Jobs
```bash
# Hourly ingest (fetch content from all sources)
python -m app.jobs.hourly

# Daily issue build (cluster, score, distill, email)
python -m app.jobs.daily

# Preview without DB writes or emails
python -m app.jobs.daily --dry-run
```

### Discord Bot
```bash
# Start Discord bot (runs alongside API when DISCORD_BOT_TOKEN is set)
python -m app.jobs.discord_bot

# Bot provides these slash commands in Discord servers:
# /subscribe <email> - Subscribe to daily digest DMs
# /unsubscribe       - Stop receiving daily digest DMs
# /status            - Check subscription status
```

### Docker
```bash
# Full stack (development)
docker compose up -d

# Run migrations via compose
docker compose run --rm migrate
```

### Production
```bash
# Deploy to production server
docker compose -f docker-compose.prod.yml up -d

# Force Watchtower to pull latest images immediately
docker exec noyau-watchtower-1 /watchtower --run-once

# Check Watchtower logs
docker compose logs watchtower

# View production logs
docker compose logs -f api
tail -f /opt/noyau/logs/app.log
```

## Architecture

### Tech Stack
- **Backend**: FastAPI + Uvicorn (async)
- **Database**: PostgreSQL 16 (Neon in production) + SQLAlchemy 2.0 async + Alembic
- **Frontend**: Astro 5.0 (in `ui/` directory, bundled into API Docker image)
- **Reverse Proxy**: Caddy 2 (auto TLS)
- **Infra**: Hetzner VM via Terraform
- **CI/CD**: GitHub Actions → GHCR → Watchtower (auto-pull)
- **LLM**: OpenAI API
- **Email**: Resend API
- **Messaging**: Slack App (OAuth), Discord Bot (discord.py)
- **Social**: TikTok Content Posting API, Instagram Graph API

### Key Directories
```
app/
├── api/           # FastAPI route handlers
├── core/          # Database, security, logging
├── models/        # SQLAlchemy ORM models
├── schemas/       # Pydantic request/response models
├── services/      # Business logic (email, validation)
├── ingest/        # Content fetchers (RSS, Reddit, Bluesky, etc.)
├── pipeline/      # Issue building (clustering, scoring, distillation)
├── jobs/          # CLI entry points for hourly/daily jobs
└── email/         # Email templates
```

### Data Flow

**Hourly Job**: Fetches content from configured sources → normalizes → upserts ContentItem → captures MetricsSnapshot

**Daily Job**: Loads recent items → filters politics → clusters by canonical identity → scores (recency + engagement + velocity + echo) → selects top 10 → distills via OpenAI → saves Issue → emails subscribers

### Scoring Algorithm
Clusters are ranked by weighted combination of:
- **Recency**: Exponential decay (18h half-life)
- **Engagement**: Normalized by source + percentile
- **Velocity**: Engagement change rate
- **Echo**: Cross-platform mentions from curated accounts
- **Practical boost**: +0.15 for engineering keywords (release, CVE, benchmark)
- **Viral override**: 1.35x multiplier for high-engagement or high-echo items

### Authentication
Magic link (passwordless) via email. Session stored in cookie. Soft gate: items 1-5 public, items 6-10 require auth.

## Configuration

- **Environment**: `.env` file (see `.env.example`)
- **Seeds & Ranking**: `config.yml` (RSS feeds, X accounts, Reddit subs, ranking weights)
- **Required env vars**: `DATABASE_URL`, `OPENAI_API_KEY`, `RESEND_API_KEY`, `SECRET_KEY`
- **Slack integration**: `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`
- **Discord bot**: `DISCORD_BOT_TOKEN`, `DISCORD_APPLICATION_ID`
- **TikTok posting**: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_ACCESS_TOKEN`, `TIKTOK_REFRESH_TOKEN`
- **Instagram posting**: `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID`

## Testing

Tests use SQLite in-memory (aiosqlite) for speed. Key fixtures in `tests/conftest.py`:
- `client`: Async test client
- `db_session`: Async SQLAlchemy session
- `test_user`, `test_magic_link`: Pre-created test data

## Key Files

| File | Purpose |
|------|---------|
| `app/pipeline/issue_builder.py` | Orchestrates full daily pipeline |
| `app/pipeline/scoring.py` | Cluster ranking algorithm |
| `app/ingest/orchestrator.py` | Fetcher orchestration and metric capture |
| `app/core/database.py` | SQLAlchemy async engine + session |
| `app/core/datetime_utils.py` | Timezone utilities, delivery window logic |
| `app/services/slack_service.py` | Slack OAuth and Block Kit DM sending |
| `app/services/discord_bot.py` | Discord bot with slash commands |
| `app/services/digest_dispatch.py` | Timezone-aware delivery orchestration |
| `app/services/tiktok_service.py` | TikTok video posting |
| `app/services/instagram_service.py` | Instagram Reels posting |
| `app/models/messaging.py` | MessagingConnection model |
| `config.yml` | Seeds and ranking configuration |

## Social Links

- **Website**: https://noyau.news
- **X/Twitter**: https://x.com/NoyauNews
- **YouTube**: https://www.youtube.com/channel/UC8ObkWnKP4UPzi2qku2TlXw
- **Discord**: https://discord.gg/YCbuNqFucb
- **TikTok**: https://tiktok.com/@noyaunews
- **Instagram**: https://instagram.com/NoyauNews

## Development Guidelines

- **Use uv** for package management instead of pip
- **Always lint** before committing: `ruff check . --fix && ruff format .`
- **Add tests** for new features in `tests/` mirroring the `app/` structure
- **Check UI impact**: When adding features, evaluate if UI components in `ui/` need updates (Astro frontend)
- **Update .env.example**: When adding or changing environment variables, always update `.env.example` to reflect the changes
- **Update terraform.tfvars.example**: When adding or changing environment variables, also update `terraform/terraform.tfvars.example` and `terraform/variables.tf` to keep infrastructure config in sync
