from __future__ import annotations

import pytest

from certman.security.envelope import SecurityError, decrypt_envelope, encrypt_envelope
from certman.security.identity import (
    generate_x25519_keypair,
    load_x25519_private_key,
    load_x25519_public_key,
)


def test_encrypt_and_decrypt_envelope(tmp_path) -> None:
    private_key_path = tmp_path / "node_x25519.pem"
    public_key_path = tmp_path / "node_x25519.pub.pem"
    generate_x25519_keypair(private_key_path, public_key_path)

    public_key = load_x25519_public_key(public_key_path)
    private_key = load_x25519_private_key(private_key_path)

    envelope = encrypt_envelope(public_key, b"secret-cert-bundle")
    plaintext = decrypt_envelope(private_key, envelope)

    assert plaintext == b"secret-cert-bundle"


def test_decrypt_envelope_rejects_wrong_key(tmp_path) -> None:
    sender_private = tmp_path / "node_a_x25519.pem"
    sender_public = tmp_path / "node_a_x25519.pub.pem"
    receiver_private = tmp_path / "node_b_x25519.pem"
    receiver_public = tmp_path / "node_b_x25519.pub.pem"
    generate_x25519_keypair(sender_private, sender_public)
    generate_x25519_keypair(receiver_private, receiver_public)

    correct_public = load_x25519_public_key(sender_public)
    wrong_private = load_x25519_private_key(receiver_private)

    envelope = encrypt_envelope(correct_public, b"secret-cert-bundle")

    with pytest.raises(SecurityError):
        decrypt_envelope(wrong_private, envelope)


def test_decrypt_envelope_rejects_tampered_ciphertext(tmp_path) -> None:
    private_key_path = tmp_path / "node_x25519.pem"
    public_key_path = tmp_path / "node_x25519.pub.pem"
    generate_x25519_keypair(private_key_path, public_key_path)

    public_key = load_x25519_public_key(public_key_path)
    private_key = load_x25519_private_key(private_key_path)

    envelope = encrypt_envelope(public_key, b"secret-cert-bundle")
    envelope.ciphertext = envelope.ciphertext[:-4] + "AAAA"

    with pytest.raises(SecurityError):
        decrypt_envelope(private_key, envelope)