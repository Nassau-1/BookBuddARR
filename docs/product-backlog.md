# Product Backlog

Date: 2026-07-02

## P0: Make The POC Product-Safe

- Add `bookbuddarr doctor`:
  - Validate CSV schema.
  - Validate registry readability.
  - Validate output paths.
  - Validate optional Service endpoints.
- Add `bookbuddarr plan`:
  - Produce a dry-run plan before updating the registry.
  - Show new/known/duplicate counts.
  - Show language split.
- Add clear error messages for missing BookBuddy columns.
- Add `.env` based config loading for local stack URLs without printing secrets.
- Add generated sample fixtures that are safe for public repo tests.

## P1: Audiobook-First Review Workflow

Status: candidate search, CSV persistence, approval/rejection tooling, state preservation, and approved export are implemented.

- Add a persistent `audiobook_matches.csv` or SQLite state:
  - book record id
  - search query
  - candidate title
  - candidate language
  - candidate URL
  - selected/rejected status
  - notes
- Add `bookbuddarr audiobook-search`:
  - Query the Torznab bridge/Prowlarr for each new book.
  - Store candidates locally.
  - Never grab automatically by default.
- Add language filters:
  - French BookBuddy record accepts French/Francais/VF/French-language candidates.
  - English BookBuddy record accepts English/Anglais candidates.
  - Unknown requires manual decision.
- Add candidate ranking:
  - title similarity
  - author similarity
  - language match
  - unabridged markers
  - known bad/noisy title filters

## P2: Service Deployment

Status: compose/env template, install/update docs, dry-run-first Prowlarr helper, and health-check helper are implemented and validated on Service.

- Add `deploy/service/compose.yaml`.
- Add `deploy/service/README.md`.
- Add `deploy/service/install.sh` or documented command sequence.
- Add a Prowlarr Generic Torznab setup helper:
  - Creates/updates `AudioBookBay Bridge`.
  - Tests caps/search.
  - Does not print API keys.
- Add health checks:
  - `/api?t=caps`
  - search fallback
  - Prowlarr indexer test
  - Readarr indexer visibility

## P3: Downstream Integration

Status: approved export, Prowlarr grab metadata, approval-gated workflow orchestration, qBittorrent monitoring, filesystem import, Audiobookshelf-path verification, and multipart `complete_grouped` validation are implemented. SABnzbd/NZBGet handoff remains TODO.

- Keep ebook route WIP until audiobook workflow is stable.
- Add Readarr dry-run lookup only:
  - Show metadata ambiguity.
  - Preserve BookBuddy language as source of truth.
- Keep Audiobookshelf API mutation optional; filesystem import/visibility verification is the implemented path.
- Keep approved grab paths gated by persisted candidate review state or explicit `approved_or_eligible` policy.
- Keep multipart completion gated on sibling part discovery or existing grouped Audiobookshelf verification.

## P4: UX

Status: local web UI exists for upload, settings, planning, ingest, candidate search, candidate approval/rejection, approved export, filtering, activity display, stack connection tests, and monitored workflow status. Auth remains future work if exposed beyond a trusted LAN/local host.

- Add a small local web UI:
  - Upload/select BookBuddy export.
  - Show new books.
  - Show audiobook candidates.
  - Approve/reject candidates.
  - Export/import actions.
- Add simple auth if exposed beyond localhost/LAN.
- Add logs and progress display for long searches.

## P5: Hardening

- Package Docker image with version tags.
- Add CI. Implemented with GitHub Actions for tests, CLI help, and Service script compilation.
- Add type checking.
- Add retry/rate-limit controls for AudioBookBay search.
- Add structured logs.
- Add import/export of review state.
