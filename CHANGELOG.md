# Changelog

## 2026-07-02

- Added Docker-first stack settings for Prowlarr, qBittorrent, optional SABnzbd/NZBGet, Audiobookshelf, optional Readarr, root mappings, and download/import modes.
- Added redacted stack connection tests and a monitored workflow command/UI action for CSV -> search -> approval policy -> Prowlarr grab -> qBittorrent monitor -> import -> verification.
- Added Prowlarr grab metadata to candidate rows, workflow status CSV output, and multipart `needs_parts`/`complete_grouped` states.
- Generalized Docker Compose for public installs while keeping Service override support.
- Added dry-run candidate search, persistent candidate review CSV state, and explicit candidate approval/rejection commands.
- Added approved candidate export as CSV and export-only Audiobookshelf JSON.
- Added configurable audiobook language root-folder mapping and read-only BookBuddy export diffing.
- Added local web UI support for candidate decisions, filtering, approved export, settings persistence, and activity display.
- Added Service deployment helpers, health checks, and GitHub Actions CI.
- Completed actual-stack Service validation through Prowlarr, qBittorrent, and the Audiobookshelf library mount for 3 approved French audiobook imports.
- Rotated the BookBuddARR Torznab API key and redacted bridge API keys from request logs.
- Added completeness review blocking for numbered part/volume audiobook candidates and corrected Zarathoustra by grouping volumes 1 and 2 in one Audiobookshelf folder.

## 2026-07-01

- Created initial BookBuddARR repository.
- Added BookBuddy CSV ingestion.
- Added ISBN-first deduplication and persistent registry handling.
- Added Readarr and audiobook review queue CSV outputs.
- Added tests and governance docs.
