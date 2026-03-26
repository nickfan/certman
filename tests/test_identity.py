from __future__ import annotations

from pathlib import Path

import pytest

from certman.security.identity import (
    generate_ed25519_keypair,
    generate_x25519_keypair,
    load_ed25519_public_key,
    load_x25519_public_key,
)


def test_generate_and_load_ed25519_keypair(tmp_path: Path) -> None:
    private_key_path = tmp_path / "node_ed25519.pem"
    public_key_path = tmp_path / "node_ed25519.pub.pem"

    generate_ed25519_keypair(private_key_path, public_key_path)

    assert private_key_path.exists()
    assert public_key_path.exists()
    public_key = load_ed25519_public_key(public_key_path)

    assert public_key is not None


def test_generate_and_load_x25519_keypair(tmp_path: Path) -> None:
    private_key_path = tmp_path / "node_x25519.pem"
    public_key_path = tmp_path / "node_x25519.pub.pem"

    generate_x25519_keypair(private_key_path, public_key_path)

    assert private_key_path.exists()
    assert public_key_path.exists()
    public_key = load_x25519_public_key(public_key_path)

    assert public_key is not None


def test_load_public_key_fails_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_ed25519_public_key(tmp_path / "missing.pem")