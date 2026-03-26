from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class SecurityError(ValueError):
    pass


@dataclass
class Envelope:
    ephemeral_public_key: str
    nonce: str
    ciphertext: str


def encrypt_envelope(recipient_public_key: x25519.X25519PublicKey, plaintext: bytes) -> Envelope:
    ephemeral_private_key = x25519.X25519PrivateKey.generate()
    shared_secret = ephemeral_private_key.exchange(recipient_public_key)
    aes_key = _derive_key(shared_secret)
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)

    return Envelope(
        ephemeral_public_key=base64.b64encode(
            ephemeral_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).decode("ascii"),
        nonce=base64.b64encode(nonce).decode("ascii"),
        ciphertext=base64.b64encode(ciphertext).decode("ascii"),
    )


def decrypt_envelope(recipient_private_key: x25519.X25519PrivateKey, envelope: Envelope) -> bytes:
    try:
        peer_public_key = x25519.X25519PublicKey.from_public_bytes(base64.b64decode(envelope.ephemeral_public_key))
        nonce = base64.b64decode(envelope.nonce)
        ciphertext = base64.b64decode(envelope.ciphertext)
        shared_secret = recipient_private_key.exchange(peer_public_key)
        aes_key = _derive_key(shared_secret)
        return AESGCM(aes_key).decrypt(nonce, ciphertext, None)
    except (ValueError, InvalidTag) as exc:
        raise SecurityError("failed to decrypt envelope") from exc


def _derive_key(shared_secret: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"certman-envelope",
    ).derive(shared_secret)