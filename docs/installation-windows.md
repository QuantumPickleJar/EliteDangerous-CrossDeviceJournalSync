# Windows 11 installation and local validation

These are local maintainer procedures for the **Windows Tower**. They have not been executed
on the Tower by cloud development. They install no service and do not stop or replace the legacy
receiver. Start with synthetic data and isolated state/output folders.

## Install and repeat safely

Install Git and a supported Python 3.11–3.14 from their official distributions. For example,
with Python 3.12 available, run PowerShell in a short checkout path:

```powershell
git clone https://github.com/QuantumPickleJar/EliteDangerous-CrossDeviceJournalSync.git C:\src\journal-cloud
Set-Location C:\src\journal-cloud
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$jc = ".\.venv\Scripts\journal-cloud.exe"
& $jc --state-dir C:\JC\synthetic init --root tests\fixtures
& $jc --state-dir C:\JC\synthetic scan --no-defaults
& $jc --state-dir C:\JC\synthetic verify
& $jc --state-dir C:\JC\synthetic status
& $jc --state-dir C:\JC\synthetic export C:\JC\feed-synthetic-001 --consumer eddiscovery
.\.venv\Scripts\pytest.exe
```

Repeating virtual-environment creation/install and `init` preserves configuration/device ID.
Skip `git clone` when the checkout already exists. A repeated export must use a new destination;
never empty a consumer's watched folder as part of setup. Short output paths also avoid legacy
Windows path-length limits in generic exports. Use the feature branch/draft PR checkout when
testing unreleased work; the procedure above clones the default branch.

Without `--state-dir`, Windows state normally lives under
`%LOCALAPPDATA%\elite-journal-cloud`. Confirm the actual platformdirs path locally if managed
profiles redirect it. Keep state on a local filesystem with suitable ACLs, not in the game
folder, OneDrive, or a live shared SQLite directory.

## Discovery and local-only real-machine test

Default discovery checks `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`.
For redirected Saved Games or another Windows profile, add an explicit root:

```powershell
& $jc --state-dir C:\JC\alpha-state init --root "C:\JC\journal-staging"
& $jc --state-dir C:\JC\alpha-state scan --no-defaults
& $jc --state-dir C:\JC\alpha-state verify
& $jc --state-dir C:\JC\alpha-state export C:\JC\feed-alpha-001 --consumer eddiscovery
```

Before that test, make a local backup and copy selected journals into `C:\JC\journal-staging`
with the game closed. Do not share those copies or command output containing private paths.
Check the original and archived SHA-256 values locally using `Get-FileHash`; confirm the source
journals and legacy receiver files were unchanged. Then test default discovery separately by
running `scan` without `--no-defaults`, using a separate state directory and reviewing the scope.
The program works even when Elite Dangerous is not running.

For growing-file validation, use a synthetic staging file: write complete fixture lines followed
by an incomplete JSON tail, scan and export, then finish that tail with LF and scan again.
Confirm the first export excludes the partial event, the second includes it once, and both raw
capture hashes remain in the archive. Do not edit a game-owned journal for this test.

## Optional network and API checks

Follow [Nextcloud setup](nextcloud-setup.md) locally. `credential-set` should store the prompted
app password in Windows Credential Manager. Confirm missing credentials produce a redacted
failure and local scan/verify/export still work. Do not enter credentials in cloud tasks.

Use an isolated test collection and the interrupted-transfer procedure in that guide. Point
EDDiscovery and EDEXO at separate test imports of the selected commander directory as described
in [migration](migration.md). A successful sync is not an import confirmation.

To inspect integration endpoints, run:

```powershell
& $jc --state-dir C:\JC\alpha-state serve --port 8765
```

In a second terminal, request `http://127.0.0.1:8765/v1/status`. Stop the foreground API with
Ctrl+C. No firewall opening, scheduled task, administrator elevation, or existing service
restart is required. A production scheduling/service policy remains an alpha deployment decision.
