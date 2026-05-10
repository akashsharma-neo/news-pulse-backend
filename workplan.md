# NewsPulse - Workplan

> **Strategy:** Foundation-first. Phase 5 → Phase 3 → Phase 4 → Phase 2.7

## Status Legend

| Badge | Meaning |
|-------|---------|
| ✅ Done | Completed |
| 🔄 In Progress | Actively being worked on |
| ⏳ Pending | Queued, next up |
| 🚫 Blocked | Waiting on something |
| 📋 Deferred | Low priority / future |

---

## Phase 1: Foundation

| # | Task | Depends On | Status | Notes |
|---|------|------------|--------|-------|
| 1.1 | Django project scaffold (settings, DB, apps) | — | ✅ Done | — |
| 1.2 | PostgreSQL setup + pgvector extension | 1.1 | ✅ Done | — |
| 1.3 | Article, Source, TopicCluster, Tab models | 1.2 | ✅ Done | — |
| 1.4 | News scraper worker (Celery + Redis) | 1.3 | ✅ Done | Scrapes India + Global sources |
| 1.5 | Topic clustering pipeline (AI groups same-story) | 1.4 | ✅ Done | — |
| 1.6 | AI summarization pipeline (~60-80 words per cluster) | 1.5 | ✅ Done | — |
| 1.7 | Embedding pipeline (local model → pgvector) | 1.3 | ✅ Done | — |

---

## Phase 2: Feed & Discovery

| # | Task | Depends On | Status | Notes |
|---|------|------------|--------|-------|
| 2.1 | Tab feed API (list clusters by tab) | 1.6, 1.7 | ✅ Done | India / Just For You / Sports / Business / Global |
| 2.2 | Article detail API (summary, sources, related) | 1.6, 1.7 | ✅ Done | — |
| 2.3 | Frontend: Next.js app setup | 2.1 | ✅ Done | App Router, Tailwind, TypeScript, Dockerfile |
| 2.4 | Frontend: Tab navigation component | 2.1 | ✅ Done | Scrollable pill tabs with API fetch + fallback |
| 2.5 | Frontend: InShorts-style headline card | 2.4 | ✅ Done | Title, summary, sources, timestamp |
| 2.6 | Frontend: Tab feed page (infinite scroll) | 2.5 | ✅ Done | Per-tab, IntersectionObserver, 20/page |
| 2.7 | "Just For You" personalization engine | 5.4 | ✅ Done | Clicks, saves, topic affinity, time-of-day decay |

---

## Phase 3: Article Detail + Chat

| # | Task | Depends On | Status | Notes |
|---|------|------------|--------|-------|
| 3.1 | Chat API (`POST /api/chat/<cluster_id>/messages/`) | 1.1 | ✅ Done | OpenAI integration, per-article threads |
| 3.2 | Chat context builder (summary + sources as context) | 3.1 | ⏳ Pending | Grounds responses in facts |
| 3.3 | Frontend: Article detail page | 2.2 | ✅ Done | Summary, sources, chat CTA |
| 3.4 | Frontend: Slide-out chat panel | 3.1, 3.3 | 🔄 In Progress | UI complete, API mocked (simulated responses) |
| 3.5 | Frontend: "Know More" expanded chat view | 3.4 | 📋 Deferred | No implementation found |

---

## Phase 4: Email Digest

| # | Task | Depends On | Status | Notes |
|---|------|------------|--------|-------|
| 4.1 | Email subscriber model + unsubscribe endpoint | 1.1 | 🚫 Blocked | digest/ app is stub only (no views/urls/migrations). Will crash at runtime (ImportError from core/urls.py). |
| 4.2 | Daily summary generator (AI-curated top stories) | 2.1 | 🚫 Blocked | digest/ app is stub only. No implementation. |
| 4.3 | Email delivery task (Celery, daily, Django SMTP) | 4.2 | 🚫 Blocked | digest/ app is stub only. No SMTP config or email deps. |
| 4.4 | Frontend: Subscription management | 4.1 | 📋 Deferred | No implementation found |

---

## Phase 5: Polish & Core

| # | Task | Depends On | Status | Notes |
|---|------|------------|--------|-------|
| 5.1 | JWT auth (DRF-simplejwt) + optional accounts | — | ✅ Done | — |
| 5.2 | Redis caching layer | 2.1 | ✅ Done | CacheManager integrated into TopicClusterViewSet |
| 5.3 | Scraper error handling + retries | 1.4 | ⏳ Pending | — |
| 5.4 | Saved articles (JWT-authenticated users) | 5.1 | ✅ Done | **CRITICAL: Gates 2.7 personalization** |
| 5.5 | Monitoring + logging | — | ⏳ Pending | — |
| 5.6 | OTP phone login | — | 📋 Deferred | — |
| 5.7 | Google OAuth login | — | 📋 Deferred | — |

---

## Execution Order

```
Phase 1 → Phase 2 → Phase 5 → Phase 3 → Phase 4 → Phase 2.7
```

**Next up:**
1. 3.4 — Wire up slide-out chat panel to real backend API
2. 3.2 — Chat context builder
3. 5.3 — Scraper error handling + retries
4. Fix digest/ app — either implement or remove from INSTALLED_APPS + urls.py (currently crashes at startup)
5. 5.5 — Monitoring + logging

---

## Design Reference

Detailed "how-to" for each feature, API contracts, data models, and trade-offs are in [design.md](design.md).
