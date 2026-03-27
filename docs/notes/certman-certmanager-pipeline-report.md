# CertMan + cert-manager Pipeline Report

- 时间: 2026-03-27T06:05:27.994514+00:00
- 模式: certman
- 条目: kumaxiong
- 总计: 3
- 成功: 3
- 失败: 0

## 步骤结果

1. PASS | certman config-validate
1. command: docker compose --profile local-linuxfs run --rm certman-linuxfs config-validate --name kumaxiong
1. returncode: 0

1. PASS | certman new
1. command: docker compose --profile local-linuxfs run --rm certman-linuxfs new --name kumaxiong --no-export
1. returncode: 0

1. PASS | certman renew dry-run
1. command: docker compose --profile local-linuxfs run --rm certman-linuxfs renew --name kumaxiong --dry-run --no-export
1. returncode: 0
