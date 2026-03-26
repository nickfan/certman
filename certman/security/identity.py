from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519


def generate_ed25519_keypair(private_key_path: str | Path, public_key_path: str | Path) -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    _write_private_key(private_key, private_key_path)
    _write_public_key(private_key.public_key(), public_key_path)


def generate_x25519_keypair(private_key_path: str | Path, public_key_path: str | Path) -> None:
    private_key = x25519.X25519PrivateKey.generate()
    _write_private_key(private_key, private_key_path)
    _write_public_key(private_key.public_key(), public_key_path)


def load_ed25519_private_key(path: str | Path) -> ed25519.Ed25519PrivateKey:
    return serialization.load_pem_private_key(_read_bytes(path), password=None)


def load_ed25519_public_key(path: str | Path) -> ed25519.Ed25519PublicKey:
    return serialization.load_pem_public_key(_read_bytes(path))


def load_x25519_private_key(path: str | Path) -> x25519.X25519PrivateKey:
    return serialization.load_pem_private_key(_read_bytes(path), password=None)


def load_x25519_public_key(path: str | Path) -> x25519.X25519PublicKey:
    return serialization.load_pem_public_key(_read_bytes(path))


def _write_private_key(private_key, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _write_public_key(public_key, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def _read_bytes(path: str | Path) -> bytes:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)
    return target.read_bytes()