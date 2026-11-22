# CI Pipeline — `.github/workflows/build.yml`

```
push to main ──► Build ──► Trivy scan ──► Integration test ──► OIDC login ──► Push to ECR
```

The pipeline was built one step at a time, pushing after each addition, so every step was verified on its own before the next was added.

---

## Triggers and permissions

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  id-token: write
```

| Key | Meaning |
|---|---|
| `push` to `main` | Every push to `main` runs the pipeline. |
| `workflow_dispatch` | Adds a **Run workflow** button for manual runs. |
| `contents: read` | The job can read the repo but not modify it. |
| `id-token: write` | Lets the job request an OIDC token from GitHub. **Required** for the AWS login. |

Top-level keys (`name`, `on`, `permissions`, `env`, `jobs`) start at column 0. Putting `permissions:` in the middle of `on:` makes the file invalid and GitHub silently won't run it.

---

## 1. Checkout

```yaml
- uses: actions/checkout@v4
```

Each run gets a **fresh, empty** Ubuntu VM. Checkout downloads the repo onto it. Without this step, every later step fails with "file not found".

## 2. Build

```yaml
- run: docker build -t "$IMAGE_NAME:${{ github.sha }}" -t "$IMAGE_NAME:latest" ./api
```

- Pulls the base image from Docker Hub and builds on the runner.
- **Two tags, one image:** the commit SHA (immutable, traceable, used for rollback and deployment) and `latest` (a convenience pointer that moves).
- `$IMAGE_NAME` is a **shell variable** — it works because `run:` is executed by bash.
- `${{ github.sha }}` is a **GitHub expression** — substituted before the command runs.

## 3. Trivy vulnerability scan

```yaml
- uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0
  with:
    image-ref: ${{ env.IMAGE_NAME }}:${{ github.sha }}
    format: table
    severity: CRITICAL,HIGH
    ignore-unfixed: true
    exit-code: "1"
```

| Setting | Why |
|---|---|
| Pinned to a **commit SHA** | Tags can be repointed by whoever controls the repo — this happened to trivy-action in March 2026. A SHA can't change. |
| `image-ref: ${{ env.IMAGE_NAME }}` | `with:` values are passed straight to the action, not through a shell, so `$IMAGE_NAME` would arrive as literal text. |
| `severity: CRITICAL,HIGH` | Gate on serious issues; MEDIUM/LOW are noise for a blocking check. |
| `ignore-unfixed: true` | Don't fail on vulnerabilities with no available fix — nothing can be done about them, and a gate that always fails gets disabled. |
| `exit-code: "1"` | Turns the scan into a **gate**: findings fail the pipeline, so the image never reaches ECR. |

## 4. Integration test

```yaml
- run: |
    cp .env.example .env
    docker compose up -d --no-build --wait
    curl -fsS http://localhost:8080/api/health
    curl -fsS http://localhost:8080/api/classes
    curl -fsS -X POST http://localhost:8080/api/bookings ...
- if: failure()
  run: docker compose logs
- if: always()
  run: docker compose down -v
```

| Part | Why |
|---|---|
| `--no-build` | Uses the image that was just built **and scanned**, instead of building a new one. |
| `--wait` | Blocks until containers report healthy. |
| Three `curl` calls | Exercise each layer: Nginx → API → DB connection, a read, and a write. |
| `curl -f` | Exit non-zero on HTTP errors. Without `-f`, a 500 response would still "pass". |
| `if: failure()` | Print container logs only when something broke. |
| `if: always()` | Always clean up, pass or fail. |

## 5. AWS login (OIDC)

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ vars.AWS_ROLE_ARN }}
    aws-region: ${{ vars.AWS_REGION }}
```

GitHub issues a signed token identifying the repo and branch; AWS STS checks it against the role's trust policy and returns credentials valid for one hour. No access keys exist.

## 6. ECR login and push

```yaml
- id: ecr
  uses: aws-actions/amazon-ecr-login@v2

- env:
    REGISTRY: ${{ steps.ecr.outputs.registry }}
    REPOSITORY: ${{ vars.ECR_REPOSITORY }}
  run: |
    for TAG in "${{ github.sha }}" latest; do
      docker tag "$IMAGE_NAME:$TAG" "$REGISTRY/$REPOSITORY:$TAG"
      docker push "$REGISTRY/$REPOSITORY:$TAG"
    done
```

- `id: ecr` names the step so later steps can read its outputs (`steps.ecr.outputs.registry`).
- Docker decides where to push from the image name, so each tag is renamed to the full ECR address first.
- `if: github.event_name != 'pull_request'` on these steps means pull requests are built, scanned and tested but never pushed.

### What appears in ECR

Each push creates three entries: an **image index** (carries the tags), the **image** itself, and a small **attestation** manifest with build provenance, which Docker adds automatically.

---

## Repository variables

Set in **Settings → Secrets and variables → Actions → Variables** — one variable per value:

| Name | Example |
|---|---|
| `AWS_REGION` | `ap-south-1` |
| `AWS_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/gym-booking-github-ecr` |
| `ECR_REPOSITORY` | `gym-api` |

None of these are secrets. The project has no secrets at all — OIDC removed the need for them.
