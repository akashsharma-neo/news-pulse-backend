# NewsPulse product backlog (NewsMine workspace)

Single source for **product and feature work** on NewsPulse: Django API in `news-pulse-backend/`, Next.js app in `news-pulse-frontend/`. Operational runbooks stay under [`docs/`](README.md).

**Last reviewed:** May 2026

---

## Status legend

| Status | Meaning |
|--------|---------|
| **Done** | Shipped and acceptable for current scope |
| **Partial** | Foundation exists; acceptance criteria not fully met |
| **Pending** | Not started |
| **Deferred** | Explicitly out of scope for now |

---

## At a glance

| # | Item | Status |
|---|------|--------|
| 1 | AI chat end-to-end | Partial |
| 2 | Sort news by recent | Done |
| 3 | Detail-page summary fallback | Done |
| 4 | Images on cards and detail | Done |
| 5 | Search | Done |
| 6 | Three suggested AI questions (Nex) | Done |
| 7 | AI model fallbacks | Pending |
| 8 | Topic subscribe + rolling summaries + timeline | Pending |
| 9 | Digest-first UI | Done |
| 10 | Sharing | Pending |
| 11 | Quicker, smoother chat | Pending |
| 12 | Better scraping (title/body, optional LLM summary) | Partial |
| 13 | More news on detail page | Done |
| 14 | User login and accounts | Done |
| 15 | AI chat rate limits + monthly quotas | Done |
| 16 | Email digest (subscribe UI + prod delivery) | Partial |
| 17 | Save/bookmark + interaction tracking | Pending |
| 18 | Monitoring and structured logging | Pending |
| 19 | Production AWS deployment | Partial |
| 20 | User rate limiting and blocking | Partial |
| 21 | Manual cluster review and approval | Pending |

**Suggested next picks:** #10 (sharing), #17 (save/bookmark), #21 (cluster review), #7 (model fallbacks).

---

## 1. Make AI chat work end-to-end

**Status:** Partial — real API wired; Nex branding and suggestions shipped (#6); polish remains in #11.

**Objective:** User opens chat from a cluster, sends messages, and receives persisted assistant replies.

**Shipped**

- `SlideOutChatPanel` calls `fetchChatMessages` / `sendChatMessage` (no mock replies).
- Numeric cluster PK is the canonical ID for send and list (`cluster_id` in body/query).
- ~~Guest JWT bootstrap in `auth.ts`~~ **Replaced** with device fingerprint + `X-Device-ID` header (no DB user created for guests).
- Chat endpoint now `AllowAny` — both guests and logged-in users can chat without a sign-in UI.
- Backend context builder and OpenAI-compatible client in [`chat/views.py`](../chat/views.py).
- 429 handling: `QuotaExceededError`, `RateLimitedError`, quota badge with color-coded progress bar, upgrade prompt on exhaustion.
- Monthly quota returned in chat response (`quota` field) and via `GET /api/quota/`.

**Still to do**

- Streaming token responses for lower perceived latency.
- Load history on every open without flicker (UX polish in #11).

**Primary files**

- Frontend: [`SlideOutChatPanel.tsx`](../../news-pulse-frontend/src/components/SlideOutChatPanel.tsx), [`api.ts`](../../news-pulse-frontend/src/lib/api.ts), [`auth.ts`](../../news-pulse-frontend/src/lib/auth.ts), [`device.ts`](../../news-pulse-frontend/src/lib/device.ts)
- Backend: [`chat/views.py`](../chat/views.py), [`chat/context_builder.py`](../chat/context_builder.py), [`core/quota.py`](../core/quota.py)

**API contract**

- Send: `POST /api/messages/send/` — `{ "cluster_id": <numeric PK>, "content": "..." }` (no auth required for guests; `X-Device-ID` header for anonymous identity).
- List: `GET /api/messages/?cluster_id=<numeric PK>` (no auth required).
- Quota: `GET /api/quota/` — returns `{ "ai_chat": { "used", "limit", "remaining", "resets_at" } }`.

---

## 2. Sort news by recent

**Status:** Done

**Objective:** Tab feed order matches “most recent” stories.

**Shipped:** Client requests explicit ordering in [`api.ts`](../../news-pulse-frontend/src/lib/api.ts):

```ts
ordering: "-primary_article__published_at"
```

**How to verify:** `GET /api/clusters/?tab=india&ordering=-primary_article__published_at` matches feed order.

---

## 3. One-paragraph summaries on detail pages (not “headings only”)

**Status:** Done — 100–120 word cluster summaries, sentence-boundary fallbacks, full summary on detail.

**Shipped:** Target length in [`worker/article_content.py`](../worker/article_content.py), member-article source gathering, serializer fallbacks, detail UI. Runbook: [`cluster-summaries.md`](cluster-summaries.md).

**Objective:** Detail view always shows readable body copy, not only the headline.

---

## 4. Image per article (shown on cards and detail)

**Status:** Done

**Objective:** Lead image on cards and detail when available.

**Shipped:** `image_url` on clusters, ingestion via [`articles/image_resolver.py`](../articles/image_resolver.py), `StoryImage` on feed and detail. Runbook: [`article-images.md`](article-images.md).

---

## 5. Search for articles or topics

**Status:** Done

**Objective:** User finds clusters (and optionally articles) by keywords.

**Shipped**

- **Postgres FTS** on `Article.full_text` + `title` with `SearchRank` ordering and `SearchHeadline` snippets (`GET /api/search/?q=<query>&tab=<slug>&page=1`).
- **Autocomplete** via `pg_trgm` similarity on `TopicCluster.keywords` (JSON field) and primary article titles (`GET /api/search/suggestions/?q=<query>`).
- **Trending** endpoint returning tab suggestions + most-clicked clusters from last 24h (`GET /api/search/trending/`).
- **Keyword extraction**: frequency-based `extract_keywords()` called during `summarize_clusters` (both single-source fallback and LLM paths), stored in `TopicCluster.keywords` JSONField.
- **pg_trgm GIN indexes**: `idx_topiccluster_keywords_trgm` on `keywords::text`, `idx_article_full_text_trgm` on `full_text`.
- **Frontend**: `SearchBar` component with debounced autocomplete dropdown and trending suggestions; `SearchResults` component with article results; integrated into `TabFeedPage` with feed/search mode toggle.

**API contract**

- Search: `GET /api/search/?q=<query>&tab=<slug>&page=1` → paginated article results.
- Suggestions: `GET /api/search/suggestions/?q=<query>` → up to 10 `{text, type}` items.
- Trending: `GET /api/search/trending/` → up to 10 `{text, type, slug?, cluster_id?}` items.

**Primary files**

- Backend: [`articles/views.py`](../articles/views.py) (search_view, suggestion_view, trending_view), [`articles/serializers.py`](../articles/serializers.py) (SearchResultSerializer, SuggestionSerializer, TrendingSerializer), [`articles/urls.py`](../articles/urls.py) (search endpoints), [`worker/article_content.py`](../worker/article_content.py) (extract_keywords), [`worker/tasks.py`](../worker/tasks.py) (keyword storage)
- Frontend: [`api.ts`](../../news-pulse-frontend/src/lib/api.ts) (fetchSearchResults, fetchSuggestions, fetchTrending), [`SearchBar.tsx`](../../news-pulse-frontend/src/components/SearchBar.tsx), [`SearchResults.tsx`](../../news-pulse-frontend/src/components/SearchResults.tsx), [`TabFeedPage.tsx`](../../news-pulse-frontend/src/components/TabFeedPage.tsx)
- Migrations: `articles/migrations/0007_topiccluster_keywords.py`, `articles/migrations/0008_pg_trgm_search.py`

---

## 6. Three suggested questions for AI (Nex)

**Status:** Done

**Objective:** Chat panel shows three tappable, story-specific prompts when the thread is empty; assistant branded as **Nex**.

**Shipped**

- `TopicCluster.suggested_prompts` generated after summarization; exposed on cluster API.
- [`articles/nex_prompts.py`](../articles/nex_prompts.py) + `backfill_cluster_suggestions` management command.
- [`SlideOutChatPanel.tsx`](../../news-pulse-frontend/src/components/SlideOutChatPanel.tsx), [`NexSuggestionChips.tsx`](../../news-pulse-frontend/src/components/NexSuggestionChips.tsx), detail CTA **Ask Nex**.
- Runbook: [`article-chat.md`](article-chat.md).

**Depends on:** #1 (send path works).

---

## 7. Fallback models and strategy for AI calls

**Status:** Pending

**Objective:** Reliable LLM usage when the primary model errors or is rate-limited (chat + cluster summarization).

**Acceptance criteria**

- Ordered primary + fallback models per use case in settings.
- Retry on 429, 5xx, empty completion before failing the request/task.
- Logs record which model succeeded (no secrets or full prompts).

**Primary files:** [`core/settings.py`](../core/settings.py), [`chat/views.py`](../chat/views.py), [`worker/tasks.py`](../worker/tasks.py)

---

## 8. Topic subscribe, rolling topic summaries, and timelines

**Status:** Pending

**Objective:** Follow a named topic (e.g. “Iran war”) and get a rolling “where things stand” summary plus a dated timeline linking to clusters.

**Acceptance criteria**

- Subscribe/unsubscribe; topic entity with cluster associations.
- Topic page: rolling summary + ordered timeline with cluster links.
- Notifications optional for v1.

**Depends on:** #14 for durable follows across devices.

---

## 9. Digest-first UI (clusters only on primary surfaces)

**Status:** Done

**Objective:** Primary surfaces show **TopicCluster** digests, not raw article rows.

**Shipped:** Tab feed, headline cards, and detail page are cluster-centric; sources are secondary on detail.

---

## 10. Sharing (clusters and detail pages)

**Status:** Pending

**Objective:** Share a story via Web Share API, copy link, or social intents.

**Acceptance criteria**

- Share on detail and/or cards; fallback copy link + toast.
- Stable detail URL (`/article/[numeric cluster id]`).
- Optional: Open Graph / Twitter meta on detail routes.

**Primary files:** [`ArticleDetailPage.tsx`](../../news-pulse-frontend/src/components/ArticleDetailPage.tsx), [`HeadlineCard.tsx`](../../news-pulse-frontend/src/components/HeadlineCard.tsx)

---

## 11. Quicker, smoother AI chat

**Status:** Pending

**Objective:** Chat feels fast and fluid—minimal perceived lag, smooth panel/scroll, resilient errors.

**Acceptance criteria**

- Optimistic UI or clear loading; streaming tokens optional but preferred.
- Smooth open/close and scroll on mobile/desktop.
- Errors do not lose the user’s draft.

**Primary files:** [`SlideOutChatPanel.tsx`](../../news-pulse-frontend/src/components/SlideOutChatPanel.tsx), optionally streaming in [`chat/views.py`](../chat/views.py)

**Depends on:** #1, #7

---

## 12. Better scraping (title and body text, de-emphasize LLM summary)

**Status:** Partial — `clean_article_text`, Hindu paywall handling, and full-body fetch shipped; optional LLM skip not done.

**Shipped:** HTML/boilerplate stripping, The Hindu `prefer_rss_body`, `reclean_article_bodies` command. See [`cluster-summaries.md`](cluster-summaries.md).

**Still to do:** Skip LLM summarization when scraped text alone is sufficient for all sources.

---

## 13. More news on article detail page

**Status:** Done

**Shipped:** Full cluster summary on detail, **More at {source}** link (`primary_url`), **More news** section via `GET /api/clusters/{id}/related/`. Frontend: [`ArticleDetailPage.tsx`](../../news-pulse-frontend/src/components/ArticleDetailPage.tsx).

**Objective:** Detail page shows related/recent clusters so the user is not at a dead end.

---

## 14. User login and accounts

**Status:** Done — email/password with verification, Firebase Google + phone OTP, sign-in UI.

**Objective:** Users sign in so preferences, follows, and history persist across devices.

**Acceptance criteria**

- Sign up / sign in / sign out UI (email+password for v1; document choice).
- Authenticated API where needed; guest browsing for read-only feed.
- Foundation for #8 topic follows and per-user chat history.

**Shipped**

- Backend: register (no JWT until verified), verify-email, resend-verification, login (403 if unverified), `/api/auth/firebase/` for Google/phone. See [`auth.md`](auth.md).
- Frontend: `/login`, `/signup`, `/auth/verify`, `/auth/check-email`, `AuthProvider`, token refresh on chat/quota, header sign-in/out, `UpgradePrompt` → signup.
- Guest browsing unchanged (`X-Device-ID`); no guest→user history merge.

**Follow-ups**

- Password reset / forgot password
- Link phone account to real email from profile

**Primary files:** [`users/`](../users/), [`news-pulse-frontend/src/contexts/AuthContext.tsx`](../../news-pulse-frontend/src/contexts/AuthContext.tsx), [`news-pulse-frontend/src/lib/auth-api.ts`](../../news-pulse-frontend/src/lib/auth-api.ts), [`device.ts`](../../news-pulse-frontend/src/lib/device.ts)

---

## 15. AI chat rate limits + monthly quotas

**Status:** Done

**Objective:** Bound OpenAI cost and abuse; clear feedback when limited. Separate monthly quotas for guests vs logged-in users.

**Shipped**

### Architecture (3 layers)

| Layer | Technology | What |
|---|---|---|
| Caddy (infra) | `rate_limit` directive | 60 req/min per IP general; 10 req/min per IP on chat endpoints |
| DRF Throttles | `ScopedRateThrottle` | `chat_send`: 30/hour per user; burst: 5/min (Redis) |
| Monthly Quotas | Redis + DB | 50/month for guests (Redis only), 200/month for users (Redis + DB dual-write) |

### Guest identity

- **Device fingerprint**: SHA-256 hash of `userAgent + screen + language + timezone + random salt`.
- **Survives localStorage clear**: Salt stored in both `localStorage` and cookie (1-year max-age).
- **No DB user created** for guests — zero database bloat.

### Monthly quota enforcement

- **Atomic**: Redis `INCR`-first pattern (increment → check → undo if over) avoids race conditions.
- **Lazy reset**: First chat of the month checks `quota_reset_at` and resets counter.
- **Redis down**: Fails open (allows requests) with warning log.
- **Test mode**: LocMemCache replaces Redis automatically; quota bypassed.

### Frontend UX

- **Quota badge** in chat header: color-coded progress bar (green ≥50%, yellow 20-50%, red <20%).
- **429 handling**: `QuotaExceededError` / `RateLimitedError` classes.
- **Quota exhausted**: Chat input replaced with upgrade prompt card.
- **Per-request metadata**: `quota` field returned in every chat send response.

### Key files

- Backend: [`core/quota.py`](../core/quota.py) (QuotaManager, RateLimiter), [`chat/views.py`](../chat/views.py), [`users/models.py`](../users/models.py), [`users/quota_views.py`](../users/quota_views.py)
- Frontend: [`device.ts`](../../news-pulse-frontend/src/lib/device.ts), [`api.ts`](../../news-pulse-frontend/src/lib/api.ts), [`auth.ts`](../../news-pulse-frontend/src/lib/auth.ts), [`SlideOutChatPanel.tsx`](../../news-pulse-frontend/src/components/SlideOutChatPanel.tsx), [`UpgradePrompt.tsx`](../../news-pulse-frontend/src/components/UpgradePrompt.tsx)
- Infra: [`deploy/Caddyfile`](../deploy/Caddyfile)

---

## 16. Email digest (subscribe UI + production delivery)

**Status:** Partial — backend API and Celery task exist; no frontend subscription UI; prod SMTP/SES must be configured.

**Objective:** Users subscribe to a daily email of top stories by tab.

**Shipped (backend)**

- `POST /api/digest/subscribe/`, token unsubscribe, staff resend in [`digest/views.py`](../digest/views.py).
- `generate_daily_digest_task` in [`digest/tasks.py`](../digest/tasks.py).

**Still to do**

- Frontend subscription form and confirmation UX.
- Production email (SES/SMTP env on server), Beat schedule for daily send.
- Optional: subscription management page (#14 may share auth patterns).

---

## 17. Save/bookmark + interaction tracking (“Just For You”)

**Status:** Pending — backend personalization engine exists; frontend never records clicks/saves.

**Objective:** Users can save stories; clicks and saves improve the **Just For You** tab.

**Shipped (backend)**

- `POST /api/interactions/` (click, save, dwell) and personalized cluster feed in [`users/views.py`](../users/views.py).
- `just-for-you` tab in seed data and frontend tab list.

**Still to do**

- Record click when opening a cluster from the feed.
- Save/bookmark button on cards or detail; wire to interactions API.
- Ensure Just For You tab calls the personalized endpoint (not generic cluster list).

**Primary files:** [`HeadlineCard.tsx`](../../news-pulse-frontend/src/components/HeadlineCard.tsx), [`ArticleDetailPage.tsx`](../../news-pulse-frontend/src/components/ArticleDetailPage.tsx), [`api.ts`](../../news-pulse-frontend/src/lib/api.ts)

---

## 18. Monitoring and structured logging

**Status:** Pending

**Objective:** Production visibility into API errors, Celery failures, scrape success rates, and LLM failures.

**Acceptance criteria**

- Structured logs (request id, task name, source URL on scrape failure).
- Health checks documented for load balancer / uptime checks.
- Optional: Flower in dev/staging; prod metrics/alerts (CloudWatch or similar) documented in deployment runbook.

**Primary files:** [`core/settings.py`](../core/settings.py), [`worker/tasks.py`](../worker/tasks.py), [`aws-deployment.md`](aws-deployment.md)

**Note:** Celery tasks already use retries (`max_retries`, `default_retry_delay`); this item is about **observability**, not basic retry logic.

---

## 19. Production AWS deployment

**Status:** Partial — compose overlay, Caddy, ECR workflows, and foundation scripts exist; full prod rollout may be incomplete.

**Objective:** NewsPulse runs on AWS (EC2 + Docker Compose + ECR) with TLS, env secrets, and smoke-test checklist.

**Shipped**

- [`docker-compose.prod.yml`](../docker-compose.prod.yml), [`deploy/`](../deploy/), GitHub Actions ECR push workflows.
- Runbook: [`aws-deployment.md`](aws-deployment.md).

**Still to do**

- Complete first prod deploy, DNS (Cloudflare), SES, and post-deploy verification per runbook.
- Frontend `NEXT_PUBLIC_API_URL` and backend `BASE_URL` / CORS for prod domains.

---

## 20. User rate limiting and blocking

**Status:** Partial — rate limits shipped for chat; no staff/admin blocking UI.

**Objective:** Limit abuse and cost across the API, and let operators block bad actors without code deploys.

**Acceptance criteria**

- Documented per-user (and per-device for guests) limits on sensitive routes: chat send, auth (register/login), search (#5), interactions (#17), digest subscribe (#16).
- Staff/admin can suspend or block a user; blocked users get a clear API response (e.g. 403) and the frontend shows an explanatory message.
- Rate-limit responses (429) are consistent and include retry guidance where applicable; frontend handles 429 on each wired surface (extends #15 for chat).
- Optional: higher limits for signed-in users vs guests when #14 ships.

**Shipped**

- **3-layer rate limiting**: Caddy IP (60/m general, 10/m chat) → Redis per-identity (30/h chat, 5/min burst) → DRF throttles (existing anon/user/auth scopes).
- **Guest device tracking**: SHA-256 fingerprint via `X-Device-ID` header; persists across localStorage clears via cookie. No DB user created.
- **Monthly AI chat quotas**: 50/anon, 200/user. Atomic Redis INCR. DB persistence for authenticated users.
- **429 responses**: Consistent format with `code` field (`quota_exceeded`, `rate_limited`) and `quota` metadata.
- **Frontend 429 handling**: `QuotaExceededError` / `RateLimitedError` classes; quota badge with color-coded progress bar; input disabled + upgrade prompt on exhaustion.

**Still to do**

- Staff/admin suspension/block endpoint with 403 response.
- Cross-endpoint rate limit documentation.
- Apply device-based limits to non-chat endpoints (interactions, digest subscribe).

**Primary files:** [`core/quota.py`](../core/quota.py), [`core/settings.py`](../core/settings.py), [`chat/views.py`](../chat/views.py), [`deploy/Caddyfile`](../deploy/Caddyfile), frontend [`api.ts`](../../news-pulse-frontend/src/lib/api.ts), [`device.ts`](../../news-pulse-frontend/src/lib/device.ts)

---

## 21. Manual cluster review and approval

**Status:** Pending — clusters publish automatically after pipeline; no editorial gate.

**Objective:** Humans review auto-clustered stories before they reach the public feed (or to reject bad merges / off-topic groupings).

**Acceptance criteria**

- Review queue for new or updated clusters (Django admin v1 acceptable; dedicated UI optional).
- Actions: approve (publish), reject (hide), optional merge/split or reassign primary article.
- Cluster lifecycle state (e.g. pending → approved / rejected); tab feeds and APIs return only approved clusters by default.
- Audit: reviewer, timestamp, and optional note on reject.
- Optional: staff notification or count of pending reviews.

**Related:** [`cluster-summaries.md`](cluster-summaries.md), [`django-admin-ops.md`](django-admin-ops.md).

**Primary files:** [`articles/`](../articles/) (cluster model + views), worker clustering tasks, [`articles/views.py`](../articles/views.py), feed/detail serializers

---

## Deferred

| Item | Notes |
|------|--------|
| Expanded “Know More” full-screen chat | UI beyond slide-out panel; no implementation |
| Password reset | Forgot-password flow for email accounts |
| Phone ↔ email linking | Add real email to phone-only accounts from profile |

---

## Shipped foundation (reference)

Not actionable backlog items—context for what already exists:

- Django + PostgreSQL + pgvector, Celery scrape → cluster → summarize pipeline
- Tab feed API, cluster detail API, Redis caching, JWT auth API
- Next.js app: tabs, infinite scroll feed, headline cards, detail page, slide-out chat
- Django admin: scrape trigger, model row counts, cluster re-summarize ([`django-admin-ops.md`](django-admin-ops.md))
- Article/cluster images pipeline
- Explicit feed ordering by `published_at`

Design detail and API contracts: [`design.md`](./design.md)
