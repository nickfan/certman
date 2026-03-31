from __future__ import annotations

import pytest

from certman.config import AppConfig, entry_delivery_targets


def test_entry_delivery_targets_prefers_new_multi_target_config() -> None:
    cfg = AppConfig.model_validate(
        {
            "run_mode": "local",
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "dns_provider": "route53",
                    "account_id": "dns-account",
                    "delivery_targets": [
                        {
                            "type": "aws-acm",
                            "account_id": "main-account",
                            "options": {"regions": ["us-east-1", "us-west-2"]},
                        },
                        {
                            "type": "k8s-ingress",
                            "scope": "kube-system/yqnlink-us-wildcard-tls",
                            "options": {"mode": "apply"},
                        },
                    ],
                }
            ],
        }
    )

    targets = entry_delivery_targets(cfg.entries[0])
    assert len(targets) == 2
    assert targets[0].type == "aws-acm"
    assert targets[1].scope == "kube-system/yqnlink-us-wildcard-tls"


def test_entry_delivery_targets_skips_disabled_targets() -> None:
    cfg = AppConfig.model_validate(
        {
            "run_mode": "local",
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "dns_provider": "route53",
                    "account_id": "dns-account",
                    "delivery_targets": [
                        {
                            "enabled": False,
                            "type": "aws-acm",
                            "account_id": "main-account",
                            "options": {"regions": ["us-east-1"]},
                        },
                        {
                            "enabled": True,
                            "type": "k8s-ingress",
                            "scope": "kube-system/example-tls",
                        },
                    ],
                }
            ],
        }
    )

    targets = entry_delivery_targets(cfg.entries[0])
    assert len(targets) == 1
    assert targets[0].type == "k8s-ingress"


def test_validate_required_secrets_checks_aws_acm_delivery_account() -> None:
    cfg = AppConfig.model_validate(
        {
            "run_mode": "local",
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "dns_provider": "route53",
                    "account_id": "dns-account",
                    "delivery_targets": [
                        {
                            "type": "aws-acm",
                            "account_id": "main-account",
                            "options": {"regions": ["us-east-1"]},
                        }
                    ],
                }
            ],
        }
    )

    env = {
        "CERTMAN_AWS_DNS_ACCOUNT_ACCESS_KEY_ID": "ak",
        "CERTMAN_AWS_DNS_ACCOUNT_SECRET_ACCESS_KEY": "sk",
        "CERTMAN_AWS_DNS_ACCOUNT_REGION": "us-east-1",
    }

    with pytest.raises(ValueError, match="MAIN_ACCOUNT"):
        cfg.validate_required_secrets(env, validate_all=True)
