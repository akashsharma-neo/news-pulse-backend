# Article-detail AI chat (Nex)

Per-cluster chat on the article detail page (`/article/{id}`) uses the Django chat API and an OpenAI-compatible LLM (OpenRouter by default). The assistant is branded **Nex** in the UI and system prompt.

## Nex suggested questions

Each `TopicCluster` may include `suggested_prompts`: up to three short, story-specific questions shown when the chat thread is empty. They are generated after summarization (or via backfill) and returned on `GET /api/clusters/{id}/`.

| Field | Type | Notes |
|-------|------|--------|
| `suggested_prompts` | `string[]` | Max 3 items, ~12 words each; answerable from the cluster summary |

**Generation:** [`articles/nex_prompts.py`](../articles/nex_prompts.py) — second lightweight LLM call in `summarize_clusters` (failures fall back to title-aware templates; never fail summarization).

**Backfill existing clusters:**

```bash
python manage.py backfill_cluster_suggestions --dry-run
python manage.py backfill_cluster_suggestions --limit 50
```

**Frontend:** [`SlideOutChatPanel.tsx`](../../news-pulse-frontend/src/components/SlideOutChatPanel.tsx) — empty state shows “Ask Nex” + chips; tap uses the same `POST /api/messages/send/` path as typed input. Generic fallbacks in [`nexPrompts.ts`](../../news-pulse-frontend/src/lib/nexPrompts.ts) when the API returns `[]`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/messages/?cluster_id=<pk>` | List messages for a cluster thread |
| `POST` | `/api/messages/send/` | Send user message, get assistant reply |

### Identifier contract

`cluster_id` is always the **numeric** `TopicCluster` primary key (same as `/api/clusters/{id}/` and the frontend detail URL). Do not send the UUID `topic_id` field.

**Send body:**

```json
{
  "cluster_id": 1,
  "content": "What is this story about?"
}
```

**Send response (201):**

```json
{
  "user_message": { "id": 1, "role": "user", "content": "...", "created_at": "..." },
  "assistant_message": { "id": 2, "role": "assistant", "content": "...", "created_at": "..." }
}
```

## OpenRouter / LLM configuration

Set in `.env` or Docker (see [celery-pipeline.md](./celery-pipeline.md) for the same variables used by summarization):

| Variable | Purpose |
|----------|---------|
| `OPENAI_COMPATIBLE_API_KEY` | OpenRouter key (`sk-or-v1-...`) |
| `OPENAI_COMPATIBLE_BASE_URL` | Default `https://openrouter.ai/api/v1` |
| `OPENAI_COMPATIBLE_MODEL` | Model id on OpenRouter |
| `CHAT_WEB_SEARCH_ENABLED` | Enable OpenRouter `openrouter:web_search` tool (default: `true` when base URL is OpenRouter) |
| `CHAT_WEB_SEARCH_MAX_RESULTS` | Max results per search call (default `5`) |
| `CHAT_WEB_SEARCH_MAX_TOTAL_RESULTS` | Cap total searches per chat turn (default `10`) |
| `CHAT_MAX_TOKENS` | Max assistant reply tokens (default `1024`) |

### Web search

Chat requests attach OpenRouter’s [`openrouter:web_search`](https://openrouter.ai/docs/guides/features/server-tools/web-search) server tool when `CHAT_WEB_SEARCH_ENABLED` is on (auto-enabled for `openrouter.ai` base URLs). The model decides whether to search — e.g. for “what happened since this story?” — rather than searching on every message.

**Cost:** Each search uses OpenRouter credits (~$0.005 per Exa/Parallel search request, plus extra input tokens for result snippets). Questions answered only from the article context usually incur **no** search fee. Set `CHAT_WEB_SEARCH_ENABLED=false` to disable. Local LM Studio / non-OpenRouter backends should leave this off (default when base URL is not OpenRouter).

Restart the Django web container/process after changing env vars.

## Frontend wiring

- [`news-pulse-frontend/src/lib/api.ts`](../../news-pulse-frontend/src/lib/api.ts) — `fetchChatMessages`, `sendChatMessage`
- [`news-pulse-frontend/src/components/SlideOutChatPanel.tsx`](../../news-pulse-frontend/src/components/SlideOutChatPanel.tsx) — loads history on open, posts to `/api/messages/send/`

`NEXT_PUBLIC_API_URL` must point at the Django API (default `http://localhost:8000/api`).

## Verify

1. Ensure at least one cluster exists with a summary (`GET /api/clusters/`).
2. Open `/article/{id}` in the frontend, tap **Ask Nex**.
3. With an empty thread, confirm three suggestion chips; tap one and get a Nex reply.
4. Send a typed question; confirm `POST /api/messages/send/` in the browser network tab.
5. Reply should reference the article context, not a placeholder string.
6. Close and reopen chat; prior messages should load via `GET /api/messages/?cluster_id=` (chips hidden when history exists).

**curl (send):**

```bash
curl -s -X POST http://localhost:8000/api/messages/send/ \
  -H "Content-Type: application/json" \
  -d '{"cluster_id": 1, "content": "Summarize this in one sentence."}'
```

If the API key is missing or invalid, the API returns `500` with `{"error": "Failed to get AI response: ..."}` and the UI shows that message.
