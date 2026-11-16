# SteamOS/Linux installation and local validation

These are local maintainer procedures for the **Steam Deck**, initially in Desktop Mode.
Cloud development has not deployed anything to the Deck. No Decky plugin, game modification,
root filesystem unlock, global package install, or legacy uploader replacement is required.

## Install without changing the OS image

Use a user-owned checkout and an already available supported Python 3.11–3.14 with `venv`/pip.
If the image lacks one, obtain a supported user-managed Python using your normal trusted
installation process; do not disable SteamOS filesystem protections for these instructions.

```sh
git clone https://github.com/QuantumPickleJar/EliteDangerous-CrossDeviceJournalSync.git "$HOME/journal-cloud"
cd "$HOME/journal-cloud"
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/journal-cloud --state-dir .journal-cloud/demo init --root tests/fixtures
.venv/bin/journal-cloud --state-dir .journal-cloud/demo scan --no-defaults
.venv/bin/journal-cloud --state-dir .journal-cloud/demo verify
.venv/bin/journal-cloud --state-dir .journal-cloud/demo export .journal-cloud/feed-001 --consumer edexo
.venv/bin/pytest
```

Skip cloning an existing checkout and select the feature branch/draft PR for unreleased tests.
Repeat install and init safely; choose a new export directory on subsequent runs.
Default Linux state normally lives at `~/.local/share/elite-journal-cloud` (or `$XDG_DATA_HOME`).
Keep each machine's state local; do not share a live SQLite database between devices.

## Discovery

Automatic Steam roots include `~/.local/share/Steam`, `~/.steam/steam`, and the Flatpak Steam
user-data location. Journal search inside a library uses:

```text
steamapps/compatdata/359320/pfx/drive_c/users/<proton-user>/Saved Games/Frontier Developments/Elite Dangerous
```

For an SD card or another non-default library, configure the directory that contains
`steamapps`. The following path is synthetic; replace it locally with the library you own:

```sh
.venv/bin/journal-cloud init --library /media/synthetic-library
.venv/bin/journal-cloud scan
.venv/bin/journal-cloud verify
```

Explicit roots are recursive and can point directly at a journal folder or recovered staging
folder. Non-default libraries are configured explicitly; this version does not parse
`libraryfolders.vdf`. Paths used in examples must not be posted with real private device names.

## Deck acceptance procedure

1. Complete the synthetic install/test sequence above. Leave legacy upload tooling running.
2. With the game closed, back up journals locally and copy a selected set to an isolated staging
   folder. Use a fresh `--state-dir`, `init --root <local-staging-folder>`, and `scan --no-defaults`.
3. Compare source and captured hashes locally with `sha256sum`; run `verify`. Confirm no source
   writes. Scan twice and confirm content deduplication and stable device identity.
4. Use a synthetic copy to simulate a growing journal and partial tail. Export before and after
   a new complete line; ensure no partial record appears in the first output.
5. Test automatic discovery separately against the actual Proton library with read-only capture.
   Repeat a scan after the game exits. Keep private data and results on the machine.
6. Follow [Nextcloud setup](nextcloud-setup.md) using a test collection, then validate that the
   Tower can pull the Deck's immutable manifests and verify the same hashes.
7. Validate consumer imports on the **Windows Tower**, independently for EDDiscovery and EDEXO,
   following [migration](migration.md). The Deck does not certify a Windows consumer import.

SteamOS credential storage requires an available, unlocked Secret Service backend. Availability
in Desktop Mode does not establish availability in Gaming Mode or a noninteractive user service.
If absent, the program fails closed for sync and remains usable locally. Do not install plaintext
keyring fallbacks. Verifying credential-vault access in the intended execution session is an
explicit blocker before unattended alpha operation. Scheduling and Gaming Mode integration are
not included in this component's first slice.

The API is optional: `.venv/bin/journal-cloud serve --port 8765` binds loopback only. No Tailscale
installation, network port exposure, or systemd unit is required. User-service scheduling can be
reviewed later after local acceptance; setup must not interrupt existing services.
