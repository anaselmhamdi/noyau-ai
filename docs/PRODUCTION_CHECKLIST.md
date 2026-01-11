# Production Deployment Checklist

Use this checklist before deploying NoyauNews to production. Check items off as you complete them.

---

## Pre-Deployment

- [ ] All tests pass: `pytest --cov`
- [ ] Linting clean: `ruff check . && ruff format . --check`
- [ ] Type checks pass: `mypy app/`
- [ ] Dependencies locked: `uv.lock` committed
- [ ] `.env.example` includes all current env vars
- [ ] `terraform/terraform.tfvars.example` up to date

---

## Infrastructure (Terraform)

### Hetzner Setup
- [ ] Hetzner Cloud account created
- [ ] API token generated (Project > Security > API Tokens)
- [ ] SSH key pair generated: `ssh-keygen -t ed25519 -C "noyau-prod"`

### Terraform Configuration
- [ ] Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars`
- [ ] Populate all required variables (see [Secrets](#secrets--environment) below)
- [ ] Review firewall: SSH restricted to your IP (`ssh_allowed_ip`)
- [ ] Run `terraform init`
- [ ] Run `terraform plan` and review changes
- [ ] Run `terraform apply`
- [ ] Note server IP from outputs

### DNS
- [ ] A record: `noyau.news` → server IPv4
- [ ] AAAA record (optional): `noyau.news` → server IPv6
- [ ] Wait for DNS propagation (check: `dig noyau.news`)

---

## Secrets & Environment

### Required Secrets

| Secret | How to Get |
|--------|------------|
| `SECRET_KEY` | `openssl rand -hex 32` |
| `DATABASE_URL` | Neon dashboard → Connection string (use pooler endpoint) |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `RESEND_API_KEY` | [resend.com/api-keys](https://resend.com/api-keys) |
| `GITHUB_TOKEN` | GitHub PAT with `read:packages` scope |

### Generate SECRET_KEY
```bash
openssl rand -hex 32
```

### Optional Secrets

| Secret | Purpose | Setup |
|--------|---------|-------|
| `TWITTER_USERNAME/PASSWORD` | Nitter RSS feeds | Dedicated Twitter account |
| `TWITTER_API_*` | Posting digest threads | [developer.twitter.com](https://developer.twitter.com) |
| `POSTHOG_API_KEY` | Analytics | [posthog.com](https://posthog.com) |
| `DISCORD_WEBHOOK_URL` | Notifications | Server Settings > Integrations > Webhooks |
| `VERIFALIA_*` | Email validation | [verifalia.com](https://verifalia.com) |
| `PEXELS_API_KEY` | Video stock footage | [pexels.com/api](https://www.pexels.com/api/) |
| `ELEVENLABS_API_KEY` | Premium TTS | [elevenlabs.io](https://elevenlabs.io) |
| `S3_*` | Video/log storage | AWS or S3-compatible provider |

---

## Security Hardening

### Application
- [ ] `DEBUG=false` in `.env`
- [ ] `BASE_URL=https://noyau.news`
- [ ] Default passwords changed (if using local Postgres)
- [ ] API docs not exposed (`/api/docs` returns 404)

### Server
- [ ] SSH password auth disabled
- [ ] Firewall active: `sudo ufw status`
- [ ] SSH only from your IP (verify firewall rules)
- [ ] Secrets file permissions: `chmod 600 /opt/noyau/.env`

### TLS
- [ ] Caddy obtaining certificates (check logs: `docker compose logs caddy`)
- [ ] HTTPS working: `curl -I https://noyau.news/health`
- [ ] HSTS header present in response

---

## Database (Neon PostgreSQL)

### Setup
- [ ] Neon project created at [console.neon.tech](https://console.neon.tech)
- [ ] Database created
- [ ] Connection string copied (use **pooler** endpoint for production)

### Configuration
- [ ] Connection pooling enabled (default in Neon)
- [ ] Autosuspend configured (recommended: 5 min for cost savings)
- [ ] Compute size appropriate (Start with 0.25 CU, scale as needed)

### Migrations
```bash
# On production server
docker compose run --rm api alembic upgrade head
```
- [ ] All migrations applied successfully
- [ ] Database schema verified

### Backup
- [ ] Neon PITR (Point-in-Time Recovery) enabled (default)
- [ ] Understand recovery process (Neon dashboard > Branches)

---

## Docker & Services

### Pre-flight
- [ ] Docker installed on server
- [ ] GHCR authentication working:
  ```bash
  echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin
  ```

### Deploy
```bash
cd /opt/noyau
docker compose pull
docker compose up -d
```

### Verify Services

| Service | Check Command | Expected |
|---------|---------------|----------|
| db (if local) | `docker compose ps db` | healthy |
| api | `curl localhost:8000/health` | `{"status":"ok"}` |
| caddy | `docker compose logs caddy` | TLS certificate obtained |
| nitter | `docker compose ps nitter` | running |
| nitter-redis | `docker compose ps nitter-redis` | healthy |

- [ ] All services running: `docker compose ps`
- [ ] No restart loops: `docker compose logs --tail=50`
- [ ] Volumes created: `docker volume ls`

---

## Application Verification

### Health & API
- [ ] Health endpoint: `curl https://noyau.news/health`
- [ ] API responding: `curl https://noyau.news/api/`

### Security
- [ ] CORS configured correctly (test from browser console)
- [ ] API docs not accessible: `curl https://noyau.news/api/docs` returns 404
- [ ] Session cookies have `Secure`, `HttpOnly`, `SameSite=Lax` flags

### Authentication
- [ ] Magic link email sends successfully
- [ ] Magic link redirects correctly
- [ ] Session created after authentication
- [ ] Logout clears session

---

## Jobs & Scheduling

### APScheduler (Recommended)
- [ ] `SCHEDULER_ENABLED=true` in `.env`
- [ ] Scheduler started (check API logs)
- [ ] Jobs registered:
  ```bash
  docker compose logs api | grep -i scheduler
  ```

### Verify Jobs Run

| Job | Schedule | Verification |
|-----|----------|--------------|
| Hourly Ingest | Every hour | Check `content_items` table for new records |
| Daily Digest | 06:00 UTC | Check `issues` table, verify email sent |

### Nitter Token Refresh
- [ ] Timer enabled: `systemctl status nitter-refresh.timer`
- [ ] Script accessible: `/opt/noyau/scripts/refresh_nitter_tokens.sh`

### Backup Timer
- [ ] Timer enabled: `systemctl status noyau-backup.timer`
- [ ] Backup directory exists: `/opt/noyau/backups/`

---

## Monitoring & Observability

### Logs
- [ ] Logs directory exists: `/opt/noyau/logs/`
- [ ] Application logging to files
- [ ] JSON format (verify with `tail -1 /opt/noyau/logs/app.log | jq`)

### Analytics (if using PostHog)
- [ ] `POSTHOG_API_KEY` set
- [ ] Events appearing in PostHog dashboard
- [ ] Key events tracked: signup, login, digest_view

### Alerts (if using Discord)
- [ ] `DISCORD_WEBHOOK_URL` set
- [ ] Test notification sent successfully
- [ ] Error alerts configured

### Uptime Monitoring
- [ ] External monitoring configured (e.g., UptimeRobot, Checkly)
- [ ] Health endpoint monitored: `https://noyau.news/health`
- [ ] Alert notifications configured

---

## Email Delivery (Resend)

### Domain Setup
- [ ] Domain added in Resend dashboard
- [ ] DNS records configured:
  - SPF record
  - DKIM record
  - DMARC record (optional but recommended)
- [ ] Domain verified (green checkmark in Resend)

### Testing
- [ ] Magic link email delivers to inbox (not spam)
- [ ] Digest email delivers correctly
- [ ] Unsubscribe link works
- [ ] Email templates render correctly

### Monitoring
- [ ] Check Resend dashboard for bounces/complaints
- [ ] Understand sending limits for your plan

---

## Post-Deployment Validation

### Full Flow Test
1. [ ] Visit `https://noyau.news`
2. [ ] Sign up with email
3. [ ] Receive magic link email
4. [ ] Click link and authenticate
5. [ ] View dashboard/digest
6. [ ] Verify all 10 items visible (authenticated)
7. [ ] Log out
8. [ ] Verify soft gate (items 6-10 gated)

### Pipeline Test
- [ ] Trigger manual ingest: `docker compose exec api python -m app.jobs.hourly`
- [ ] Verify content items created
- [ ] Trigger manual digest: `docker compose exec api python -m app.jobs.daily --dry-run`
- [ ] Review dry-run output

### First Production Run
- [ ] Wait for first scheduled hourly ingest
- [ ] Verify content items populated
- [ ] Wait for first daily digest (06:00 UTC)
- [ ] Verify issue created
- [ ] Verify digest email received

---

## Rollback Procedure

If deployment fails:

```bash
# 1. Check logs for errors
docker compose logs --tail=100

# 2. Rollback to previous image (if applicable)
docker compose pull api:previous-tag
docker compose up -d api

# 3. Rollback database migration (if needed)
docker compose exec api alembic downgrade -1

# 4. Restore from Neon PITR (if database corrupted)
# Use Neon dashboard > Branches > Restore
```

---

## Quick Reference

### SSH to Server
```bash
ssh root@$(terraform output -raw server_ipv4)
```

### View Logs
```bash
docker compose logs -f api        # API logs
docker compose logs -f caddy      # Reverse proxy logs
tail -f /opt/noyau/logs/app.log  # Application file logs
```

### Restart Services
```bash
docker compose restart api
docker compose restart caddy
docker compose up -d  # All services
```

### Check Service Health
```bash
docker compose ps
curl localhost:8000/health
curl https://noyau.news/health
```

### Database Access
```bash
# Via psql (Neon)
psql "postgresql://user:pass@host/db?sslmode=require"

# Via Docker (local dev)
docker compose exec db psql -U noyau -d noyau
```

---

## Appendix: Environment Variable Reference

See `.env.example` for the complete list. Critical production variables:

| Variable | Production Value | Notes |
|----------|------------------|-------|
| `DEBUG` | `false` | Enables JSON logging, disables API docs |
| `BASE_URL` | `https://noyau.news` | Affects cookie security, email links |
| `SECRET_KEY` | (generated) | Must be unique and secret |
| `DATABASE_URL` | Neon pooler URL | Use `?sslmode=require` |
| `SCHEDULER_ENABLED` | `true` | Enable APScheduler for jobs |
