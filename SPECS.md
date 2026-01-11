# NoyauAI Product Specification (v1)
Owner: user
Goal: Build a side-project daily digest app optimized for sharing + subscriber growth.

## 0) Product summary
Daily "raw brief" digest:
- Exactly **10 items/day**
- **Score-driven** (recency + engagement + velocity + echo)
- Bias toward **practical engineering** (releases, postmortems, CVEs, benchmarks, migrations)
- **Broader tech news allowed** (trust score)
- **Politics excluded**
- **Security/outages only rise if viral**
- “Echo” is satisfied if **many curated X accounts** talk about it (cross-platform not required)
- UI: **Astro**
- Backend: **FastAPI**
- DB: **Postgres**
- Infra: **Hetzner VM** provisioned via **Terraform**
- Proxy/TLS: **Caddy**
- Scheduler: **systemd timers or cron** (cheapest)

Web: public + soft gate
- `/daily/YYYY-MM-DD` public issue page
- Soft gate: **Top 5 fully visible**, items 6–10 show **headline + teaser only**
- Unlock via **magic link** email auth (cookie-based)
- Email: daily at **08:00 user’s timezone by default** (v1 can default to Europe/Paris; configurable later)

Primary KPI: subscriber growth


---

## 1) Architecture (cheapest, side-project friendly)
### Services on one VM
- Postgres
- FastAPI API (auth + issue APIs + events)
- Worker commands (run via systemd timers/cron; can be same container/image as API)
- Caddy reverse proxy (serves Astro static output and proxies `/api` and `/auth`)

### No queues / no redis / no Temporal in v1.

### Data flow
Ingest -> normalize -> metrics snapshots -> cluster -> score -> select top 10 -> LLM distill -> store issue -> render web+email


---

## 2) Data model (v1)
Tables:

### users
- id (pk)
- email (unique)
- timezone (default "Europe/Paris")
- delivery_time_local (default "08:00")
- ref_code (unique)
- created_at

### magic_links
- token_hash (pk)
- email
- redirect_path
- expires_at
- used_at

### sessions
- id (pk)
- user_id (fk)
- expires_at
- created_at

### content_items
- id (pk)
- source (x, reddit, github, youtube, devto, rss, status)
- source_id (nullable)
- url (unique)
- title
- author
- published_at
- fetched_at
- text (post text OR snippet OR transcript chunk ref)
- raw_json_ref (blob key or local file path)

### metrics_snapshots
- id (pk)
- item_id (fk)
- captured_at
- metrics_json (jsonb: likes/rt/replies, upvotes/comments, views/comments, stars/forks)

### clusters
- id (pk)
- issue_date (date)
- dominant_topic (macro|oss|security|dev|deepdive|sauce)
- cluster_score (float)
- created_at

### cluster_items (m2m)
- cluster_id
- item_id
- rank_in_cluster

### cluster_summaries (LLM output per cluster)
- cluster_id (pk/fk)
- headline
- teaser
- takeaway
- why_care (nullable)
- bullets_json (array length 2)
- citations_json (array length 1–3)
- confidence ("low"|"medium"|"high")

### issues
- issue_date (pk)
- public_url
- created_at

### events
- id (pk)
- user_id (nullable)
- event_name
- ts
- properties_json


---

## 3) Sources & seeds (v1 connectors)
Target stack bias: python, go, langchain, k8s, bigquery, kafka, dbt, opentelemetry, SRE, observability.

In v1 support:
- RSS feeds: cloud + changelogs + kubernetes + arXiv
- GitHub releases.atom feeds
- X curated accounts (echo)
- Reddit subreddits
- dev.to tags
- YouTube channels with transcript-based summarization

Azure updates explicitly excluded (ignore).

Note: If YouTube transcript is unavailable, either skip or fallback to description (configurable). Prefer skip for v1.

All seeds are configurable via a single YAML file `config.yml`.


---

## 4) Clustering (v1 no embeddings)
Cluster items into “stories” using cheap canonical identities:

### Canonical identity extraction rules
- If URL present: canonicalize (strip utm params, normalize scheme, remove trailing slash)
- If GitHub URL: extract repo `owner/name`
- If CVE present: extract CVE id
- Otherwise canonical = domain + path prefix

### Cluster grouping
- Same canonical identity => same cluster
- Within a cluster, keep top N items by engagement/velocity for LLM context (N=3..10)

Embeddings are deferred to v1.1.


---

## 5) Ranking & selection
You rank clusters, not items. Exactly 10 clusters/day.

### Required snapshots
Velocity requires at least 2 metrics snapshots per item (hourly snapshots are enough).

### Metrics definitions
- age_hours = now - published_at
- recency = exp(-age_hours / half_life_hours), half_life_hours default 18

Per source, compute engagement_now from latest snapshot:
- X: likes + 2*retweets + replies
- Reddit: upvotes + 2*comments
- YouTube: views + 2*comments (or views_delta if available)
- GitHub: stars + forks (but prefer stars_delta_24h)
- RSS/blog: engagement may be absent; treat as low engagement but allow via recency + echo if discussed on X

Velocity:
- vel = (eng_now - eng_prev) / dt_hours
- Normalize engagement and velocity per source via percentiles over last 7 days to avoid cross-source dominance.

Echo (X only):
- echo_count = distinct curated X accounts referencing the cluster within last 12h
- Reference detection: matching canonical identity (url/repo/cve) between tweet and cluster.
- cross-platform not required.

Practical boost:
- If title/text contains any of:
  release, changelog, benchmark, postmortem, incident, outage, CVE, exploit, patch, migration, performance
- Or citation domain includes github.com/*/releases, kubernetes.io, cloud release notes, vendor advisories.

Already-seen penalty:
- Penalize clusters similar to yesterday's top clusters by canonical identity (exact match) in v1.

### Score formula (defaults)
score =
  0.30*recency +
  0.20*engagement_pctl +
  0.25*velocity_pctl +
  0.25*echo_scaled +
  practical_boost -
  already_seen_penalty

echo_scaled = log1p(echo_count)

### Viral override (always eligible)
A cluster is viral if ANY:
- engagement_pctl >= 90 (within its source)
- velocity_pctl >= 90
- echo_count >= 3

If viral:
- score *= 1.35
- no topic restrictions (security/outage can rise)

### Selection
- Sort clusters by score desc
- Take top 10
- One combined list (no sections)


---

## 6) LLM distillation contract (for each of the 10 clusters)
Only run LLM on selected top 10 clusters.

### Input payload per cluster
- dominant_topic
- cluster canonical identity
- items[] (3–10):
  - title, snippet/text excerpt, url, published_at, metrics summary
- instruction: practical engineering bias, concise, no politics

### Output JSON schema (strict)
{
  "headline": "string",
  "teaser": "string (1 line, public)",
  "takeaway": "string (1–2 lines)",
  "why_care": "string (optional 1 line)",
  "bullets": ["string", "string"],
  "citations": [{"url":"string","label":"string"}],
  "confidence": "low|medium|high"
}

### Hard rules
- No factual claims without citations.
- If uncertain, phrase uncertainty; set confidence low.
- If political content is detected, the cluster should be excluded earlier; if it slips through, produce minimal content with low confidence.


---

## 7) API contract (FastAPI)
### Auth
POST /auth/request-link
Body: { "email": "x@y.com", "redirect": "/daily/2026-01-10" }
Response: { "ok": true }

GET /auth/magic?token=...
- Validates token, creates session cookie, redirects to redirect_path

### Session
GET /api/me
Response: { "authed": true|false }

### Issues
GET /api/issues/{date}?view=public
- Returns 10 items, but items 6–10 locked: headline + teaser only

GET /api/issues/{date}?view=full
- Requires session cookie
- Returns full 10 items: headline, teaser, takeaway, bullets, citations, confidence

### Events
POST /api/events
Body: { "event_name": "issue_view", "properties": {...} }
Store in events table (user_id nullable)


---

## 8) Astro UI spec (static + client unlock)
Routes:
- / (landing + subscribe)
- /daily/[date] (issue page)
- optionally /archives later

Soft gate behavior:
- Public static HTML shows:
  - items 1–5 fully
  - items 6–10 headline+teaser + lock + inline email form
- After magic-link login:
  - client calls /api/me -> if authed calls /api/issues/{date}?view=full
  - replaces locked items with full content

Rendering:
- One combined ordered list 1..10

Sharing:
- Provide "copy share snippet" (top 3 + issue link) suitable for WhatsApp/Slack


---

## 9) Email spec
- Daily send at 08:00 local time (v1 can send one global time; implement per-user later)
- Subject A/B:
  A: "Noyau — {Day} {Mon} {DD} (10 things worth knowing)"
  B: "10 things worth knowing today — Noyau"
- Body:
  - Items 1–5 include bullets
  - Items 6–10 teaser only
  - CTA: “Read full issue” -> /daily/YYYY-MM-DD
  - CTA: “Forward to a friend”


---

## 10) Jobs (systemd timers preferred)
### Hourly: ingest + snapshots
- Fetch from all sources
- Upsert content_items by url
- Append metrics_snapshots
- For X: ingest tweets from curated accounts, store as content_items with source="x", and capture metrics

### Daily: build issue
- Window: last 24h (or 36h to reduce misses)
- Filter politics
- Dedupe
- Cluster
- Score clusters
- Select top 10
- LLM distill top 10 -> cluster_summaries
- Store issues row
- Write a public JSON file for Astro build (optional but recommended for SEO)

Public JSON output format:
{
  "date": "YYYY-MM-DD",
  "items": [
     { "rank":1, "headline":"", "teaser":"", "bullets":["",""], "citations":[...], "locked":false },
     ...
  ]
}

- Run Astro build and deploy static output
- Send daily emails


---

## 11) Config file (single YAML)
Store at ./config.yml

Example:
digest:
  max_items: 10
  send_time_default_local: "08:00"
  web_soft_gate:
    free_items: 5

filters:
  exclude_politics: true
  politics_keywords: ["election","senate","parliament","candidate","campaign","prime minister","president","vote","party"]

ranking:
  half_life_hours: 18
  weights: { recency: 0.30, engagement: 0.20, velocity: 0.25, echo: 0.25 }
  echo_window_hours: 12
  viral: { engagement_pctl: 90, velocity_pctl: 90, echo_accounts: 3 }
  practical_boost_keywords: ["release","changelog","benchmark","postmortem","incident","outage","cve","exploit","patch","migration","performance"]

seeds:
  rss_feeds: []
  github_release_feeds: []
  x_accounts: []
  reddit_subreddits: []
  devto_tags: []
  youtube_channels: []


---

## 12) Terraform deployment (Hetzner VM)
Use Terraform to provision:
- 1 server (Ubuntu 22.04 or 24.04)
- firewall allowing:
  - TCP 22 (your IP)
  - TCP 80/443 (public)
- optional: floating IP
- cloud-init user_data to install Docker + Compose plugin + Caddy (or run Caddy in docker)

### Requirements
- Use hetznercloud/hcloud provider
- Variables: hcloud_token, ssh_public_key, ssh_allowed_ip, domain_name, server_type, location
- Output: server public IP

### Terraform spec (agent should implement)
Resources:
- hcloud_ssh_key
- hcloud_firewall with rules:
  - inbound 22 from var.ssh_allowed_ip/32
  - inbound 80,443 from 0.0.0.0/0 and ::/0
- hcloud_server:
  - image: ubuntu-24.04 (or ubuntu-22.04)
  - server_type: cx22 (cheap) or cx32 (if you want more headroom)
  - firewall_ids: [firewall.id]
  - ssh_keys: [ssh_key.id]
  - user_data: cloud-init that:
    - installs docker + compose plugin
    - creates /opt/noyau
    - installs git
    - (optional) clones repo
    - sets up systemd services/timers for hourly + daily jobs
    - starts docker compose for db/api/caddy

DNS:
- If managing DNS outside Terraform, document manual step:
  - A record domain -> server IP
  - Caddy handles TLS automatically.

State:
- local state is fine for side project; optionally remote state later.

Security:
- store secrets in .env on server (not in Terraform)
- cloud-init can create an empty .env to be filled manually.

### systemd timers spec (agent implement)
- noyau-hourly.timer -> runs /opt/noyau/scripts/hourly.sh
- noyau-daily.timer -> runs /opt/noyau/scripts/daily.sh
Scripts should run docker compose exec worker commands.

---

## 13) Implementation task list (agent-friendly)
1) Set up DB schema + migrations (or run schema.sql on startup)
2) Implement auth:
   - request-link -> store magic link token_hash -> send email
   - magic -> validate -> create session cookie -> redirect
3) Implement /api/issues public/full:
   - pull clusters+summaries for date
   - enforce soft gate on public
4) Implement events endpoint + storage
5) Implement ingest pipeline (start with RSS + GitHub releases + X):
   - RSS fetcher
   - GitHub releases.atom fetcher
   - X fetcher from curated accounts (API-based)
   - store content_items + metrics snapshots
6) Implement clustering v1 by canonical identity
7) Implement scoring (recency/engagement/velocity/echo/practical/viral)
8) Implement daily issue builder selecting top 10 and calling LLM for summaries
9) Implement email digest sender
10) Implement Astro UI:
    - /daily/[date] static build from public JSON OR minimal client fetch for public view
    - inline subscribe, unlock flow
11) Deploy with Docker Compose + Caddy locally
12) Terraform Hetzner infra + cloud-init + systemd timers
13) Observability: basic logs + error alerts (optional)
14) Backups: nightly pg_dump

END.
