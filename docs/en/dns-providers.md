# DNS Provider Usage

This project supports three DNS providers for DNS-01 certificate issuance:

- Aliyun DNS
- Cloudflare DNS
- AWS Route53

All required certbot plugins are managed in [pyproject.toml](../../pyproject.toml) and installed via `uv sync` or `uv add`.

## Common Flow

1. Copy [data/conf/.env.example](../data/conf/.env.example) to `data/conf/.env` and fill in provider secrets.
2. Copy a provider example file under `data/conf/` and rename it to `item_<name>.toml`.
3. Run config validation.
4. Run `new` or `renew`.

Example commands:

```sh
uv run certman config-validate --name <entry-name>
# use --all only when you intentionally want full merged-entry validation
uv run certman config-validate --all
uv run certman entries
uv run certman new --name <entry-name>
uv run certman renew --name <entry-name>
uv run certman renew --all
```

Environment variable lookup uses normalized account_id (trim + uppercase + '-' to '_').

On Windows, `certbot` may require an elevated shell. Prefer:

```sh
gsudo uv run certman new --name <entry-name>
```

## Test Modes And Production Impact

There are three commonly used execution modes in this project:

- `acme_server = "staging"`: test issuance against Let's Encrypt staging
- `acme_server = "prod"`: real issuance against Let's Encrypt production
- `renew --dry-run`: renewal rehearsal against staging

### `acme_server = "staging"`

When global config uses `staging`, `certman new` passes `--test-cert` to certbot.

What it means:

- certbot still performs real DNS-01 validation
- your DNS provider will still create and remove `_acme-challenge` TXT records
- it does not issue a browser-trusted production certificate
- it is suitable for validating credentials, DNS permissions, and workflow correctness

This is not a pure local simulation. It talks to the Let's Encrypt staging environment and touches your real DNS zone.

### `acme_server = "prod"`

When global config uses `prod`, certbot talks to the real Let's Encrypt production environment.

What it means:

- real DNS-01 validation still happens
- a real production certificate is issued on success
- browser and clients will trust the certificate normally
- rate limits and issuance quotas are production limits

Use this only after confirming the staging flow is correct.

### `renew --dry-run`

`uv run certman renew --dry-run --name <entry-name>` is a renewal rehearsal.

What it means:

- certbot still runs the real validation flow against staging
- your DNS provider still creates and removes temporary `_acme-challenge` TXT records
- no production certificate is replaced
- no final renewed certificate is persisted for production use

So `dry-run` is not a fake local mock. It is a safe workflow check that still uses real DNS validation.

## Will Testing Affect Production Domains?

Usually the impact is limited and acceptable, but it is not zero.

What testing does affect:

- it modifies real DNS by adding temporary `_acme-challenge` TXT records
- it appears in DNS provider audit logs or API operation history
- it may conflict with other ACME automation if the same challenge record is being managed elsewhere at the same time

What testing normally does not affect:

- it does not change your normal website records such as `A`, `AAAA`, or `CNAME`
- it does not change your application traffic routing
- it does not replace your current production certificate when using staging or `renew --dry-run`

Recommended practice:

1. Verify provider permissions and config with `staging`
2. Run `renew --dry-run` if you want to validate the renewal path
3. Switch to `prod` only after the staging workflow is stable

## Credential Modes

Each entry supports two modes:

- Ops mode: set `account_id`, then load secrets from `data/conf/.env`
- Portable mode: embed credentials in the item file, optionally via `${ENV_VAR}` references

Ops mode is recommended for normal operations because secrets can be shared across multiple entries.

## Aliyun DNS

Reference template: [data/conf/item_example.example.toml](../data/conf/item_example.example.toml)

Ops mode item example:

```toml
description = "example.com via aliyun"
primary_domain = "example.com"
secondary_domains = ["www.example.com"]
wildcard = true

dns_provider = "aliyun"
account_id = "ALI_EXAMPLE"
```

Required `.env` keys:

```env
CERTMAN_ALIYUN_ALI_EXAMPLE_ACCESS_KEY_ID=<your-access-key-id>
CERTMAN_ALIYUN_ALI_EXAMPLE_ACCESS_KEY_SECRET=<your-access-key-secret>
```

Portable mode item example:

```toml
description = "example.com via aliyun"
primary_domain = "example.com"
dns_provider = "aliyun"

[credentials]
access_key_id = "${ALIYUN_ACCESS_KEY_ID}"
access_key_secret = "${ALIYUN_ACCESS_KEY_SECRET}"
```

Notes:

- `secondary_domains` is optional
- if `wildcard = true`, `*.primary_domain` will be added automatically
- certman writes a runtime credentials file under `data/run/credentials/aliyun_<account>.ini`

## Cloudflare DNS

Reference template: [data/conf/item_cloudflare.example.toml](../data/conf/item_cloudflare.example.toml)

Cloudflare recommends API Token instead of Global API Key.

Recommended token permissions:

- Zone:DNS:Edit
- Zone:Zone:Read

Ops mode item example:

```toml
description = "example.com via cloudflare"
primary_domain = "example.com"
secondary_domains = ["www.example.com"]
wildcard = true

dns_provider = "cloudflare"
account_id = "CF_EXAMPLE"
```

Required `.env` keys:

```env
CERTMAN_CLOUDFLARE_CF_EXAMPLE_API_TOKEN=<your-cloudflare-api-token>
```

Portable mode item example:

```toml
description = "example.com via cloudflare"
primary_domain = "example.com"
dns_provider = "cloudflare"

[credentials]
api_token = "${CLOUDFLARE_API_TOKEN}"
```

Notes:

- certman writes a runtime credentials file under `data/run/credentials/cloudflare_<account>.ini`
- the token must be able to edit DNS records in the target zone

## AWS Route53

Reference template: [data/conf/item_route53.example.toml](../data/conf/item_route53.example.toml)

Minimal IAM capabilities usually required:

- `route53:ListHostedZones`
- `route53:GetChange`
- `route53:ChangeResourceRecordSets`

Ops mode item example:

```toml
description = "example.com via route53"
primary_domain = "example.com"
secondary_domains = ["www.example.com"]
wildcard = true

dns_provider = "route53"
account_id = "AWS_EXAMPLE"
```

Required `.env` keys:

```env
CERTMAN_AWS_AWS_EXAMPLE_ACCESS_KEY_ID=<your-access-key-id>
CERTMAN_AWS_AWS_EXAMPLE_SECRET_ACCESS_KEY=<your-secret-access-key>
CERTMAN_AWS_AWS_EXAMPLE_REGION=us-east-1
```

Portable mode item example:

```toml
description = "example.com via route53"
primary_domain = "example.com"
dns_provider = "route53"

[credentials]
access_key_id = "${AWS_ACCESS_KEY_ID}"
access_key_secret = "${AWS_SECRET_ACCESS_KEY}"
```

Notes:

- if region is omitted in ops mode, current implementation defaults to `us-east-1`
- certman writes a runtime AWS credentials file under `data/run/credentials/route53_<account>.ini`

### Route53 issuance + ACM / k8s delivery

If you issue through Route53 and want to continue with controlled delivery after
renewal, keep DNS credentials and delivery credentials separate:

- `account_id` on the entry can represent the DNS account used by certbot
- each `delivery_targets[]` item can declare its own `account_id`
- each `delivery_targets[]` item can also declare `enabled = true|false`
- a common pattern is:
  - DNS account: manage `_acme-challenge`
  - AWS main account: import into ACM
  - k8s runtime: update the TLS Secret consumed by Traefik / Ingress

For CloudFront consumption, ACM import must target `us-east-1`.

## Validation And Issue/Renew Examples

Validate config before issuing:

```sh
uv run certman config-validate --name mysite

# full validation for all merged entries
uv run certman config-validate --all
```

List merged entries:

```sh
uv run certman entries
```

Issue a new certificate for a single entry:

```sh
uv run certman new --name mysite
```

Issue with verbose certbot output:

```sh
uv run certman new --name mysite --verbose
```

Renew one entry:

```sh
uv run certman renew --name mysite
```

Renew all entries:

```sh
uv run certman renew --all
```

Dry-run renew against staging:

```sh
uv run certman renew --name mysite --dry-run
```

## Related Files

- [README.md](../README.md)
- [data/conf/.env.example](../data/conf/.env.example)
- [data/conf/item_example.example.toml](../data/conf/item_example.example.toml)
- [data/conf/item_cloudflare.example.toml](../data/conf/item_cloudflare.example.toml)
- [data/conf/item_route53.example.toml](../data/conf/item_route53.example.toml)
