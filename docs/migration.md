# Legacy migration and consumer compatibility

The legacy Windows Tower receiver works in the maintainer's private environment. Its code and
archive are unavailable here. This repository does not import its database, assume its path
layout, replace its receiver, or deploy to either machine. Begin with parallel, isolated local
validation and leave existing services intact.

## Recovery evidence and unresolved accounting

A prior manual recovery established these observations:

| Consumer/evidence | Observed result |
| --- | --- |
| EDEXO | 25 consolidated journals recognized |
| EDDiscovery | 36 recovered ScanOrganic events imported |
| Completed analyses | Nine restored |
| EDEXO pending entries | 129,227,500 CR across eight entries |
| Separate census comparison | 17-event discrepancy remains unresolved |

These are compatibility requirements for preserving the original recovery history, not expected
constants for arbitrary input, algorithm targets, or fixture data. Tests use unrelated synthetic
history. Do not fabricate events, delete sales/deaths, recalculate credits to match these totals,
or claim the 17-event discrepancy is resolved by transport success.

## Windows Tower: local migration rehearsal

1. Back up the legacy receiver configuration, archive, consolidated feed, and each consumer's
   database locally using that software's documented process. Keep all backups private.
2. With the game closed, copy a selected original journal set into a separate staging folder.
   Preserve source copies and hashes. No receiver source code is required to scan `.log` files.
3. Follow the Windows install guide using isolated Journal Cloud state and `scan --no-defaults`
   pointed at staging. Run verify, rescan, and verify again. Compare captured hashes with originals.
4. Export to a new generation with `--consumer eddiscovery`, and separately with `--consumer edexo`.
   Read `feed.json` for selected sessions and any conflicts. A failed export must be investigated;
   never use `--allow-conflicts` merely to bypass a migration discrepancy.
5. Choose one opaque commander directory in each consumer export. These folders are flat and
   preserve original journal basenames. Generic exports instead nest commander/session/content;
   do not assume either consumer scans them recursively.
6. Use a separate consumer test database/profile or its documented manual import path. Confirm
   the exact versions support the exported files, original event sequence, and commander changes.
   Do not attach the same session from several export generations to a live watched feed.
7. Compare complete journal records, biological Log/Sample/Analyse events, sales, deaths,
   resurrection, pending data, and consumer-specific accounting independently. Check for lost and
   duplicate events. Preserve each consumer's import report locally; upload success is irrelevant
   to whether import completed.
8. For the recovered incident dataset, compare against the evidence table only when using that
   same privately held history. Investigate the separate 17-event census discrepancy explicitly.
   Do not put the data or commander identifiers into public fixtures or issues.

Multi-commander files are kept intact; `commander_count > 1` in `feed.json` signals that local
review is needed before import. Files before a commander event have an unknown-commander group.
No event is moved between commanders or files. Divergent snapshots stay archived; generic
`--allow-conflicts` output is for comparison and may repeat shared-prefix events. Consumer
adapters refuse basename collisions rather than inventing journal filenames.

## Steam Deck: collection rehearsal

Use the SteamOS guide to test default and explicitly configured Proton libraries with separate
state. Capture with the game stopped, then use a synthetic growing-file test. Verify hashes and
repeat scans before optional Nextcloud testing. A later real append test should finish with a
scan after game shutdown. Do not alter the live journal to simulate corruption or growth.

After a synthetic two-device Nextcloud round trip, repeat with an approved local test dataset
using the same isolation and privacy precautions. Source discovery, transfer verification,
Tower ingestion, feed export, EDDiscovery import, and EDEXO import are separate acceptance steps.

## Rollback and blockers

Rollback means stop invoking Journal Cloud and keep using the unchanged legacy system. It does
not require rewriting source journals or uninstalling consumer software. Retain failed state and
exports privately for investigation. Never copy a live SQLite file alone while WAL is active;
stop the worker/API and back up the entire state directory.

Before local alpha deployment, validate Windows/SteamOS discovery and vault access, real
Nextcloud conditional operations/interruption recovery, and both consumers' import behavior.
Review conflict handling, backup/restore, snapshot size/performance, and generation-import
operating procedures. Decide scheduling/monitoring separately without interrupting existing
services. Resolve or explicitly carry the 17-event census discrepancy as an independent known
issue. There is no safe automatic cutover or receiver migration adapter in this slice.
