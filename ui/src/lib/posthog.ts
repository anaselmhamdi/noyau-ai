import posthog from 'posthog-js';

// Event type definitions for type-safe tracking
export type TrackingEvent =
  // Acquisition
  | { name: 'page_viewed'; properties: PageViewedProps }
  | { name: 'landing_page_viewed'; properties: LandingPageViewedProps }
  | { name: 'issue_page_viewed'; properties: IssuePageViewedProps }
  // Activation
  | { name: 'item_viewed'; properties: ItemViewedProps }
  | { name: 'soft_gate_hit'; properties: SoftGateHitProps }
  | { name: 'signup_form_shown'; properties: SignupFormShownProps }
  | { name: 'signup_started'; properties: SignupStartedProps }
  | { name: 'signup_completed'; properties: SignupCompletedProps }
  | { name: 'magic_link_clicked'; properties: MagicLinkClickedProps }
  | { name: 'session_started'; properties: SessionStartedProps }
  // Retention
  | { name: 'return_visit'; properties: ReturnVisitProps }
  | { name: 'full_issue_consumed'; properties: FullIssueConsumedProps }
  // Referral
  | { name: 'share_snippet_copied'; properties: ShareSnippetCopiedProps }
  | { name: 'share_link_clicked'; properties: ShareLinkClickedProps }
  | { name: 'referral_landing'; properties: ReferralLandingProps };

// Property interfaces
interface PageViewedProps {
  path: string;
  referrer: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  device_type: 'desktop' | 'mobile' | 'tablet';
  is_mobile: boolean;
}

interface LandingPageViewedProps {
  referrer: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  entry_point: string;
}

interface IssuePageViewedProps {
  issue_date: string;
  referrer: string;
  is_latest: boolean;
  items_visible: 5 | 10;
}

interface ItemViewedProps {
  item_rank: number;
  issue_date: string;
  is_locked: boolean;
  cluster_id?: string;
}

interface SoftGateHitProps {
  item_rank: number;
  issue_date: string;
  time_on_page_seconds: number;
}

interface SignupFormShownProps {
  trigger: 'scroll' | 'gate_hit' | 'cta_click' | 'page_load';
  issue_date?: string;
}

interface SignupStartedProps {
  email_domain: string;
  issue_date?: string;
  form_location: 'hero' | 'footer' | 'inline';
}

interface SignupCompletedProps {
  email_domain: string;
  issue_date?: string;
  validation_status: 'valid' | 'invalid' | 'unknown';
}

interface MagicLinkClickedProps {
  token_age_seconds: number;
  email_client?: string;
}

interface SessionStartedProps {
  is_new_user: boolean;
  signup_source?: string;
  ref_code?: string;
}

interface ReturnVisitProps {
  days_since_last_visit: number;
  entry_point: string;
}

interface FullIssueConsumedProps {
  issue_date: string;
  time_on_page_seconds: number;
  items_clicked: number;
}

interface ShareSnippetCopiedProps {
  issue_date: string;
  platform_hint?: string;
  items_in_snippet: number;
}

interface ShareLinkClickedProps {
  issue_date: string;
  share_platform: 'whatsapp' | 'slack' | 'twitter' | 'linkedin' | 'copy';
}

interface ReferralLandingProps {
  ref_code: string;
  referrer_user_id?: string;
  issue_date?: string;
}

// Initialize PostHog
export function initPostHog(apiKey: string, options?: { debug?: boolean }) {
  if (typeof window === 'undefined') return;

  posthog.init(apiKey, {
    api_host: 'https://us.i.posthog.com',
    person_profiles: 'identified_only',
    capture_pageview: false, // We handle this manually for more control
    capture_pageleave: true,
    autocapture: false, // We use explicit tracking for better data quality
    persistence: 'localStorage+cookie',
    loaded: (ph) => {
      if (options?.debug) {
        ph.debug();
      }
    },
  });
}

// Type-safe event tracking
export function track<T extends TrackingEvent>(event: T['name'], properties: T['properties']) {
  if (typeof window === 'undefined') return;
  posthog.capture(event, properties);
}

// Convenience functions for common events
export function trackPageView(path: string) {
  const params = new URLSearchParams(window.location.search);
  const referrer = document.referrer;

  const properties: PageViewedProps = {
    path,
    referrer,
    utm_source: params.get('utm_source') || undefined,
    utm_medium: params.get('utm_medium') || undefined,
    utm_campaign: params.get('utm_campaign') || undefined,
    utm_content: params.get('utm_content') || undefined,
    device_type: getDeviceType(),
    is_mobile: window.innerWidth < 768,
  };

  track('page_viewed', properties);

  // Also track specific page types
  if (path === '/' || path === '') {
    track('landing_page_viewed', {
      referrer,
      utm_source: properties.utm_source,
      utm_medium: properties.utm_medium,
      utm_campaign: properties.utm_campaign,
      utm_content: properties.utm_content,
      entry_point: 'direct',
    });
  }
}

export function trackIssuePageView(issueDate: string, isLatest: boolean, itemsVisible: 5 | 10) {
  track('issue_page_viewed', {
    issue_date: issueDate,
    referrer: document.referrer,
    is_latest: isLatest,
    items_visible: itemsVisible,
  });
}

export function trackSoftGateHit(itemRank: number, issueDate: string, pageLoadTime: number) {
  const timeOnPage = Math.floor((Date.now() - pageLoadTime) / 1000);
  track('soft_gate_hit', {
    item_rank: itemRank,
    issue_date: issueDate,
    time_on_page_seconds: timeOnPage,
  });
}

export function trackSignupFormShown(trigger: SignupFormShownProps['trigger'], issueDate?: string) {
  track('signup_form_shown', { trigger, issue_date: issueDate });
}

export function trackSignupStarted(email: string, formLocation: 'hero' | 'footer' | 'inline', issueDate?: string) {
  const domain = email.split('@')[1] || 'unknown';
  track('signup_started', {
    email_domain: domain,
    issue_date: issueDate,
    form_location: formLocation,
  });
}

export function trackShareSnippetCopied(issueDate: string, itemCount: number) {
  track('share_snippet_copied', {
    issue_date: issueDate,
    items_in_snippet: itemCount,
  });
}

export function trackReferralLanding(refCode: string, issueDate?: string) {
  track('referral_landing', {
    ref_code: refCode,
    issue_date: issueDate,
  });
}

export function trackMagicLinkClicked() {
  // Estimate token age from URL or default to 0
  // The actual age would need to come from the backend
  track('magic_link_clicked', {
    token_age_seconds: 0,
    email_client: detectEmailClient(),
  });
}

// Detect email client from referrer or user agent hints
function detectEmailClient(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  const referrer = document.referrer.toLowerCase();
  if (referrer.includes('mail.google')) return 'gmail';
  if (referrer.includes('outlook')) return 'outlook';
  if (referrer.includes('yahoo')) return 'yahoo';
  if (referrer.includes('proton')) return 'protonmail';
  return undefined;
}

// User identification
export function identifyUser(userId: string, properties?: Record<string, any>) {
  if (typeof window === 'undefined') return;
  posthog.identify(userId, properties);
}

export function setUserProperties(properties: Record<string, any>) {
  if (typeof window === 'undefined') return;
  posthog.people.set(properties);
}

export function incrementUserProperty(property: string, value: number = 1) {
  if (typeof window === 'undefined') return;
  posthog.people.set_once({ [property]: 0 }); // Ensure property exists
  posthog.capture('$set', { $set: { [property]: { $add: value } } });
}

// Session management
export function resetUser() {
  if (typeof window === 'undefined') return;
  posthog.reset();
}

// Feature flags
export function isFeatureEnabled(flag: string): boolean {
  if (typeof window === 'undefined') return false;
  return posthog.isFeatureEnabled(flag) ?? false;
}

export function getFeatureFlag(flag: string): string | boolean | undefined {
  if (typeof window === 'undefined') return undefined;
  return posthog.getFeatureFlag(flag);
}

// Utility functions
function getDeviceType(): 'desktop' | 'mobile' | 'tablet' {
  if (typeof window === 'undefined') return 'desktop';

  const width = window.innerWidth;
  if (width < 768) return 'mobile';
  if (width < 1024) return 'tablet';
  return 'desktop';
}

// Page timing helper
let pageLoadTime = 0;
export function setPageLoadTime() {
  pageLoadTime = Date.now();
}
export function getPageLoadTime(): number {
  return pageLoadTime;
}

// Export raw posthog instance for advanced use cases
export { posthog };
