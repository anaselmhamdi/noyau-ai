# NoyauAI

Daily tech digest for engineers. Curates 10 ranked stories from RSS, GitHub, X, Reddit, dev.to, and YouTube.

## Quick Start

```bash
# Clone and setup
git clone https://github.com/YOUR_REPO/noyau-ai.git
cd noyau-ai
cp .env.example .env  # Add your API keys

# Start PostgreSQL
docker compose up -d db

# Install dependencies
uv pip install -e ".[dev]"

# Run migrations and start API
alembic upgrade head
uvicorn app.main:app --reload
```

## Commands

| Command | Description |
|---------|-------------|
| `pytest` | Run tests |
| `ruff check . --fix && ruff format .` | Lint and format |
| `python -m app.jobs.hourly` | Ingest content from sources |
| `python -m app.jobs.daily` | Build daily issue |
| `python -m app.jobs.daily --dry-run` | Preview without saving |

## Configuration

- **Environment**: Copy `.env.example` to `.env` and add your API keys
- **Sources**: Edit `config.yml` to add/remove RSS feeds, X accounts, subreddits, etc.

## Production Deployment

See the [Production Checklist](./docs/PRODUCTION_CHECKLIST.md) for the complete go-to-production guide.

Quick overview:
1. Configure Terraform: `cp terraform/terraform.tfvars.example terraform/terraform.tfvars`
2. Provision infrastructure: `terraform apply`
3. Point DNS to server IP
4. Deploy: `docker compose -f docker-compose.prod.yml up -d`

### Auto-Deployment with Watchtower

CI pushes images to GHCR on every merge to main. Watchtower auto-pulls within 5 minutes.

```bash
# Force immediate update
docker exec noyau-watchtower-1 /watchtower --run-once

# Check Watchtower logs
docker compose logs watchtower
```

## Documentation

| Doc | Description |
|-----|-------------|
| [CLAUDE.md](./CLAUDE.md) | Architecture, data flow, development guidelines |
| [docs/API.md](./docs/API.md) | API endpoints and examples |
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System diagrams and components |
| [docs/PROCESS.md](./docs/PROCESS.md) | Pipeline deep dive |
| [docs/PRODUCTION_CHECKLIST.md](./docs/PRODUCTION_CHECKLIST.md) | Go-to-production checklist |
| [SPECS.md](./SPECS.md) | Full product specification |

## Community

Join our Discord to discuss the daily digest, suggest sources, and connect with other builders:

**[Join Discord](https://discord.gg/YCbuNqFucb)**

## License

MIT
