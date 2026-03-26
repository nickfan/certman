# Layered Operations Manual (CLI / Agent / Service)

This manual focuses on parameters, behavior contracts, state machine semantics, and operational boundaries.

## 1. Responsibility Boundaries

- CLI: human-facing entrypoint for cert lifecycle commands.
- Service: persistent job orchestration, APIs, and webhook delivery.
- Agent: node-side executor talking to control plane via signed messages.

## 2. Global Configuration Parameters

| Parameter | Purpose | Default | Layer |
| --- | --- | --- | --- |
| run_mode | local/agent/server mode | local | all |
| global.data_dir | data root | data | all |
| global.acme_server | staging/prod ACME env | staging | CLI/Service |
| global.email | certbot registration email | admin@example.com | CLI/Service |
| global.letsencrypt_dir | certbot state dir | letsencrypt | CLI/Service |
| server.db_path | control plane DB path | data/run/certman.db | Service/Agent |
| server.listen_host | API listen host | 0.0.0.0 | Service |
| server.listen_port | API listen port | 8000 | Service |
| server.signing_key_path | server Ed25519 private key | null | Service/Agent |
| control_plane.endpoint | control plane base URL | n/a | Agent |
| control_plane.poll_interval_seconds | poll interval seconds | 30 | Agent |
| node_identity.node_id | node unique id | n/a | Agent |
| node_identity.private_key_path | node private key path | n/a | Agent |

## 3. CLI Command Manual

### 3.1 config-validate

```bash
uv run certman -D data config-validate --name site-a

# full merged-entry validation
uv run certman -D data config-validate --all
```

Fails when required provider env vars are missing or run_mode requirements are not met.

### 3.2 new

```bash
uv run certman -D data new --name site-a --force --verbose
```

Parameters:

- --name target entry
- --force force re-issue
- --export/--no-export post-issue export toggle

### 3.3 renew

```bash
uv run certman -D data renew --all --force
```

Parameters:

- --all or --name
- --dry-run staging-only simulation

### 3.4 check

```bash
uv run certman -D data check --warn-days 30 --force-renew-days 7
```

Threshold formulas:

- warning when days_left <= warn_days
- force-renew when days_left <= force_renew_days

### 3.5 export

```bash
uv run certman -D data export --name site-a --overwrite
```

Exports from certbot live path into data/output/<entry>/.

## 4. Service API Manual

### 4.0 Live API documentation

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

These endpoints are exposed directly by `certman-server`.

### 4.1 Certificate APIs

POST /api/v1/certificates

```json
{"entry_name":"site-a"}
```

202 response:

```json
{"success":true,"data":{"job_id":"..."}}
```

GET /api/v1/certificates

- returns recent certificate-related jobs (`issue` + `renew`).

GET /api/v1/certificates/{entry_name}

- returns jobs for one configured entry.

POST /api/v1/certificates/{entry_name}/renew

```json
{"success":true,"data":{"job_id":"...","created":true}}
```

If a queued renew job already exists for the same entry, the existing job is reused and `created=false`.

### 4.2 Job APIs

GET /api/v1/jobs

- supports `subject_id`, `status`, `limit` query filters.

GET /api/v1/jobs/{job_id}

Status enum: queued, running, completed, failed, cancelled.

### 4.3 Webhook APIs

POST /api/v1/webhooks

```json
{"topic":"job.completed","endpoint":"https://ops.example/hook","secret":"topsecret"}
```

GET /api/v1/webhooks

- list subscriptions with optional topic/status filters.

GET /api/v1/webhooks/{subscription_id}

- fetch one subscription.

PUT /api/v1/webhooks/{subscription_id}

- update endpoint, secret, or status.

DELETE /api/v1/webhooks/{subscription_id}

- remove a subscription.

### 4.4 Node registration API

POST /api/v1/nodes/register

- requires a one-time registration token.
- accepts a PEM-encoded Ed25519 public key.
- returns `poll_endpoint` for subsequent agent polling.

## 5. Agent Protocol Manual

### 5.1 poll

POST /api/v1/node-agent/poll fields:

- node_id
- timestamp
- nonce
- agent_version
- signature

Server behavior:

- verifies signature
- stores nonce and rejects replay with 409
- claims next available job and returns signed bundle metadata

### 5.2 result

POST /api/v1/node-agent/result fields:

- node_id, job_id, status(completed|failed)
- output/error
- timestamp, nonce, signature

Constraints:

- only running jobs can transition
- node ownership must match
- signature covers job_id/status/output/error payload

## 6. Remote CLI Manual (`certmanctl`)

Primary commands:

- `certmanctl health`
- `certmanctl cert create|list|get|renew`
- `certmanctl job get|list|wait`
- `certmanctl webhook create|list|get|update|delete`

`certmanctl` is a user-facing wrapper over REST. It is the recommended interface for shell automation that prefers stable command names and exit codes.

## 7. MCP Status

- This repository provides a stdio MCP server via `certman-mcp`.
- Start with `uv run certman-mcp --endpoint http://127.0.0.1:8000` and use it as a tool wrapper over control-plane REST APIs.

## 8. State Machine and Concurrency

- initial state: queued
- claim transition: queued -> running (atomic)
- completion: running -> completed or failed
- renew uniqueness: max one queued/running per subject

## 9. Security Baseline

- nonce TTL: 3600s default, align with retry window
- node clock skew: keep within 60s target
- key rotation: recommend quarterly rotation with migration window

## 10. Production Baseline

- run daily check + alert, keep renew outside alert path
- ensure server and worker share same persistent db_path
- monitor 401/409 ratios on node-agent APIs for drift/replay anomalies
