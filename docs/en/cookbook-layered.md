# Layered Cookbook (CLI / Agent / Service)

Real operator scenarios organized as: goal -> steps -> validation -> pitfalls.

## Scenario 1: First Domain Onboarding (CLI)

Goal: issue cert for site-a and export delivery artifacts.

Steps:

```bash
uv run certman -D data config-validate
uv run certman -D data new --name site-a --verbose
uv run certman -D data export --name site-a
```

Validation:

- data/output/site-a/fullchain.pem exists
- data/output/site-a/privkey.pem exists

Pitfalls:

- Missing account_id-mapped env variables in .env.
- Using prod ACME while still testing.

## Scenario 2: Daily Monitoring without Auto-Fix (CLI)

Goal: alert by exit code only.

```bash
uv run certman -D data check --warn-days 30 --force-renew-days 7
```

Exit codes:

- 0 OK
- 10 warning window
- 20 force-renew window / expired
- 30 missing cert files / entry

## Scenario 3: Unified Job Submission (Service)

Goal: external systems submit jobs only through API.

```bash
uv run certman-server -D data
uv run certman-worker -D data --loop --interval-seconds 15

curl -X POST http://127.0.0.1:8000/api/v1/certificates \
  -H "content-type: application/json" \
  -d '{"entry_name":"site-a"}'

curl http://127.0.0.1:8000/api/v1/jobs/<job_id>
```

Validation: queued -> running -> completed/failed.

## Scenario 4: Avoid Duplicate Renew Queueing (Service)

Goal: no duplicate queued/running renew jobs for same subject.

Operational guidance:

- Submit renew jobs via unique enqueue path in service layer.
- Ensure migration 003 is applied.

Validation:

- At most one queued/running renew job per subject_id.

## Scenario 5: Controlled Node Polling (Agent)

Goal: edge node claims jobs with signed requests.

```bash
uv run certman-agent -D data --once
```

Validation:

- poll returns assignments.
- claimed job is bound to node_id.

## Scenario 6: Signed Result Reporting with Replay Defense (Agent -> Service)

Goal: node reports completed/failed securely.

Key rules:

- Signature covers job_id/status/output/error.
- Nonce is single-use; replay returns 409.
- Only running jobs can be updated.

Validation:

- Final status observable from /api/v1/jobs/{job_id}.

## Scenario 7: Webhook Notifications (Service)

Goal: notify downstream systems on job events.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/webhooks \
  -H "content-type: application/json" \
  -d '{"topic":"job.completed","endpoint":"https://ops.example.com/hook","secret":"topsecret"}'
```

Validation:

- downstream receives signed callback.
- delivery failures visible in service logs.

## Scenario 8: Remote Operations with certmanctl (Service)

Goal: let operators and automation manage the control plane without composing raw curl requests.

Steps:

```bash
uv run certmanctl --endpoint http://127.0.0.1:8000 health
uv run certmanctl --endpoint http://127.0.0.1:8000 cert create --entry-name site-a
uv run certmanctl --endpoint http://127.0.0.1:8000 job wait --job-id <job_id>
uv run certmanctl --endpoint http://127.0.0.1:8000 webhook list
```

Validation:

- `certmanctl` output matches the REST payload semantics.
- operators can complete issue/query/webhook workflows without hand-writing HTTP.

Pitfalls:

- wrong `--endpoint` is a transport problem, not an API business error.
- `job wait` exits only after `completed`, `failed`, or `cancelled`.
