# Product Status

Date: 2026-07-02

## Current Stage

BookBuddARR is a **v1 approval-gated Docker product candidate with actual-stack live validation for the monitored automation flow**.

It has real working pieces:

- BookBuddy CSV ingestion.
- Stable registry to avoid reprocessing old exports.
- ISBN-first deduplication.
- Language-aware audiobook routing rules.
- Generated audiobook review queue.
- Dry-run Torznab audiobook candidate search.
- Local CSV audiobook candidate review state.
- Explicit candidate list/approve/reject/export commands.
- Approved candidate CSV export and export-only Audiobookshelf JSON.
- Candidate review state preservation across search reruns.
- Candidate completeness review for numbered parts/volumes before approval.
- Configurable audiobook language root-folder mapping.
- Read-only BookBuddy export diffing.
- Local web UI for CSV upload, settings, planning, ingest, candidate review, approved export, filtering, activity display, stack connection testing, and monitored workflow execution.
- Stack settings UI for Prowlarr, qBittorrent, optional SABnzbd/NZBGet, Audiobookshelf, optional Readarr, root folders, categories, and download/import modes.
- CLI and web workflow orchestration from CSV through plan, ingest, Prowlarr aggregate search, candidate grouping, approval policy, Prowlarr grab, qBittorrent monitoring, import, and Audiobookshelf-path verification.
- Workflow status CSV with `needs_review`, `needs_parts`, `grabbing`, `downloading`, `complete`, `complete_grouped`, and `blocked` states.
- Repeatable Service deployment package under `deploy/service/`.
- Dry-run-first Prowlarr Generic Torznab setup/update helper.
- Secret-redacted Service health-check helper.
- GitHub Actions CI for tests, CLI help checks, and Service script compilation.
- Optional AudioBookBay Torznab bridge.
- Deployed Service-stack bridge proof.
- Prowlarr `AudioBookBay Bridge` indexer proof.
- Readarr visibility proof.

Remaining product risks:

- The AudioBookBay-specific Torznab bridge currently authenticates correctly but returns zero results because upstream fetches time out from Service.
- Prowlarr aggregate search works through other configured indexers and was used for actual-stack validation.
- No production observability around bridge failures or noisy results.
- qBittorrent credentials exposed during manual Service inspection were rotated in qBittorrent plus dependent stack configs on 2026-07-02.
- SABnzbd/NZBGet are not implemented as download monitors yet.

## Proven Live State

Local repo:

- Path: `C:\Users\EnzoTERRIER\Codex\projects\BookBuddARR`
- GitHub: `https://github.com/Nassau-1/BookBuddARR`
- Latest known pushed commit: `90168d9`
- Tests: `python -m pytest tests` passes with 33 tests.

Service VM:

- `bookbuddarr-web` runs on port `8788` and returned HTTP `200` in final validation.
- `bookbuddarr-torznab` runs on port `8765` and unauthenticated caps returned HTTP `401` in final validation.
- API key is stored on Service at `/srv/media-stack/compose/bookbuddarr-torznab.env`.
- The BookBuddARR Torznab API key was rotated on 2026-07-02 after log exposure during validation.
- qBittorrent credentials were rotated on 2026-07-02 after manual validation exposure, and the Prowlarr download-client update tested successfully.
- Prowlarr has a configured qBittorrent download client named `qBittorrent VPN`.
- Prowlarr aggregate search returned audiobook-category results from configured indexers.
- Readarr sees `AudioBookBay Bridge (Prowlarr)`.

Actual-stack validation on 2026-07-02:

- Regenerated current-format audiobook review queue from the 143-row registry.
- Created BookBuddARR review CSVs from Prowlarr aggregate search and qBittorrent completed audiobook-category items.
- Approved 3 candidates through `bookbuddarr candidates approve`.
- Exported approved candidates through `bookbuddarr candidates export-approved`.
- Prowlarr successfully handed 3 approved torrent releases to qBittorrent.
- Imported 3 completed qBittorrent audiobook-category items into `/mnt/nas/data/Audiobooks/Francais`.
- Verified all 3 imports are visible through the Audiobookshelf container mount under `/audiobooks/Francais`.
- Verified imported file counts through the Audiobookshelf mount: `3`, `60`, and `707` files.
- Corrected multipart handling after identifying `Ainsi parlait Zarathoustra 1 - Le declin` as volume 1 only:
  - Found volume 2, `Le Grand Midi`, through Prowlarr/qBittorrent.
  - Approved it with the explicit incomplete override because all parts were being grouped together.
  - Grouped the two completed parts into one French Audiobookshelf book folder.
  - Verified the grouped folder through the Audiobookshelf mount with `214` files.
- Final monitored workflow validation on Service:
  - Three approved non-multipart rows completed with workflow state `complete`.
  - The Zarathoustra multipart validation completed with workflow state `complete_grouped`.
  - The final multipart status detail was `verified_existing_grouped_import`, proving the workflow can verify an already-grouped Audiobookshelf import even after qBittorrent no longer lists the sibling torrents.

BookBuddy export proof:

- Input rows: `143`
- Unique rows: `143`
- Duplicates in export: `0`
- Language split: `122` French, `20` English, `1` unknown

## Product Definition

The intended final product is:

> A self-hosted bridge that turns repeated BookBuddy exports into an approval-gated, language-aware audiobook workflow for Arr-style stacks, with Prowlarr aggregate search, qBittorrent monitoring, and Audiobookshelf-root import verification.

## Non-Goals For Now

- Fully automatic grabbing from AudioBookBay without review.
- Circumventing tracker or site rules.
- Publishing or redistributing protected works.
- Treating Readarr metadata as authoritative when it contradicts BookBuddy language intent.
- Replacing Prowlarr; BookBuddARR should complement it.
