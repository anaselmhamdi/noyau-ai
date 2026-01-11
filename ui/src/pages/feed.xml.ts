import type { APIRoute } from 'astro';

const BASE_URL = 'https://noyau.news';

interface Citation {
  url: string;
  label: string;
}

interface FeedItem {
  rank: number;
  headline: string;
  teaser: string;
  takeaway?: string;
  bullets?: string[];
  citations?: Citation[];
  locked: boolean;
}

interface IssueResponse {
  date: string;
  items: FeedItem[];
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

export const GET: APIRoute = async () => {
  const issues: IssueResponse[] = [];

  try {
    // Get recent dates
    const datesRes = await fetch(
      `${import.meta.env.API_URL || ''}/api/issues/dates`
    );
    if (datesRes.ok) {
      const { dates } = await datesRes.json();
      const recentDates = dates.slice(0, 10);

      // Fetch each issue
      for (const date of recentDates) {
        const issueRes = await fetch(
          `${import.meta.env.API_URL || ''}/api/issues/${date}?view=public`
        );
        if (issueRes.ok) {
          issues.push(await issueRes.json());
        }
      }
    }
  } catch {
    // Continue with empty feed
  }

  const now = new Date().toUTCString();

  const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>noyau - Daily Tech Digest</title>
    <description>10 things worth knowing. Daily engineering news, no fluff.</description>
    <link>${BASE_URL}</link>
    <atom:link href="${BASE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
    <language>en-us</language>
    <lastBuildDate>${now}</lastBuildDate>
    <ttl>60</ttl>
    <image>
      <url>${BASE_URL}/logo.png</url>
      <title>noyau</title>
      <link>${BASE_URL}</link>
    </image>
${issues
  .map((issue) => {
    const formattedDate = new Date(issue.date).toUTCString();
    const freeItems = issue.items.filter((item) => !item.locked);

    const contentHtml = freeItems
      .map(
        (item) => `
<h3>${item.rank}. ${escapeXml(item.headline)}</h3>
<p><em>${escapeXml(item.teaser)}</em></p>
${item.takeaway ? `<p>${escapeXml(item.takeaway)}</p>` : ''}
${item.bullets?.length ? `<ul>${item.bullets.map((b) => `<li>${escapeXml(b)}</li>`).join('')}</ul>` : ''}
${item.citations?.length ? `<p>Sources: ${item.citations.map((c) => `<a href="${c.url}">${escapeXml(c.label)}</a>`).join(', ')}</p>` : ''}`
      )
      .join('<hr/>');

    const description = freeItems
      .slice(0, 3)
      .map((item) => item.headline)
      .join(' | ');

    return `    <item>
      <title>Daily Digest - ${issue.date}</title>
      <link>${BASE_URL}/daily/${issue.date}</link>
      <guid isPermaLink="true">${BASE_URL}/daily/${issue.date}</guid>
      <pubDate>${formattedDate}</pubDate>
      <description>${escapeXml(description)}</description>
      <content:encoded><![CDATA[${contentHtml}]]></content:encoded>
    </item>`;
  })
  .join('\n')}
  </channel>
</rss>`;

  return new Response(rss, {
    headers: {
      'Content-Type': 'application/rss+xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600',
    },
  });
};
