# GitHub Actions → ECR (dev branch → PR → main)

Images are built in CI, not on EC2. Work on **`dev`**, open a PR to **`main`**, and **merging** that PR triggers a `push` to `main`, which runs the ECR workflow in each repo that changed.

## Branch flow

```text
dev  →  PR to main  →  merge  →  push to main  →  deploy-ecr.yml  →  ECR
```

- Pushes to **`dev`** do **not** build images.
- **`workflow_dispatch`** on `main` lets you rebuild manually (Actions → workflow → Run workflow).

## One-time setup (per GitHub repo)

Do this for **`news-pulse-backend`** and **`news-pulse-frontend`** (Settings → Secrets and variables → Actions).

### 1. AWS ECR repositories

Either run on your laptop:

```bash
cd news-pulse-backend
export AWS_REGION=ap-south-1   # or your region
./deploy/aws-foundation.sh     # creates newspulse-api + newspulse-web among other resources
```

Or let the workflow create the repo on first run (IAM user needs `ecr:CreateRepository`).

### 2. IAM user for GitHub Actions

Create an IAM user (e.g. `github-newspulse-ecr`) with programmatic access. Attach a policy that allows push to your two repos, for example **AmazonEC2ContainerRegistryPowerUser** scoped to:

- `newspulse-api`
- `newspulse-web`

Minimum actions: `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, and optionally `ecr:CreateRepository`, `ecr:DescribeRepositories`.

### 3. GitHub secrets (both repos)

| Secret | Value |
|--------|--------|
| `AWS_ACCESS_KEY_ID` | IAM access key |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key |

### 4. GitHub variables (both repos)

| Variable | Example | Required |
|----------|---------|----------|
| `AWS_REGION` | `ap-south-1` | Optional (default Mumbai) |

**Frontend repo only:**

| Variable | Example |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | `https://api.yourdomain.com/api` |

### 5. Put workflows on `main`

The workflow file must exist on **`main`** before merges will run it.

1. Commit `.github/workflows/deploy-ecr.yml` on `dev`.
2. Open PR `dev` → `main` and merge.
3. That merge triggers the first ECR build (if AWS secrets are set).

## After a successful build

EC2 `.env` should reference `:latest` (see `config/env/prod.deploy.example`):

```bash
ECR_API_IMAGE=<account>.dkr.ecr.<region>.amazonaws.com/newspulse-api:latest
ECR_WEB_IMAGE=<account>.dkr.ecr.<region>.amazonaws.com/newspulse-web:latest
```

Then on the instance:

```bash
cd /opt/newspulse && ./deploy/deploy.sh
```

## Verify

- GitHub → **Actions** → “Build and push … to ECR” → green run on `main`.
- AWS → **ECR** → repository → image tags `latest` and commit SHA.
- Optional: **Actions** → “Deploy to EC2 via SSM” (backend repo) after images exist.

## Troubleshooting

| Failure | Fix |
|---------|-----|
| Workflow does not appear | Merge workflow file to `main` first. |
| `Credentials could not be loaded` | Add `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` secrets. |
| `Set repository variable NEXT_PUBLIC_API_URL` | Frontend repo → Variables → `NEXT_PUBLIC_API_URL`. |
| `pull access denied` on EC2 | EC2 instance IAM role needs ECR pull; run `deploy.sh` after CI succeeds. |
| Build slow / OOM on API image | Normal for torch build; re-run workflow if GitHub runner flakes. |

See also [deploy/README.md](../deploy/README.md) and [aws-deployment.md](aws-deployment.md).
