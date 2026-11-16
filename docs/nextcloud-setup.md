# Optional Nextcloud WebDAV

Do this only on a maintainer-owned Windows Tower or Steam Deck, after synthetic/local checks.
No Nextcloud credentials are needed for development or CI, and none should be sent to Codex,
issues, PRs, logs, or diagnostic exports. A single-machine archive needs no cloud configuration.

## Prepare an isolated collection

Use an HTTPS Nextcloud installation with a valid certificate and a dedicated pre-created
collection such as `JournalCloud-Test`. Copy the collection's WebDAV URL from Nextcloud's
Files settings and append the collection name. A typical shape is:

```text
https://cloud.example.invalid/remote.php/dav/files/synthetic-user/JournalCloud-Test
```

This is a reserved synthetic hostname and username, not a working server. The configured
collection must already exist. Journal Cloud creates only its relative `v1` directories.
Do not reuse a legacy receiver directory or the Nextcloud root for first validation.

Create a revocable application password locally in Nextcloud. Use a dedicated account/share
with the narrowest practical access; actual credential scope depends on server configuration.
Every device using this collection is a trusted writer. This version has no per-device signatures.

On each machine, run against its separate state directory (substitute the real URL/user locally):

```sh
journal-cloud init --webdav-url https://cloud.example.invalid/remote.php/dav/files/synthetic-user/JournalCloud-Test --username synthetic-user
journal-cloud credential-set
journal-cloud sync
journal-cloud status
journal-cloud verify
```

The password prompt is hidden and stored through the OS vault. Do not embed a password in the
URL, command line, environment files, shell script, or JSON config. Unknown/plaintext/chained
keyring backends are rejected. On SteamOS, check that an unlocked Secret Service is available
in the intended session. Windows uses Credential Manager. `init` changes configuration without
replacing the device ID, running sync, stopping services, or installing a scheduler.

## Verification and restart procedure

Run on the **Steam Deck** first using only synthetic staging journals and a test collection:

1. Scan synthetic fixtures with `scan --root <synthetic-folder> --no-defaults`. Run `sync`.
2. Inspect device-separated `v1/devices/<device-id>/objects` and `manifests` locally. Compare
   remote bytes/hash with local `verify`; `transport_verified` means read-back verification only.
3. On the **Windows Tower**, use another fresh state/ID and the same test collection. Run sync
   then verify. Confirm `ingested` download state and an identical deterministic export.
4. On the **Deck**, disable its network using normal local controls, add a synthetic complete
   event, scan and sync. Confirm a persistent `retry` job with a fixed `network_error` code.
5. Close the foreground sync process, restart it, and restore connectivity. Respect recorded
   backoff (2 seconds after first failed attempt, doubling up to one hour). Confirm eventual
   transport verification and then separately confirm Tower ingestion.
6. In the test collection only, interrupt a larger synthetic transfer before manifest publication
   (Ctrl+C or normal process termination). Restart sync. It must reuse verified identical remote
   bytes, publish a manifest only after the object is verified, and never create duplicate feed
   events. `tests/test_sync.py` automates the equivalent failure after object publication.
7. Confirm a missing/wrong/revoked application credential fails without revealing values. After
   fixing it locally, `sync --retry-failed` resets terminal jobs for the current endpoint.

The offline fixture tests are authoritative regression checks; real server testing validates
Nextcloud versions, permissions, proxy behavior, TLS, MKCOL, PROPFIND Depth 1, and conditional
PUT semantics. Redirects are deliberately not followed: configure the final canonical HTTPS
collection URL. Existing remote content is never overwritten on a hash mismatch.

`sync` is one-shot, not a daemon. New remote publications made during a command may be found on
the next invocation. Exit 1 indicates a discovery error or retry/failed jobs for the current
endpoint; status also retains historical jobs for previous endpoints. Discovery errors are
separate from durable transfer failures. Upload acknowledgements cannot prove the legacy
receiver, another archive, EDDiscovery, or EDEXO imported anything.

Keep server versioning/backups and device backups according to local policy. No remote delete,
retention cleanup, filename reuse, or proprietary consumer software is managed by this service.
