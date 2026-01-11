# NoyauAI Process Documentation

## Daily Content Pipeline

This document explains how content flows through NoyauAI from ingestion to delivery.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         NOYAUAI PIPELINE                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  HOURLY (every hour)                                                     │
│  ═══════════════════                                                     │
│                                                                          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│  │  Fetch   │ → │Normalize │ → │  Upsert  │ → │ Snapshot │             │
│  │ Sources  │   │   URLs   │   │  Items   │   │ Metrics  │             │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘             │
│                                                                          │
│  DAILY (06:00 UTC)                                                       │
│  ═════════════════                                                       │
│                                                                          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│  │  Load    │ → │  Filter  │ → │ Cluster  │ → │  Score   │             │
│  │ 36h data │   │ Politics │   │ by ID    │   │  Rank    │             │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘             │
│       │                                             │                    │
│       │              ┌──────────────────────────────┘                    │
│       │              │                                                   │
│       │         ┌────▼─────┐   ┌──────────┐   ┌──────────┐             │
│       │         │  Select  │ → │  Distill │ → │  Store   │             │
│       │         │  Top 10  │   │   LLM    │   │   DB     │             │
│       │         └──────────┘   └──────────┘   └──────────┘             │
│       │                             │               │                    │
│       │                             │               │                    │
│       │              ┌──────────────┴───────────────┘                    │
│       │              │                                                   │
│       │         ┌────▼─────┐   ┌──────────┐                             │
│       └────────→│  Write   │ → │  Send    │                             │
│                 │  JSON    │   │  Emails  │                             │
│                 └──────────┘   └──────────┘                             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Phase 1: Hourly Ingest

### Purpose
Continuously collect content from all configured sources and track engagement metrics over time.

### Trigger
- systemd timer: `noyau-hourly.timer`
- Runs every hour with 5-minute random delay
- Command: `python -m app.jobs.hourly`

### Process

#### Step 1.1: Fetch from Sources

Each source fetcher runs independently:

**RSS Feeds**
```
For each feed in config.seeds.rss_feeds:
    1. HTTP GET feed URL
    2. Parse with feedparser
    3. Extract: title, url, published_at, description
    4. Yield RawContent items
```

**GitHub Releases**
```
For each repo in config.seeds.github_release_feeds:
    1. Fetch releases.atom
    2. Parse Atom entries
    3. Extract: version, release notes, url
    4. Yield RawContent with source="github"
```

**X/Twitter (via Nitter)**
```
For each account in config.seeds.x_accounts:
    For each Nitter instance in config.nitter.instances:
        1. Try: GET https://{instance}/{username}/rss
        2. If success: parse and yield items
        3. If fail: try next instance
```

**Reddit**
```
For each subreddit in config.seeds.reddit_subreddits:
    1. GET https://reddit.com/r/{sub}/hot.json
    2. Parse JSON response
    3. Extract: title, selftext, upvotes, comments
    4. Yield RawContent items
```

**dev.to**
```
For each tag in config.seeds.devto_tags:
    1. GET https://dev.to/api/articles?tag={tag}
    2. Parse JSON response
    3. Extract: title, description, reactions, comments
    4. Yield RawContent items
```

**YouTube**
```
For each channel in config.seeds.youtube_channels:
    1. Fetch channel RSS feed
    2. For each video:
        a. Extract basic metadata
        b. Try: fetch transcript via youtube-transcript-api
        c. Yield RawContent with transcript text
```

#### Step 1.2: Normalize

For each RawContent item:

```python
# URL Canonicalization
url = "https://example.com/article?utm_source=twitter&ref=news"
canonical = canonicalize_url(url)
# Result: "https://example.com/article"

# Extract canonical identity for clustering
identity = extract_canonical_identity(url, text)
# Priorities:
# 1. "github:owner/repo" for GitHub URLs
# 2. "cve:CVE-YYYY-XXXXX" if CVE mentioned
# 3. Canonical URL otherwise
```

#### Step 1.3: Upsert Content Items

```python
# Check if URL already exists
existing = SELECT * FROM content_items WHERE url = ?

if existing:
    # Item already in DB, just add metrics
    pass
else:
    # Insert new item
    INSERT INTO content_items (
        source, url, title, author, published_at, text
    )
```

#### Step 1.4: Create Metrics Snapshot

```python
# Every hour, capture current engagement
INSERT INTO metrics_snapshots (
    item_id,
    captured_at,
    metrics_json
)

# Example metrics_json by source:
# X: {"likes": 100, "retweets": 50, "replies": 25}
# Reddit: {"upvotes": 500, "comments": 100, "upvote_ratio": 0.92}
# YouTube: {"views": 10000, "comments": 50}
# GitHub: {"stars": 100, "forks": 20}
# dev.to: {"reactions": 50, "comments": 10}
```

### Output

After each hourly run:
- New content items in `content_items` table
- Engagement snapshots in `metrics_snapshots` table
- Logs with ingest stats (items processed, errors)

---

## Phase 2: Daily Issue Build

### Purpose
Select the top 10 most relevant stories and create the daily digest.

### Trigger
- systemd timer: `noyau-daily.timer`
- Runs at 06:00 UTC daily
- Command: `python -m app.jobs.daily`

### Process

#### Step 2.1: Load Content Window

```python
# Get items from last 36 hours (overlap to catch items near cutoff)
cutoff = now() - 36 hours

items = SELECT * FROM content_items
        WHERE published_at >= cutoff
        WITH metrics_snapshots
```

#### Step 2.2: Filter Political Content

Two-stage filter to remove political content while minimizing false positives:

**Stage 1: Keyword Match**
```python
keywords = ["election", "senate", "parliament", "candidate", ...]

def keyword_filter(text):
    return any(kw in text.lower() for kw in keywords)
```

**Stage 2: LLM Validation**
```python
# Only for items that matched keywords
if keyword_filter(item.text):
    # Ask LLM to validate
    is_political = await llm_politics_check(item.text)

    # "leader election in distributed systems" → not_political
    # "presidential election results" → political
```

#### Step 2.3: Build Clusters

Group items by canonical identity:

```python
clusters = defaultdict(list)

for item in items:
    identity = extract_canonical_identity(item.url, item.text)
    clusters[identity].append(item)

# Example clusters:
# "github:kubernetes/kubernetes" → [release post, tweet, HN discussion]
# "cve:CVE-2024-1234" → [blog post, tweet, reddit thread]
# "https://blog.example.com/article" → [single item]
```

#### Step 2.4: Score Clusters

For each cluster, compute composite score:

```python
def score_cluster(identity, items):
    best_item = max(items, key=engagement)

    # Component scores
    recency = exp(-age_hours / 18)  # Half-life decay

    engagement_pctl = percentile(
        engagement(best_item),
        historical_distribution[source]
    )

    velocity = (eng_now - eng_1h_ago) / 1h
    velocity_pctl = percentile(velocity, historical_distribution[source])

    echo = count_distinct_x_accounts_mentioning(identity)
    echo_scaled = log1p(echo)

    # Boosts and penalties
    practical_boost = 0.15 if has_practical_keywords(items) else 0
    already_seen = 0.30 if identity in yesterday_top_10 else 0

    # Final score
    score = (
        0.30 * recency +
        0.20 * engagement_pctl/100 +
        0.25 * velocity_pctl/100 +
        0.25 * echo_scaled +
        practical_boost -
        already_seen
    )

    # Viral boost
    if engagement_pctl >= 90 or velocity_pctl >= 90 or echo >= 3:
        score *= 1.35

    return score
```

#### Step 2.5: Select Top 10

```python
ranked = sorted(clusters, key=score, reverse=True)
top_10 = ranked[:10]
```

#### Step 2.6: LLM Distillation

For each of the top 10 clusters:

```python
# Prepare input
input_data = {
    "dominant_topic": infer_topic(identity),
    "canonical_identity": identity,
    "items": [
        {
            "title": item.title,
            "url": item.url,
            "text_excerpt": item.text[:500],
            "published_at": item.published_at,
            "metrics_summary": format_metrics(item)
        }
        for item in cluster_items[:5]
    ]
}

# Call OpenAI with structured output
response = await client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": DISTILL_PROMPT},
        {"role": "user", "content": format_input(input_data)}
    ],
    response_format=ClusterDistillOutput
)

summary = response.choices[0].message.parsed
# Guaranteed to match schema:
# - headline (max 90 chars)
# - teaser (1 line)
# - takeaway (1-2 lines)
# - why_care (optional)
# - bullets (2 items)
# - citations (1-3 URLs)
# - confidence (low/medium/high)
```

#### Step 2.7: Store Results

```python
# Create issue record
INSERT INTO issues (issue_date, public_url)

# For each cluster
for rank, (identity, items, score, summary) in enumerate(top_10):
    # Store cluster
    INSERT INTO clusters (
        issue_date, canonical_identity, dominant_topic, cluster_score
    )

    # Link items
    for item in items:
        INSERT INTO cluster_items (cluster_id, item_id, rank)

    # Store summary
    INSERT INTO cluster_summaries (
        cluster_id, headline, teaser, takeaway,
        why_care, bullets_json, citations_json, confidence
    )
```

#### Step 2.8: Write Public JSON

```python
# Write to public/issues/2026-01-10.json
{
    "date": "2026-01-10",
    "items": [
        {
            "rank": 1,
            "headline": "...",
            "teaser": "...",
            "takeaway": "...",  # Only for rank 1-5
            "bullets": [...],    # Only for rank 1-5
            "citations": [...],  # Only for rank 1-5
            "locked": false
        },
        ...
        {
            "rank": 6,
            "headline": "...",
            "teaser": "...",
            "locked": true  # Items 6-10 are soft-gated
        },
        ...
    ]
}
```

#### Step 2.9: Send Emails

```python
for user in all_subscribers:
    await send_daily_digest(
        email=user.email,
        issue_date=today,
        items=formatted_items
    )
```

### Output

After daily job:
- `issues` table updated with new issue
- `clusters` and `cluster_summaries` populated
- `public/issues/{date}.json` written
- Emails sent to all subscribers

---

## Scoring Formula Deep Dive

### Recency Score

Uses exponential decay with configurable half-life:

```
recency = e^(-age_hours / half_life_hours)

With half_life = 18 hours:
- 0 hours ago: recency = 1.0
- 18 hours ago: recency = 0.37
- 36 hours ago: recency = 0.14
- 54 hours ago: recency = 0.05
```

### Engagement Percentile

Normalized across sources using 7-day historical data:

```python
# Build distribution per source
historical = {
    "reddit": [all upvotes+2*comments from last 7 days],
    "x": [all likes+2*rt+replies from last 7 days],
    ...
}

# Calculate percentile
def get_percentile(source, value):
    dist = sorted(historical[source])
    position = binary_search(dist, value)
    return (position / len(dist)) * 100
```

### Velocity

Rate of engagement change:

```python
def velocity(item):
    if len(item.snapshots) < 2:
        return 0

    latest = item.snapshots[-1]
    previous = item.snapshots[-2]

    dt_hours = (latest.time - previous.time).hours
    eng_diff = engagement(latest) - engagement(previous)

    return eng_diff / dt_hours
```

### Echo Detection

Counts distinct X accounts mentioning the cluster:

```python
def compute_echo(cluster_identity, x_items, window_hours=12):
    cutoff = now() - window_hours
    authors = set()

    for tweet in x_items:
        if tweet.published_at >= cutoff:
            # Check if tweet references the cluster
            tweet_identity = extract_canonical_identity(tweet.url, tweet.text)
            if tweet_identity == cluster_identity:
                authors.add(tweet.author)

    return len(authors)
```

### Practical Boost Keywords

```python
practical_keywords = [
    "release", "changelog", "benchmark", "postmortem",
    "incident", "outage", "cve", "exploit", "patch",
    "migration", "performance"
]

def practical_boost(items):
    for item in items:
        text = (item.title + " " + item.text).lower()
        if any(kw in text for kw in practical_keywords):
            return 0.15
    return 0
```

---

## API Request Flow

### Magic Link Authentication

```
1. POST /auth/request-link {"email": "user@example.com", "redirect": "/daily/2026-01-10"}
   → Generate random token
   → Hash and store in magic_links table
   → Send email with link
   → Return {"ok": true}

2. User clicks link in email:
   GET /auth/magic?token=xxx&redirect=/daily/2026-01-10
   → Hash token, lookup in magic_links
   → Verify not expired, not used
   → Mark as used
   → Find or create user
   → Create session
   → Set session_id cookie
   → Redirect to /daily/2026-01-10

3. Subsequent requests include cookie:
   GET /api/me (Cookie: session_id=xxx)
   → Lookup session
   → Verify not expired
   → Return user info
```

### Issue Retrieval with Soft Gate

```
# Unauthenticated request
GET /api/issues/2026-01-10
→ Load clusters for date
→ Items 1-5: Full content
→ Items 6-10: headline + teaser only, locked=true

# Authenticated request
GET /api/issues/2026-01-10?view=full (with session cookie)
→ Verify session
→ Load clusters for date
→ All items: Full content, locked=false
```

---

## Error Handling

### Ingest Errors

```python
# Per-source failure isolation
for fetcher in fetchers:
    try:
        async for item in fetcher.fetch():
            process(item)
    except Exception as e:
        log.error("fetcher_error", source=fetcher.name, error=str(e))
        # Continue to next source - don't fail entire ingest
```

### LLM Errors

```python
# Retry with backoff
for attempt in range(3):
    try:
        return await distill_cluster(...)
    except RateLimitError:
        await sleep(2 ** attempt)

# On persistent failure
return None  # Skip this cluster, use remaining 9
```

### Email Errors

```python
for user in users:
    try:
        await send_email(user)
    except Exception:
        log.error("email_failed", email=user.email)
        # Continue to next user
```

---

## Monitoring Checklist

### Daily Health Check

- [ ] Hourly job ran 24 times (check logs)
- [ ] Daily job completed successfully
- [ ] Issue has 10 clusters with summaries
- [ ] Public JSON file exists
- [ ] Emails sent without errors

### Weekly Review

- [ ] Source coverage: All sources returning content?
- [ ] Cluster diversity: Not dominated by single source?
- [ ] LLM quality: Summaries making sense?
- [ ] Email deliverability: Bounce rate acceptable?
