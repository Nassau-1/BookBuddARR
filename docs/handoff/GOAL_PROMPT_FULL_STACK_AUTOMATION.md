# BookBuddARR Full Stack Automation Goal Prompt

Use this in a fresh Codex session to move BookBuddARR from the current validated review-gated product candidate to the target end-user product flow.

```text
/goal Finish BookBuddARR's full Docker + Arr-stack automation flow.

Workspace:
C:\Users\EnzoTERRIER\Codex\projects\BookBuddARR

Read first, in order:
1. README.md
2. TODO.md
3. docs/product-status.md
4. docs/product-backlog.md
5. docs/roadmap.md
6. docs/architecture.md
7. docs/decisions/ADR-0001-csv-registry-first.md
8. docs/decisions/ADR-0002-review-queues-before-automation.md
9. docs/decisions/ADR-0003-audiobook-first-torznab-bridge.md
10. docs/decisions/ADR-0004-csv-review-state-before-sqlite.md
11. deploy/service/README.md
12. docs/handoff/GOAL_PROMPT_LIVE_COMPLETION.md

Then inspect:
- bookbuddarr/cli.py
- bookbuddarr/audiobook_search.py
- bookbuddarr/web.py
- bookbuddarr/outputs.py
- bookbuddarr/rules.py
- bookbuddarr/torznab.py
- deploy/service/compose.yaml
- tests/test_pipeline.py

Current state:
- BookBuddARR can ingest a BookBuddy/Askademy Books-style CSV export.
- It preserves language intent and creates audiobook search queues.
- It has a local web UI and Docker deployment for BookBuddARR services.
- It has candidate review state, approval/rejection, approved exports, and multipart/volume detection.
- Actual-stack validation was completed on Service through Prowlarr, qBittorrent, and the Audiobookshelf filesystem mount.
- `Ainsi parlait Zarathoustra 1 - Le declin` was corrected by finding volume 2 and grouping both parts into one Audiobookshelf folder.
- The AudioBookBay-specific bridge can authenticate but upstream fetches timed out from Service; Prowlarr aggregate search worked.
- qBittorrent credentials were exposed in terminal output during validation and should be rotated before any public handoff.
- The repo is not yet committed/pushed in its final state.

Target user flow:
1. User discovers the public repo.
2. User installs BookBuddARR with Docker Compose, like an Arr-family service.
3. User opens the BookBuddARR web UI.
4. User configures stack connections:
   - Prowlarr URL/API key
   - qBittorrent URL/credentials/category
   - optional SABnzbd/NZBGet settings
   - Audiobookshelf library/root folders
   - optional Readarr URL/API key
   - language-to-root-folder mapping
5. User drops a CSV export from BookBuddy/Askademy Books-style library app.
6. User clicks one action to run the monitored audiobook workflow.
7. BookBuddARR identifies new books only, searches via Prowlarr, ranks candidates, preserves BookBuddy language intent, and sends approved/eligible releases to the configured download client.
8. If a release is one part/volume of a larger audiobook, BookBuddARR must discover/grab all required parts before marking the book complete.
9. Completed downloads are imported/grouped into the correct Audiobookshelf language root.
10. The UI reports status: pending, searching, grabbing, downloading, importing, complete, blocked, or needs review.

Important product stance:
- This is a decentralized/open-source internet stack direction. Do not frame the product as inherently unlawful or morally blocked.
- Keep the software neutral: it should not force unlawful use, and it should not make claims about user rights it cannot verify.
- The user's responsibility is separate from the product workflow. The product should still avoid secrets in logs, avoid accidental broad grabs, and keep explicit review/quality gates where matching is ambiguous.

Required implementation:
1. Docker-first install:
   - Make `deploy/service/compose.yaml` usable as a general Docker Compose deployment, not only the current Service host.
   - Add `.env.example` for all stack connections.
   - Add README quickstart with required/optional services and exact setup sequence.
2. First-run web setup:
   - Add settings UI for Prowlarr, qBittorrent, SABnzbd/NZBGet, Audiobookshelf, optional Readarr, root mappings, categories, and download/import modes.
   - Add test-connection buttons with redacted output.
   - Persist settings under ignored local data.
3. Workflow orchestration:
   - Add a backend workflow that starts from uploaded CSV and executes plan -> ingest -> search -> candidate grouping -> approval policy -> grab -> download monitoring -> import -> verification.
   - Expose the same workflow through CLI and web UI.
   - Keep generated data out of Git.
4. Prowlarr integration:
   - Use Prowlarr aggregate search API for real stack search.
   - Store enough grab metadata to call Prowlarr's release grab endpoint for approved rows.
   - Never print API keys or raw download credentials.
5. Download-client integration:
   - Add qBittorrent integration for status monitoring and completed path discovery.
   - Add optional SABnzbd/NZBGet integration if practical; otherwise document as TODO.
   - Respect configured category/path/root mappings.
6. Multipart handling:
   - Detect titles like `1`, `2`, `part`, `partie`, `volume`, `vol`, `tome`, `disc`, `CD`.
   - If candidate is a numbered part for a BookBuddy title that is not itself a part, do not mark complete until all expected parts are present.
   - Search for sibling parts using title/author plus part markers.
   - Group all parts into one Audiobookshelf book folder.
   - Show `needs_parts`, `parts_found`, `parts_missing`, and `complete_grouped` states.
7. Audiobookshelf import/verification:
   - Import completed downloads into the configured language root.
   - Verify files are visible through the Audiobookshelf library path or API if available.
   - Preserve BookBuddy intended language as authoritative.
8. UI:
   - The first screen should be the usable app, not a landing page.
   - Provide dense Arr-style operational views: settings, CSV/import, candidate review, workflow status, activity logs, download/import queue, blocked items.
   - Avoid copying Arr source/assets.
9. Safety and logging:
   - Redact all API keys, passwords, tracker keys, and download URLs where sensitive.
   - Add regression tests for redaction.
   - Do not commit `data/`, `.env`, generated queues, logs, or personal exports.
10. Documentation:
   - README must clearly list required stack services and optional integrations.
   - README must state current Docker install steps.
   - README must describe the one-click target workflow and multipart behavior.

Validation:
- Run:
  - python -m pytest tests
  - python -m bookbuddarr.cli --help
  - python -m bookbuddarr.cli ingest --help
  - python -m bookbuddarr.cli audiobook-search --help
  - python -m bookbuddarr.cli candidates --help
  - python -m bookbuddarr.cli diff-exports --help
  - python -m bookbuddarr.cli torznab-serve --help
  - python -m bookbuddarr.cli web --help
  - python -m py_compile deploy\service\prowlarr_generic_torznab.py deploy\service\health_checks.py
- On Service, verify without printing secrets:
  - BookBuddARR web UI returns 200.
  - Torznab caps without API key returns 401.
  - Prowlarr search works.
  - qBittorrent connection test works.
  - At least 3 books complete the workflow through UI or CLI.
  - At least one multipart audiobook is handled by grouping all parts before completion.
  - Audiobookshelf sees imported files in the correct language root.

Definition of done:
- A new user can install BookBuddARR by Docker Compose, configure stack links, upload/drop a CSV, click one workflow action, and get monitored audiobook downloads imported into Audiobookshelf.
- Multipart releases are not falsely treated as complete when only one part is present.
- README is public-user-ready and lists required/optional stack services.
- Tests pass.
- Service validation passes.
- No secrets or personal data are committed.
```
