"""Discover journals without opening or modifying game files."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

GAME_ID = "359320"
JOURNAL_DIR = Path("Saved Games") / "Frontier Developments" / "Elite Dangerous"


def discover(
    roots: Iterable[Path] = (),
    libraries: Iterable[Path] = (),
    home: Path | None = None,
    *,
    defaults: bool = True,
) -> list[Path]:
    """Explicit roots are recursive; libraries point at folders containing steamapps.

    Steam libraryfolders.vdf parsing is deliberately unnecessary: callers may configure
    any library or a complete Proton prefix explicitly.
    """
    home = home or Path.home()
    candidates = ([home / JOURNAL_DIR] if defaults else []) + list(roots)
    steam_roots = (
        [
            home / ".local/share/Steam",
            home / ".steam/steam",
            home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        ]
        if defaults
        else []
    ) + list(libraries)
    for library in steam_roots:
        users = library / "steamapps/compatdata" / GAME_ID / "pfx/drive_c/users"
        if users.is_dir():
            candidates.extend(user / JOURNAL_DIR for user in users.iterdir() if user.is_dir())
    found: set[Path] = set()
    for root in candidates:
        if root.is_file() and root.name.lower().startswith("journal."):
            found.add(root.resolve())
        elif root.is_dir():
            found.update(p.resolve() for p in root.rglob("Journal.*.log") if p.is_file())
    return sorted(found, key=str)
