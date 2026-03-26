#!/usr/bin/env bash
set -euo pipefail

TAG="edge"
DOCKERHUB_IMAGE="nickfan/certman"
GHCR_IMAGE="ghcr.io/nickfan/certman"
PUSH="false"
SKIP_BUILD="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      TAG="$2"
      shift 2
      ;;
    --dockerhub-image)
      DOCKERHUB_IMAGE="$2"
      shift 2
      ;;
    --ghcr-image)
      GHCR_IMAGE="$2"
      shift 2
      ;;
    --push)
      PUSH="true"
      shift
      ;;
    --skip-build)
      SKIP_BUILD="true"
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "usage: $0 [--tag <tag>] [--dockerhub-image <repo>] [--ghcr-image <repo>] [--push] [--skip-build]" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DOCKERHUB_REF="${DOCKERHUB_IMAGE}:${TAG}"
GHCR_REF="${GHCR_IMAGE}:${TAG}"

echo "[certman-image] project root: ${PROJECT_ROOT}"
echo "[certman-image] docker hub tag: ${DOCKERHUB_REF}"
echo "[certman-image] ghcr tag: ${GHCR_REF}"

if [[ "${SKIP_BUILD}" != "true" ]]; then
  echo "[certman-image] building image..."
  docker build -t "${DOCKERHUB_REF}" -t "${GHCR_REF}" "${PROJECT_ROOT}"
fi

if [[ "${PUSH}" == "true" ]]; then
  echo "[certman-image] pushing ${DOCKERHUB_REF}"
  docker push "${DOCKERHUB_REF}"

  echo "[certman-image] pushing ${GHCR_REF}"
  docker push "${GHCR_REF}"

  echo "[certman-image] push completed"
else
  echo "[certman-image] build completed (push skipped). use --push to publish."
fi
