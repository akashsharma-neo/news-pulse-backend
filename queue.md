# NewsPulse - Task Queue

> **Strategy:** Foundation-first. We complete all unblocking tasks in Phase 5 before moving into high-level features (Phase 3/4) and finally the complex personalization engine (Phase 2.7).

## ✅ COMPLETED
**5.1** JWT auth (DRF-simplejwt) + optional accounts.
> *Foundation — gates 5.4 (saved articles) and needed for 2.7 (personalization)*

---

## 🚀 NEXT UP (Unblocking Foundation & Cores)
*These tasks must be finished to unblock the personalization engine and stabilize infrastructure.*

**5.2** Redis caching layer — Cache feed responses, cluster data.
→ **Status: done ✅**
> *Implemented CacheManager and integrated into TopicClusterViewSet*

**5.4** Saved articles — JWT-authenticated users can save clusters.
→ **Status: done ✅**
> *CRITICAL: Gates 2.7 personalization engine*

---

## 🛠️ FEATURE DEVELOPMENT (Phase 3 & 4)
*Core user-facing features that rely on the foundation being stable.*

### Phase 3: Article Detail + Chat
**3.1** Chat API — `POST /api/chat/<cluster_id>/messages/` stores user message, returns OpenAI response.
→ **Status: done ✅**

**3.2** Chat context builder — Builds prompt from cluster summary + source links + conversation history.
→ **CRITICAL: Grounds responses.**

**3.3** Article detail page — Full summary, sources section, slide-out chat panel.
→ **Status: done ✅**

**3.4** Slide-out chat panel — Inline chat on article detail page.
→ **Status: done ✅

**3.5** "Know More" expanded chat view — Full-screen chat interface with article context sidebar.
→ **Status: to be reviewed**

### Phase 4: Email Digest
**4.1** Email subscriber model + unsubscribe endpoint.
→ **Status: to be reviewed**

**4.2** Daily summary generator — AI-curated top stories across all tabs + generated summary.
→ **Status: to be reviewed**

**4.3** Email delivery — Scheduled Celery task, runs daily, sends digest via Django SMTP.
→ **Status: to be reviewed**

**4.4** Frontend: Subscription management.
→ **Status: to be reviewed**

---

## 🎯 INTEGRATION & PERSONALIZATION (The Final Layer)
*Deeply integrated features that depend on everything else being done.*

### Phase 2.7: "Just For You" Personalization
**2.7** Personalization Engine — Tracks clicks, saves, topic affinity, time of [recency] decay. Ranks feed items accordingly.
→ **Status: done ✅**
> *DEPENDS ON: 5.4 (Saved articles)*

---

## 📋 BACKLOG / DEFERRED
**5.6** OTP phone login — Phone verification flow, OTP rate limiting, token auth backend.
**5.7** Google OAuth login — OAuth2 client, callback view, account linking.
