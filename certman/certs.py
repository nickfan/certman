from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import ssl


@dataclass(frozen=True)
class CertStatus:
    not_after: datetime

    @property
    def days_left(self) -> int:
        delta = self.not_after - datetime.now(timezone.utc)
        return int(delta.total_seconds() // 86400)


def read_x509_not_after(cert_pem_path: Path) -> datetime:
    """Read notAfter from a PEM certificate file.

    Uses Python's builtin ssl private API to avoid an external openssl dependency.
    """

    # `_test_decode_cert` expects a filesystem path.
    info = ssl._ssl._test_decode_cert(str(cert_pem_path))  # type: ignore[attr-defined]
    # Example format: 'Jun 10 12:00:00 2026 GMT'
    not_after_str = info["notAfter"]
    not_after = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(
        tzinfo=timezone.utc
    )
    return not_after


def get_cert_status(cert_pem_path: Path) -> CertStatus:
    not_after = read_x509_not_after(cert_pem_path)
    return CertStatus(not_after=not_after)
