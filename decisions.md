# NewsPulse - Decisions Log

> Trade-offs and rationale. Updated as decisions are made.

## Decisions

| # | Decision | Value | When |
|---|----------|-------|------|
| D1 | Product concept | Shots.in-style aggregator + AI chat per article | 2026-05-05 |
| D2 | Geo scope | India only (Phase 1). No country detection. | 2026-05-06 |
| D3 | News sources | Web scraping only (no RSS). Multiple sources → AI-summarized | 2026-05-06 |
| D4 | Dedup approach | Topic-level clustering (same story = 1 unified article) | 2026-05-06 |
| D5 | Q&A scope | Per-article chat only | 2026-05-05 |
| D6 | LLM provider | OpenAI API | 2026-05-06 |
| D7 | Vector storage | pgvector (PostgreSQL) | 2026-05-06 |
| D8 | Frontend | Next.js (App Router) | 2026-05-06 |
| D9 | Celery broker | Redis | 2026-05-06 |
| D10 | Caching | Redis | 2026-05-06 |
| D11 | Email | Django SMTP | 2026-05-06 |
| D12 | Auth | JWT via DRF | 2026-05-06 |
| D13 | Embedding model | Local (for now) | 2026-05-06 |
