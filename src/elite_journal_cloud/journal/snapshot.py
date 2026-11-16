"""Byte-preserving journal validation and identity, independent of source paths."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024


class JournalError(ValueError):
    """Invalid input; messages intentionally omit event contents."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def reject_constant(value: str) -> None:
    raise JournalError("non-finite JSON number")


@dataclass(frozen=True)
class Snapshot:
    raw: bytes
    complete: bytes
    events: tuple[dict[str, Any], ...]
    session: str
    commanders: tuple[str, ...]
    timestamp: str

    @property
    def raw_hash(self) -> str:
        return digest(self.raw)

    @property
    def complete_hash(self) -> str:
        return digest(self.complete)


def validate(raw: bytes) -> Snapshot:
    """Retain a trailing partial record, but never parse or publish it."""
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise JournalError("snapshot exceeds size limit")
    complete = raw[: raw.rfind(b"\n") + 1]
    events: list[dict[str, Any]] = []
    commanders: set[str] = set()
    try:
        for number, line in enumerate(complete.splitlines(), 1):
            value = json.loads(
                line.decode("utf-8-sig" if number == 1 else "utf-8"), parse_constant=reject_constant
            )
            if not isinstance(value, dict) or not isinstance(value.get("event"), str):
                raise JournalError("record must be a JSON event object")
            stamp = value.get("timestamp")
            if not isinstance(stamp, str):
                raise JournalError("event timestamp missing")
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise JournalError("event timestamp must include timezone")
            if value["event"] in {"Commander", "LoadGame"}:
                commander = value.get("FID") or value.get("Name") or value.get("Commander")
                if isinstance(commander, str) and commander:
                    commanders.add(commander)
            events.append(value)
    except (UnicodeError, ValueError, RecursionError):
        raise JournalError("invalid complete journal record") from None
    if not events or events[0]["event"] != "Fileheader":
        raise JournalError("first complete event must be Fileheader")
    # Full header includes timestamp and part; it is stable as the journal grows.
    session = digest(canonical(events[0]))
    return Snapshot(
        raw,
        complete,
        tuple(events),
        session,
        tuple(sorted(commanders)),
        str(events[0]["timestamp"]),
    )
