# Automated releases

CertMan publishes containers from the `master` branch through GitHub Actions.
Maintainers only need to update the project version in `pyproject.toml` and keep
`uv.lock` in sync.

## Release behavior

Every pull request to `master` runs:

- `uv lock --check`
- the complete pytest suite
- release version validation
- an AMD64 and ARM64 container build without publishing

Every push to `master` that passes validation publishes:

- `nickfan/certman:edge`
- `ghcr.io/nickfan/certman:edge`
- an immutable `sha-<commit>` tag in both registries

If `pyproject.toml` contains a version without a corresponding `vX.Y.Z` git
tag, the same workflow additionally publishes `X.Y.Z` and `latest` in both
registries, verifies that all manifests are anonymously pullable, and then
creates the `vX.Y.Z` tag and GitHub Release.

The release workflow never publishes a version lower than the highest existing
semantic-version tag. A failed image publication does not create a git tag or
GitHub Release, so rerunning the workflow is safe.

## Required repository configuration

GitHub repository settings:

- Actions: enabled
- Workflow token: workflow-level permissions are declared in YAML
- GHCR package `certman`: Public visibility

Actions repository secrets:

| Secret | Required | Purpose |
| --- | --- | --- |
| `DOCKERHUB_USERNAME` | Yes | Docker Hub account that owns `nickfan/certman` |
| `DOCKERHUB_TOKEN` | Yes | Docker Hub access token with Read & Write permission |
| `RELEASE_WEBHOOK_URL` | No | HTTPS endpoint notified after a version release |
| `RELEASE_WEBHOOK_SECRET` | No | HMAC-SHA256 signing key for webhook payloads |

GHCR uses the short-lived GitHub-provided `GITHUB_TOKEN`; no custom GHCR token
is stored.

Secrets belong in GitHub **Settings → Secrets and variables → Actions**. Do not
put them in `.env`, repository variables, workflow YAML, or committed files.

## Version release procedure

1. Update `[project].version` in `pyproject.toml`.
2. Run `uv lock`.
3. Commit the version and application changes in the same pull request.
4. Merge the pull request after CI succeeds.

The merge starts the release. Do not create the git tag manually.

## Release webhook

The webhook is optional and is not needed to trigger GitHub Actions. When both
webhook secrets are configured, the release job sends a JSON payload after the
GitHub Release is created. It includes the repository, version, tag, commit,
release URL, image digest, and both image references.

Validate the `X-CertMan-Signature-256` header by calculating:

```text
sha256=HMAC_SHA256(RELEASE_WEBHOOK_SECRET, raw_request_body)
```

The event name is sent in `X-CertMan-Event: release.published`.

## Recovery

- If tests or image publication fail, fix the cause and rerun the workflow.
- If public manifest verification fails for GHCR, set the package visibility to
  Public and rerun the workflow.
- If Docker Hub login fails, rotate `DOCKERHUB_TOKEN` and update only the
  repository secret.
- If a version tag already exists, bump the version instead of overwriting the
  released tag.
