"""JSON-first command line for offline capture, sync, and consumer exports."""

from __future__ import annotations

import argparse
import getpass
import json
import sqlite3
import sys
from pathlib import Path

from filelock import Timeout
from platformdirs import user_data_path

from elite_journal_cloud import __version__
from elite_journal_cloud.api.server import serve
from elite_journal_cloud.config import Config, credential_key, get_password, secure_keyring
from elite_journal_cloud.feed.adapters import CONSUMERS
from elite_journal_cloud.feed.export import export
from elite_journal_cloud.journal.discovery import discover
from elite_journal_cloud.journal.snapshot import JournalError
from elite_journal_cloud.storage.store import Store
from elite_journal_cloud.sync.engine import SyncEngine
from elite_journal_cloud.sync.webdav import WebDAV


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="journal-cloud")
    cli.add_argument("--version", action="version", version=__version__)
    cli.add_argument("--state-dir", type=Path, default=user_data_path("elite-journal-cloud"))
    commands = cli.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="idempotently create nonsecret configuration")
    init.add_argument("--root", action="append", type=Path, default=[])
    init.add_argument("--library", action="append", type=Path, default=[])
    init.add_argument("--webdav-url")
    init.add_argument("--username")
    commands.add_parser("credential-set", help="store app password in supported OS vault")
    scan = commands.add_parser("scan")
    scan.add_argument(
        "--no-defaults", action="store_true", help="scan configured/explicit roots only"
    )
    scan.add_argument("--root", action="append", type=Path, default=[])
    scan.add_argument("--library", action="append", type=Path, default=[])
    sync = commands.add_parser("sync")
    sync.add_argument("--retry-failed", action="store_true")
    commands.add_parser("status")
    commands.add_parser("verify")
    feed = commands.add_parser("export")
    feed.add_argument("destination", type=Path)
    feed.add_argument("--allow-conflicts", action="store_true")
    feed.add_argument("--consumer", choices=CONSUMERS, default="generic")
    api = commands.add_parser("serve")
    api.add_argument("--port", type=int, default=8765)
    return cli


def execute(args: argparse.Namespace) -> tuple[object, int]:
    root: Path = args.state_dir
    if args.command == "serve":
        serve(root, args.port)
        return {}, 0
    with Store(root) as store:
        path = root / "config.json"
        config = Config.load(path)
        # Persist generated identity before the first capture, even without explicit init.
        if not path.exists():
            config.save(path)
        if args.command == "init":
            config.roots = sorted(set(config.roots + [str(p.resolve()) for p in args.root]))
            config.libraries = sorted(
                set(config.libraries + [str(p.resolve()) for p in args.library])
            )
            if args.webdav_url:
                # Validate URL without ever requesting credentials or opening a connection.
                adapter = WebDAV(args.webdav_url, args.username or config.username or "", "")
                adapter.close()
                config.webdav_url = args.webdav_url
            if args.username:
                config.username = args.username
            config.save(path)
            return {"configured": True, "cloud_configured": bool(config.webdav_url)}, 0
        if args.command == "credential-set":
            key = credential_key(config)
            backend = secure_keyring()
            password = getpass.getpass("Nextcloud application password: ")
            if not password:
                raise ValueError("empty application password")
            backend.set_password("elite-journal-cloud", key, password)
            return {"credential_stored": True}, 0
        if args.command == "scan":
            roots = [Path(p) for p in config.roots] + args.root
            libraries = [Path(p) for p in config.libraries] + args.library
            paths = discover(roots, libraries, defaults=not args.no_defaults)
            accepted, rejected = 0, 0
            for source in paths:
                try:
                    store.ingest(source, config.device)
                    accepted += 1
                except (JournalError, OSError):
                    rejected += 1
            return {"discovered": len(paths), "accepted": accepted, "rejected": rejected}, int(
                rejected > 0
            )
        if args.command == "verify":
            result = store.verify()
            return result, int(not result["ok"])
        if args.command == "export":
            return export(
                store,
                args.destination,
                allow_conflicts=args.allow_conflicts,
                consumer=args.consumer,
            ), 0
        if args.command == "sync":
            if not config.webdav_url or not config.username:
                return {"cloud": "not_configured", **store.status()}, 0
            remote = WebDAV(config.webdav_url, config.username, get_password(config))
            try:
                result = SyncEngine(store, remote).run(retry_failed=args.retry_failed)
            finally:
                remote.close()
            states = result["current_endpoint_transfers"]
            if not isinstance(states, dict):
                raise ValueError("invalid internal transfer state")
            failed = bool(result["discovery_error"] or states.get("retry") or states.get("failed"))
            return result, int(failed)
        return {"cloud_configured": bool(config.webdav_url), **store.status()}, 0


def main() -> None:
    args = parser().parse_args()
    try:
        result, code = execute(args)
    except JournalError as exc:
        result, code = {"error": "journal_validation_failed", "reason": str(exc)}, 1
    except Timeout:
        result, code = {"error": "archive_busy", "hint": "retry after the current worker exits"}, 1
    except (ValueError, OSError, sqlite3.Error):
        result, code = (
            {"error": "operation_failed", "hint": "check configuration, integrity and docs"},
            1,
        )
    except Exception:
        # Credential backend errors can contain service addresses or credential values.
        result, code = {"error": "operation_failed", "hint": "credential or runtime failure"}, 1
    print(json.dumps(result, sort_keys=True))
    sys.exit(code)
