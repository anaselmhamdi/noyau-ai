import type { APIRoute } from 'astro';

interface IssueItem {
  rank: number;
  headline: string;
  teaser: string;
  locked: boolean;
}

interface IssueResponse {
  date: string;
  items: IssueItem[];
}

export const GET: APIRoute = async () => {
  let latestIssue: IssueResponse | null = null;

  try {
    const res = await fetch(
      `${import.meta.env.API_URL || ''}/api/issues/latest?view=public`
    );
    if (res.ok) {
      latestIssue = await res.json();
    }
  } catch {
    // Continue without latest issue
  }

  const content = `# noyau.news - Extended LLM Context

> NoyauAI delivers a daily digest of 10 algorithmically-ranked tech stories for engineers.

## Mission

Cut through the noise. Surface practical engineering news that matters. No fluff, no politics, just actionable intelligence for builders.

## Content Pipeline

1. INGEST: Hourly fetch from curated sources
   - RSS: Google Cloud, AWS, Kubernetes, Hacker News, arXiv
   - GitHub: Releases for popular projects (Python, Go, Kubernetes, LangChain, etc.)
   - X/Twitter: Curated accounts (Karpathy, Simon Willison, Charity Majors, etc.)
   - Reddit: r/programming, r/golang, r/Python, r/kubernetes, r/devops, r/MachineLearning

2. CLUSTER: Group related items by canonical identity (same story, multiple sources)

3. SCORE: Rank clusters by weighted algorithm
   - Recency: 30% (18h half-life exponential decay)
   - Engagement: 20% (normalized by source)
   - Velocity: 25% (engagement change rate)
   - Echo: 25% (cross-platform mentions)
   - Practical boost: +0.15 for releases, CVEs, benchmarks, postmortems
   - Viral override: 1.35x for high-engagement items

4. DISTILL: Top 10 clusters summarized via LLM
   - Headline: Concise, informative title
   - Teaser: One-line summary
   - Takeaway: Actionable insight
   - Why Care: Context for engineers
   - Bullets: Key points
   - Citations: Source URLs

5. DELIVER: Email at 08:00 local time, web at /daily/YYYY-MM-DD

## Schema

Each issue item contains:
- rank: 1-10
- headline: string (max 200 chars)
- teaser: string (max 500 chars)
- takeaway: string (full insight)
- why_care: string (optional context)
- bullets: string[] (key points)
- citations: {url, label}[] (sources)
- confidence: "low" | "medium" | "high"

## Current Issue

${
  latestIssue
    ? `Date: ${latestIssue.date}

Stories:
${latestIssue.items
  .map(
    (item) => `${item.rank}. ${item.headline}
   ${item.teaser}${item.locked ? ' [subscribers only]' : ''}
`
  )
  .join('\n')}`
    : 'No current issue available.'
}

## API

GET /api/issues/latest
GET /api/issues/{YYYY-MM-DD}
GET /api/issues/dates

## Feeds

RSS: /feed.xml
Sitemap: /sitemap.xml

## Rate Limits

Please respect: 1 request per second, cache when possible.

## Contact

Web: https://noyau.news
`;

  return new Response(content, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'public, max-age=3600',
    },
  });
};
