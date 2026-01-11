/**
 * JSON-LD Schema helpers for SEO structured data
 */

export interface IssueItem {
  rank: number;
  headline: string;
  teaser: string;
  takeaway?: string;
  bullets?: string[];
  citations?: { url: string; label: string }[];
}

const SITE_URL = 'https://noyau.news';
const LOGO_URL = `${SITE_URL}/logo.png`;

export function generateOrganizationSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'NoyauNews',
    alternateName: 'Noyau',
    url: SITE_URL,
    logo: LOGO_URL,
    description: 'Daily engineering digest. 10 things worth knowing.',
    foundingDate: '2024',
  };
}

export function generateWebSiteSchema() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'NoyauNews',
    alternateName: 'Noyau',
    url: SITE_URL,
    description: '10 things worth knowing. Daily engineering digest.',
    publisher: {
      '@type': 'Organization',
      name: 'noyau',
      logo: {
        '@type': 'ImageObject',
        url: LOGO_URL,
      },
    },
  };
}

export function generateNewsArticleSchema(
  date: string,
  headline: string,
  description: string
) {
  const publishedTime = `${date}T08:00:00Z`;

  return {
    '@context': 'https://schema.org',
    '@type': 'NewsArticle',
    headline: headline,
    description: description,
    datePublished: publishedTime,
    dateModified: publishedTime,
    author: {
      '@type': 'Organization',
      name: 'noyau',
      url: SITE_URL,
    },
    publisher: {
      '@type': 'Organization',
      name: 'noyau',
      logo: {
        '@type': 'ImageObject',
        url: LOGO_URL,
      },
    },
    mainEntityOfPage: {
      '@type': 'WebPage',
      '@id': `${SITE_URL}/daily/${date}`,
    },
    image: `${SITE_URL}/og-default.png`,
  };
}

export function generateItemListSchema(date: string, items: IssueItem[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: `Daily Tech Digest - ${date}`,
    numberOfItems: items.length,
    itemListElement: items.map((item) => ({
      '@type': 'ListItem',
      position: item.rank,
      item: {
        '@type': 'TechArticle',
        headline: item.headline,
        description: item.teaser,
        url: `${SITE_URL}/daily/${date}#story-${item.rank}`,
      },
    })),
  };
}

export function generateBreadcrumbSchema(
  items: { name: string; url: string }[]
) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };
}
