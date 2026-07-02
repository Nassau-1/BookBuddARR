# BookBuddARR Live Completion Goal Prompt

Use this in a fresh Codex session when ready to finish the remaining TODOs and validate the full workflow on Service.

```text
/goal Finish BookBuddARR's remaining product TODOs and close with a live, lawful, review-gated validation where at least 3 audiobooks are found, manually approved, downloaded/imported from authorized sources, and confirmed in the correct language.

Workspace:
C:\Users\EnzoTERRIER\Codex\projects\BookBuddARR

Mandatory read order:
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
12. docs/handoff/PRODUCT_FINALIZATION_PROMPT.md
13. docs/handoff/GOAL_PROMPT_FINISH_TODOS.md

Then inspect:
- bookbuddarr/cli.py
- bookbuddarr/audiobook_search.py
- bookbuddarr/web.py
- bookbuddarr/outputs.py
- bookbuddarr/rules.py
- deploy/service/compose.yaml
- deploy/service/prowlarr_generic_torznab.py
- deploy/service/health_checks.py
- tests/test_pipeline.py

Current live facts:
- Public repo: https://github.com/Nassau-1/BookBuddARR
- Service web UI: http://192.168.1.48:8788
- Torznab bridge API: http://192.168.1.48:8765/api
- Service container `bookbuddarr-web` runs on port 8788.
- Service container `bookbuddarr-torznab` runs on port 8765 and unauthenticated caps should return 401.
- Prowlarr has/should have `AudioBookBay Bridge`.
- Readarr sees/should see `AudioBookBay Bridge (Prowlarr)`.
- `data/` is ignored and must not be committed except `data/.gitkeep`.
- BookBuddy language intent is authoritative.
- The accepted UI is an original Arr-style local web UI; do not copy Arr source/assets.

Remaining product TODOs:
1. Sync and run the final implementation on Service.
2. Validate Service web UI, Torznab bridge protection, Prowlarr visibility, and Readarr visibility without printing secrets.
3. Use the Service UI and/or CLI to complete the review-gated live validation.
4. Find, approve, and lawfully download/import at least 3 audiobooks in the correct language.
5. Verify target library/location visibility and language correctness.
6. If lawful/authorized titles are unavailable, document the exact blocker and do not substitute unauthorized downloads.

Live validation close condition:
Close the phase only after proving at least 3 audiobook items were:
- found through the BookBuddARR review workflow,
- manually reviewed and approved,
- lawful to download/import: public-domain, Creative Commons, directly user-owned, user-provided, or otherwise explicitly authorized,
- downloaded/imported without bypassing site/tracker rules,
- visible in the target library/location,
- confirmed in the correct BookBuddy intended language.

Important: If the only available candidates are not clearly lawful/authorized, stop and report that the live download validation is blocked. Do not substitute unauthorized downloads. Prefer public-domain/Creative Commons sources such as LibriVox or Internet Archive test titles when authorization is unclear. If using tracker results, require explicit per-title user authorization before download and keep the review gate.

Safety rules:
- Do not print API keys, tracker keys, qBittorrent credentials, BookBuddy personal export contents, generated personal registry contents, or env files.
- Do not auto-grab or auto-download broad search results.
- Do not remove review gates.
- Do not add a qBittorrent handoff unless it is driven only by explicitly approved candidates and lawful/authorized titles.
- Prefer dry-run and preview commands before stateful operations.
- Keep tests synthetic.
- Keep generated local/Service data out of Git.

Implementation guidance:
- Keep CSV review state for now per ADR-0004.
- Add focused CLI commands if useful, for example:
  - `bookbuddarr candidates list`
  - `bookbuddarr candidates approve`
  - `bookbuddarr candidates reject`
  - `bookbuddarr candidates export-approved`
  - `bookbuddarr diff-exports`
- The web UI must call the same backend logic as the CLI.
- Approved exports should be plain local files with clear columns and no automatic downstream mutation by default.
- Language-root mapping should default to current behavior:
  - French -> `/Data/Audiobooks/Francais`
  - English -> `/Data/Audiobooks/English`
  - Unknown -> manual review
- Add a QA script or GitHub Actions CI if practical; otherwise document exact local QA commands.

Suggested execution order:
1. Re-check git status and live Service status.
2. Run local validation.
3. Sync to Service and restart/rebuild the BookBuddARR compose services.
4. Use the Service UI and/or CLI for final live validation.
5. Find, approve, and lawfully download/import at least 3 audiobooks in the correct language.
6. Verify library/location visibility and language correctness.
7. Update docs/TODO/status/roadmap and final summary.

Required validation commands:
python -m pytest tests
python -m bookbuddarr.cli --help
python -m bookbuddarr.cli ingest --help
python -m bookbuddarr.cli audiobook-search --help
python -m bookbuddarr.cli candidates --help
python -m bookbuddarr.cli diff-exports --help
python -m bookbuddarr.cli torznab-serve --help
python -m bookbuddarr.cli web --help
python -m py_compile deploy\service\prowlarr_generic_torznab.py deploy\service\health_checks.py

Required Service checks without printing secrets:
ssh service "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'bookbuddarr|prowlarr|readarr|audiobookshelf|qbittorrent'"
ssh service "curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8788/'"
ssh service "curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8765/api?t=caps'"

Expected:
- Service UI returns 200.
- Unauthenticated bridge caps returns 401.
- BookBuddARR containers are up.

Definition of done:
- All remaining TODOs are implemented or explicitly documented as blocked with evidence.
- At least 3 lawful/authorized audiobook downloads/imports are successfully validated in the correct language.
- Review gates remain intact.
- Tests and CLI help checks pass.
- Public docs are updated.
- No generated data or secrets are committed.
- Final answer clearly states product-ready pieces, review-only pieces, live validation evidence, and any residual blocked work.
```
