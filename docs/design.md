# NewsPulse - Design Document

> **Status:** Draft — awaiting feature discussion

## Concept

**InShorts-style news aggregator** — bite-sized headlines, AI-generated unified summaries, conversational depth on every story.

Think: InShorts but with AI depth. You see a headline → tap → get a clean summary + sources → chat with the AI for deeper context, explanations, or follow-ups.

**Tabs:** India · Just For You · Sports · Business · Global
- **India** — Indian news (NDTV, TOI, Indian Express, Hindu, etc.)
- **Just For You** — personalized feed (clicks, saves, time of day, topics)
- **Sports** — cricket, IPL, football, Olympics, etc.
- **Business** — markets, stocks, economy, startups
- **Global** — world news (BBC, CNN, Reuters, Al Jazeera, etc.)

## Decisions (2026-05-05)

| Decision | Value |
|----------|-------|
| Q&A scope | Per-article chat only |
| News sources | **Web scraping only** (no RSS). Multiple sources per story → AI-summarized |
| News sources — India | NDTV, Times of India, Indian Express, Hindu, Moneycontrol, ESPNcricinfo, etc. |
| News sources — Global | BBC, CNN, Reuters, Al Jazeera, etc. |
| Geo scope | Multi-tab: India · Just For You · Sports · Business · Global |
| Dedup approach | **Topic-level clustering** — same story from 5 sources = 1 unified article |
| Product scope | Global consumer product (India-first) |
| Semantic search | Embeddings-based (local model) |
| LLM provider | OpenAI API (chat) |
| Vector storage | pgvector (PostgreSQL) |
| Frontend | Next.js |
| Celery broker | Redis |
| Caching | Redis |
| Email | Django SMTP (simple) |
| Auth | JWT via DRF |
| Embedding model | Local (for now) |

## Proposed Architecture

```
├── backend/                  # Django + DRF + PostgreSQL + pgvector
│   ├── core/                 # Settings, URLs, WSGI
│   ├── articles/             # Article model, topic clustering, summaries
│   ├── sources/              # Scraper definitions (no RSS)
│   ├── worker/               # Celery tasks: scrape, cluster, summarize, embed
│   ├── chat/                 # Per-article conversation threads
│   ├── digest/               # Daily summary generation, email delivery
│   └── users/                # JWT auth, profiles
├── frontend/                 # Next.js (App Router)
│   ├── app/                  # Routes: /, /article/[id], /saved
│   ├── components/           # HeadlineCard, SummaryView, ChatPanel, KnowMore
│   └── lib/                  # API client, hooks
├── cache/                    # Redis (caching + Celery broker)
└── embeddings/               # Local embedding model + pgvector
```

## Key Flows

1. **Scrape** — Periodic jobs scrape news sources by category:
   - India: NDTV, TOI, Indian Express, Hindu, Moneycontrol
   - Sports: ESPNcricinfo, Sportskeeda, etc.
   - Business: Moneycontrol, Economic Times, etc.
   - Global: BBC, CNN, Reuters, Al Jazeera
2. **Cluster** — AI groups articles covering the same story/topic from different sources
3. **Summarize** — Generate a unified AI summary per story (combines perspectives)
4. **Embed** — Generate embeddings for the summary + full text (local model → pgvector)
5. **Tab Feed** — User browses headlines by tab (India · Just For You · Sports · Business · Global)
6. **Article Detail** — Tap headline → see full summary, source links, embedded chat
7. **Chat** — Per-article AI chat for deeper context, explanations, follow-ups

## Core Features

### Headline Feed (InShorts style)
- Clean list of news headlines with AI-generated summaries (~60-80 words)
- Each card shows: title, summary snippet, source logos/links, timestamp
- One unified article per story (clustered from multiple sources)
- No duplicate stories from different providers
- Infinite scroll
- **Tab navigation:** India · Just For You · Sports · Business · Global
- **Just For You:** personalized ranking (clicks, saves, time of day, topic affinity)

### Article Detail
- Full AI-generated summary (combines multiple source perspectives)
- "Sources" section — links to original articles
- Embedded chat panel (slide-out on right)
- **"Know More"** button → expanded full-screen chat interface

### Chat
- Per-article context only (summary + sources as ground truth)
- Follow-up questions, fact-checking, explain concepts, get background
- Powered by OpenAI API
- Ephemeral in MVP (no chat history)

### Email Digest
- Daily summary of top stories (India)
- AI-generated brief
- Opt-in subscription via Django SMTP

### User
- JWT auth via DRF (optional accounts)
- Anonymous browsing by default
- Saved articles, preferences for logged-in users

---
*This file will be updated with API contracts, data models, and trade-offs during the Design phase.*
