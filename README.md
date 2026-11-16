# Elite Companion Suite — Journal Cloud

Cross-device journal capture, immutable archiving, optional Nextcloud synchronization,
and consolidated exports for Elite Dangerous. This repository implements Journal Cloud.
Elite Companion Decky and Elite Companion VR are separate future consumers; neither UI
is included here.

**Status: development vertical slice toward v0.1.0-alpha.1.** The Python package uses the
PEP 440 version `0.1.0a1`. No release or production deployment is implied.

This is an independent community project, not an officially endorsed Frontier
Developments product. Elite Dangerous and related names belong to their respective owners.

## What works

- Windows 11 and SteamOS/Linux discovery, with configurable journal roots and Steam libraries.
- Original-byte SHA-256 objects, device/commander provenance, and repeated growing snapshots.
- Complete newline-terminated events only in exports; partial tails stay in the archive.
- Persistent upload/download jobs, bounded retries, restart recovery, and integrity checks.
- HTTPS Nextcloud WebDAV with device-separated immutable paths and mocked integration tests.
- Deterministic consolidated exports, including EDDiscovery and EDEXO directory adapters.
- JSON CLI status and opt-in versioned, read-only loopback HTTP endpoints.

Local capture, verification, status, and export work without Nextcloud and without the game
running. Successful upload means only that remote bytes were read back and verified. Remote
archive ingestion and EDDiscovery/EDEXO import are separate acknowledgements and remain unknown.

## Developer quick start (synthetic data only)

Python 3.11–3.14 is supported. CI runs the same suite on Windows and Linux for each version.
Create a virtual environment, activate it, and run:

```sh
python -m pip install -e ".[dev]"
journal-cloud --state-dir .journal-cloud/demo init --root tests/fixtures
journal-cloud --state-dir .journal-cloud/demo scan --no-defaults
journal-cloud --state-dir .journal-cloud/demo status
journal-cloud --state-dir .journal-cloud/demo sync
journal-cloud --state-dir .journal-cloud/demo verify
journal-cloud --state-dir .journal-cloud/demo export .journal-cloud/feed-001 --consumer eddiscovery
pytest
ruff check .
ruff format --check .
mypy src
```

`sync` reports `not_configured` in this example. Tests exercise the actual WebDAV adapter
against `httpx.MockTransport`; no network server, account, password, or private journals are
needed. `tests/test_sync.py` includes interrupted-publication and restart recovery procedures.
Use a fresh export destination for every generation; inspect `feed.json` before importing.
`--no-defaults` disables automatic game-directory discovery, including in synthetic examples.

## Installation and operation

- [Windows 11 installation and local validation](docs/installation-windows.md)
- [SteamOS/Linux installation and local validation](docs/installation-steamos.md)
- [Optional Nextcloud setup](docs/nextcloud-setup.md)
- [Architecture and interfaces](docs/architecture.md), [decision records](docs/adr/README.md)
- [Read-only integration API](docs/api.md)
- [Legacy migration and consumer validation](docs/migration.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), [changes](CHANGELOG.md)

`journal-cloud --help` lists `init`, `credential-set`, `scan`, `sync`, `status`, `verify`,
`export`, and `serve`. Use `--state-dir` before the subcommand. Default state comes from
`platformdirs`: local application data on Windows, user data on Linux. Configuration is
nonsecret JSON inside the state directory. `init` preserves the generated device ID and
adds paths idempotently. There is no service installer, autostart, or automatic process restart.

Application passwords are prompted locally with `credential-set` and stored only in a
supported OS credential vault. No password command-line option or plaintext fallback exists.
Do not commit configuration, archives, diagnostic copies, or credentials.

## Known limits before local alpha

Real Nextcloud, Windows credential-vault, SteamOS credential-vault, and consumer-import tests
remain required on the maintainer's machines. Storage currently uses full snapshots, a 128 MiB
snapshot limit, and conservative exact-byte prefix matching. It has no watcher, scheduler,
retention policy, end-to-end encryption, consumer acknowledgement protocol, or legacy receiver
adapter. Feed updates are explicit generation exports; do not point a consumer at growing
archive objects or repeatedly import older generations. Divergence requires human review.

Optional EDDiscovery, EDEXO, Steam/Proton, and Tailscale are installed separately by their users.
No proprietary application files or game assets are redistributed. Tailscale/private HTTP is
an architectural extension point, not a dependency or implemented transport in this slice.

## License

[MIT](LICENSE). Preserve the license and this disclosure in contributions.

### AI Assistance Disclosure

This project is developed with assistance from AI-powered development tools, including OpenAI Codex and ChatGPT.
AI assistance has been involved in at least parts of code generation, debugging, refactoring, documentation, testing and certain slices of architectural planning
AI-assisted contributions are subject to the same review, testing, and quality expectations as human-written code. The project maintainer is responsible for deciding what is accepted into the repository.
This disclosure is provided for transparency and does not change the project's open-source license.
