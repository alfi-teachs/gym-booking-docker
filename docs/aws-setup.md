# AWS Setup

Region: **ap-south-1**. Replace `<ACCOUNT_ID>`, `<OWNER_ID>` and `<REPO_ID>` with your own values.

---

## 1. ECR repository

**ECR → Create repository**

| Setting | Value |
|---|---|
| Name | `gym-api` |
| Visibility | Private |
| Tag mutability | Mutable (so `latest` can move) |
| Encryption | AES-256 (default) |

### Lifecycle policy

```json
{
  "rulePriority": 1,
  "description": "keep last 30 images",
  "selection": {
    "tagStatus": "any",
    "countType": "imageCountMoreThan",
    "countNumber": 30
  },
  "action": { "type": "expire" }
}
```

Each push creates three ECR entries (index, image, attestation), so 30 keeps roughly the last 10 builds.

---

## 2. GitHub OIDC identity provider

Created once per AWS account (already existed from a previous project):

| Setting | Value |
|---|---|
| Provider URL | `https://token.actions.githubusercontent.com` |
| Audience | `sts.amazonaws.com` |

---

## 3. IAM role — `gym-booking-github-ecr`

### Find the repo ID

GitHub sends the token subject in its **immutable-ID format**, which includes the owner and repo IDs:

```
repo:<owner>@<OWNER_ID>/<repo>@<REPO_ID>:ref:refs/heads/main
```

The repo ID is the first `"id"` at `https://api.github.com/repos/<owner>/<repo>`.

### Trust policy — who can assume the role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:alfi-teachs@<OWNER_ID>/gym-booking-docker@<REPO_ID>:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

Only the `main` branch of this exact repository can assume the role. A deleted and recreated repo with the same name gets a new ID and is rejected.

### Permissions policy — what the role can do

One inline policy, `push-to-ecr`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PushToGymApiRepo",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:ap-south-1:<ACCOUNT_ID>:repository/gym-api"
    }
  ]
}
```

| Statement | Explanation |
|---|---|
| `EcrLogin` | The `docker login` permission. It **must** be `Resource: "*"` — AWS doesn't support scoping `GetAuthorizationToken` to a repository. |
| `PushToGymApiRepo` | The layer-upload sequence: check which layers exist → upload new layers in parts → write the manifest (`PutImage`). Scoped to the one repository. |

### How a push uses these permissions

1. `BatchCheckLayerAvailability` — "which layers do you already have?" (unchanged layers are skipped)
2. `InitiateLayerUpload` → `UploadLayerPart` → `CompleteLayerUpload` — upload each new layer
3. `PutImage` — save the manifest under a tag

---

## Verifying the role

Temporarily add this step after the AWS login to confirm which identity the pipeline has:

```yaml
- run: aws sts get-caller-identity
```

Expected `Arn`: `arn:aws:sts::<ACCOUNT_ID>:assumed-role/gym-booking-github-ecr/GitHubActions`.
