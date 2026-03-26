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
uv run certman -D data config-validate
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

### 4.1 Submit Issue Job

POST /api/v1/certificates

```json
{"entry_name":"site-a"}
```

202 response:

```json
{"success":true,"data":{"job_id":"..."}}
```

### 4.2 Query Job

GET /api/v1/jobs/{job_id}

Status enum: queued, running, completed, failed, cancelled.

### 4.3 Register Webhook

POST /api/v1/webhooks

```json
{"topic":"job.completed","endpoint":"https://ops.example/hook","secret":"topsecret"}
```

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

## 6. State Machine and Concurrency

- initial state: queued
- claim transition: queued -> running (atomic)
- completion: running -> completed or failed
- renew uniqueness: max one queued/running per subject

## 7. Security Baseline

- nonce TTL: 3600s default, align with retry window
- node clock skew: keep within 60s target
- key rotation: recommend quarterly rotation with migration window

## 8. Production Baseline

- run daily check + alert, keep renew outside alert path
- ensure server and worker share same persistent db_path
- monitor 401/409 ratios on node-agent APIs for drift/replay anomalies
