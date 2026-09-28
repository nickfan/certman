# Contributing to CertMan

## Before you start

- Use Python 3.12 and `uv`.
- Keep credentials, certificate material, `data/conf/config.toml`, runtime state, and generated outputs out of Git.
- Read the relevant README and existing tests before changing behavior.

Set up the repository with:

```bash
uv sync
```

## Branches and pull requests

Create a focused branch from `master`:

```bash
git switch -c fix/short-description
```

Use `fix/`, `feat/`, `docs/`, or `ci/` prefixes. Keep one logical change per pull request. Explain the behavior changed, migration or operational impact, and the checks you ran. Do not include secrets or private runtime configuration.

## Validation

Run the same checks used by CI before opening a pull request:

```bash
uv lock --check
uv run --frozen pytest
python scripts/release_metadata.py --check-only
```

For container-related changes, also run a local build when Docker is available:

```bash
docker buildx build --platform linux/amd64,linux/arm64 .
```

## Versioning and releases

When a release is intended, update `[project].version` in `pyproject.toml` and keep `uv.lock` synchronized. The version must be greater than the latest `vX.Y.Z` tag. Do not create the tag manually.

After a pull request is merged into `master`, the `release` workflow:

1. tests and resolves release metadata;
2. builds and publishes multi-architecture images to Docker Hub (`nickfan/certman`) and GHCR (`ghcr.io/nickfan/certman`);
3. always publishes `edge` and `sha-<commit>`;
4. publishes `X.Y.Z` and `latest` when the version has no matching `vX.Y.Z` tag;
5. verifies public manifests and creates the Git tag and GitHub Release.

This workflow publishes registry artifacts. It does not deploy CertMan to Kubernetes, Docker Compose, or any other runtime environment. Runtime rollout requires a separate, explicit deployment process.

## Review boundary

Generated agent bundles, local IDE settings, MCP server definitions, identity files, and learning/instinct files do not belong in this repository unless a separate, reviewed project requirement explicitly calls for them.
