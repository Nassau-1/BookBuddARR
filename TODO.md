# TODO

Detailed product backlog lives in `docs/product-backlog.md`.

Fresh-session finish prompts:

- `docs/handoff/GOAL_PROMPT_FINISH_TODOS.md`
- `docs/handoff/GOAL_PROMPT_LIVE_COMPLETION.md` for the Service/live validation phase.
- `docs/handoff/GOAL_PROMPT_FULL_STACK_AUTOMATION.md` for the next product slice: Docker install, stack configuration, CSV drop, monitored search/grab/import, and multipart grouping.

## Completed Foundation Slice

- Added `bookbuddarr doctor`.
- Added `bookbuddarr plan`.
- Added synthetic CSV fixtures.
- Added `docs/roadmap.md`.

## Completed Candidate Review Slice

- Add `bookbuddarr audiobook-search` in dry-run/review mode.
- Persist audiobook candidate review state in local CSV.
- Add language-aware candidate filtering and ranking.
- Keep audiobook search dry-run/review-first.

## Completed Local UI Slice

- Add `bookbuddarr web`.
- Add Arr-style local UI for BookBuddy CSV upload and settings.
- Wire UI actions for `Doctor`, `Plan`, `Ingest`, and review-only `Audiobook Search`.
- Keep uploads and settings under ignored `data/` paths.

## Completed Service Deployment Slice

- Add Service deployment docs under `deploy/service/`.
- Add Prowlarr Generic Torznab setup/update script for Service.
- Add health-check commands for bridge, Prowlarr, and Readarr visibility.
- Keep API keys in env files and redact secrets in script output.

## Completed Full Stack Automation Slice

- Docker install comparable to Prowlarr/Radarr/Sonarr is implemented through `deploy/service/compose.yaml`.
- First-run setup screen for required stack URLs/API keys/root folders is implemented in the web UI.
- CSV drop from BookBuddy/Askademy Books-style export is implemented.
- One-click monitored run from CSV to candidate search, approval policy, Prowlarr grab, qBittorrent monitoring, import, and Audiobookshelf filesystem verification is implemented.
- Multipart detection blocks single parts as `needs_parts`; grouped completion requires sibling parts before `complete_grouped`.
- qBittorrent credentials exposed during manual validation were rotated and dependent stack configuration was updated.
- Actual-stack validation completed on Service:
  - Prowlarr aggregate search candidate generation.
  - qBittorrent completed-item import into language roots.
  - Audiobookshelf mount verification.
  - Zarathoustra multipart workflow verification as `complete_grouped`.

## Later

- Add authenticated API-backed Audiobookshelf integration if needed. Current workflow verifies filesystem visibility first.
- Add SABnzbd/NZBGet handoff. Current settings and connection scaffolding are present; qBittorrent is the implemented monitor.
- Add richer observability and retry/rate-limit controls for noisy or slow indexer searches.
- Fix or replace the AudioBookBay-specific bridge source path if upstream Service fetches continue timing out.
- Harden Service validation into a single repeatable operator command or runbook.

## Corrected During Validation

- `Ainsi parlait Zarathoustra 1 - Le declin` was identified as volume 1 of a multipart audiobook, not the whole work by itself.
- Found and approved `Ainsi parlait Zarathoustra 2 - Le Grand Midi` through the actual Prowlarr/qBittorrent stack path.
- Grouped both completed parts into one Audiobookshelf French book folder and verified visibility through the Audiobookshelf container mount.
