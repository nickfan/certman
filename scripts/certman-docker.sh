#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE="${CERTMAN_IMAGE:-nickfan/certman:edge}"
DATA_DIR_HOST="${CERTMAN_DATA_DIR_HOST:-${PROJECT_ROOT}/data}"

docker run --rm \
  -v "${DATA_DIR_HOST}:/data" \
  -e CERTMAN_DATA_DIR=/data \
  "${IMAGE}" \
  "$@"