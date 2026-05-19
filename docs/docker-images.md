# Docker images (slim API vs optional embeddings)

## Two images, one codebase

| Target / ECR repo | Contains | Used by |
|-------------------|----------|---------|
| **`runtime`** → `newspulse-api` | Django, Celery, scrape/cluster/summarize (OpenRouter) | Prod default: `django`, `celery`, `celerybeat` |
| **`embeddings`** → `newspulse-api-embeddings` | runtime + CPU PyTorch + `sentence-transformers` | Optional `celery-embeddings` profile only |

**Production default:** `EMBEDDINGS_ENABLED=false` — no GPU, no CUDA, no local ML models in the main image.

Summaries use **OpenRouter** (HTTP). Local embeddings are optional for vector search experiments.

## Why CUDA appeared in CI logs

Default PyPI `torch` pulls `nvidia-cuda-*` packages. The old Dockerfile installed `sentence-transformers` in the **same** image as Django, so every prod build downloaded ~1GB+ of unused GPU wheels.

**Fix:** `requirements.txt` has no torch/ML stack. The embeddings image installs torch with `pip install --index-url https://download.pytorch.org/whl/cpu` (primary index only — not `--extra-index-url`, which still allows PyPI CUDA wheels on x86), then `sentence-transformers`.

## Local dev

```bash
# Default stack (slim)
docker compose up -d

# Optional embeddings worker
docker compose --profile embeddings up -d celery-embeddings
```

## CI

| Workflow | When | Image |
|----------|------|--------|
| `deploy-ecr.yml` | Every merge to `main` | `newspulse-api` (`target: runtime`) |
| `deploy-ecr-embeddings.yml` | Manual (Actions → Run workflow) | `newspulse-api-embeddings` |

## Prod with embeddings (unusual)

1. Run **Build and push embeddings image to ECR** workflow.
2. In `.env`: `ECR_EMBEDDINGS_IMAGE=...amazonaws.com/newspulse-api-embeddings:latest`
3. `EMBEDDINGS_ENABLED=true` and `docker compose --profile embeddings up -d celery-embeddings`
4. Use `t4g.medium` or larger (4 GiB+ RAM).

Most deployments skip steps 1–4.
