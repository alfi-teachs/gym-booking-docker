# Troubleshooting

Real problems hit while building this project, how each was diagnosed, and the fix.

The approach throughout: **add one pipeline step at a time and push after each**, so any failure points to exactly one change. And when something fails, **read what the tool actually received** in the logs rather than what the file is assumed to say.

---

## 1. `Unable to resolve action aquasecurity/trivy-action@0.28.0`

**Symptom:** the workflow failed before running any step.

**Cause:** a real supply-chain incident. On 19 March 2026 an attacker with compromised credentials force-pushed almost all `trivy-action` version tags to point at credential-stealing code. During remediation the old tags (0.0.1–0.34.2) were deleted, so `0.28.0` no longer exists. Safe versions are `v0.35.0` and later.

**Fix:** use the current release, **pinned to its commit SHA**:

```yaml
uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0
```

The SHA was looked up with:

```bash
git ls-remote https://github.com/aquasecurity/trivy-action 'refs/tags/v0.36.0*'
```

For an annotated tag, the line ending in `^{}` is the actual commit.

**Lesson:** a tag is a movable label; a commit SHA is immutable. A "verified creator" badge protects against impersonation, not against the real publisher being compromised. SHA-pinned workflows were unaffected by the attack.

Reference: CVE-2026-33634 / GHSA-69fq-xp46-6x23.

---

## 2. `could not parse reference: $IMAGE_NAME:0fecdd1…`

**Symptom:** Trivy failed to find the image.

**Diagnosis:** the error shows the commit SHA *was* substituted but `$IMAGE_NAME` was not — Trivy received the literal string `$IMAGE_NAME`.

**Cause:** `image-ref: "$IMAGE_NAME:${{ github.sha }}"`. Values under `with:` are passed directly to the action; no shell runs, so shell variables aren't expanded. GitHub only substitutes `${{ }}` expressions.

**Fix:** `image-ref: ${{ env.IMAGE_NAME }}:${{ github.sha }}`

| Where | Works |
|---|---|
| inside `run:` | `$IMAGE_NAME` or `${{ env.IMAGE_NAME }}` |
| inside `with:` | `${{ env.IMAGE_NAME }}` only |

---

## 3. Trivy scan failing on every run

**Symptom:** the scan reported 152 OS vulnerabilities and failed.

**Step 1 — outdated packages.** The base image was built before some Debian security fixes. Adding `apt-get upgrade` to the runtime stage moved the image from Debian 13.7 to 13.8 and reduced the count to 124. Still failing.

**Step 2 — read the actual settings.** The raw log showed the environment the action received:

```
INPUT_SEVERITY: CRITICAL,HIGH,MEDIUM
INPUT_IGNORE_UNFIXED: false
```

So the workflow file still gated on **MEDIUM** and on vulnerabilities with **no fix available**. Debian base images almost always contain unfixed MEDIUM issues, so this gate could never pass, whatever was changed in the image.

**Fix:** `severity: CRITICAL,HIGH` and `ignore-unfixed: true`. The scan then passed.

**Lesson:** a security gate must be satisfiable. Gate on what you can act on (fixable, high severity); a gate that always fails gets switched off.

---

## 4. Workflow didn't run at all after a push

**Symptom:** no run appeared in the Actions tab.

**Cause:** the `permissions:` block was pasted inside the `on:` block, so `workflow_dispatch:` ended up under `permissions:`. GitHub rejected the file as invalid.

**Fix:** top-level keys (`name`, `on`, `permissions`, `env`, `jobs`) all start at column 0, each closing the previous block.

---

## 5. `not authorized to perform: ecr:GetAuthorizationToken`

**Symptom:** the ECR login step failed:

```
User: arn:aws:sts::<ACCOUNT_ID>:assumed-role/gym-booking-github-ecr/GitHubActions
is not authorized to perform: ecr:GetAuthorizationToken on resource: *
```

**Diagnosis:** the message names `assumed-role/gym-booking-github-ecr`, which proves the **OIDC trust worked** — the problem was permissions, not authentication.

**Cause:** the push permissions and the login permission had ended up in separate, incomplete policies; the role was missing `GetAuthorizationToken`.

**Fix:** a single inline policy with both statements — `GetAuthorizationToken` on `*` and the push actions on the `gym-api` repository ARN. IAM changes apply immediately, so the failed run was simply re-run.

**Related mistake:** a policy `Sid` containing a space (`"ecr attach"`) is invalid — `Sid` must be alphanumeric.

---

## 6. Three entries in ECR for one push

**Not a bug.** The runner's Docker builds an OCI **image index** (which carries the tags) pointing to the **image** and a small **attestation** manifest with build provenance. The lifecycle policy limit was raised from 10 to 30 because each push now counts as three.

---

## 7. Local development notes

- **Don't keep Docker projects in OneDrive.** Sync conflicts with volumes and build files cause slow builds and file-lock errors.
- **Copying from a `.zip` path** (`…\file.zip\folder`) fails in Git Bash — the archive has to be extracted first:
  ```bash
  powershell -Command "Expand-Archive -Path 'C:\path\file.zip' -DestinationPath 'C:\path' -Force"
  ```
- **Database password in `.env`:** use letters and numbers only. Symbols such as `@` or `/` break the `postgresql://user:pass@host/db` URL.
