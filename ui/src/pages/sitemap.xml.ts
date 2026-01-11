import type { APIRoute } from 'astro';

const BASE_URL = 'https://noyau.news';

export const GET: APIRoute = async () => {
  let issueDates: string[] = [];

  try {
    const res = await fetch(
      `${import.meta.env.API_URL || ''}/api/issues/dates`
    );
    if (res.ok) {
      const data = await res.json();
      issueDates = data.dates || [];
    }
  } catch {
    // Continue with empty list
  }

  const today = new Date().toISOString().split('T')[0];

  const staticPages = [
    { loc: '/', changefreq: 'daily', priority: '1.0' },
  ];

  const issuePages = issueDates.map((date) => ({
    loc: `/daily/${date}`,
    lastmod: date,
    changefreq: 'never' as const,
    priority: date === today ? '0.9' : '0.7',
  }));

  const allPages = [...staticPages, ...issuePages];

  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${allPages
  .map(
    (page) => `  <url>
    <loc>${BASE_URL}${page.loc}</loc>
    ${'lastmod' in page && page.lastmod ? `<lastmod>${page.lastmod}</lastmod>` : ''}
    <changefreq>${page.changefreq}</changefreq>
    <priority>${page.priority}</priority>
  </url>`
  )
  .join('\n')}
</urlset>`;

  return new Response(sitemap, {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600',
    },
  });
};
