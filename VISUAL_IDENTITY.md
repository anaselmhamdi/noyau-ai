NoyauAI — Visual Identity (v1)
> One-line: A calm, high-signal daily digest for builders.  
> Positioning: “Kernel-level” essentials — ranked, brief, actionable.
***1) Brand basics
Name
NoyauAI
Pronunciation (optional helper)
nwah-YOH (French). You don’t need to teach it—let the product do the work.
Tagline options
Pick one and use it everywhere:
The kernel brief for builders.
Daily signal for engineers.
Ranked tech + AI, distilled.
Voice
Practical, low-hype
Short sentences
Opinionated only when backed by evidence
Avoid marketing fluff (“revolutionary”, “game-changing”, “disrupt”)
***2) Logo system (simple + flexible)
Primary mark concept
Bracketed kernel dot: [ ● ]  
Meaning: “core signal in context”.
Use cases:
Favicon
App icon
Watermark
Loading state
Wordmark
NoyauAI in a clean sans (Inter / system-ui), with subtle emphasis:
Noyau normal weight
AI slightly heavier or same weight with tighter tracking
Clear space
Keep at least 1× the dot diameter of clear space around the mark.
Don’ts
Don’t add gradients or glows to the logo itself.
Don’t stretch.
Don’t outline the wordmark.
***3) Color palette
Design principle: 3 neutrals + 1 signal accent.  
Use the accent color only for “this matters” states: score, selected filter, primary actions.
Core palette (dark-first)
Ink (background): #0B0F14
Slate (surface/cards): #111827
Border: #223047
Text (primary): #E5E7EB
Text (muted): #94A3B8
Accents
Signal (cyan): #22D3EE  ← default accent
Macro (amber): #F59E0B  ← sparing use (macro/markets)
Positive: #22C55E
Negative: #EF4444
Usage rules
Default UI is neutral.
Cyan = selected, important, high score.
Amber = macro context or “watch” items (not the primary CTA).
***4) Typography
Fonts
UI / headlines: Inter  
  Fallback: system-ui, -apple-system, Segoe UI, Roboto, Arial
Mono / tags / scores: JetBrains Mono  
  Fallback: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas
Type scale (recommended)
H1: 28–32 / 700
H2: 18–20 / 650
Body: 14–16 / 450
Meta: 12–13 / 450 (mono)
Typography principles
Headlines: short, scannable.
Teasers: max 2 lines.
Metadata: always smaller + muted + mono.
***5) Layout & spacing
Grid & spacing
Base spacing unit: 8px
Card padding: 16–20px
Corner radius: 16px
Border width: 1px, low contrast
Page structure
Sticky top bar: logo, search, filters
Feed: stacked cards with consistent density
Minimal side chrome; content is the hero
***6) Components (UI spec)
Digest card (default)
Structure
Source + category (muted)
Headline (strong)
Teaser (muted, 2 lines max)
Footer row: Score pill • age • tags • actions
States
Hover: slight lift + border brightens
Selected: cyan border or left accent rule
Score pill
Shape: rounded-full
Default: neutral border + muted text
High score: cyan border + cyan text (avoid filled backgrounds)
Tags (chips)
Mono, small, subtle background
Example topics: k8s, dbt, snowflake, scraping, langchain, kafka, bigquery
Filters (chips)
Selected: cyan outline + cyan text
Unselected: neutral outline + muted
Soft gate / public preview
Public: headline + teaser visible
Locked content: fade/blur body with calm CTA  
  Copy: “Get the full brief via magic link.”
***7) Motion & interaction
Rule: motion supports scanning, never distracts.
Hover: 120–160ms
Page transitions: none (keep it snappy)
Loading: subtle shimmer on card skeletons
***8) Imagery & iconography
Icons
Use thin-line icons (Lucide-like).
Keep icon sizes consistent (16–18px).
Data viz (optional)
Micro sparklines for macro only.
Avoid colorful charts; keep neutral unless explicitly highlighting.
Backgrounds
Optional subtle grid/noise at 3–6% opacity.
***9) Content guidelines (the “brief” style)
Headline
Max 90 characters
Prefer verbs + concrete nouns
Avoid clickbait punctuation
Teaser
1–2 sentences
Answer: “What changed?” + “Why it matters?”
“Why it matters” block (optional)
Max 2 bullets
Prefer actionable implications:
“Affects X users because…”
“Changes cost/latency/risk by…”
***10) Accessibility baseline
Maintain strong contrast for text on Ink/Slate.
Never use color alone to signal meaning: pair with icon/label.
Focus states: visible cyan outline on interactive elements.
***11) Implementation tokens
CSS variables
:root {
  --ink: #0B0F14;
  --slate: #111827;
  --border: #223047;
  --text: #E5E7EB;
  --muted: #94A3B8;
  --signal: #22D3EE;
  --macro: #F59E0B;
  --good: #22C55E;
  --bad: #EF4444;
  --radius: 16px;
}
Tailwind mapping (example)
// tailwind.config.js (conceptual)
theme: {
  extend: {
    colors: {
      ink: "#0B0F14",
      slate: "#111827",
      border: "#223047",
      text: "#E5E7EB",
      muted: "#94A3B8",
      signal: "#22D3EE",
      macro: "#F59E0B",
      good: "#22C55E",
      bad: "#EF4444",
    },
    borderRadius: {
      card: "16px",
    },
  }
}
***12) Quick copy examples
Primary CTA
“Get the brief”
“Open today’s digest”
“Send magic link”
Section labels
“Signal”
“Macro”
“Viral (if relevant)”
“Context”
***13) Brand checklist (ship-ready)
Logo mark [●] works at 16px
One accent color only (cyan)
Card hierarchy feels calm at ~10 items/day
Score pill readable at a glance
Public preview: headline + teaser visible, rest softly gated
