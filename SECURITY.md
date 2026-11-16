# Security policy

This is an unreleased development slice, with no production support guarantee. Report a
sensitive finding through the repository's private security reporting facility if available.
If private reporting is unavailable, ask the maintainer for a private channel without including
exploit details or private data in a public issue. No unverified security email is published here.

## Boundaries

- Game journals are opened read-only. Archives and exported journals remain private data.
- Source contents are preserved, not scrubbed. Commander metadata exists in manifests and
  SQLite even though API responses omit identifiers and HTTP logging is disabled.
- SHA-256 detects corruption and content identity; it does not authenticate a device. Devices
  sharing a Nextcloud account/collection are trusted writers. A compromised account can inject
  internally consistent synthetic history. No signatures or end-to-end encryption exist yet.
- WebDAV requires HTTPS with certificate verification, timeouts, bounded response bodies,
  disabled redirects, restricted device/path components, and hardened XML parsing.
- Application passwords are accepted only by a local hidden prompt and stored using Windows
  Credential Manager, Linux Secret Service, or the supported macOS backend. Plaintext, chained,
  and unknown keyring backends are rejected. A Linux session with no unlocked Secret Service
  can still capture and export locally, but cannot sync with this credential workflow.
- Config, queue, objects, and exports contain no stored password. Configuration can still
  reveal account names and server locations. Error reports contain fixed codes; do not turn
  on verbose third-party HTTP logging while using credentials.
- The API binds only to `127.0.0.1`, rejects foreign Host and Origin headers, does not enable
  CORS, and implements GET only. It has no authentication for other local processes. Do not
  forward it over a network or expose it through Tailscale without a separate security design.
- Protect state/export directories with OS access controls and disk encryption. New state
  directories request mode 0700 on POSIX; existing directories and Windows ACLs are inherited.
  The application does not encrypt archives or configure your ACLs automatically.

Do not submit configuration files, real journals, credential vault exports, raw HTTP traces,
or an entire state directory as diagnostics. Share only reviewed synthetic reproductions and
redacted CLI status/error codes. There is intentionally no bulk diagnostic-export feature.

## Operational safety

Objects are written through temporary files, fsynced, and atomically replaced under an archive
writer lock. SQLite uses WAL and FULL synchronous mode. This supports process interruption;
power-loss durability depends on the filesystem, disk, OS, and backup policy. Objects can be
orphaned by interrupted ingestion and are retained. There is no garbage collector. Keep backups
of the complete stopped state directory, not just SQLite while WAL writes are active.

`verify` detects corruption; it does not repair or overwrite immutable objects. Stop using a
failed archive, keep a copy, and restore from a separately verified backup. A failed transfer
can be explicitly retried with `sync --retry-failed` after resolving its cause. Never infer
consumer import from upload success.
