# NewsPulse - Workplan

> **Reordered 2026-05-07:** Phase 5 before Phase 3. Foundation-first approach.
> Phase 2.7 moved to last — depends on 5.4 (saved articles).

## Phase 1: Foundation
| # | Task | Depends On |
|---|------|------------|
| 1.1 | Django project scaffold (settings, DB, apps) | — |
| 1.2 | PostgreSQL setup + pgvector extension | 1.1 |
| 1.3 | Article model + Source model + TopicCluster model + Tab/Category model | 1.2 |
| 1.4 | News scraper worker (Celery + Redis, scrapes India + Global sources) | 1.3 |
| 1.5 | Topic clustering pipeline (AI groups same-story articles) | 1.4 |
| 1.6 | AI summarization pipeline (unified summary per cluster, ~60-80 words) | 1.5 |
| 1.7 | Embedding pipeline (local model → pgvector) | 1.3 |

## Phase 2: Feed & Discovery
| # | Task | Depends On |
|---|------|------------|
| 2.1 | Tab feed API (list clusters by tab: India/JustForYou/Sports/Business/Global) | 1.6, 1.7 |
| 2.2 | Article detail API (summary, sources, related) | 1.6, 1.7 |
| 2.3 | Frontend: Next.js app setup (App Router, Tailwind) | 2.1 |
| 2.4 | Frontend: Tab navigation component (India · Just For You · Sports · Business · Global) | 2.1 |
| 2.5 | Frontend: InShorts-style headline card (title, ~60-word summary, sources, timestamp) | 2.4 |
| 2.6 | Frontend: Tab feed page (infinite scroll, per-tab) | 2.5 |
| 2.7 | "Just For You" personalization (clicks, saves, topic affinity, time of day) | 5.4 |

## Phase 3: Article Detail + Chat
| # | Task | Depends On |
|---|------|------------|
| 3.1 | Chat API (OpenAI integration, per-article threads) | 1.1 |
| 3.2 | Chat context builder (summary + sources as prompt context) | 3.1 |
| 3.3 | Frontend: Article detail page (summary, sources, chat) | 2.2 |
| 3.4 | Frontend: Slide-out chat panel | 3.1, 3.3 |
| 3.5 | Frontend: "Know More" expanded chat view | 3.4 |

## Phase 4: Email Digest
| # | Task | Depends On |
|---|------|------------|
| 4.1 | Email subscriber model + unsubscribe endpoint | 1.1 |
| 4.2 | Daily summary generator (AI-curated top stories across tabs) | 2.1 |
| 4.3 | Email delivery task (Celery, daily, Django SMTP) | 4.2 |
| 4.4 | Frontend: Subscription management | 4.1 |

## Phase 5: Polish (Moved up — Foundation First)
| # | Task | Depends On |
|---|------|------------|
| 5.1 | JWT auth (DRF-simplejwt) + optional accounts | — |
| 5.2 | Redis caching layer | 2.1 |
| 5.3 | Scraper error handling + retries | 1.4 |
| 5.4 | Saved articles (JWT-authenticated users) | 5.1 |
| 5.5 | Monitoring + logging | — |

---
*Execution order: Phase 5 → Phase 3 → Phase 4 → Phase 2.7*
