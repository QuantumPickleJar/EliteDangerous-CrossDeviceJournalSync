"""Nonsecret configuration and OS credential-store boundary."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import keyring

from elite_journal_cloud.storage.store import DEVICE, atomic_write


@dataclass
class Config:
    device: str = field(default_factory=lambda: uuid.uuid4().hex)
    roots: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    webdav_url: str | None = None
    username: str | None = None

    @classmethod
    def load(cls, path: Path) -> Config:
        if not path.exists():
            return cls()
        config = cls(**json.loads(path.read_text(encoding="utf-8")))
        if not DEVICE.fullmatch(config.device):
            raise ValueError("invalid device ID")
        return config

    def save(self, path: Path) -> None:
        atomic_write(path, json.dumps(asdict(self), indent=2).encode() + b"\n")


def credential_key(config: Config) -> str:
    if not config.webdav_url or not config.username:
        raise ValueError("configure WebDAV URL and username first")
    # Never use credential contents as an identifier.
    from elite_journal_cloud.journal.snapshot import digest

    return digest((config.webdav_url.rstrip("/") + "\n" + config.username).encode())


def secure_keyring() -> keyring.backend.KeyringBackend:
    backend = keyring.get_keyring()
    module = type(backend).__module__
    if module not in {
        "keyring.backends.Windows",
        "keyring.backends.SecretService",
        "keyring.backends.macOS",
    }:
        raise ValueError("supported OS credential store unavailable; see installation docs")
    return backend


def get_password(config: Config) -> str:
    password = secure_keyring().get_password("elite-journal-cloud", credential_key(config))
    if not password:
        raise ValueError("application credential missing; run credential-set locally")
    return password
