# Roadmap

Date: 2026-07-02

BookBuddARR is moving from a v1 integrated POC to a product-grade, audiobook-first workflow. The product remains approval-gated: it may search and rank candidates, but grabs/imports require persisted approval or the explicit high-confidence `approved_or_eligible` policy.

## Smallest True Product Milestone

The smallest product milestone after the POC is:

> A repeatable BookBuddy export workflow that can validate input, preview registry impact, generate review queues, search audiobook candidates in dry-run mode, and persist those candidates for explicit user review.

This milestone is product-grade when a user can run the workflow repeatedly without losing state, leaking personal data into Git, or silently accepting a candidate in the wrong language.

## P0: Product-Safe Foundation

User-facing workflow:

1. Export a CSV from BookBuddy.
2. Run `bookbuddarr doctor <export.csv>` to validate schema, registry readiness, output paths, and optional local endpoints.
3. Run `bookbuddarr plan <export.csv>` to preview new, known, duplicate, and language-split counts.
4. Run `bookbuddarr ingest <export.csv>` only after the plan looks correct.
5. Review generated queues manually.

Scope:

- CSV schema diagnostics for missing BookBuddy columns.
- Dry-run planning before registry updates.
- Optional `.env` loading for local endpoints.
- Synthetic public fixtures and tests.
- No network search required for P0.
- No grabs.

## P1: Audiobook Candidate Review

Status: dry-run candidate search, CSV persistence, explicit approval/rejection, approved export, and review-state preservation are implemented.

User-facing workflow:

1. Run `bookbuddarr audiobook-search` against the Torznab bridge or Prowlarr.
2. Persist candidate matches locally.
3. Review candidate title, URL, language, score, and decision status in `audiobook_matches.csv`.
4. Approve or reject candidates explicitly before any later handoff.
5. Export only approved candidates to CSV or export-only Audiobookshelf JSON.

Scope:

- Persist review state in CSV for the next milestone.
- Include `record_id`, search query, candidate title, candidate language, candidate URL, score, decision status, and notes.
- Preserve existing `decision_status` and `notes` when searches are rerun.
- Apply language-aware filtering and ranking.
- French BookBuddy records must not silently accept English candidates.
- Unknown-language records require manual review.
- No auto-grab.

## P2: Repeatable Service Deployment

Status: compose/env template, install/update docs, Prowlarr setup/update helper, and health-check helper are implemented and validated on Service.

User-facing workflow:

1. Configure env files on the Service host.
2. Deploy or update the Torznab bridge with documented commands.
3. Validate caps/search health checks.
4. Configure or update the Prowlarr Generic Torznab indexer without printing secrets.

Scope:

- `deploy/service/compose.yaml`.
- `deploy/service/README.md`.
- Install/update command sequence.
- Prowlarr setup/update helper with redacted output.
- Health checks for bridge, Prowlarr, and Readarr visibility.

## P3: Downstream Integration

Status: approved candidate export, Prowlarr grab metadata, stack settings, connection tests, qBittorrent monitoring, filesystem import, and workflow status are implemented. Actual-stack validation completed on 2026-07-02 with 3 approved French audiobook imports visible through the Audiobookshelf mount and one multipart audiobook validated as `complete_grouped`.

User-facing workflow:

1. Review candidates and language warnings.
2. Export approved items or send them to downstream tools through explicit dry-run-first integrations.
3. Preserve BookBuddy language intent when Readarr metadata disagrees.

Scope:

- Readarr lookup remains dry-run until metadata ambiguity is handled.
- Audiobookshelf wanted-list planning is export-only JSON; filesystem import and visibility verification are implemented.
- Approved grab paths are only allowed after candidate review state exists or after the explicit eligible policy accepts a high-confidence, language-matching, non-multipart candidate.
- Single numbered parts remain `needs_parts` until sibling parts are found and grouped.
- Live validation must use public-domain, Creative Commons, directly user-owned, user-provided, or otherwise explicitly authorized sources.

Actual-stack validation note:

- Prowlarr aggregate search and qBittorrent handoff were validated with the existing Service stack.
- The AudioBookBay-specific bridge authenticated correctly but upstream fetches timed out from Service during validation.
- qBittorrent credentials exposed during manual validation were rotated in qBittorrent and dependent stack config on 2026-07-02.
- Final Service checks: BookBuddARR web returned HTTP `200`, unauthenticated Torznab caps returned HTTP `401`, and the Zarathoustra multipart workflow completed as `complete_grouped` with `verified_existing_grouped_import`.

## P4: UX and Hardening

Scope:

- Local web UI for upload, planning, candidate review, candidate decisions, filtering, activity display, and export actions.
- Localhost/LAN auth if exposed beyond a trusted host.
- CI, type checking, structured logs, retries, rate limits, and versioned Docker images.
